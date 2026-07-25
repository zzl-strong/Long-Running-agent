"""Skill and Memory file-system persistence.

Memory = running state (task-specific, high-frequency change):
  - task_state.json  — structured JSON: feature status, milestones, verification state
  - progress.md      — append-only log: per-session summaries (what was done, completion %)
  - decisions.md     — append-only log: architecture decisions, constraints, replan events
  - facts.md         — append-only log: verified facts, feature failure records
  - handoffs/*.md    — per-session structured handoff (git commit, issues, next action)

Skill = reusable experience (cross-task, low-frequency change):
  - .agent/skills/*/SKILL.md  — skill content (created by orchestrator auto-extraction
                                 or by the model via the write tool)
  - INDEX.md                   — auto-rebuilt index of all skills on disk

Governance rules:
- Memory .md files are append-only (never overwrite history).
  Reason: these are audit logs. Overwriting would destroy the record of what happened.
  If something was wrong, append a correction — never erase the original.
- Write-before-read: check for duplicates before appending
- Confidence tags on all facts/decisions
- Skills are auto-extracted by the orchestrator from successful recovery patterns.
  The model may also create skills via the write tool, but the orchestrator's
  auto-extraction is the primary and reliable path.
"""
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .config import Config


class Confidence(str, Enum):
    VERIFIED = "verified"       # Confirmed by running tests
    OBSERVED = "observed"       # Seen in practice but not formally tested
    ASSUMED = "assumed"         # Best guess, should be re-checked if issues arise
    CORRECTED = "corrected"     # Was wrong before, now corrected
    DEPRECATED = "deprecated"   # No longer relevant


@dataclass
class MemoryEntry:
    """A single entry in a memory file."""
    content: str
    confidence: Confidence = Confidence.OBSERVED
    session_id: int = 0
    timestamp: str = ""
    source_type: str = "agent"  # agent, verifier, orchestrator, maintenance

    def to_markdown(self) -> str:
        if not self.timestamp:
            self.timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        return (
            f"\n<!-- entry session={self.session_id} confidence={self.confidence.value} "
            f"source={self.source_type} time={self.timestamp} -->\n"
            f"{self.content}\n"
        )

    @staticmethod
    def parse_from_markdown(text: str) -> Optional["MemoryEntry"]:
        """Parse a markdown memory entry back if possible."""
        m = re.search(r'<!-- entry session=(\d+) confidence=(\w+) source=(\w+) time=([^>]+) -->', text)
        if not m:
            return None
        return MemoryEntry(
            content=text.split("-->", 1)[1].strip() if "--> " in text else "",
            confidence=Confidence(m.group(2)),
            session_id=int(m.group(1)),
            source_type=m.group(3),
            timestamp=m.group(4),
        )


@dataclass
class SkillEntry:
    """Metadata about a skill in the index."""
    name: str
    summary: str               # One-line description
    path: str                  # Relative path to the skill file
    tags: List[str] = field(default_factory=list)
    success_count: int = 0     # Times this skill was used successfully
    failure_count: int = 0     # Times this skill was used and resulted in failure
    status: str = "active"     # active, suspect, deprecated

    def to_index_line(self) -> str:
        tags_str = ", ".join(self.tags) if self.tags else ""
        return f"- **{self.name}**: {self.summary} (tags: {tags_str}, successes: {self.success_count})"


class MemorySkillManager:
    """Manages persistent memory and skill files on disk."""

    def __init__(self, config: Config):
        self.config = config
        self.memory_dir = config.paths.memory_dir
        self.skills_dir = config.paths.skills_dir
        self.handoffs_dir = config.paths.handoffs_dir

    # ── Memory operations ────────────────────────────────────────────

    def append_to_memory(
        self,
        filename: str,
        content: str,
        confidence: Confidence = Confidence.OBSERVED,
        session_id: int = 0,
        source_type: str = "agent",
        check_duplicate: bool = True,
    ) -> Tuple[bool, str]:
        """Append an entry to a memory markdown file.

        Returns (written, reason). If check_duplicate is True, first checks if a
        similar entry already exists and skips writing if so.
        """
        filepath = os.path.join(self.memory_dir, filename)

        if check_duplicate and os.path.exists(filepath):
            if self._has_similar_entry(filepath, content):
                return (False, "Duplicate entry detected — skipping append")

        entry = MemoryEntry(
            content=content,
            confidence=confidence,
            session_id=session_id,
            source_type=source_type,
        )

        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(entry.to_markdown())

        return (True, f"Appended to {filename}")

    def append_correction(
        self,
        filename: str,
        original_summary: str,
        correction: str,
        session_id: int = 0,
    ) -> bool:
        """Append a correction entry for a previously incorrect record.

        This follows the append-only principle: never delete old records,
        instead append a correction entry that explicitly references and
        supersedes the original.
        """
        content = (
            f"[Correction] Corrects previous record: {original_summary}\n"
            f"Correction: {correction}\n"
            f"Reason: subsequent verification found the original record was inaccurate. "
            f"This entry supersedes the original."
        )
        _, msg = self.append_to_memory(
            filename, content,
            confidence=Confidence.CORRECTED,
            session_id=session_id,
            source_type="maintenance",
            check_duplicate=False,
        )
        return True

    def read_memory_tail(self, filename: str, lines: int = 50) -> str:
        """Read the last N lines of a memory file."""
        filepath = os.path.join(self.memory_dir, filename)
        if not os.path.exists(filepath):
            return f"(File {filename} does not exist)"
        with open(filepath, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
        return "".join(all_lines[-lines:])

    def read_memory_full(self, filename: str) -> str:
        """Read the entire memory file."""
        filepath = os.path.join(self.memory_dir, filename)
        if not os.path.exists(filepath):
            return f"(File {filename} does not exist)"
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()

    def _has_similar_entry(self, filepath: str, new_content: str) -> bool:
        """Check if a memory file already contains a similar entry.

        Uses a simple hash-based similarity check — not perfect but cheap.
        """
        norm_new = " ".join(new_content.lower().split())[:200]
        new_hash = hashlib.md5(norm_new.encode()).hexdigest()

        if not os.path.exists(filepath):
            return False

        with open(filepath, "r", encoding="utf-8") as f:
            existing = f.read()

        # Check for near-duplicate entries by hashing sliding windows
        if len(existing) > 200:
            for i in range(0, len(existing) - 200, 100):
                window = " ".join(existing[i:i+200].lower().split())
                if hashlib.md5(window.encode()).hexdigest() == new_hash:
                    return True

        return False

    def get_entries_by_confidence(self, filename: str, confidence: Confidence) -> List[str]:
        """Get all entries with a specific confidence label."""
        filepath = os.path.join(self.memory_dir, filename)
        if not os.path.exists(filepath):
            return []
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        # Find entries with matching confidence tag
        entries = []
        pattern = rf'<!-- entry.*?confidence={confidence.value}.*?-->\s*\n(.*?)\n'
        for m in re.finditer(pattern, content, re.DOTALL):
            entries.append(m.group(1).strip())
        return entries

    # ── Skill operations ─────────────────────────────────────────────

    def rebuild_index(self) -> int:
        """Scan .agent/skills/ for SKILL.md files and rebuild INDEX.md.

        This is the bridge between the model (which creates SKILL.md files
        using the write tool) and the skill index (which bootstrap reads).
        Called by the orchestrator after each session.

        Returns the number of skills found.
        """
        if not os.path.isdir(self.skills_dir):
            return 0

        skills = []
        for entry in sorted(os.listdir(self.skills_dir)):
            skill_dir = os.path.join(self.skills_dir, entry)
            if not os.path.isdir(skill_dir):
                continue
            skill_file = os.path.join(skill_dir, "SKILL.md")
            if not os.path.exists(skill_file):
                continue

            # Parse skill metadata from the file
            name = entry
            summary = ""
            tags = []
            try:
                with open(skill_file, "r", encoding="utf-8") as f:
                    content = f.read()
                # Extract title (first # heading)
                import re as _re
                m = _re.match(r'^#\s+(.+)', content)
                if m:
                    name = m.group(1).strip()
                # Extract summary
                m = _re.search(r'\*\*Summary\*\*:\s*(.+)', content)
                if m:
                    summary = m.group(1).strip()
                # Extract tags
                m = _re.search(r'\*\*Tags\*\*:\s*(.+)', content)
                if m:
                    tags = [t.strip() for t in m.group(1).split(',') if t.strip()]
            except Exception:
                pass

            # Preserve existing success/failure counts if skill already indexed
            old_index = self.load_skill_index()
            old_entry = next((s for s in old_index if s.name == name), None)

            skills.append(SkillEntry(
                name=name,
                summary=summary,
                path=f".agent/skills/{entry}/SKILL.md",
                tags=tags,
                success_count=old_entry.success_count if old_entry else 0,
                failure_count=old_entry.failure_count if old_entry else 0,
                status=old_entry.status if old_entry else "active",
            ))

        self.save_skill_index(skills)
        return len(skills)

    def load_skill_index(self) -> List[SkillEntry]:
        """Load the skill index."""
        index_path = os.path.join(self.skills_dir, "INDEX.md")
        if not os.path.exists(index_path):
            return []
        skills = []
        with open(index_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("- **"):
                    # Parse: - **name**: summary (tags: ..., successes: N)
                    m = re.match(r'- \*\*(.+?)\*\*: (.+?) \(tags: (.+?), successes: (\d+)\)', line)
                    if m:
                        skills.append(SkillEntry(
                            name=m.group(1),
                            summary=m.group(2),
                            tags=[t.strip() for t in m.group(3).split(",") if t.strip()],
                            success_count=int(m.group(4)),
                        ))
        return skills

    def save_skill_index(self, skills: List[SkillEntry]):
        """Write the skill index."""
        index_path = os.path.join(self.skills_dir, "INDEX.md")
        os.makedirs(os.path.dirname(index_path), exist_ok=True)
        lines = [
            "# Skill Index\n",
            "List of all accumulated reusable skills. Each session reads only this index "
            "at startup; full skill files are loaded on demand when needed.\n",
            "| Name | Summary | Tags | Successes | Status |",
            "|------|---------|------|-----------|--------|",
        ]
        for s in skills:
            lines.append(f"| **{s.name}** | {s.summary} | {', '.join(s.tags)} | {s.success_count} | {s.status} |")
        with open(index_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def read_skill(self, skill_name: str) -> Optional[str]:
        """Read the full content of a specific skill."""
        # Search for skill file
        for entry in os.listdir(self.skills_dir):
            skill_dir = os.path.join(self.skills_dir, entry)
            if os.path.isdir(skill_dir):
                skill_file = os.path.join(skill_dir, "SKILL.md")
                if os.path.exists(skill_file):
                    # Check the index to match name
                    index = self.load_skill_index()
                    for s in index:
                        if s.name == skill_name and os.path.exists(os.path.join(self.config.project_root, s.path)):
                            with open(os.path.join(self.config.project_root, s.path), "r", encoding="utf-8") as f:
                                return f.read()
        return None

    def create_skill(
        self,
        name: str,
        summary: str,
        content: str,
        tags: List[str],
    ) -> bool:
        """Create a new skill file and update the index."""
        # Create skill directory
        safe_name = re.sub(r'[^\w\-.]', '-', name.lower())
        skill_dir = os.path.join(self.skills_dir, safe_name)
        os.makedirs(skill_dir, exist_ok=True)

        # Write skill content
        skill_file = os.path.join(skill_dir, "SKILL.md")
        if os.path.exists(skill_file):
            return False  # Already exists

        full_content = (
            f"# {name}\n\n"
            f"**Summary**: {summary}\n\n"
            f"**Tags**: {', '.join(tags)}\n\n"
            f"---\n\n"
            f"{content}\n"
        )
        with open(skill_file, "w", encoding="utf-8") as f:
            f.write(full_content)

        # Update index
        skills = self.load_skill_index()
        skills.append(SkillEntry(
            name=name,
            summary=summary,
            path=f".agent/skills/{safe_name}/SKILL.md",
            tags=tags,
            success_count=0,
        ))
        self.save_skill_index(skills)
        return True

    def record_skill_usage(self, name: str, was_successful: bool):
        """Update success/failure counts for a skill."""
        skills = self.load_skill_index()
        for s in skills:
            if s.name == name:
                if was_successful:
                    s.success_count += 1
                else:
                    s.failure_count += 1
                    if s.failure_count >= 2 and s.success_count == 0:
                        s.status = "suspect"
                break
        self.save_skill_index(skills)

    # ── Maintenance ──────────────────────────────────────────────────

    def run_maintenance(self, session_id: int) -> Dict[str, Any]:
        """Run periodic maintenance on memory and skill files.

        Operations:
        - Deduplicate facts.md entries
        - Merge similar skills
        - Mark deprecated entries
        - Report statistics
        """
        stats = {"dedup_count": 0, "skills_merged": 0, "deprecated": 0}

        # Deduplicate facts.md
        facts_path = os.path.join(self.memory_dir, "facts.md")
        if os.path.exists(facts_path):
            deduped = self._deduplicate_file(facts_path)
            stats["dedup_count"] = deduped

        # Check for suspect skills
        skills = self.load_skill_index()
        for s in skills:
            if s.status == "suspect" and s.failure_count >= 3 and s.success_count == 0:
                s.status = "deprecated"
                stats["deprecated"] += 1
        self.save_skill_index(skills)

        # Append maintenance summary to progress
        self.append_to_memory(
            "progress.md",
            f"[Maintenance Session {session_id}]: deduplicated {stats['dedup_count']} records, "
            f"deprecated {stats['deprecated']} skills.",
            confidence=Confidence.VERIFIED,
            session_id=session_id,
            source_type="maintenance",
            check_duplicate=False,
        )

        return stats

    def _deduplicate_file(self, filepath: str) -> int:
        """Remove duplicate entries from a memory file. Returns count removed."""
        if not os.path.exists(filepath):
            return 0

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        # Split by entry markers
        entries = re.split(r'(<!-- entry .*? -->)', content)
        seen = set()
        unique_parts = []
        removed = 0

        for i, part in enumerate(entries):
            if re.match(r'<!-- entry .*?-->', part):
                # Normalize and check duplicate
                norm = " ".join(part.split())
                if norm in seen:
                    # Mark as deduplicated
                    entries[i] = part.replace("-->", "deduplicated=true -->[deduplicated]")
                    removed += 1
                else:
                    seen.add(norm)
            unique_parts.append(part)

        if removed > 0:
            backup = filepath + f".before_dedup_{int(time.time())}"
            os.rename(filepath, backup)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("".join(unique_parts))

        return removed

    # ── Initialization ───────────────────────────────────────────────

    def initialize_task_memory(self, task_id: str, task_state_json: str):
        """Initialize memory files for a new task."""
        os.makedirs(self.memory_dir, exist_ok=True)
        os.makedirs(self.handoffs_dir, exist_ok=True)
        os.makedirs(self.skills_dir, exist_ok=True)

        # Write task_state.json
        state_path = os.path.join(self.memory_dir, "task_state.json")
        with open(state_path, "w", encoding="utf-8") as f:
            f.write(task_state_json)

        # Initialize empty memory files with headers
        for filename, header in [
            ("progress.md", "# Progress Log\n\n<!-- Records completion status of each session. Append-only. -->\n"),
            ("decisions.md", "# Architecture Decisions & Constraints\n\n<!-- Records confirmed architecture decisions and environment constraints. Append-only. -->\n"),
            ("facts.md", "# Confirmed Facts\n\n<!-- Records verified facts and discoveries. Append-only. -->\n"),
        ]:
            filepath = os.path.join(self.memory_dir, filename)
            if not os.path.exists(filepath):
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(header)

        # Initialize skill index if not exists
        index_path = os.path.join(self.skills_dir, "INDEX.md")
        if not os.path.exists(index_path):
            with open(index_path, "w", encoding="utf-8") as f:
                f.write("# Skill Index\n\nNo skills accumulated yet. Verified reusable methods will be recorded here as the project progresses.\n")
