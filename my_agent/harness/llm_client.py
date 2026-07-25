"""LLM API client wrapper for DeepSeek (OpenAI-compatible protocol)."""
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from openai import OpenAI

from .config import Config, get_api_key


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: Dict[str, Any]

@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

@dataclass
class NormalizedResponse:
    """Unified response format across LLM providers."""
    content: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"  # end_turn, tool_use, max_tokens, stop_sequence
    usage: Usage = field(default_factory=Usage)
    raw: Any = None

    @property
    def total_tokens(self) -> int:
        return self.usage.input_tokens + self.usage.output_tokens

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


# OpenAI function-calling tool schemas
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Execute a shell command inside the workspace directory. "
                           "Use for running tests, building code, installing packages, "
                           "git operations, or any other CLI task. "
                           "Returns exit_code, stdout, stderr, and a truncated flag. "
                           "If output is truncated, re-run with more specific commands (e.g., "
                           "use head/tail/grep to narrow down).",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute. It runs inside the workspace directory."
                    },
                    "timeout_sec": {
                        "type": "integer",
                        "description": "Optional timeout in seconds (default 120).",
                        "default": 120
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read",
            "description": "Read file content. Supports reading specific line ranges. "
                           "Use this to examine files in workspace/ or .agent/. "
                           "For large files, always use start_line/end_line to read only "
                           "the relevant sections instead of reading the whole file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to read, relative to project root."
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "Optional: first line to read (1-indexed, inclusive)."
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "Optional: last line to read (1-indexed, inclusive)."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write",
            "description": "Write or append content to a file. "
                           "Use mode='overwrite' to create or replace a file. "
                           "Use mode='append' to add content at the end of an existing file. "
                           "IMPORTANT: .agent/memory/*.md files are append-only — use mode='append' for those.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to write, relative to project root."
                    },
                    "content": {
                        "type": "string",
                        "description": "The content to write or append."
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["overwrite", "append"],
                        "description": "Write mode: 'overwrite' replaces the file, 'append' adds to the end."
                    }
                },
                "required": ["path", "content", "mode"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit",
            "description": "Replace a specific string in a file with another string (exact match). "
                           "Use this for surgical edits — changing a few lines without reading/writing the entire file. "
                           "old_string must match exactly, including whitespace and indentation. "
                           "If old_string is not unique in the file, the call fails — use replace_all=true "
                           "or make old_string more specific (include surrounding context lines).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to edit, relative to project root."
                    },
                    "old_string": {
                        "type": "string",
                        "description": "The exact text to find and replace. Must match character-for-character "
                                       "including whitespace, indentation, and blank lines."
                    },
                    "new_string": {
                        "type": "string",
                        "description": "The text to replace old_string with."
                    },
                    "replace_all": {
                        "type": "boolean",
                        "description": "If true, replace ALL occurrences of old_string. "
                                       "If false (default), fail if old_string appears more than once.",
                        "default": False
                    }
                },
                "required": ["path", "old_string", "new_string"]
            }
        }
    }
]


class LLMClient:
    """Thin wrapper around OpenAI-compatible chat completions API.

    Supports DeepSeek V4 features: thinking_mode, configurable model per instance.
    Pass an optional llm_config to override model/temperature/thinking_mode for
    Planner and Verifier instances.
    """

    def __init__(self, config: Config, llm_config: Optional["LLMConfig"] = None):
        api_key = get_api_key(config)
        if not api_key:
            raise ValueError(
                f"API key not found. Set {config.llm.api_key_env} environment variable "
                f"or create a .env file with {config.llm.api_key_env}=<your-key>"
            )
        self.config = config
        self.llm_config = llm_config or config.llm
        self.client = OpenAI(api_key=api_key, base_url=self.llm_config.base_url)
        self.model = self.llm_config.model

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> NormalizedResponse:
        """Send a chat completion request and return a normalized response."""
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.llm_config.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.llm_config.max_tokens_per_response,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        # DeepSeek V4 thinking_mode: pass via extra_body
        thinking_mode = getattr(self.llm_config, 'thinking_mode', None)
        if thinking_mode and thinking_mode != "non-thinking":
            kwargs["extra_body"] = {"thinking_mode": thinking_mode}

        # Retry on transient errors
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(**kwargs)
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                time.sleep(2 ** attempt)

        return self._normalize(response)

    def _normalize(self, response: Any) -> NormalizedResponse:
        """Convert OpenAI API response to NormalizedResponse."""
        choice = response.choices[0]
        message = choice.message

        # Extract content
        content = message.content or ""

        # Extract tool calls
        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    args = {}
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args,
                ))

        # Determine stop reason
        finish_reason = choice.finish_reason
        if finish_reason == "tool_calls":
            stop_reason = "tool_use"
        elif finish_reason == "stop":
            stop_reason = "end_turn"
        elif finish_reason == "length":
            stop_reason = "max_tokens"
        else:
            stop_reason = finish_reason or "end_turn"

        # Extract usage
        usage = Usage(
            input_tokens=response.usage.prompt_tokens if response.usage else 0,
            output_tokens=response.usage.completion_tokens if response.usage else 0,
        )

        return NormalizedResponse(
            content=content,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            usage=usage,
            raw=response,
        )
