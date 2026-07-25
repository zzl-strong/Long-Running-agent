"""Self-verification: Tier-1 automated checks and Tier-2 independent LLM review.

Tier 1: Execute acceptance.command and check exit_code. Deterministic and cheap.
Tier 2: Independent LLM session reviewing only code+acceptance criteria (not conversation history).
         Costs more tokens, catches issues tier-1 tests miss.
"""
import json
import os
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .config import Config
from .context_manager import load_system_prompt
from .llm_client import LLMClient, TOOL_DEFINITIONS
from .task_state import (
    Acceptance,
    Feature,
    Milestone,
    Status,
    TaskState,
    update_feature_status,
    save_task_state,
    save_task_state_snapshot,
)
from .tools import ToolExecutor


@dataclass
class VerificationResult:
    feature_id: str
    tier1_pass: bool
    tier1_output: str = ""
    tier1_exit_code: int = -1
    tier2_pass: Optional[bool] = None  # None = tier2 not run
    tier2_evidence: List[str] = field(default_factory=list)
    final_pass: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "tier1_pass": self.tier1_pass,
            "tier1_exit_code": self.tier1_exit_code,
            "tier1_output": self.tier1_output[:1000],
            "tier2_pass": self.tier2_pass,
            "tier2_evidence": self.tier2_evidence,
            "final_pass": self.final_pass,
        }


def _has_verdict(content: str) -> bool:
    """Check if the verifier's response contains a VERDICT line."""
    return bool(re.search(r'VERDICT:\s*(pass|fail)', content, re.IGNORECASE))


def run_tier1(
    feature: Feature,
    tool_executor: ToolExecutor,
    timeout_sec: int = 180,
    api_check_timeout_sec: int = 60,
) -> Tuple[bool, int, str]:
    """Execute automated acceptance test for a feature.

    Returns (pass, exit_code, output).
    """
    acceptance = feature.acceptance
    if not acceptance.command:
        return (False, -1, "No acceptance command defined")

    # Guard against trivial acceptance commands (model tampering)
    trivial_patterns = [
        r'^\s*echo\s', r'^\s*true\s*$', r'^\s*/\*true\s*$',
        r'^\s*:\s*$',  # shell no-op
    ]
    import re as _re
    cmd_stripped = acceptance.command.strip()
    for pattern in trivial_patterns:
        if _re.match(pattern, cmd_stripped):
            return (False, -1,
                    f"REJECTED: acceptance command appears trivial: '{cmd_stripped[:80]}'. "
                    f"The command must actually verify the feature (e.g., pytest, not echo).")

    result = tool_executor.run("bash", {
        "command": acceptance.command,
        "timeout_sec": timeout_sec,
    })

    exit_code = result.exit_code if result.exit_code is not None else -1
    output = result.stdout + "\n" + result.stderr

    expected = acceptance.expect_exit_code
    passed = (exit_code == expected)

    # Run API contract check if defined
    if not passed:
        # Don't bother — main acceptance already failed
        return (passed, exit_code, output)

    if acceptance.has_api_check:
        api_result = tool_executor.run("bash", {
            "command": acceptance.api_check,
            "timeout_sec": api_check_timeout_sec,
        })
        api_code = api_result.exit_code if api_result.exit_code is not None else -1
        if api_code != 0:
            output += (
                f"\n[API CHECK FAILED] exit_code={api_code}\n"
                f"Command: {acceptance.api_check}\n"
                f"stdout: {api_result.stdout}\n"
                f"stderr: {api_result.stderr}"
            )
            passed = False
            exit_code = api_code

    return (passed, exit_code, output)


def run_tier2(
    feature: Feature,
    task_state: TaskState,
    config: Config,
    client: LLMClient,
    tool_executor: ToolExecutor,
    logs_dir: str,
    session_id: int,
    spec_path: Optional[str] = None,
) -> VerificationResult:
    """Run independent LLM verification for a feature.

    Key design: verifier gets NO conversation history from the coding agent.
    It only sees:
    - Feature description + acceptance criteria
    - Current file contents (via its own read/batch tools)
    - Tier-1 result
    - decisions.md (for constraint checking)
    """
    prompts_dir = os.path.join(os.path.dirname(__file__), "prompts")
    system_prompt = load_system_prompt(prompts_dir, "verifier")
    user_template = load_system_prompt(prompts_dir, "verifier_user")

    if user_template:
        spec_section = ""
        if spec_path and os.path.exists(spec_path):
            spec_template = load_system_prompt(prompts_dir, "verifier_spec_section")
            spec_section = spec_template.format(spec_path=spec_path) if spec_template else ""
        verifier_prompt = user_template.format(
            feature_id=feature.id,
            feature_desc=feature.description,
            dependencies=str(feature.depends_on) if feature.depends_on else "none",
            tier1_result="(will be injected after tier-1 runs)",
            spec_section=spec_section,
        )
    else:
        verifier_prompt = (
            f"Verify feature {feature.id}: {feature.description}\n"
            f"Dependencies: {feature.depends_on or 'none'}\n"
        )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": verifier_prompt},
    ]

    # Verifier agent loop — generous turn budget to avoid premature cutoff
    verifier_turns = 0
    max_verifier_turns = config.verification.max_verifier_turns
    tier1_result = run_tier1(feature, tool_executor)
    tier1_pass, tier1_code, tier1_output = tier1_result

    transcript_path = f"{logs_dir}/verifier_s{session_id:04d}_{feature.id}.jsonl"

    verdict = VerificationResult(
        feature_id=feature.id,
        tier1_pass=tier1_pass,
        tier1_output=tier1_output,
        tier1_exit_code=tier1_code,
    )

    # Inject tier-1 result so verifier doesn't need to re-run
    messages.append({"role": "user", "content": f"[System]: Tier-1 automated acceptance result: exit_code={tier1_code}, "
                    f"{'PASS' if tier1_pass else 'FAIL'}.\nOutput summary:\n{tier1_output[:config.verification.tier1_output_max_chars]}"})

    input_tok = 0
    output_tok = 0

    while verifier_turns < max_verifier_turns:
        # ── Final turn: force a verdict if not already given ──────────
        if verifier_turns == max_verifier_turns - 1:
            last_content = messages[-1].get("content", "") if messages[-1].get("role") == "assistant" else ""
            if not _has_verdict(last_content):
                messages.append({"role": "user", "content": (
                    "[System]: This is your final turn. You have gathered enough information. "
                    "Output your VERDICT: pass|fail with EVIDENCE now. No more tool calls."
                )})

        response = client.chat(messages, tools=TOOL_DEFINITIONS)
        input_tok += response.usage.input_tokens
        output_tok += response.usage.output_tokens

        assistant_msg = {"role": "assistant", "content": response.content}
        if response.tool_calls:
            assistant_msg["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)}}
                for tc in response.tool_calls
            ]
        messages.append(assistant_msg)

        # Log event
        with open(transcript_path, "a") as f:
            f.write(json.dumps({
                "type": "verifier_turn",
                "turn": verifier_turns,
                "content": response.content[:500],
                "tool_calls": [(tc.name, tc.arguments) for tc in response.tool_calls],
                "usage": {"input": response.usage.input_tokens, "output": response.usage.output_tokens},
                "timestamp": time.time(),
            }, ensure_ascii=False) + "\n")

        if response.stop_reason == "end_turn" and not response.tool_calls:
            verifier_turns += 1
            # If model stopped without giving a verdict, force one
            if not _has_verdict(response.content):
                messages.append({"role": "user", "content": (
                    "[System]: You stopped without giving a verdict. "
                    "You MUST output VERDICT: pass|fail and EVIDENCE now. No more analysis."
                )})
                continue  # Give the model one more turn to produce a verdict
            break

        if not response.tool_calls:
            verifier_turns += 1
            break

        # Execute tools for verifier
        verifier_turns += 1
        for tc in response.tool_calls:
            result = tool_executor.run(tc.name, tc.arguments)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result.to_message(),
            })

    # Parse verdict from final content
    all_content = ""
    for msg in messages:
        if msg["role"] == "assistant":
            all_content += msg.get("content", "") + "\n"

    m = re.search(r'VERDICT:\s*(pass|fail)', all_content, re.IGNORECASE)
    if m:
        verdict.tier2_pass = m.group(1).lower() == "pass"

    # Extract evidence lines
    evidence_section = re.search(r'EVIDENCE:\n(.*?)(?=\Z)', all_content, re.DOTALL)
    if evidence_section:
        for line in evidence_section.group(1).strip().split("\n"):
            line = line.strip()
            if line.startswith("- "):
                verdict.tier2_evidence.append(line[2:])

    # Final verdict: both tiers must pass
    if verdict.tier2_pass is not None:
        verdict.final_pass = verdict.tier1_pass and verdict.tier2_pass
    else:
        # If tier-2 failed to produce a verdict, rely on tier-1 only but mark as less confident
        verdict.final_pass = verdict.tier1_pass

    return verdict


def should_run_tier2(feature: Feature, config: Config) -> bool:
    """Determine if tier-2 verification should run for this feature.

    Sampling strategy: run tier-2 on a subset to control costs.
    Always run tier-2 for features that previously failed.
    """
    if not config.verification.tier2_enabled:
        return False
    if feature.status == Status.FAILED:
        return True  # always double-check previously-failed features
    return random.random() < config.verification.tier2_sample_rate


def apply_verification(
    task_state: TaskState,
    verification: VerificationResult,
    session_id: int,
    state_path: str,
    snapshots_dir: str,
) -> bool:
    """Apply verification result to task state.

    A feature is marked passing ONLY if verification passes.
    The model itself cannot directly set passing status.
    """
    result = task_state.get_feature(verification.feature_id)
    if result is None:
        return False

    _, feature = result

    if verification.final_pass:
        t2_str = f"tier2=PASS" if verification.tier2_pass else (
            f"tier2=SKIP" if verification.tier2_pass is None else f"tier2=FAIL"
        )
        evidence = "; ".join(verification.tier2_evidence) if verification.tier2_evidence else "none"
        feature.last_verified_session = session_id
        ok = update_feature_status(
            task_state, verification.feature_id, Status.PASSING,
            session_id=None,
            notes=f"Verified: tier1={'PASS' if verification.tier1_pass else 'FAIL'}, {t2_str}. "
                  f"T2 evidence: {evidence}",
        )
    else:
        feature.last_verified_session = session_id
        ok = update_feature_status(
            task_state, verification.feature_id, Status.FAILED,
            session_id=None,
            notes=f"Verification failed: tier1={'PASS' if verification.tier1_pass else 'FAIL'}, "
                  f"tier2={'PASS' if verification.tier2_pass else 'SKIP/FAIL'}\n"
                  f"Evidence: {'; '.join(verification.tier2_evidence)}",
            increment_attempts=True,
        )

    if ok:
        save_task_state(task_state, state_path)
        save_task_state_snapshot(task_state, session_id, snapshots_dir)

    return ok


def create_verification_summary(results: List[VerificationResult]) -> Dict[str, Any]:
    """Summarize verification results across features."""
    total = len(results)
    tier1_pass = sum(1 for r in results if r.tier1_pass)
    tier2_run = sum(1 for r in results if r.tier2_pass is not None)
    tier2_pass = sum(1 for r in results if r.tier2_pass is True)
    tier2_fail = sum(1 for r in results if r.tier2_pass is False)
    final_pass = sum(1 for r in results if r.final_pass)

    # Find divergence cases (tier1 pass but tier2 fail)
    divergences = [
        {"feature_id": r.feature_id, "tier1": r.tier1_pass, "tier2": r.tier2_pass}
        for r in results if r.tier1_pass and r.tier2_pass is False
    ]

    return {
        "total_features_verified": total,
        "tier1_pass_count": tier1_pass,
        "tier2_run_count": tier2_run,
        "tier2_pass_count": tier2_pass,
        "tier2_fail_count": tier2_fail,
        "final_pass_count": final_pass,
        "tier_divergences": divergences,
    }
