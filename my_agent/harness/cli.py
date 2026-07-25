"""Command-line interface for the Long-Running Coding Agent System.

Usage:
    # Spec-based task
    python -m harness.cli start --task <id> --spec <file.md> [--project <dir>] [--start]

    # Free-form task (no spec required)
    python -m harness.cli run --task <id> --goal "<description>" [--project <dir>]

    # Resume / status
    python -m harness.cli resume --task <id> [--project <dir>]
    python -m harness.cli status [--task <id>] [--project <dir>]
"""
import argparse
import os
import sys
from typing import Optional

from .config import Config, load_config
from .task_state import load_task_state, save_task_state, get_completion_summary
from .orchestrator import Orchestrator, run_initialization


def _resolve_project(args) -> str:
    """Determine project directory: --project flag or current directory."""
    if hasattr(args, 'project') and args.project:
        return os.path.abspath(args.project)
    return os.getcwd()


def _get_config(project_root: str) -> Config:
    return load_config(project_root)


# ═══════════════════════════════════════════════════════════════════════
# Commands
# ═══════════════════════════════════════════════════════════════════════

def cmd_start(args):
    """Initialize and optionally start a spec-based task."""
    project_root = _resolve_project(args)
    config = _get_config(project_root)
    task_id = args.task
    spec_path = args.spec

    if not spec_path:
        print("Error: --spec is required for spec-based tasks.")
        sys.exit(1)
    if not os.path.exists(spec_path):
        print(f"Error: spec file not found: {spec_path}")
        sys.exit(1)

    print(f"Project: {project_root}")
    print(f"Creating task '{task_id}' from {spec_path}")
    task_state = run_initialization(config, task_id, spec_path)

    print(f"\nTask '{task_id}' initialized:")
    print(f"  Milestones: {len(task_state.milestones)}")
    print(f"  Features: {task_state.total_feature_count}")
    print(f"  Budget: {task_state.budget.max_sessions} sessions / {task_state.budget.max_wall_clock_hours}h")
    print(f"\nState file: {config.paths.memory_dir}/task_state.json")

    if args.start:
        print("\nStarting agent loop...")
        _do_run(config, task_id, args)


def cmd_run(args):
    """Run a free-form coding task (no spec file required)."""
    project_root = _resolve_project(args)
    config = _get_config(project_root)
    task_id = args.task
    goal = args.goal

    if not goal:
        print("Error: --goal is required for free-form tasks")
        sys.exit(1)

    state_path = os.path.join(config.paths.memory_dir, "task_state.json")
    existing = load_task_state(state_path)
    if existing and existing.task_id == task_id and not args.force:
        print(f"Task '{task_id}' already exists. Use 'resume' to continue.")
        print(f"  Progress: {existing.completion_ratio:.1%} "
              f"({existing.all_pass_count}/{existing.total_feature_count} passing)")
        print("  Use --force to reinitialize.")
        sys.exit(1)

    from .orchestrator import plan_freeform_task

    print(f"Project: {project_root}")
    print(f"Decomposing goal into features...")
    task_state = plan_freeform_task(config, task_id, goal)
    print(f"\nTask '{task_id}' ready: {task_state.total_feature_count} features, "
          f"{len(task_state.milestones)} milestones")

    if args.start:
        print("\nStarting agent loop...")
        _do_run(config, task_id, args)


def cmd_resume(args):
    """Resume an existing task.

    Recovery logic:
    1. Find the latest snapshot (task_state_sNNNN.json) — this is the
       last good state after a completed verification cycle.
    2. Restore it to task_state.json.
    3. Delete any session_NNNN.jsonl files NEWER than the snapshot —
       these were interrupted and may be incomplete.
    4. New sessions pick up from the highest remaining session number.
    """
    project_root = _resolve_project(args)
    config = _get_config(project_root)
    task_id = args.task

    import re as _re
    logs_dir = config.paths.logs_dir
    snapshots_dir = os.path.join(logs_dir, "snapshots")
    state_path = os.path.join(config.paths.memory_dir, "task_state.json")

    # ── 1. Find latest snapshot ──────────────────────────────────────
    latest_snap_n = 0
    latest_snap_path = None
    if os.path.isdir(snapshots_dir):
        for fname in os.listdir(snapshots_dir):
            m = _re.match(r'task_state_s(\d+)\.json', fname)
            if m:
                n = int(m.group(1))
                if n > latest_snap_n:
                    latest_snap_n = n
                    latest_snap_path = os.path.join(snapshots_dir, fname)

    if latest_snap_path is None:
        print("Error: No snapshots found. Cannot resume.")
        sys.exit(1)

    # ── 2. Restore task state from latest snapshot ───────────────────
    snap_state = load_task_state(latest_snap_path)
    if snap_state is None:
        print(f"Error: Could not load snapshot {latest_snap_path}")
        sys.exit(1)
    save_task_state(snap_state, state_path)
    print(f"Restored task state from snapshot: task_state_s{latest_snap_n:04d}.json")
    task_state = snap_state

    # ── 3. Delete session logs newer than the snapshot ───────────────
    # These are interrupted/incomplete — their verification never completed.
    if os.path.isdir(logs_dir):
        for fname in os.listdir(logs_dir):
            m = _re.match(r'session_(\d+)\.jsonl', fname)
            if m:
                n = int(m.group(1))
                if n > latest_snap_n:
                    path = os.path.join(logs_dir, fname)
                    os.remove(path)
                    print(f"  Deleted interrupted session log: {fname}")

    # ── 4. Show latest handoff ──────────────────────────────────────
    handoffs_dir = config.paths.handoffs_dir
    if os.path.isdir(handoffs_dir):
        handoff_files = sorted(
            [f for f in os.listdir(handoffs_dir) if f.endswith(".md")],
            reverse=True,
        )
        if handoff_files:
            print(f"Latest handoff: {handoff_files[0]}")

    print(f"\nProject: {project_root}")
    print(f"Resuming task '{task_id}'")
    summary = get_completion_summary(task_state)
    print(f"  Current: {summary['passing']}/{summary['total_features']} passing "
          f"({summary['completion_ratio']:.1%})")
    print(f"  Pending: {summary['pending']}, Failed: {summary['failed']}")

    _do_run(config, task_id, args)


def cmd_status(args):
    """Print current task status."""
    project_root = _resolve_project(args)
    config = _get_config(project_root)

    state_path = os.path.join(config.paths.memory_dir, "task_state.json")
    print(f"\nProject: {config.project_root}")
    print(f"Workspace: {config.paths.workspace}")

    if not os.path.exists(state_path):
        print("No active task.")
        return

    task_state = load_task_state(state_path)
    if task_state is None:
        print(f"Error loading state from {state_path}")
        return

    summary = get_completion_summary(task_state)
    print(f"\nTask: {summary['task_id']}")
    print(f"Created: {task_state.created_at}")
    print(f"Completion: {summary['completion_ratio']:.1%} "
          f"({summary['passing']}/{summary['total_features']} passing)")
    print(f"  passing: {summary['passing']}  failed: {summary['failed']}  "
          f"pending: {summary['pending']}  blocked: {summary['blocked']}")

    print(f"\nMilestones:")
    for ms in task_state.milestones:
        pct = f"{ms.passing_count}/{ms.feature_count}" if ms.feature_count else "0/0"
        marker = "✓" if ms.is_done else "○"
        print(f"  {marker} {ms.id}: {ms.title} ({pct} passing)")
        for f in ms.features:
            sym = {"passing": "✓", "failed": "✗", "in_progress": "▶", "blocked": "⊘", "pending": "○"}
            print(f"      {sym.get(f.status.value, '?')} {f.id} [{f.status.value}] {f.description[:80]}")


def _do_run(config: Config, task_id: str, args):
    """Execute the main orchestrator loop."""
    orchestrator = Orchestrator(config)

    max_sessions = getattr(args, 'max_sessions', None)
    max_hours = getattr(args, 'max_hours', None)
    spec_path = getattr(args, 'spec', None)

    report = orchestrator.run(
        task_id=task_id,
        spec_path=spec_path,
        max_sessions=max_sessions,
        max_hours=max_hours,
    )
    print(f"\n{'='*60}")
    print(f"Run complete.")
    print(f"  Sessions: {report['total_sessions']}")
    print(f"  Wall clock: {report.get('total_wall_clock_hours', 0):.1f}h")
    print(f"  Ended: {report['ended_reason']}")


# ═══════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Coding Agent System — Single-Project Coding Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create task from spec file and run
  python -m harness.cli start --task my-task --spec spec.md --project ./my-project --start

  # Free-form task
  python -m harness.cli run --task build-api --goal "Build a FastAPI user management system"

  # Resume / Status
  python -m harness.cli resume --task my-task --project ./my-project
  python -m harness.cli status --project ./my-project
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # start — spec-based task
    p_start = subparsers.add_parser("start", help="Initialize and optionally run a spec-based task")
    p_start.add_argument("--task", required=True, help="Task name/ID")
    p_start.add_argument("--spec", required=True, help="Path to task specification file")
    p_start.add_argument("--start", action="store_true", help="Start running immediately after init")
    p_start.add_argument("--project", help="Project directory (default: cwd)")

    # run — free-form task
    p_run = subparsers.add_parser("run", help="Run a free-form coding task (no spec file)")
    p_run.add_argument("--task", required=True, help="Task name/ID")
    p_run.add_argument("--goal", required=True, help="Natural language description of the task")
    p_run.add_argument("--start", action="store_true", help="Start running immediately after init")
    p_run.add_argument("--force", action="store_true", help="Reinitialize if task already exists")
    p_run.add_argument("--max-sessions", type=int, help="Override max sessions")
    p_run.add_argument("--max-hours", type=float, help="Override max hours")
    p_run.add_argument("--project", help="Project directory (default: cwd)")

    # resume
    p_resume = subparsers.add_parser("resume", help="Resume an existing task")
    p_resume.add_argument("--task", required=True, help="Task name/ID")
    p_resume.add_argument("--max-sessions", type=int, help="Override max sessions")
    p_resume.add_argument("--max-hours", type=float, help="Override max hours")
    p_resume.add_argument("--project", help="Project directory (default: cwd)")

    # status
    p_status = subparsers.add_parser("status", help="Show task status")
    p_status.add_argument("--task", required=False, help="Task name/ID (optional)")
    p_status.add_argument("--project", help="Project directory (default: cwd)")

    args = parser.parse_args()

    if args.command == "start":
        cmd_start(args)
    elif args.command == "run":
        cmd_run(args)
    elif args.command == "resume":
        cmd_resume(args)
    elif args.command == "status":
        cmd_status(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
