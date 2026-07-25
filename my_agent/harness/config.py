"""Configuration loader for the Long-Running Coding Agent System.

Configuration hierarchy (later overrides earlier):
  1. Built-in defaults
  2. Harness config: my_agent/config.yaml (optional fallback)
  3. Project config: <project_root>/config.yaml
  4. Environment variables (DEEPSEEK_API_KEY etc.)
"""
import os
import yaml
from dataclasses import dataclass, field
from typing import List, Optional


_HARNESS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # my_agent/


@dataclass
class LLMConfig:
    model: str = "deepseek-v4-pro"
    api_key_env: str = "DEEPSEEK_API_KEY"
    base_url: str = "https://api.deepseek.com"
    max_tokens_per_response: int = 16384
    temperature: float = 0.6
    thinking_mode: str = "thinking"  # non-thinking | thinking | thinking_max

@dataclass
class SessionConfig:
    max_turns: int = 200
    max_tokens: int = 750000       # ~75% of 1M context (DeepSeek V4)
    context_window: int = 1000000  # DeepSeek V4: 1M tokens
    switch_ratio: float = 0.75

@dataclass
class ContextConfig:
    tool_result_clearing_rounds: int = 10
    tool_result_min_tokens: int = 500
    # Transcript truncation for LLM prompts (skill extraction, summaries)
    transcript_max_chars: int = 8000
    transcript_head_chars: int = 2000
    transcript_tail_chars: int = 6000
    handoff_files_max: int = 10
    work_queue_max_items: int = 5

@dataclass
class BudgetConfig:
    max_sessions: int = 40
    max_wall_clock_hours: float = 8.0

@dataclass
class VerificationConfig:
    enabled: bool = True          # global kill-switch: false → skip all verification, trust model
    tier2_enabled: bool = True
    tier2_sample_rate: float = 0.3
    max_retry_attempts: int = 3
    max_verifier_turns: int = 50
    tier1_timeout_sec: int = 180
    api_check_timeout_sec: int = 60
    tier1_output_max_chars: int = 2000
    replan_consecutive_failures: int = 5
    replan_max_count: int = 3
    skill_extraction_min_attempts: int = 3

@dataclass
class MaintenanceConfig:
    interval_sessions: int = 10

@dataclass
class PathsConfig:
    workspace: str = "./workspace"
    agent_dir: str = "./.agent"
    logs_dir: str = "./logs"
    memory_dir: str = "./.agent/memory"
    skills_dir: str = "./.agent/skills"
    handoffs_dir: str = "./.agent/memory/handoffs"

@dataclass
class DockerConfig:
    """Docker execution sandbox. When runtime_container is set, bash commands
    run inside the container instead of locally. Workspace is mounted at /workspace."""
    runtime_container: str = ""    # container name for bash execution (empty = local)
    test_image_prefix: str = ""    # e.g. "ghcr.nju.edu.cn/multimodal-art-projection/nl2repobench"

@dataclass
class SafetyConfig:
    allowed_paths: List[str] = field(default_factory=lambda: ["./workspace", "./.agent"])
    bash_timeout_sec: int = 120
    max_stdout_chars: int = 8000
    max_stderr_chars: int = 8000
    max_read_chars: int = 16000

@dataclass
class Config:
    llm: LLMConfig = field(default_factory=LLMConfig)
    planner: LLMConfig = field(default_factory=LLMConfig)     # optional: separate model for Planner
    verifier_model: LLMConfig = field(default_factory=LLMConfig)  # optional: separate model for Verifier
    session: SessionConfig = field(default_factory=SessionConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    budget: BudgetConfig = field(default_factory=BudgetConfig)
    verification: VerificationConfig = field(default_factory=VerificationConfig)
    maintenance: MaintenanceConfig = field(default_factory=MaintenanceConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    docker: DockerConfig = field(default_factory=DockerConfig)
    project_root: str = "."


def _apply_yaml_section(config: Config, raw: dict, section: str, dataclass_type, config_attr: str):
    """Apply a YAML section to config, only overwriting fields that exist in the dataclass."""
    if section in raw:
        fields = dataclass_type.__dataclass_fields__
        current = getattr(config, config_attr)
        for k, v in raw[section].items():
            if k in fields:
                setattr(current, k, v)


def _resolve_paths(config: Config):
    """Resolve relative paths against project_root."""
    for field_name in ["workspace", "agent_dir", "logs_dir", "memory_dir", "skills_dir", "handoffs_dir"]:
        raw_val = getattr(config.paths, field_name)
        if raw_val.startswith("./"):
            setattr(config.paths, field_name, os.path.join(config.project_root, raw_val[2:]))
        elif not os.path.isabs(raw_val):
            setattr(config.paths, field_name, os.path.join(config.project_root, raw_val))

    config.safety.allowed_paths = [
        os.path.join(config.project_root, p[2:]) if p.startswith("./") else
        (os.path.join(config.project_root, p) if not os.path.isabs(p) else p)
        for p in config.safety.allowed_paths
    ]

_SECTIONS = [
    ("llm", LLMConfig, "llm"),
    ("planner", LLMConfig, "planner"),
    ("verifier_model", LLMConfig, "verifier_model"),
    ("session", SessionConfig, "session"),
    ("context", ContextConfig, "context"),
    ("budget", BudgetConfig, "budget"),
    ("verification", VerificationConfig, "verification"),
    ("maintenance", MaintenanceConfig, "maintenance"),
    ("paths", PathsConfig, "paths"),
    ("safety", SafetyConfig, "safety"),
    ("docker", DockerConfig, "docker"),
]


def load_config(project_root: str = ".") -> Config:
    """Load configuration with proper precedence.

    Args:
        project_root: Path to the project directory. Defaults to cwd.

    Returns:
        Config with all paths resolved relative to project_root.
    """
    project_root = os.path.abspath(project_root)
    config = Config(project_root=project_root)

    # Layer 1: Harness config (my_agent/config.yaml) — optional fallback defaults
    harness_config = os.path.join(_HARNESS_DIR, "config.yaml")
    if os.path.exists(harness_config):
        with open(harness_config, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        for section, dtype, attr in _SECTIONS:
            _apply_yaml_section(config, raw, section, dtype, attr)

    # Layer 2: Project config (<project_root>/config.yaml) — overrides harness
    project_config_path = os.path.join(project_root, "config.yaml")
    if os.path.exists(project_config_path):
        with open(project_config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        for section, dtype, attr in _SECTIONS:
            _apply_yaml_section(config, raw, section, dtype, attr)

    # Resolve paths
    _resolve_paths(config)

    return config


def get_api_key(config: Config) -> str:
    """Get API key from environment variable or .env files.

    Search order: env var → project .env → harness .env
    """
    key = os.getenv(config.llm.api_key_env, "")
    if key:
        return key

    candidates = [
        os.path.join(config.project_root, ".env"),   # project dir
        os.path.join(_HARNESS_DIR, ".env"),          # harness dir (my_agent/)
    ]
    for env_file in candidates:
        if os.path.exists(env_file):
            with open(env_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith(f"{config.llm.api_key_env}="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""
