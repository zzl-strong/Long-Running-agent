"""Tool implementations: bash, read, write — with safety boundaries.

All tools operate within allowed paths (workspace/ and .agent/) and enforce
output truncation, timeout, and append-only rules for memory files.
"""
import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .config import Config


@dataclass
class ToolResult:
    """Unified result from tool execution."""
    tool_name: str
    success: bool
    error: Optional[str] = None
    # bash-specific
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    truncated: bool = False
    # read/write
    content: str = ""
    lines_read: Optional[int] = None
    path: str = ""

    def to_message(self) -> str:
        """Format as a message string for the LLM."""
        if self.tool_name == "bash":
            parts = [f"[exit_code: {self.exit_code}]"]
            if self.stdout:
                if self.truncated:
                    parts.append(f"[stdout (truncated):\n{self.stdout}\n...]")
                else:
                    parts.append(f"[stdout:\n{self.stdout}]")
            if self.stderr:
                parts.append(f"[stderr:\n{self.stderr}]")
            if not self.stdout and not self.stderr:
                parts.append("[no output]")
            return "\n".join(parts)
        elif self.tool_name == "read":
            if self.error:
                return f"[read error: {self.error}]"
            if self.lines_read:
                return f"[read {self.lines_read} lines from {self.path}]\n{self.content}"
            return f"[read from {self.path}]\n{self.content}"
        elif self.tool_name == "write":
            if self.error:
                return f"[write error: {self.error}]"
            return f"[wrote to {self.path}]"
        elif self.tool_name == "edit":
            if self.error:
                return f"[edit error: {self.error}]"
            return f"[edited {self.path}]\n{self.content}"
        return str(self)

    def estimate_tokens(self) -> int:
        """Rough token count estimate for this result (char/4)."""
        text = self.to_message()
        return len(text) // 4


class ToolExecutor:
    """Execute tool calls with safety constraints."""

    def __init__(self, config: Config):
        self.config = config
        self.allowed_paths = config.safety.allowed_paths
        self.workspace = config.paths.workspace
        self.memory_dir = config.paths.memory_dir

    def run(self, tool_name: str, arguments: Dict[str, Any]) -> ToolResult:
        """Dispatch tool execution."""
        if tool_name == "bash":
            return self._bash(
                arguments.get("command", ""),
                arguments.get("timeout_sec", self.config.safety.bash_timeout_sec),
            )
        elif tool_name == "read":
            return self._read(
                arguments.get("path", ""),
                arguments.get("start_line"),
                arguments.get("end_line"),
            )
        elif tool_name == "write":
            return self._write(
                arguments.get("path", ""),
                arguments.get("content", ""),
                arguments.get("mode", "overwrite"),
            )
        elif tool_name == "edit":
            return self._edit(
                arguments.get("path", ""),
                arguments.get("old_string", ""),
                arguments.get("new_string", ""),
                arguments.get("replace_all", False),
            )
        else:
            return ToolResult(tool_name=tool_name, success=False, error=f"Unknown tool: {tool_name}")

    def _resolve_path(self, path: str) -> str:
        """Resolve and validate a path is within allowed directories.

        In container mode (runtime_container set), also accepts /workspace/...
        paths by mapping them to the project_root automatically.
        """
        if not path:
            raise ValueError("Empty path")

        runtime_container = getattr(self.config.docker, 'runtime_container', '')

        # In container mode: map /workspace/... → project_root/... for validation
        if runtime_container and (path.startswith("/workspace/") or path == "/workspace"):
            suffix = path[10:] if path.startswith("/workspace/") else ""
            path = self.config.project_root + suffix
            # Now path is /home/.../bench-decouple[/...], proceed to resolve

        # Allow ./ prefixed paths
        if path.startswith("./"):
            path = os.path.join(self.config.project_root, path[2:])
        elif not os.path.isabs(path):
            path = os.path.join(self.config.project_root, path)

        path = os.path.normpath(os.path.abspath(path))

        # Check path is within allowed directories
        allowed = False
        for allowed_dir in self.allowed_paths:
            allowed_abs = os.path.normpath(os.path.abspath(allowed_dir))
            if path.startswith(allowed_abs + os.sep) or path == allowed_abs:
                allowed = True
                break
        if not allowed:
            # Show relative paths in error to avoid leaking host absolute paths
            try:
                rel_path = os.path.relpath(path, self.config.project_root)
                rel_allowed = [os.path.relpath(a, self.config.project_root) for a in self.allowed_paths]
            except ValueError:
                rel_path = path
                rel_allowed = self.allowed_paths
            raise PermissionError(
                f"Path '{rel_path}' is outside allowed directories: {rel_allowed}. "
                f"Use paths under workspace/ or .agent/ only."
            )
        return path

    def _to_container_path(self, host_path: str) -> str:
        """Convert a host absolute path to a container path (/workspace/...)."""
        prefix = self.config.project_root.rstrip("/")
        if host_path.startswith(prefix + os.sep) or host_path == prefix:
            return "/workspace" + host_path[len(prefix):]
        # Fallback: should not happen if path passed _resolve_path
        return host_path

    def _container_run(self, cmd: str, stdin_content: Optional[str] = None,
                       timeout_sec: int = 120) -> tuple:
        """Run a shell command inside the runtime container, return (exit_code, stdout, stderr)."""
        container = self.config.docker.runtime_container
        escaped_cmd = cmd.replace("'", "'\"'\"'")
        full_cmd = f"docker exec -i -w /workspace {container} sh -c '{escaped_cmd}'"
        try:
            proc = subprocess.run(
                full_cmd, shell=True, input=stdin_content,
                capture_output=True, text=True, timeout=timeout_sec,
            )
            return proc.returncode, (proc.stdout or ""), (proc.stderr or "")
        except subprocess.TimeoutExpired:
            return -1, "", f"Timeout after {timeout_sec}s"
        except Exception as e:
            return -1, "", str(e)

    def _ensure_container_running(self) -> bool:
        """Check the runtime container is running; try to start it if stopped."""
        container = self.config.docker.runtime_container
        if not container:
            return False
        # Check if running
        r1 = subprocess.run(
            f"docker ps --format '{{{{.Names}}}}' | grep -q '^{container}$'",
            shell=True, capture_output=True,
        )
        if r1.returncode == 0:
            return True
        # Try to start it
        subprocess.run(f"docker start {container} 2>/dev/null", shell=True)
        # Re-check
        r2 = subprocess.run(
            f"docker ps --format '{{{{.Names}}}}' | grep -q '^{container}$'",
            shell=True, capture_output=True,
        )
        return r2.returncode == 0

    def _bash(self, command: str, timeout_sec: int) -> ToolResult:
        """Execute a shell command inside the workspace."""
        if not command or not command.strip():
            return ToolResult(
                tool_name="bash", success=False, error="Empty command",
                exit_code=1
            )

        # Security: reject commands that try to cd out of workspace
        if ".." in command and ("cd" in command):
            return ToolResult(
                tool_name="bash", success=False, exit_code=1,
                error="Security: changing directory outside workspace is not allowed",
                stderr="cd with '..' is not allowed"
            )

        # Determine execution target: local or Docker container
        runtime_container = getattr(self.config.docker, 'runtime_container', '')
        if runtime_container:
            # Run inside Docker container; workspace is mounted at /workspace
            escaped = command.replace("'", "'\"'\"'")
            full_command = f"docker exec -w /workspace {runtime_container} sh -c '{escaped}'"
            cwd = None  # docker exec handles working directory
        else:
            full_command = command
            cwd = self.workspace

        try:
            proc = subprocess.run(
                full_command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                env={**os.environ, "DEBIAN_FRONTEND": "noninteractive"},
            )

            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            truncated = False

            max_stdout = self.config.safety.max_stdout_chars
            max_stderr = self.config.safety.max_stderr_chars

            if len(stdout) > max_stdout:
                stdout = stdout[:max_stdout]
                truncated = True
            if len(stderr) > max_stderr:
                stderr = stderr[:max_stderr]
                truncated = True

            return ToolResult(
                tool_name="bash",
                success=proc.returncode == 0,
                exit_code=proc.returncode,
                stdout=stdout,
                stderr=stderr,
                truncated=truncated,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                tool_name="bash",
                success=False,
                exit_code=-1,
                error=f"Command timed out after {timeout_sec}s",
                stderr=f"Timeout after {timeout_sec} seconds",
            )
        except Exception as e:
            return ToolResult(
                tool_name="bash",
                success=False,
                exit_code=-1,
                error=str(e),
                stderr=str(e),
            )

    def _read(self, path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> ToolResult:
        """Read a file, optionally with line range."""
        try:
            resolved = self._resolve_path(path)
        except (ValueError, PermissionError) as e:
            return ToolResult(tool_name="read", success=False, error=str(e), path=path)

        runtime_container = getattr(self.config.docker, 'runtime_container', '')

        if runtime_container:
            if not self._ensure_container_running():
                return ToolResult(
                    tool_name="read", success=False, path=path,
                    error=f"Runtime container '{runtime_container}' is not running or could not be started"
                )
            container_path = self._to_container_path(resolved)

            # Check file exists in container
            rc, _, _ = self._container_run(f"test -f '{container_path}'")
            if rc != 0:
                rc2, _, _ = self._container_run(f"test -d '{container_path}'")
                if rc2 == 0:
                    return ToolResult(
                        tool_name="read", success=False, path=path,
                        error=f"Not a file: {path}"
                    )
                return ToolResult(
                    tool_name="read", success=False, path=path,
                    error=f"File not found: {path}"
                )

            try:
                if start_line is not None or end_line is not None:
                    sl = start_line or 1
                    el = end_line if end_line is not None else ""
                    sed_range = f"{sl},{el}p" if end_line is not None else f"{sl},\\$p"
                    rc, content, stderr = self._container_run(
                        f"sed -n '{sed_range}' '{container_path}'"
                    )
                    lines_read = len(content.splitlines())
                else:
                    rc, content, stderr = self._container_run(
                        f"cat '{container_path}'"
                    )
                    lines_read = content.count("\n")
                    if content and not content.endswith("\n"):
                        lines_read += 1

                if rc != 0:
                    return ToolResult(
                        tool_name="read", success=False, path=path,
                        error=stderr or "Failed to read file"
                    )

                max_chars = self.config.safety.max_read_chars
                truncated = False
                if len(content) > max_chars:
                    content = content[:max_chars] + "\n... [truncated, use start_line/end_line to read specific sections]"
                    truncated = True
                    if lines_read:
                        lines_read = len(content.splitlines())

                return ToolResult(
                    tool_name="read",
                    success=True,
                    path=path,
                    content=content,
                    lines_read=lines_read,
                )
            except Exception as e:
                return ToolResult(
                    tool_name="read", success=False, path=path, error=str(e)
                )
        else:
            # Local: use host filesystem
            if not os.path.exists(resolved):
                return ToolResult(
                    tool_name="read", success=False, path=path,
                    error=f"File not found: {path}"
                )
            if not os.path.isfile(resolved):
                return ToolResult(
                    tool_name="read", success=False, path=path,
                    error=f"Not a file: {path}"
                )

            try:
                with open(resolved, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()

                if start_line is not None or end_line is not None:
                    sl = (start_line or 1) - 1
                    el = end_line if end_line is not None else len(lines)
                    sl = max(0, sl)
                    el = min(len(lines), el)
                    selected = lines[sl:el]
                    content = "".join(selected)
                    lines_read = len(selected)
                else:
                    content = "".join(lines)
                    lines_read = len(lines)

                max_chars = self.config.safety.max_read_chars
                if len(content) > max_chars:
                    content = content[:max_chars] + "\n... [truncated, use start_line/end_line to read specific sections]"
                    if lines_read:
                        lines_read = len(content.splitlines())

                return ToolResult(
                    tool_name="read",
                    success=True,
                    path=path,
                    content=content,
                    lines_read=lines_read,
                )
            except Exception as e:
                return ToolResult(
                    tool_name="read", success=False, path=path, error=str(e)
                )

    def _write(self, path: str, content: str, mode: str) -> ToolResult:
        """Write or append to a file."""
        try:
            resolved = self._resolve_path(path)
        except (ValueError, PermissionError) as e:
            return ToolResult(tool_name="write", success=False, error=str(e), path=path)

        # Watchdog rule: .agent/memory/*.md files are append-only
        if resolved.startswith(os.path.normpath(os.path.abspath(self.memory_dir))):
            if resolved.endswith(".md") and mode != "append":
                return ToolResult(
                    tool_name="write",
                    success=False,
                    path=path,
                    error=f"Memory markdown files ({path}) are append-only. Use mode='append' to add content. "
                          "To correct errors, append a correction entry — never overwrite history."
                )
            # task_state.json is special — allow overwrite but we validate structure elsewhere
            if resolved.endswith("task_state.json") and mode != "overwrite":
                pass  # allow overwrite for structured state

        is_append = (mode == "append")

        runtime_container = getattr(self.config.docker, 'runtime_container', '')

        if runtime_container:
            if not self._ensure_container_running():
                return ToolResult(
                    tool_name="write", success=False, path=path,
                    error=f"Runtime container '{runtime_container}' is not running or could not be started"
                )
            container_path = self._to_container_path(resolved)

            try:
                # Ensure parent directory exists
                parent_dir = os.path.dirname(container_path)
                rc, _, stderr = self._container_run(f"mkdir -p '{parent_dir}'")
                if rc != 0:
                    return ToolResult(
                        tool_name="write", success=False, path=path,
                        error=f"Failed to create directory: {stderr}"
                    )

                # For append mode, ensure trailing newline for clean separation
                write_content = content
                if is_append and write_content and not write_content.startswith("\n"):
                    write_content = "\n" + write_content

                # Write content via stdin pipe into container
                if is_append:
                    rc, _, stderr = self._container_run(
                        f"cat >> '{container_path}'", stdin_content=write_content
                    )
                else:
                    rc, _, stderr = self._container_run(
                        f"cat > '{container_path}'", stdin_content=write_content
                    )

                if rc != 0:
                    return ToolResult(
                        tool_name="write", success=False, path=path,
                        error=f"Failed to write: {stderr}"
                    )

                return ToolResult(
                    tool_name="write",
                    success=True,
                    path=path,
                    content=f"{'Appended' if is_append else 'Wrote'} to {path} ({len(content)} chars)",
                )
            except Exception as e:
                return ToolResult(
                    tool_name="write", success=False, path=path, error=str(e)
                )
        else:
            # Local: use host filesystem
            try:
                os.makedirs(os.path.dirname(resolved), exist_ok=True)

                if is_append and os.path.exists(resolved):
                    write_mode = "a"
                else:
                    write_mode = "w"

                # For append mode, ensure trailing newline for clean separation
                if write_mode == "a" and content and not content.startswith("\n"):
                    content = "\n" + content

                with open(resolved, write_mode, encoding="utf-8") as f:
                    f.write(content)

                return ToolResult(
                    tool_name="write",
                    success=True,
                    path=path,
                    content=f"{'Appended' if write_mode == 'a' else 'Wrote'} to {path} ({len(content)} chars)",
                )
            except Exception as e:
                return ToolResult(
                    tool_name="write", success=False, path=path, error=str(e)
                )

    def _edit(self, path: str, old_string: str, new_string: str, replace_all: bool = False) -> ToolResult:
        """Replace old_string with new_string in a file (exact match)."""
        try:
            resolved = self._resolve_path(path)
        except (ValueError, PermissionError) as e:
            return ToolResult(tool_name="edit", success=False, error=str(e), path=path)

        if not old_string:
            return ToolResult(tool_name="edit", success=False, path=path,
                            error="old_string must not be empty")

        runtime_container = getattr(self.config.docker, 'runtime_container', '')

        if runtime_container:
            if not self._ensure_container_running():
                return ToolResult(
                    tool_name="edit", success=False, path=path,
                    error=f"Runtime container '{runtime_container}' is not running or could not be started"
                )
            container_path = self._to_container_path(resolved)

            # Check file exists
            rc, _, _ = self._container_run(f"test -f '{container_path}'")
            if rc != 0:
                return ToolResult(tool_name="edit", success=False, path=path,
                                error=f"File not found: {path}")

            # Read content from container
            try:
                rc, content, stderr = self._container_run(f"cat '{container_path}'")
                if rc != 0:
                    return ToolResult(tool_name="edit", success=False, path=path,
                                    error=f"Failed to read: {stderr}")
            except Exception as e:
                return ToolResult(tool_name="edit", success=False, path=path, error=str(e))

            # Edit in Python (same logic as local path)
            if old_string not in content:
                return ToolResult(
                    tool_name="edit", success=False, path=path,
                    error=f"old_string not found in {path}. "
                          f"Ensure the string matches exactly, including whitespace and indentation."
                )

            count = content.count(old_string)
            if count > 1 and not replace_all:
                return ToolResult(
                    tool_name="edit", success=False, path=path,
                    error=f"old_string appears {count} times in {path}. "
                          f"Use replace_all=true to replace all occurrences, "
                          f"or make old_string more specific to match only the target location."
                )

            if replace_all:
                new_content = content.replace(old_string, new_string)
            else:
                new_content = content.replace(old_string, new_string, 1)

            if new_content == content:
                return ToolResult(
                    tool_name="edit", success=False, path=path,
                    error=f"Edit resulted in no change. old_string == new_string."
                )

            # Write back to container
            try:
                rc, _, stderr = self._container_run(
                    f"cat > '{container_path}'", stdin_content=new_content
                )
                if rc != 0:
                    return ToolResult(tool_name="edit", success=False, path=path,
                                    error=f"Failed to write: {stderr}")
            except Exception as e:
                return ToolResult(tool_name="edit", success=False, path=path, error=str(e))

            replaced_count = count if replace_all else 1
            return ToolResult(
                tool_name="edit",
                success=True,
                path=path,
                content=f"Replaced {replaced_count} occurrence(s) in {path} "
                        f"({len(old_string)} → {len(new_string)} chars)",
            )
        else:
            # Local: use host filesystem
            if not os.path.exists(resolved):
                return ToolResult(tool_name="edit", success=False, path=path,
                                error=f"File not found: {path}")
            if not os.path.isfile(resolved):
                return ToolResult(tool_name="edit", success=False, path=path,
                                error=f"Not a file: {path}")

            if not old_string:
                return ToolResult(tool_name="edit", success=False, path=path,
                                error="old_string must not be empty")

            try:
                with open(resolved, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                return ToolResult(tool_name="edit", success=False, path=path, error=str(e))

            if old_string not in content:
                return ToolResult(
                    tool_name="edit", success=False, path=path,
                    error=f"old_string not found in {path}. "
                          f"Ensure the string matches exactly, including whitespace and indentation."
                )

            count = content.count(old_string)
            if count > 1 and not replace_all:
                return ToolResult(
                    tool_name="edit", success=False, path=path,
                    error=f"old_string appears {count} times in {path}. "
                          f"Use replace_all=true to replace all occurrences, "
                          f"or make old_string more specific to match only the target location."
                )

            if replace_all:
                new_content = content.replace(old_string, new_string)
            else:
                new_content = content.replace(old_string, new_string, 1)

            if new_content == content:
                return ToolResult(
                    tool_name="edit", success=False, path=path,
                    error=f"Edit resulted in no change. old_string == new_string."
                )

            try:
                with open(resolved, "w", encoding="utf-8") as f:
                    f.write(new_content)
            except Exception as e:
                return ToolResult(tool_name="edit", success=False, path=path, error=str(e))

            replaced_count = count if replace_all else 1
            return ToolResult(
                tool_name="edit",
                success=True,
                path=path,
                content=f"Replaced {replaced_count} occurrence(s) in {path} "
                        f"({len(old_string)} → {len(new_string)} chars)",
            )
