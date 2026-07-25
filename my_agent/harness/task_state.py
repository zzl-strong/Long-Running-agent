"""Task state management: data structures, selection algorithm, state machine.

task_state.json is the single source of truth. It is structured JSON — the model
can update status fields via write tool, but the verifier enforces that passing
status can only be set when verification succeeds.
"""
import copy
import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class Status(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    FAILED = "failed"
    PASSING = "passing"
    SKIPPED = "skipped"  # Feature was deemed unnecessary during execution (dynamic replanning)


VALID_TRANSITIONS = {
    Status.PENDING: {Status.IN_PROGRESS, Status.PASSING, Status.SKIPPED},
    Status.IN_PROGRESS: {Status.PASSING, Status.FAILED, Status.BLOCKED, Status.PENDING, Status.SKIPPED},
    Status.FAILED: {Status.IN_PROGRESS, Status.PENDING, Status.SKIPPED},
    Status.BLOCKED: {Status.PENDING, Status.IN_PROGRESS, Status.SKIPPED},
    Status.PASSING: {Status.FAILED},  # regression: only verifier can downgrade from passing
    Status.SKIPPED: {Status.PENDING},  # can be revived if circumstances change
}


@dataclass
class Acceptance:
    type: str = "automated_test"
    command: str = ""
    expect_exit_code: int = 0
    api_check: str = ""  # Optional: command to verify public API contract (imports, signatures)

    def to_dict(self) -> Dict[str, Any]:
        d = {"type": self.type, "command": self.command, "expect_exit_code": self.expect_exit_code}
        if self.api_check:
            d["api_check"] = self.api_check
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Acceptance":
        return cls(
            type=d.get("type", "automated_test"),
            command=d.get("command", ""),
            expect_exit_code=d.get("expect_exit_code", 0),
            api_check=d.get("api_check", ""),
        )

    @property
    def has_api_check(self) -> bool:
        return bool(self.api_check and self.api_check.strip())


@dataclass
class Feature:
    id: str
    description: str
    depends_on: List[str] = field(default_factory=list)
    acceptance: Acceptance = field(default_factory=Acceptance)
    status: Status = Status.PENDING
    attempts: int = 0
    last_verified_session: Optional[int] = None
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "depends_on": self.depends_on,
            "acceptance": self.acceptance.to_dict(),
            "status": self.status.value,
            "attempts": self.attempts,
            "last_verified_session": self.last_verified_session,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Feature":
        acc = d.get("acceptance", {})
        # Fix Planner common mistake: acceptance as string instead of {command, expect_exit_code}
        if isinstance(acc, str):
            desc = d.get("description", "feature")
            short = "".join(c if c.isalnum() or c in '._-' else '_' for c in desc.lower())[:40]
            acc = {
                "type": "automated_test",
                "command": f"cd workspace && python -m pytest tests/ -q -k \"{short}\"",
                "expect_exit_code": 0,
            }
        # Handle unknown status values from Planner output (e.g. "completed" → "passing")
        raw_status = d.get("status", "pending")
        try:
            status = Status(raw_status)
        except ValueError:
            _STATUS_FALLBACK = {
                "completed": Status.PASSING,
                "done": Status.PASSING,
                "ready": Status.PENDING,
                "active": Status.IN_PROGRESS,
                "error": Status.FAILED,
            }
            status = _STATUS_FALLBACK.get(raw_status, Status.PENDING)
        return cls(
            id=d["id"],
            description=d.get("description", ""),
            depends_on=d.get("depends_on", []),
            acceptance=Acceptance.from_dict(acc),
            status=status,
            attempts=d.get("attempts", 0),
            last_verified_session=d.get("last_verified_session"),
            notes=d.get("notes", ""),
        )


@dataclass
class Milestone:
    id: str
    title: str
    features: List[Feature] = field(default_factory=list)

    @property
    def feature_count(self) -> int:
        return len(self.features)

    @property
    def passing_count(self) -> int:
        return sum(1 for f in self.features if f.status == Status.PASSING)

    @property
    def failed_count(self) -> int:
        return sum(1 for f in self.features if f.status == Status.FAILED)

    @property
    def is_done(self) -> bool:
        """Milestone is done when all features are PASSING or SKIPPED."""
        return all(f.status in (Status.PASSING, Status.SKIPPED) for f in self.features)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "features": [f.to_dict() for f in self.features],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Milestone":
        return cls(
            id=d.get("id", f"M-{d.get('title', 'unknown')[:20]}"),
            title=d.get("title", ""),
            features=[Feature.from_dict(f) for f in d.get("features", [])],
        )


@dataclass
class FinalVerification:
    command: str = ""
    status: Status = Status.PENDING
    last_run_session: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command": self.command,
            "status": self.status.value,
            "last_run_session": self.last_run_session,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FinalVerification":
        raw_status = d.get("status", "pending")
        try:
            status = Status(raw_status)
        except ValueError:
            _FV_FALLBACK = {"completed": Status.PASSING, "done": Status.PASSING, "pass": Status.PASSING}
            status = _FV_FALLBACK.get(raw_status, Status.PENDING)
        return cls(
            command=d.get("command", ""),
            status=status,
            last_run_session=d.get("last_run_session"),
        )


@dataclass
class TaskBudget:
    max_sessions: int = 40
    max_wall_clock_hours: float = 8.0

    def to_dict(self) -> Dict[str, Any]:
        return {"max_sessions": self.max_sessions, "max_wall_clock_hours": self.max_wall_clock_hours}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TaskBudget":
        return cls(
            max_sessions=d.get("max_sessions", 40),
            max_wall_clock_hours=d.get("max_wall_clock_hours", 8.0),
        )


@dataclass
class TaskState:
    task_id: str
    created_at: str = ""
    budget: TaskBudget = field(default_factory=TaskBudget)
    milestones: List[Milestone] = field(default_factory=list)
    final_verification: FinalVerification = field(default_factory=FinalVerification)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def all_features(self) -> List[Tuple[Milestone, Feature]]:
        """Return all (milestone, feature) pairs ordered by milestone/feature order."""
        result = []
        for ms in self.milestones:
            for f in ms.features:
                result.append((ms, f))
        return result

    def get_feature(self, feature_id: str) -> Optional[Tuple[Milestone, Feature]]:
        """Find a feature by id across all milestones."""
        for ms in self.milestones:
            for f in ms.features:
                if f.id == feature_id:
                    return (ms, f)
        return None

    def get_milestone(self, milestone_id: str) -> Optional[Milestone]:
        for ms in self.milestones:
            if ms.id == milestone_id:
                return ms
        return None

    @property
    def all_pass_count(self) -> int:
        return sum(1 for _, f in self.all_features() if f.status in (Status.PASSING, Status.SKIPPED))

    @property
    def total_feature_count(self) -> int:
        return sum(ms.feature_count for ms in self.milestones)

    @property
    def completion_ratio(self) -> float:
        total = self.total_feature_count
        if total == 0:
            return 0.0
        return self.all_pass_count / total

    @property
    def is_complete(self) -> bool:
        """All features passing or skipped AND final verification passed."""
        all_ok = all(f.status in (Status.PASSING, Status.SKIPPED) for _, f in self.all_features())
        final_ok = self.final_verification.status == Status.PASSING
        return all_ok and final_ok

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "created_at": self.created_at,
            "budget": self.budget.to_dict(),
            "milestones": [m.to_dict() for m in self.milestones],
            "final_verification": self.final_verification.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TaskState":
        return cls(
            task_id=d["task_id"],
            created_at=d.get("created_at", ""),
            budget=TaskBudget.from_dict(d.get("budget", {})),
            milestones=[Milestone.from_dict(m) for m in d.get("milestones", [])],
            final_verification=FinalVerification.from_dict(d.get("final_verification", {})),
        )


def load_task_state(path: str) -> Optional[TaskState]:
    """Load task state from JSON file."""
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return TaskState.from_dict(raw)


def save_task_state(state: TaskState, path: str):
    """Save task state to JSON file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Backup before overwrite
    if os.path.exists(path):
        backup = path + ".bak"
        with open(path, "r") as src, open(backup, "w") as dst:
            dst.write(src.read())
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state.to_dict(), f, indent=2, ensure_ascii=False)


def save_task_state_snapshot(state: TaskState, session_id: int, snapshots_dir: str):
    """Save an immutable snapshot for experimental analysis."""
    os.makedirs(snapshots_dir, exist_ok=True)
    snapshot_path = os.path.join(snapshots_dir, f"task_state_s{session_id:04d}.json")
    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(state.to_dict(), f, indent=2, ensure_ascii=False)


def deps_satisfied(feature: Feature, task_state: TaskState) -> bool:
    """Check if all dependencies of a feature are passing."""
    if not feature.depends_on:
        return True
    for dep_id in feature.depends_on:
        result = task_state.get_feature(dep_id)
        if result is None:
            return False
        _, dep_feature = result
        if dep_feature.status != Status.PASSING:
            return False
    return True


def pick_next_feature(task_state: TaskState, max_retry: int = 3) -> Optional[Tuple[Milestone, Feature]]:
    """Select the next feature to work on.

    Algorithm:
    1. First: retry previously failed features (not exceeding max_retry)
    2. Second: first pending feature with satisfied dependencies (in milestone order)
    3. None → all done or blocked
    """
    # Priority 1: failed features eligible for retry
    for ms in task_state.milestones:
        for f in ms.features:
            if f.status == Status.FAILED and f.attempts <= max_retry and deps_satisfied(f, task_state):
                return (ms, f)

    # Priority 2: first pending feature with satisfied deps
    for ms in task_state.milestones:
        for f in ms.features:
            if f.status == Status.PENDING and deps_satisfied(f, task_state):
                return (ms, f)

    # Priority 3: blocked features — could be unblocked now that deps are passing
    for ms in task_state.milestones:
        for f in ms.features:
            if f.status == Status.BLOCKED and deps_satisfied(f, task_state):
                return (ms, f)

    return None


def update_feature_status(
    task_state: TaskState,
    feature_id: str,
    new_status: Status,
    session_id: Optional[int] = None,
    notes: str = "",
    increment_attempts: bool = False,
) -> bool:
    """Update a feature's status with validation.

    Returns True if the update was valid and applied, False if rejected.
    """
    result = task_state.get_feature(feature_id)
    if result is None:
        return False

    _, feature = result
    old_status = feature.status

    # Validate transition
    if new_status not in VALID_TRANSITIONS.get(old_status, set()):
        return False

    feature.status = new_status
    # NOTE: last_verified_session is NOT set here. It is only set by the
    # verifier (apply_verification) and regression check — places where
    # verification actually runs. Marking a feature IN_PROGRESS does not
    # count as verification.
    if notes:
        sep = " | " if feature.notes else ""
        feature.notes = feature.notes + sep + notes
    if increment_attempts:
        feature.attempts += 1

    return True


def get_completion_summary(task_state: TaskState) -> Dict[str, Any]:
    """Generate a summary of current completion status."""
    status_counts = {s.value: 0 for s in Status}
    for _, f in task_state.all_features():
        status_counts[f.status.value] += 1

    return {
        "task_id": task_state.task_id,
        "total_features": task_state.total_feature_count,
        "passing": status_counts["passing"],
        "failed": status_counts["failed"],
        "in_progress": status_counts["in_progress"],
        "pending": status_counts["pending"],
        "blocked": status_counts["blocked"],
        "completion_ratio": task_state.completion_ratio,
        "final_verification": task_state.final_verification.status.value,
    }
