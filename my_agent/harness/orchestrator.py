"""Orchestrator: session lifecycle management and the main control loop.

The orchestrator is the "engine" that enables multi-hour autonomous operation.
It decides when to start/end sessions, which features to work on, whether
to run verification, and when the entire task is complete.

Key design changes (v2):
- Multi-feature sessions: the model works until context is near-full, not 1-per-session
- Context-driven switching: sessions end when context hits ~75%, not after 1 feature
- Auto-handoff: orchestrator generates handoff documents after each session
- Auto-memory: orchestrator updates progress.md, decisions.md, facts.md
"""
import copy
import json
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .agent_loop import AgentLoop, IdleAction, SessionBudget, SessionResult
from .config import Config
from .context_manager import (
    build_bootstrap_messages,
    load_system_prompt,
    should_end_session,
    HandoffInfo,
)
from .llm_client import LLMClient
from .memory_skill import Confidence, MemorySkillManager
from .task_state import (
    Acceptance,
    Feature,
    Milestone,
    Status,
    TaskState,
    load_task_state,
    save_task_state,
    save_task_state_snapshot,
    pick_next_feature,
    get_completion_summary,
    update_feature_status,
)
from .tools import ToolExecutor
from .verifier import (
    VerificationResult,
    run_tier1,
    run_tier2,
    should_run_tier2,
    apply_verification,
    create_verification_summary,
)

# ── Anti-cheat patterns ──────────────────────────────────────────────
# Compiled once at import time. These detect attempts to copy from
# pre-existing libraries instead of implementing from scratch.
import re as _re
_ANTI_CHEAT_PATTERNS = [
    # Direct source inspection of installed packages (most subtle cheat)
    (_re.compile(r'inspect\.getsource(?:lines)?\s*\('), "inspect.getsource — reading installed package source code"),
    (_re.compile(r'inspect\.getfile\s*\('), "inspect.getfile — locating installed package files"),
    # Reading Python stdlib/site-packages directly (obvious cheat)
    (_re.compile(r'cat\s+\/usr\/(?:local\/)?lib\/python\d+\.\d+\/'), "cat of Python library install path"),
    # Cloning or downloading external repos
    (_re.compile(r'git\s+clone\s+https?://'), "git clone from external URL"),
    # Downloading source archives from package registries
    (_re.compile(r'(wget|curl)\s+.*github\.com'), "wget/curl from GitHub"),
    (_re.compile(r'(wget|curl)\s+.*pypi\.org'), "wget/curl from PyPI"),
]


class Orchestrator:
    """Top-level controller for the long-running coding agent system."""

    def __init__(self, config: Config):
        self.config = config
        self.client = LLMClient(config)                        # main coding agent
        self.planner_client = LLMClient(config, config.planner)  # Planner (can be flash)
        self.verifier_client = LLMClient(config, config.verifier_model)  # Verifier (should be pro)
        self.tool_executor = ToolExecutor(config)
        self.agent_loop = AgentLoop(config, self.client, self.tool_executor)
        self.memory = MemorySkillManager(config)
        self.verification_results: List[VerificationResult] = []
        self._consecutive_failures = 0
        self._consecutive_failures = 0
        self._replan_count = 0
        # ── Anti-cheat tracker ─────────────────────────────────────────
        self._events: List[Dict[str, Any]] = []
        self._premature_claims: List[Dict[str, Any]] = []
        self._cheat_flags: List[Dict[str, Any]] = []
        self._console: List[str] = []  # captures key terminal output
    def run(
        self,
        task_id: str,
        spec_path: Optional[str] = None,
        max_sessions: Optional[int] = None,
        max_hours: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Main entry point: run the agent system to completion or budget exhaustion.

        Sessions now work continuously on multiple features until context is near-full,
        then handoff to the next session. The orchestrator:
        1. Provides the initial work queue (next N pending features)
        2. When model goes idle: injects "next feature" prompt if context has room
        3. When context is full: ends session, verifies all touched features,
           generates handoff + memory updates
        """
        state_path = os.path.join(self.config.paths.memory_dir, "task_state.json")
        snapshots_dir = os.path.join(self.config.paths.logs_dir, "snapshots")
        handoffs_dir = self.config.paths.handoffs_dir
        os.makedirs(snapshots_dir, exist_ok=True)
        os.makedirs(handoffs_dir, exist_ok=True)

        # Initialize or resume
        task_state = load_task_state(state_path)
        start_time = time.time()

        if task_state is None:
            if spec_path:
                task_state = self._initialize_task(task_id, spec_path)
            else:
                raise ValueError(f"No existing task '{task_id}' found and no spec provided. "
                                 "Use --spec to create a new task.")

        effective_max_sessions = max_sessions or self.config.budget.max_sessions
        effective_max_hours = max_hours or self.config.budget.max_wall_clock_hours
        maintenance_interval = self.config.maintenance.interval_sessions
        # Detect highest existing session number to avoid overwriting logs on resume
        session_count = self._detect_latest_session_number(
            self.config.paths.logs_dir
        )
        # Metrics collector
        all_session_results: List[SessionResult] = []

        # Main loop
        while True:
            elapsed_hours = (time.time() - start_time) / 3600

            # ── Budget checks ──────────────────────────────────────────
            if session_count >= effective_max_sessions:
                self._add_event("budget_sessions_exhausted",
                                             {"sessions": session_count, "max": effective_max_sessions})
                break

            if elapsed_hours >= effective_max_hours:
                self._add_event("budget_time_exhausted",
                                             {"hours": elapsed_hours, "max": effective_max_hours})
                break

            # ── Pick initial feature for this session ──────────────────
            result = pick_next_feature(task_state, max_retry=self.config.verification.max_retry_attempts)
            if result is None:
                if task_state.is_complete:
                    self._add_event("task_complete", get_completion_summary(task_state))
                    break
                elif task_state.completion_ratio >= 1.0:
                    if self.config.verification.enabled:
                        self._run_final_verification(task_state, session_count, state_path, snapshots_dir)
                    else:
                        # Verification disabled: auto-pass final verification
                        task_state.final_verification.status = Status.PASSING
                        task_state.final_verification.last_run_session = session_count
                        save_task_state(task_state, state_path)
                        print("  [Verification DISABLED] Final verification auto-passed")
                    if task_state.is_complete:
                        break
                    else:
                        self._inject_integration_fix(task_state, session_count, state_path)
                        continue
                else:
                    self._add_event("stalled",
                                                 {"reason": "remaining features blocked",
                                                  "summary": get_completion_summary(task_state)})
                    break

            milestone, initial_feature = result
            session_count += 1

            # Snapshot task state BEFORE session (to diff changes later)
            task_state_before = copy.deepcopy(task_state)

            print(f"\n{'='*60}")
            print(f"Session {session_count}: Starting with {initial_feature.id} — {initial_feature.description}")
            print(f"Status: {initial_feature.status.value}, Attempts: {initial_feature.attempts}")
            print(f"Completion: {task_state.completion_ratio:.1%} "
                  f"({task_state.all_pass_count}/{task_state.total_feature_count})")
            print(f"{'='*60}\n")
            self._console.append(
                f"Session {session_count}: {initial_feature.id} [{initial_feature.status.value}] "
                f"attempts={initial_feature.attempts} completion={task_state.completion_ratio:.1%}"
            )

            # ── Build session context ──────────────────────────────────
            system_prompt = load_system_prompt(
                os.path.join(os.path.dirname(__file__), "prompts"),
                "coding_agent",
            )
            # Detect spec file for bootstrap (e.g., start.md from NL2RepoBench)
            spec_path = self._detect_spec_file()
            bootstrap = build_bootstrap_messages(self.config, state_path, spec_path)

            # Build work queue (initial feature + next few pending)
            work_queue = self._build_work_queue(
                task_state, initial_feature,
                max_items=self.config.context.work_queue_max_items,
            )
            work_instruction = self._build_work_instruction(work_queue)
            bootstrap.append({"role": "user", "content": work_instruction})

            # Session budget
            session_budget = SessionBudget(
                max_turns=self.config.session.max_turns,
                max_total_tokens=self.config.session.max_tokens,
            )

            # ── on_idle callback: inject next feature if context has room ──
            # Capture references for the closure
            state_path_ref = state_path
            max_retry = self.config.verification.max_retry_attempts
            switch_ratio = self.config.session.switch_ratio
            context_window = self.config.session.context_window

            def on_idle(messages, turn, tokens_used):
                """Called when the model goes idle (end_turn, no tool calls).

                Returns IdleAction — if should_continue, inject a prompt for the next feature.
                """
                # If context is near-full, stop the session
                token_threshold = int(switch_ratio * context_window)
                if tokens_used >= token_threshold:
                    print(f"  [on_idle] Context near-full ({tokens_used}/{context_window} tokens), ending session.")
                    return IdleAction(should_continue=False)

                # Reload task state from disk (model may have updated it)
                ts = load_task_state(state_path_ref)
                if ts is None:
                    return IdleAction(should_continue=False)

                # Pick next pending feature
                next_result = pick_next_feature(ts, max_retry=max_retry)
                if next_result is None:
                    print(f"  [on_idle] No more pending features. Ending session.")
                    return IdleAction(should_continue=False)

                next_ms, next_feat = next_result

                # Mark this feature as in_progress
                update_feature_status(ts, next_feat.id, Status.IN_PROGRESS,
                                      session_id=None, increment_attempts=True)
                save_task_state(ts, state_path_ref)

                print(f"  [on_idle] Injecting next feature: {next_feat.id} — {next_feat.description[:60]}")

                inject_template = load_system_prompt(
                    os.path.join(os.path.dirname(__file__), "prompts"),
                    "on_idle_inject",
                )
                prompt = inject_template.format(
                    feature_id=next_feat.id,
                    feature_desc=next_feat.description,
                    acceptance_command=next_feat.acceptance.command,
                    expect_exit_code=next_feat.acceptance.expect_exit_code,
                )
                return IdleAction(should_continue=True, prompt=prompt)

            # Mark initial feature as in_progress
            update_feature_status(task_state, initial_feature.id, Status.IN_PROGRESS,
                                  session_id=session_count, increment_attempts=True)
            # Orchestrator-owned attempt tracking (model-proof)
            save_task_state(task_state, state_path)

            # ── Run the session ────────────────────────────────────────
            session_result = self.agent_loop.run_session(
                session_id=session_count,
                system_prompt=system_prompt,
                bootstrap_messages=bootstrap,
                budget=session_budget,
                logs_dir=self.config.paths.logs_dir,
                on_idle=on_idle,
            )

            # Collect session result for metrics
            all_session_results.append(session_result)

            # ── Post-session: reload and diff ──────────────────────────
            task_state = load_task_state(state_path)
            if task_state is None:
                print("ERROR: task_state.json was lost!")
                break

            # Find features that changed status during this session
            changed_features = self._diff_task_state(task_state_before, task_state)
            print(f"  Features touched this session: {changed_features}")

            # ── Verify each changed feature ────────────────────────────
            if self.config.verification.enabled:
                for feat_id in changed_features:
                    result_feat = task_state.get_feature(feat_id)
                    if result_feat is None:
                        continue
                    _, current_feature = result_feat

                    # Only verify features the model claims as passing
                    if current_feature.status != Status.PASSING:
                        continue

                    t1_pass, t1_code, t1_output = run_tier1(
                        current_feature, self.tool_executor,
                        timeout_sec=self.config.verification.tier1_timeout_sec,
                        api_check_timeout_sec=self.config.verification.api_check_timeout_sec,
                    )
                    verification = VerificationResult(
                        feature_id=feat_id,
                        tier1_pass=t1_pass,
                        tier1_output=t1_output,
                        tier1_exit_code=t1_code,
                    )

                    # Run tier-2 only if tier-1 passed (tier-1 fail = immediate rejection)
                    if t1_pass and should_run_tier2(current_feature, self.config):
                        print(f"  Running tier-2 verification for {feat_id}...")
                        verification = run_tier2(
                            current_feature, task_state, self.config,
                            self.verifier_client, self.tool_executor,
                            self.config.paths.logs_dir, session_count,
                            spec_path=spec_path,
                        )
                        verification.tier1_pass = t1_pass
                        verification.tier1_exit_code = t1_code
                        verification.tier1_output = t1_output
                        verification.final_pass = t1_pass and (verification.tier2_pass is not False)
                    else:
                        verification.final_pass = t1_pass

                    # ── Regression check ──────────────────────────────
                    if verification.final_pass:
                        regressed = self._check_regression(
                            task_state, task_state_before, feat_id, session_count, state_path,
                        )
                        if regressed:
                            verification.final_pass = False
                            verification.tier2_evidence.append(
                                f"REGRESSION: {len(regressed)} previously-passing feature(s) now fail: "
                                + ", ".join(regressed)
                            )
                            rmsg = f"REGRESSION: {feat_id} broke {regressed}"
                            print(f"  *** {rmsg}")
                            self._console.append(rmsg)

                    self.verification_results.append(verification)

                    # Apply verification result
                    apply_verification(
                        task_state, verification, session_count,
                        state_path, snapshots_dir,
                    )
                    t2_str = 'PASS' if verification.tier2_pass else ('SKIP' if verification.tier2_pass is None else 'FAIL')
                    vmsg = f"Verification {feat_id}: tier1={'PASS' if t1_pass else 'FAIL'}, tier2={t2_str}, final={'PASS' if verification.final_pass else 'FAIL'}"
                    print(f"  {vmsg}")
                    self._console.append(vmsg)

                    # Check for premature claim
                    if not verification.final_pass:
                        self._log_premature_claim(feat_id, session_count, session_result, verification)
                        self._consecutive_failures += 1
                    else:
                        self._consecutive_failures = 0  # reset on success
            else:
                # ── Verification disabled: trust model's self-reported status ──
                print(f"  [Verification DISABLED] Trusting model-reported status for: {changed_features}")
                for feat_id in changed_features:
                    result_feat = task_state.get_feature(feat_id)
                    if result_feat is None:
                        continue
                    _, feat = result_feat
                    if feat.status == Status.PASSING:
                        feat.last_verified_session = session_count
                        print(f"    {feat_id}: model claims PASSING → accepted")
                    elif feat.status == Status.FAILED:
                        print(f"    {feat_id}: model reports FAILED")
                # Snapshot after accepting model status
                save_task_state_snapshot(task_state, session_count, snapshots_dir)
                self._consecutive_failures = 0

            # ── Check if replan is needed ────────────────────────────────
            replanned = self._check_and_replan(
                task_state, session_count, state_path, handoffs_dir,
                changed_features, session_result,
            )
            if replanned:
                # After replan, reload state and skip handoff (plan was restructured)
                task_state = load_task_state(state_path)
                if task_state is None:
                    break
                self._consecutive_failures = 0
                print(f"  Post-replan: {task_state.total_feature_count} features, "
                      f"{task_state.all_pass_count} resolved")

            # ── Auto-generate handoff ──────────────────────────────────
            self._generate_handoff(session_count, session_result, task_state,
                                   changed_features, handoffs_dir)

            # ── Auto-extract skills from successful patterns ──────────────
            self._extract_skills_from_session(session_count, session_result, task_state, changed_features)

            # ── Anti-cheat scan ───────────────────────────────────────
            self._check_for_cheating(session_result, session_count, task_id)

            # ── Auto-update memory files ───────────────────────────────
            self._update_memory_files(session_count, task_state, changed_features)

            # ── Snapshot ───────────────────────────────────────────────
            save_task_state_snapshot(task_state, session_count, snapshots_dir)

            # ── Maintenance ────────────────────────────────────────────
            if session_count % maintenance_interval == 0:
                print(f"\n  Running maintenance (session {session_count})...")
                self.memory.run_maintenance(session_count)

            # Reload from disk
            task_state = load_task_state(state_path)
            if task_state is None:
                break

        # ── Generate unified run report ────────────────────────────────
        total_wall = (time.time() - start_time) / 3600
        final_summary = get_completion_summary(task_state) if task_state else {}
        verif_summary = create_verification_summary(self.verification_results)

        # Build per-session timeline
        sessions_info = []
        for sr in all_session_results:
            session_wall = sr.end_time - sr.start_time if sr.start_time and sr.end_time else 0
            sessions_info.append({
                "session_id": sr.session_id,
                "wall_seconds": round(session_wall, 1),
                "turns": sr.turns,
                "tokens_in": sr.tokens_input,
                "tokens_out": sr.tokens_output,
                "stop_reason": sr.stop_reason,
                "idle_injections": sr.idle_injections,
            })

        # Build per-feature status
        features_info = {}
        if task_state:
            for _, feat in task_state.all_features():
                features_info[feat.id] = {
                    "status": feat.status.value,
                    "attempts": feat.attempts,
                    "description": feat.description[:120],
                    "last_verified_session": feat.last_verified_session,
                }

        run_report = {
            "task_id": task_id,
            "ended_reason": "complete" if (task_state and task_state.is_complete) else "budget_or_stalled",
            # Overall
            "total_sessions": session_count,
            "total_wall_hours": round(total_wall, 2),
            "total_wall_seconds": round(total_wall * 3600, 1),
            # Completion
            "completion": final_summary,
            # Per-session
            "sessions": sessions_info,
            # Per-feature
            "features": features_info,
            # Verification
            "verification": verif_summary,
            # Events
            "console": self._console,
            "events": self._events,
            "cheat_flags": self._cheat_flags,
        }

        report_path = os.path.join(self.config.paths.logs_dir, "run_report.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(run_report, f, indent=2, ensure_ascii=False)
        print(f"\nRun report written to {report_path}")

        return run_report

    @staticmethod
    def _detect_latest_session_number(logs_dir: str) -> int:
        """Find the highest session_NNNN.jsonl number in logs_dir.

        On resume, this prevents overwriting previous session logs.
        Returns 0 if no logs exist (fresh start).
        """
        if not os.path.isdir(logs_dir):
            return 0
        import re as _re
        max_n = 0
        for fname in os.listdir(logs_dir):
            m = _re.match(r'session_(\d+)\.jsonl', fname)
            if m:
                max_n = max(max_n, int(m.group(1)))
        return max_n

    # ── Work queue helpers ─────────────────────────────────────────────

    def _build_work_queue(
        self,
        task_state: TaskState,
        initial_feature: Feature,
        max_items: Optional[int] = None,
    ) -> List[Feature]:
        """Build a queue of the next N features to work on in a session."""
        if max_items is None:
            max_items = self.config.context.work_queue_max_items
        queue = [initial_feature]
        seen = {initial_feature.id}

        for _ in range(max_items - 1):
            result = pick_next_feature(task_state, max_retry=self.config.verification.max_retry_attempts)
            if result is None:
                break
            _, feat = result
            if feat.id in seen:
                break
            seen.add(feat.id)
            queue.append(feat)

        return queue

    def _build_work_instruction(self, work_queue: List[Feature]) -> str:
        """Build the work-queue instruction for the start of a session."""
        if not work_queue:
            return "No features to work on."

        # Build the work queue item list — IDs only, details in task_state.json
        queue_items_lines = []
        for i, feat in enumerate(work_queue):
            queue_items_lines.append(f"{i+1}. **{feat.id}** [{feat.status.value}]")
        queue_items_str = "\n".join(queue_items_lines)

        # Load template from prompts directory
        template = load_system_prompt(
            os.path.join(os.path.dirname(__file__), "prompts"),
            "work_instruction",
        )
        return template.format(work_queue_items=queue_items_str)

    # ── Regression check ────────────────────────────────────────────────

    def _check_regression(
        self,
        task_state: TaskState,
        task_state_before: TaskState,
        current_feat_id: str,
        session_id: int,
        state_path: str,
    ) -> List[str]:
        """Re-run acceptance commands of features that were PASSING BEFORE this session.

        Only checks features that were already verified and marked PASSING in a
        previous session — not features that just became PASSING in the current
        session. Same-session features may legitimately depend on each other.
        """
        # Build set of features that were PASSING before this session started
        before_passing = {
            f.id for _, f in task_state_before.all_features()
            if f.status == Status.PASSING
        }

        regressed = []
        for ms in task_state.milestones:
            for f in ms.features:
                if f.id == current_feat_id:
                    continue
                if f.id not in before_passing:
                    continue  # not verified before → skip
                if not f.acceptance.command:
                    continue
                # Re-run the acceptance command
                passed, code, output = run_tier1(
                    f, self.tool_executor,
                    timeout_sec=self.config.verification.tier1_timeout_sec,
                )
                if not passed:
                    regressed.append(f.id)
                    f.last_verified_session = session_id
                    update_feature_status(
                        task_state, f.id, Status.FAILED,
                        session_id=None,
                        notes=f"Regression: broken by changes in {current_feat_id}. "
                              f"Acceptance exit_code={code}",
                    )
                    print(f"    Regression: {f.id} acceptance failed (exit_code={code})")
        if regressed:
            save_task_state(task_state, state_path)
        return regressed

    # ── Task state diff ────────────────────────────────────────────────

    def _diff_task_state(
        self,
        before: TaskState,
        after: TaskState,
    ) -> List[str]:
        """Find feature IDs whose status changed between two task states."""
        changed = []
        before_map = {f.id: f.status for _, f in before.all_features()}
        after_map = {f.id: f.status for _, f in after.all_features()}

        for feat_id, after_status in after_map.items():
            before_status = before_map.get(feat_id)
            if before_status != after_status:
                changed.append(feat_id)

        # Also catch new features (e.g., injected fix features)
        for feat_id in after_map:
            if feat_id not in before_map:
                changed.append(feat_id)

        return changed

    # ── Auto-handoff ───────────────────────────────────────────────────

    def _generate_handoff(
        self,
        session_id: int,
        session_result: SessionResult,
        task_state: TaskState,
        changed_features: List[str],
        handoffs_dir: str,
    ):
        """Generate a structured handoff document automatically after each session."""
        # Get last git commit
        git_hash = ""
        git_msg = ""
        git_result = self.tool_executor.run("bash", {
            "command": "git log --oneline -1",
            "timeout_sec": 10,
        })
        if git_result.success and git_result.stdout.strip():
            git_hash = git_result.stdout.strip()

        # Get last commit message
        git_msg_result = self.tool_executor.run("bash", {
            "command": "git log -1 --format='%s'",
            "timeout_sec": 10,
        })
        if git_msg_result.success:
            git_msg = git_msg_result.stdout.strip()

        # Collect unresolved issues
        unresolved = self._extract_unresolved_issues(session_result)

        # Determine next action
        next_action = self._determine_next_action(task_state, changed_features)

        # Collect do-not-do items from failed features
        do_not_do = self._extract_do_not_do(task_state, changed_features)

        # Collect files to re-read
        files_to_read = self._extract_files_to_read(session_result)

        # Determine feature context
        if changed_features:
            primary_feature = changed_features[-1]  # last one worked on
            result_feat = task_state.get_feature(primary_feature)
            if result_feat:
                _, feat = result_feat
                feature_desc = feat.description
            else:
                feature_desc = primary_feature
        else:
            primary_feature = "none"
            feature_desc = "no features changed"

        # Generate session summary via LLM (cheap model, truncated transcript)
        session_summary = self._generate_session_summary(session_result, session_id, changed_features)

        handoff = HandoffInfo(
            session_id=session_id,
            feature_id=primary_feature,
            feature_desc=feature_desc,
            summary=session_summary,
            git_commit=git_hash,
            commit_note=git_msg,
            unresolved_issues=unresolved,
            next_action=next_action,
            do_not_do=do_not_do,
            files_to_read=files_to_read,
        )

        handoff_path = os.path.join(handoffs_dir, f"session_{session_id:04d}.md")

        # If agent already created a handoff inside the container (root-owned), remove it first
        if os.path.exists(handoff_path):
            os.remove(handoff_path)

        with open(handoff_path, "w", encoding="utf-8") as f:
            f.write(handoff.to_markdown())

        print(f"  Handoff written to {handoff_path}")

    def _generate_session_summary(
        self,
        session_result: SessionResult,
        session_id: int,
        changed_features: List[str],
    ) -> str:
        """Generate a 3-5 sentence natural language summary of the session.

        Uses the planner/flash LLM on a truncated transcript — cheap and fast.
        Returns empty string if transcription is unavailable or LLM fails.
        """
        transcript_path = session_result.transcript_path
        if not transcript_path or not os.path.exists(transcript_path):
            return ""

        # Read last ~6KB of transcript (enough for context, cheap for LLM)
        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                content = f.read()
            # Truncate: keep first 2KB (setup) + last 4KB (most recent work)
            if len(content) > self.config.context.transcript_max_chars:
                content = (
                    content[:self.config.context.transcript_head_chars]
                    + "\n...[truncated]...\n"
                    + content[-self.config.context.transcript_tail_chars:]
                )
        except Exception:
            return ""

        # Load prompt templates from prompts/ directory
        prompts_dir = os.path.join(os.path.dirname(__file__), "prompts")
        system_prompt = load_system_prompt(prompts_dir, "session_summarizer")
        user_template = load_system_prompt(prompts_dir, "session_summarizer_user")

        if not system_prompt:
            system_prompt = "You are a session summarizer. Output only a 3-5 sentence plain-text summary."

        if user_template:
            features_str = ", ".join(changed_features) if changed_features else "unknown"
            prompt = user_template.format(
                changed_features=features_str,
                transcript_excerpt=content[:8000],
            )
        else:
            prompt = (
                f"Summarize this coding session transcript in 3-5 sentences.\n\n"
                f"Features worked on: {', '.join(changed_features) if changed_features else 'unknown'}\n\n"
                f"Transcript excerpt:\n{content[:8000]}"
            )

        try:
            response = self.planner_client.chat([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ])
            summary = response.content.strip()
            if len(summary) < 20:
                return ""
            return summary
        except Exception:
            return ""

    def _extract_unresolved_issues(self, session_result: SessionResult) -> List[str]:
        """Extract unresolved issues from the session transcript."""
        issues = []

        # Scan the transcript for error patterns
        transcript_path = session_result.transcript_path
        if not transcript_path or not os.path.exists(transcript_path):
            return issues

        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        event = json.loads(line.strip())
                    except json.JSONDecodeError:
                        continue

                    if event.get("type") == "tool_result":
                        if not event.get("success") and event.get("tool") != "read":
                            # Extract error summary
                            error_msg = event.get("error", "") or event.get("stderr", "")
                            if error_msg:
                                short = error_msg[:200].replace("\n", " ")
                                issues.append(f"Session error: {short} — auto-detected from transcript")
        except Exception:
            pass

        return issues[:5]  # Limit to top 5

    def _determine_next_action(
        self,
        task_state: TaskState,
        changed_features: List[str],
    ) -> str:
        """Determine the single most important next action."""
        # Priority: retry failed features
        result = pick_next_feature(task_state, max_retry=self.config.verification.max_retry_attempts)
        if result:
            _, feat = result
            return f"Implement {feat.id} — {feat.description}, then run `{feat.acceptance.command}`"

        # Check final verification
        if task_state.final_verification.status != Status.PASSING:
            return f"Run final verification: `{task_state.final_verification.command}`"

        return "All features are complete. Task finished."

    def _extract_do_not_do(self, task_state: TaskState, changed_features: List[str]) -> List[str]:
        """Extract things to avoid based on what failed."""
        items = []
        for feat_id in changed_features:
            result = task_state.get_feature(feat_id)
            if result is None:
                continue
            _, feat = result
            if feat.status == Status.FAILED and feat.attempts >= 2:
                items.append(f"{feat_id} has failed {feat.attempts} times — analyze the cause carefully before retrying, do not blindly retry")
        return items

    def _extract_files_to_read(self, session_result: SessionResult) -> List[str]:
        """Suggest files the next session should read.

        Excludes files that the bootstrap sequence already mandates (handoff itself,
        task_state.json), so only workspace files and other genuinely new files appear.
        """
        files = []  # handoff and task_state.json are already in bootstrap — exclude them

        # Add git-diff for files changed this session
        if session_result.transcript_path:
            try:
                git_files = self.tool_executor.run("bash", {
                    "command": "git diff --name-only HEAD~1 2>/dev/null || git ls-files --others --exclude-standard",
                    "timeout_sec": 10,
                })
                if git_files.success:
                    for f in git_files.stdout.strip().split("\n"):
                        f = f.strip()
                        if f and not f.startswith(".agent/") and not f.startswith("logs/"):
                            files.append(f"workspace/{f}" if not f.startswith("workspace/") else f)
            except Exception:
                pass

        return files[:self.config.context.handoff_files_max]

    def _detect_spec_file(self) -> Optional[str]:
        """Detect the original task spec file for bootstrap reading.

        For NL2RepoBench tasks, this is start.md. For other tasks, look for
        common spec file patterns in the project root.
        """
        import os as _os
        candidates = [
            _os.path.join(self.config.project_root, "start.md"),
            _os.path.join(self.config.project_root, "spec.md"),
            _os.path.join(self.config.project_root, "SPEC.md"),
            _os.path.join(self.config.project_root, "task.md"),
            _os.path.join(self.config.project_root, "TASK.md"),
        ]
        for path in candidates:
            if _os.path.isfile(path):
                return path
        return None

    # ── Auto-skill extraction ───────────────────────────────────────────

    def _extract_skills_from_session(
        self,
        session_id: int,
        session_result: SessionResult,
        task_state: TaskState,
        changed_features: List[str],
    ):
        """Analyze session results, auto-create skills via LLM, and rebuild the index.

        Two sources of skills:
        1. LLM-extracted: features that passed after multiple attempts → the LLM reads
           the transcript and extracts specific fix patterns, pitfalls, and insights.
        2. Model-written: the model creates SKILL.md files via the write tool
           (e.g. `write: .agent/skills/pytest-fixtures/SKILL.md`)

        The index is rebuilt from whatever SKILL.md files exist on disk,
        so both sources are captured.
        """
        transcript_path = session_result.transcript_path
        has_transcript = transcript_path and os.path.exists(transcript_path)

        for feat_id in changed_features:
            result = task_state.get_feature(feat_id)
            if result is None:
                continue
            _, feat = result
            # Use orchestrator's authoritative attempt count
            if feat.status != Status.PASSING or feat.attempts < self.config.verification.skill_extraction_min_attempts:
                continue

            # Try LLM extraction from transcript if available
            skill_content = None
            if has_transcript:
                skill_content = self._llm_extract_skill(
                    feat, session_id, session_result, feat.attempts
                )

            # Fall back to template if LLM extraction fails or returns nothing useful
            if not skill_content or len(skill_content) < 80:
                print(f"  [Skill] LLM extraction produced no useful content for {feat_id}, skipping")
                continue

            skill_name = f"fix-{feat.id.lower()}"
            skill_summary = f"Fix pattern for {feat.id}: {feat.description[:80]}"
            tags = ["llm-extracted", f"session-{session_id}", feat_id.split('.')[0]]
            self.memory.create_skill(skill_name, skill_summary, skill_content, tags)
            print(f"  [Skill] LLM-extracted '{skill_name}' from feature {feat_id}")

        # Rebuild index from all SKILL.md files on disk
        count = self.memory.rebuild_index()
        if count > 0:
            print(f"  [Skill] Index rebuilt: {count} skills available")

    def _llm_extract_skill(
        self,
        feat: "Feature",
        session_id: int,
        session_result: "SessionResult",
        attempts: int,
    ) -> str:
        """Use the planner/flash LLM to extract a real skill from the session transcript.

        Trigger condition (evaluated by caller): feature is PASSING and orchestrator-tracked
        attempts >= 2. This means the feature was retried at least once before succeeding,
        so there may be a recoverable pattern worth capturing.

        The LLM reads a truncated transcript and identifies: what went wrong,
        what was the fix, and what key insight to carry forward.
        """
        transcript_path = session_result.transcript_path
        if not transcript_path or not os.path.exists(transcript_path):
            return ""

        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return ""

        # Truncate: keep segments relevant to this feature
        max_chars = self.config.context.transcript_max_chars
        if len(content) > max_chars:
            feat_pattern = feat.id
            segments = []
            last_idx = 0
            window_size = max_chars // 4  # ~2K context per match
            for i in range(len(content)):
                window = content[i:i + len(feat_pattern) + 10]
                if feat_pattern in window:
                    start = max(0, i - 500)
                    end = min(len(content), i + len(feat_pattern) + window_size)
                    if start > last_idx + 100:
                        segments.append(content[start:end])
                        last_idx = end
            if segments:
                content = "\n...[gap]...\n".join(segments[:3])
            content = content[:max_chars]

        # Load prompt templates from prompts/ directory
        prompts_dir = os.path.join(os.path.dirname(__file__), "prompts")
        system_prompt = load_system_prompt(prompts_dir, "skill_extractor")
        user_template = load_system_prompt(prompts_dir, "skill_extractor_user")

        if not system_prompt:
            system_prompt = "You are a skill extraction agent. Extract specific, reusable patterns from coding session transcripts. If you cannot find a clear pattern, respond with 'NO_PATTERN'."

        if user_template:
            user_prompt = user_template.format(
                feature_id=feat.id,
                feature_desc=feat.description,
                attempts=str(attempts),
                notes=feat.notes or "(none)",
                transcript_excerpt=content[:8000],
            )
        else:
            user_prompt = (
                f"Extract a reusable skill from transcript.\n"
                f"Feature: {feat.id} — {feat.description}\n"
                f"Attempts: {attempts}\n\n{content[:8000]}"
            )

        try:
            response = self.planner_client.chat([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ])
            result = response.content.strip()
            if "NO_PATTERN" in result or len(result) < 80:
                return ""
            return result
        except Exception:
            return ""

    # ── Auto-memory updates ────────────────────────────────────────────

    def _update_memory_files(
        self,
        session_id: int,
        task_state: TaskState,
        changed_features: List[str],
    ):
        """Update progress.md with session summary. Called automatically after each session."""
        summary = get_completion_summary(task_state)

        # Build progress entry
        features_summary = ", ".join(changed_features) if changed_features else "none"
        progress_entry = (
            f"Session {session_id}: processed {len(changed_features)} features ({features_summary}). "
            f"Current: {summary['passing']}/{summary['total_features']} passing "
            f"({summary['completion_ratio']:.1%}), "
            f"failed={summary['failed']}, pending={summary['pending']}, blocked={summary['blocked']}"
        )

        self.memory.append_to_memory(
            "progress.md",
            progress_entry,
            confidence=Confidence.VERIFIED,
            session_id=session_id,
            source_type="orchestrator",
            check_duplicate=False,
        )

        # Orchestrator does NOT write to facts.md.
        # Verification outcomes (pass/fail, evidence, attempts) are already stored in
        # task_state.json via apply_verification() → feat.notes. The agent reads
        # task_state.json at bootstrap. Duplicating this in facts.md is pure redundancy.
        #
        # facts.md is for AGENT-WRITTEN discoveries only:
        # - Coding agent: [DISCOVERY] / [FIX] — non-obvious behaviors and fixes
        # - Verifier: [CONTRACT] — API signature deviations from spec

        print(f"  Memory files updated (progress + facts)")

    # ── Dynamic replanning ─────────────────────────────────────────────

    def _check_and_replan(
        self,
        task_state: TaskState,
        session_id: int,
        state_path: str,
        handoffs_dir: str,
        changed_features: List[str],
        session_result: SessionResult,
    ) -> bool:
        """Check if the current plan needs revision and trigger replan if so.

        Triggers:
        1. Consecutive verification failures >= 3: the plan may be wrong
        2. All remaining features are BLOCKED: dependencies may need restructuring
        3. Model explicitly requested replan (detected via session transcript)

        The replan sends the current state + what was learned to the Planner,
        which can add/remove/merge/split features. Old features that are no
        longer needed are marked as SKIPPED.

        Returns True if replan was performed.
        """
        # Condition 1: Any failed feature has too many attempts
        replan_trigger_attempts = self.config.verification.replan_consecutive_failures
        over_limit = [
            f"{f.id}(attempts={f.attempts})"
            for _, f in task_state.all_features()
            if f.status == Status.FAILED and f.attempts > replan_trigger_attempts
        ]
        if over_limit:
            trigger_reason = f"features over retry limit: {', '.join(over_limit)}"
        # Condition 2: All remaining features blocked
        elif self._all_remaining_blocked(task_state):
            trigger_reason = "all remaining features are blocked"
        # Condition 3: Check if model signaled replan in last session
        elif self._model_requested_replan(session_result):
            trigger_reason = "model requested replan"
        else:
            return False

        if self._replan_count >= self.config.verification.replan_max_count:
            print(f"  [Replan] Skipping — max replans reached ({self.config.verification.replan_max_count})")
            return False

        self._replan_count += 1
        print(f"\n  [Replan #{self._replan_count}] Triggered by: {trigger_reason}")
        print(f"  [Replan] Calling Planner to restructure the plan...")

        # Build replan context
        context = self._build_replan_context(task_state)

        planner_prompt = load_system_prompt(
            os.path.join(os.path.dirname(__file__), "prompts"),
            "planner",
        )

        replan_messages = [
            {"role": "system", "content": planner_prompt},
            {"role": "user", "content": (
                load_system_prompt(
                    os.path.join(os.path.dirname(__file__), "prompts"),
                    "planner_replan_user",
                ).format(trigger_reason=trigger_reason, context=context)
            )},
        ]

        response = self.planner_client.chat(replan_messages)
        raw = response.content

        # Extract JSON from Planner response
        replan_data = self._extract_json(raw, task_state.task_id, "replan")

        # Merge: preserve passing features, update the rest
        try:
            new_state = TaskState.from_dict(replan_data)
            merged = self._merge_plans(task_state, new_state)
            save_task_state(merged, state_path)

            # Record the replan event
            self.memory.append_to_memory(
                "decisions.md",
                f"[Replan #{self._replan_count} Session {session_id}] Trigger: {trigger_reason}. "
                f"Before: {task_state.total_feature_count} features, "
                f"After: {merged.total_feature_count} features.",
                confidence=Confidence.VERIFIED,
                session_id=session_id,
                source_type="orchestrator",
                check_duplicate=False,
            )
            return True
        except Exception as e:
            print(f"  [Replan] Failed to merge plans: {e}")
            return False

    def _all_remaining_blocked(self, task_state: TaskState) -> bool:
        """Check if all non-passing non-skipped features are blocked."""
        remaining = [
            f for _, f in task_state.all_features()
            if f.status not in (Status.PASSING, Status.SKIPPED)
        ]
        if not remaining:
            return False
        return all(f.status == Status.BLOCKED for f in remaining)

    def _model_requested_replan(self, session_result: SessionResult) -> bool:
        """Check if the model explicitly requested a plan revision."""
        if not session_result.transcript_path:
            return False
        try:
            with open(session_result.transcript_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        event = json.loads(line.strip())
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") == "assistant":
                        content = event.get("content", "")
                        if any(phrase in content.lower() for phrase in [
                            "replan", "restructure the plan", "revise the plan",
                            "need to replan", "plan needs adjustment", "plan needs to change",
                            "original plan", "initial plan",
                        ]):
                            return True
        except Exception:
            pass
        return False

    def _build_replan_context(self, task_state: TaskState) -> str:
        """Build a structured summary of current state for the Planner."""
        lines = [f"Task: {task_state.task_id}", ""]
        for ms in task_state.milestones:
            lines.append(f"## {ms.id}: {ms.title}")
            if not ms.features:
                continue
            for f in ms.features:
                sym = {"passing": "✓", "failed": "✗", "blocked": "⊘", "skipped": "−",
                       "in_progress": "▶", "pending": "○"}
                extra = ""
                if f.notes:
                    extra = f" — {f.notes[:100]}"
                lines.append(
                    f"  {sym.get(f.status.value, '?')} {f.id} [{f.status.value}] "
                    f"{f.description[:100]} (attempts: {f.attempts}){extra}"
                )
        return "\n".join(lines)

    def _merge_plans(self, old_state: TaskState, new_state: TaskState) -> TaskState:
        """Merge a replanned state into the old state.

        Rules:
        1. Preserve PASSING features from old state (don't touch verified work)
        2. For features in new state that also exist in old: use new's definition
           but keep old's status if it was PASSING
        3. New features from new state are added
        4. Features in old but not in new are marked SKIPPED unless PASSING
        5. Non-PASSING features that survive the replan get their attempts reset
           (the old approach failed, the replan is a fresh start)
        """
        new_feature_ids = {f.id for _, f in new_state.all_features()}

        for ms in old_state.milestones:
            for f in ms.features:
                if f.status == Status.PASSING:
                    continue  # never touch passing features
                if f.id not in new_feature_ids:
                    # This feature was removed in the new plan → skip it
                    f.status = Status.SKIPPED
                    f.notes = (f.notes + " | [Replan] No longer needed, marked as skipped").strip(" |")
                else:
                    # Feature survives replan — reset attempts since old approach failed
                    if f.attempts > 0:
                        f.notes = (f.notes + f" | [Replan] attempts reset from {f.attempts} to 0").strip(" |")
                        f.attempts = 0

        # Add new features from the new plan
        old_ids = {f.id for _, f in old_state.all_features()}
        for ms in new_state.milestones:
            old_ms = old_state.get_milestone(ms.id)
            if old_ms:
                for f in ms.features:
                    if f.id not in old_ids:
                        old_ms.features.append(f)
            else:
                # New milestone entirely
                old_state.milestones.append(ms)

        return old_state

    # ── Initialization ─────────────────────────────────────────────────

    def _initialize_task(self, task_id: str, spec_path: str) -> TaskState:
        """Initialize a new task: run Planner to decompose the spec into features."""
        print(f"Initializing task '{task_id}' from spec: {spec_path}")

        with open(spec_path, "r", encoding="utf-8") as f:
            spec_content = f.read()

        planner_prompt = load_system_prompt(
            os.path.join(os.path.dirname(__file__), "prompts"),
            "planner",
        )

        init_messages = [
            {"role": "system", "content": planner_prompt},
            {"role": "user", "content": (
                load_system_prompt(
                    os.path.join(os.path.dirname(__file__), "prompts"),
                    "planner_init_user",
                ).format(task_id=task_id, spec_content=spec_content)
            )},
        ]

        response = self.planner_client.chat(init_messages)
        content = response.content

        task_data = self._extract_json(content, task_id, spec_content)
        task_state = TaskState.from_dict(task_data)
        task_state.created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        state_path = os.path.join(self.config.paths.memory_dir, "task_state.json")
        save_task_state(task_state, state_path)

        task_state_json = json.dumps(task_state.to_dict(), indent=2, ensure_ascii=False)
        self.memory.initialize_task_memory(task_id, task_state_json)

        # Initialize git repo
        ws = self.config.paths.workspace
        if not os.path.exists(os.path.join(ws, ".git")):
            os.makedirs(ws, exist_ok=True)
            self.tool_executor.run("bash", {
                "command": "git init && git config user.email 'agent@localhost' && git config user.name 'Coding Agent' && git add -A && git commit -m 'Initial commit'"
            })

        print(f"Task initialized: {task_state.total_feature_count} features across {len(task_state.milestones)} milestones")
        return task_state

    def _extract_json(self, content: str, task_id: str, spec_content: str) -> Dict[str, Any]:
        """Robust JSON extraction from LLM output.

        Handles common LLM JSON mistakes:
        - Markdown code fences
        - Trailing commas
        - Invalid escape sequences (\\U, \\x, etc. in strings)
        - Unescaped backslashes in Windows paths
        """
        content = re.sub(r'```json\s*', '', content)
        content = re.sub(r'```\s*$', '', content)
        content = content.strip()

        # Extract JSON object
        json_start = content.find("{")
        json_end = content.rfind("}") + 1
        if json_start < 0 or json_end <= json_start:
            print("Using fallback: no JSON object found.")
            return _build_fallback_task(task_id, spec_content, self.config)

        json_str = content[json_start:json_end]

        # Attempt 1: direct parse
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

        # Attempt 2: fix common issues
        repaired = json_str
        # Trailing commas
        repaired = re.sub(r',\s*}', '}', repaired)
        repaired = re.sub(r',\s*]', ']', repaired)
        # Invalid escape sequences: replace \ not followed by valid escape char
        repaired = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', repaired)

        try:
            return json.loads(repaired)
        except json.JSONDecodeError as e:
            print(f"Planner JSON parse error (after repair): {e}")
            print(f"Content preview: {json_str[:800]}")

        print("Using fallback task structure.")
        return _build_fallback_task(task_id, spec_content, self.config)

    # ── Final verification ─────────────────────────────────────────────

    def _run_final_verification(self, task_state: TaskState, session_id: int,
                                 state_path: str, snapshots_dir: str):
        """Run the final global verification command."""
        cmd = task_state.final_verification.command
        if not cmd:
            return
        result = self.tool_executor.run("bash", {"command": cmd, "timeout_sec": 300})
        if result.exit_code == 0:
            task_state.final_verification.status = Status.PASSING
            task_state.final_verification.last_run_session = session_id
        else:
            task_state.final_verification.status = Status.FAILED
            task_state.final_verification.last_run_session = session_id
        save_task_state(task_state, state_path)
        save_task_state_snapshot(task_state, session_id, snapshots_dir)

    def _inject_integration_fix(self, task_state: TaskState, session_id: int, state_path: str):
        """Create a new 'integration fix' feature when final verification fails."""
        fix_feature = Feature(
            id=f"FIX-s{session_id}",
            description=f"Fix integration test failures (discovered in session {session_id})",
            depends_on=[],
            acceptance=Acceptance(
                type="automated_test",
                command=task_state.final_verification.command,
                expect_exit_code=0,
            ),
            status=Status.PENDING,
            notes=f"Triggered by global verification failure in session {session_id}",
        )
        fix_milestone = Milestone(
            id="M-FIXES",
            title="Integration Fixes",
            status=Status.PENDING,
            features=[fix_feature],
        )
        task_state.milestones.append(fix_milestone)
        save_task_state(task_state, state_path)
        print(f"  Injected integration fix feature: {fix_feature.id}")

    # ── Anti-cheat ──────────────────────────────────────────────────────

    def _check_for_cheating(self, session_result: "SessionResult", session_id: int,
                             task_id: str):
        """Scan session transcript for attempts to copy from pre-existing libraries.

        Two categories of detection:
        1. Generic: inspect.getsource, cat of site-packages, git clone, wget/curl
        2. Task-specific: pip install of a package matching the task name
           (e.g., for task "decouple", flag "pip install python-decouple" or "pip install decouple")
        """
        transcript_path = session_result.transcript_path
        if not transcript_path or not os.path.exists(transcript_path):
            return

        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return

        violations = []

        # Generic patterns — scan the full transcript
        for pattern, label in _ANTI_CHEAT_PATTERNS:
            matches = pattern.findall(content)
            if matches:
                violations.append((label, len(matches)))

        # Task-specific: pip install of the target library.
        # Only scan bash COMMANDS, not pip output (which may legitimately
        # contain the package name when installing agent's own -e . package).
        bash_commands: List[str] = []
        for line in content.split("\n"):
            try:
                event = json.loads(line.strip())
                if event.get("type") == "tool_result" and event.get("tool") == "bash":
                    cmd = event.get("arguments", {}).get("command", "")
                    bash_commands.append(cmd)
            except (json.JSONDecodeError, KeyError):
                pass
        commands_text = "\n".join(bash_commands)

        task_pkg_patterns = [
            _re.compile(rf'pip\d*\s+install\s+(?:\S+/)?{_re.escape(task_id)}\b', _re.IGNORECASE),
            _re.compile(rf'pip\d*\s+install\s+python-{_re.escape(task_id)}\b', _re.IGNORECASE),
            _re.compile(rf'pip\d*\s+install\s+{_re.escape(task_id)}-python\b', _re.IGNORECASE),
        ]
        for pat in task_pkg_patterns:
            matches = pat.findall(commands_text)
            if matches:
                violations.append((f"pip install of task library '{task_id}'", len(matches)))
                break

        if violations:
            print(f"\n  ⚠️  ANTI-CHEAT: Session {session_id} has {len(violations)} suspicious pattern(s):")
            for label, count in violations:
                print(f"     - {label} ({count} occurrence(s))")
            # Write to decisions.md for audit trail
            self.memory.append_to_memory(
                "decisions.md",
                f"[Anti-cheat Session {session_id}] Detected {len(violations)} suspicious pattern(s): "
                + "; ".join(f"{label} ({count}x)" for label, count in violations),
                confidence=Confidence.OBSERVED,
                session_id=session_id,
                source_type="orchestrator",
                check_duplicate=False,
            )
            # Record in premature_claims-style tracker for final report
            self._cheat_flags.append({
                "session_id": session_id,
                "violations": [{"label": l, "count": c} for l, c in violations],
                "timestamp": time.time(),
            })

    # ── Logging ────────────────────────────────────────────────────────

    def _add_event(self, event_type: str, data: Dict[str, Any]):
        """Record an orchestrator event in memory — written to run_report at task end."""
        msg = f"[{event_type}] {json.dumps(data, ensure_ascii=False)}"
        self._events.append({"type": event_type, "timestamp": time.time(), **data})
        self._console.append(msg)
        print(f"  {msg}")

    _premature_claims: List[Dict[str, Any]] = []

    def _log_premature_claim(self, feature_id: str, session_id: int,
                             session_result: SessionResult, verification: VerificationResult):
        """Record a premature completion claim."""
        claim = {
            "feature_id": feature_id,
            "session_id": session_id,
            "tier1_actual": verification.tier1_pass,
            "tier2_actual": verification.tier2_pass,
            "timestamp": time.time(),
        }
        self._premature_claims.append(claim)
        self._add_event("premature_claim", claim)
        print(f"  *** PREMATURE CLAIM: model said done but verification failed for {feature_id}")


def run_initialization(config: Config, task_id: str, spec_path: str) -> TaskState:
    """Initialize task without starting the main loop (for CLI 'start' command)."""
    orch = Orchestrator(config)
    return orch._initialize_task(task_id, spec_path)


def plan_freeform_task(config: Config, task_id: str, goal: str) -> TaskState:
    """Decompose a free-form task description into a structured TaskState.

    Uses the Planner LLM to analyze the goal (which may be vague),
    make reasonable assumptions, and produce structured features with
    acceptance criteria. This is the key to handling underspecified tasks:
    the Planner fills in the gaps.

    Returns a TaskState ready to be saved and executed.
    """
    orch = Orchestrator(config)

    planner_prompt = load_system_prompt(
        os.path.join(config.project_root, "harness", "prompts"),
        "planner",
    )

    init_messages = [
        {"role": "system", "content": planner_prompt},
        {"role": "user", "content": (
            load_system_prompt(
                os.path.join(orch.config.project_root, "harness", "prompts"),
                "planner_freeform_user",
            ).format(task_id=task_id, goal=goal)
        )},
    ]

    response = orch.planner_client.chat(init_messages)
    content = response.content
    print(f"  [Planner] Response: {len(content)} chars")
    if len(content) < 2000:
        print(f"  [Planner] Raw: {content[:500]}")

    # Extract JSON
    task_data = orch._extract_json(content, task_id, goal)
    if "milestones" not in task_data:
        print(f"  [Planner] WARNING: no milestones in output, using fallback")
        task_data = _build_fallback_task(task_id, goal, config)
    task_state = TaskState.from_dict(task_data)
    task_state.created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Write to disk
    state_path = os.path.join(config.paths.memory_dir, "task_state.json")
    save_task_state(task_state, state_path)

    # Initialize memory
    task_state_json = json.dumps(task_state.to_dict(), indent=2, ensure_ascii=False)
    orch.memory.initialize_task_memory(task_id, task_state_json)

    # Init git
    ws = config.paths.workspace
    if not os.path.exists(os.path.join(ws, ".git")):
        os.makedirs(ws, exist_ok=True)
        orch.tool_executor.run("bash", {
            "command": "git init && git config user.email 'agent@localhost' && git config user.name 'Coding Agent' && git add -A && git commit -m 'Initial commit'"
        })

    print(f"Free-form task decomposed: {task_state.total_feature_count} features "
          f"across {len(task_state.milestones)} milestones")

    # Show the plan to the user
    print(f"\n  Plan:")
    for ms in task_state.milestones:
        print(f"  {ms.id}: {ms.title} ({len(ms.features)} features)")
        for f in ms.features:
            notes_hint = f" [{f.notes[:60]}...]" if f.notes else ""
            print(f"    - {f.id}: {f.description[:80]}{notes_hint}")

    return task_state


def _build_fallback_task(task_id: str, content: str, config: Config = None) -> Dict[str, Any]:
    """Build a minimal task state when Planner JSON fails to parse.

    Instead of generating useless 'echo' acceptance commands, creates
    reasonable pytest-based commands that the agent can fill in.
    The agent is expected to write actual tests during implementation.
    """
    features = []
    current_milestone = None

    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue

        # Detect milestone headers
        m = re.match(r'#+\s*(?:Milestone|M|Phase)\s*(\d+)[：:]\s*(.+)', line, re.IGNORECASE)
        if m:
            current_milestone = {
                "id": f"M{m.group(1)}",
                "title": m.group(2).strip(),
                "status": "pending",
                "features": [],
            }
            continue

        # Detect feature lines: "- F1.1: description" or "### F1.1 description"
        fm = re.match(r'[-*]\s+F(\d+\.\d+)[：:]?\s*(.+)', line)
        if not fm:
            fm = re.match(r'#+\s*F(\d+\.\d+)[：:\s]+(.+)', line)

        if fm and current_milestone is not None:
            desc = fm.group(2).strip()
            desc = re.sub(r'`([^`]+)`', r'\1', desc)
            desc = re.sub(r'\*\*([^*]+)\*\*', r'\1', desc)

            # Generate a real pytest acceptance command
            short = re.sub(r'[^\w]+', '_', desc.lower())[:40]
            cmd = f"cd workspace && python -m pytest tests/ -q -k \"{short}\""

            features.append({
                "id": f"F{fm.group(1)}",
                "description": desc[:200],
                "depends_on": [],
                "acceptance": {
                    "type": "automated_test",
                    "command": cmd,
                    "expect_exit_code": 0,
                },
                "status": "pending",
                "attempts": 0,
                "last_verified_session": None,
                "notes": "[Fallback] Planner JSON parsing failed, auto-generated. Agent must implement and write tests.",
            })

    if not features:
        features = [{
            "id": "F1",
            "description": content.strip()[:200],
            "depends_on": [],
            "acceptance": {
                "type": "automated_test",
                "command": "cd workspace && python -m pytest tests/ -q",
                "expect_exit_code": 0,
            },
            "status": "pending",
            "attempts": 0,
            "last_verified_session": None,
            "notes": "[Fallback] Single feature. Agent must write its own tests and decompose the task.",
        }]

    milestones = [{
        "id": "M1",
        "title": "Main Task",
        "status": "pending",
        "features": features,
    }]

    return {
        "task_id": task_id,
        "budget": {
            "max_sessions": config.budget.max_sessions if config else 40,
            "max_wall_clock_hours": config.budget.max_wall_clock_hours if config else 8,
        },
        "milestones": milestones,
        "final_verification": {
            "command": "cd workspace && python -m pytest tests/ -q --tb=short",
            "status": "pending",
        },
    }
