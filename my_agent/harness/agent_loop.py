"""Single-session agent loop: LLM-driven tool-calling cycle.

Each session runs within a budget (turns + tokens) and logs every step
to a JSONL transcript. The session ends when the model signals completion,
runs out of budget, or the orchestrator forces a stop.
"""
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .config import Config
from .context_manager import compress_messages, clear_stale_tool_results
from .llm_client import LLMClient, NormalizedResponse, TOOL_DEFINITIONS
from .tools import ToolExecutor, ToolResult


@dataclass
class SessionBudget:
    max_turns: int
    max_total_tokens: int
    turns_used: int = 0
    tokens_used: int = 0

    @property
    def exhausted(self) -> bool:
        return self.turns_used >= self.max_turns or self.tokens_used >= self.max_total_tokens

    @property
    def usage_ratio(self) -> float:
        if self.max_total_tokens <= 0:
            return 0.0
        return self.tokens_used / self.max_total_tokens


@dataclass
class IdleAction:
    """Decision returned by on_idle callback when the model stops mid-session."""
    should_continue: bool
    prompt: str = ""  # injection prompt to append as a user message


@dataclass
class SessionResult:
    """Result of a completed agent session."""
    session_id: int
    feature_ids: List[str] = field(default_factory=list)  # features touched this session
    transcript_path: str = ""
    turns: int = 0
    tokens_input: int = 0
    tokens_output: int = 0
    stop_reason: str = ""  # "budget_exhausted", "end_turn", "context_full", "idle_no_work"
    feature_status_after: str = ""  # high-level summary
    verification_result: Optional[Dict[str, Any]] = None
    # ── Timing metrics ──────────────────────────────────────────────
    start_time: float = 0.0      # epoch seconds when session began
    end_time: float = 0.0        # epoch seconds when session ended
    idle_injections: int = 0     # number of times on_idle injected a new feature


class AgentLoop:
    """Manages a single session of the coding agent loop."""

    def __init__(self, config: Config, client: LLMClient, tool_executor: ToolExecutor):
        self.config = config
        self.client = client
        self.tools = tool_executor

    def run_session(
        self,
        session_id: int,
        system_prompt: str,
        bootstrap_messages: List[Dict[str, Any]],
        budget: SessionBudget,
        logs_dir: str,
        should_end_fn: Optional[Callable[[List[Dict], int, int], bool]] = None,
        on_idle: Optional[Callable[[List[Dict], int, int], IdleAction]] = None,
    ) -> SessionResult:
        """Run a single agent session.

        Args:
            session_id: Unique session identifier
            system_prompt: The system prompt for this session
            bootstrap_messages: Initial messages before the loop starts
            budget: Session budget constraints
            logs_dir: Directory to write transcript
            should_end_fn: Optional external check to force session end
            on_idle: Called when the model produces end_turn with no tool calls.
                     Returns IdleAction — if should_continue=True, the prompt is
                     injected as a user message and the session continues.
                     This enables multi-feature sessions: the orchestrator can
                     feed the next feature when the model goes idle.

        Returns:
            SessionResult with summary statistics
        """
        session_start = time.time()
        messages = [{"role": "system", "content": system_prompt}] + bootstrap_messages

        transcript_path = os.path.join(logs_dir, f"session_{session_id:04d}.jsonl")
        os.makedirs(os.path.dirname(transcript_path), exist_ok=True)

        total_input_tokens = 0
        total_output_tokens = 0
        turn_count = 0
        idle_injections = 0

        self._log_event(transcript_path, {
            "type": "session_start",
            "session_id": session_id,
            "timestamp": time.time(),
            "budget_max_turns": budget.max_turns,
            "budget_max_tokens": budget.max_total_tokens,
        })

        while True:
            # Check budget
            if budget.exhausted:
                self._log_event(transcript_path, {
                    "type": "session_end",
                    "reason": "budget_exhausted",
                    "turns": turn_count,
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "idle_injections": idle_injections,
                })
                return SessionResult(
                    session_id=session_id,
                    transcript_path=transcript_path,
                    turns=turn_count,
                    tokens_input=total_input_tokens,
                    tokens_output=total_output_tokens,
                    stop_reason="budget_exhausted",
                    feature_status_after="incomplete",
                    start_time=session_start,
                    end_time=time.time(),
                    idle_injections=idle_injections,
                )

            # External check (token threshold / forced stop)
            if should_end_fn and should_end_fn(messages, turn_count, total_input_tokens + total_output_tokens):
                self._log_event(transcript_path, {
                    "type": "session_end",
                    "reason": "context_full_or_forced",
                    "turns": turn_count,
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "idle_injections": idle_injections,
                })
                return SessionResult(
                    session_id=session_id,
                    transcript_path=transcript_path,
                    turns=turn_count,
                    tokens_input=total_input_tokens,
                    tokens_output=total_output_tokens,
                    stop_reason="context_full",
                    feature_status_after="partial",
                    start_time=session_start,
                    end_time=time.time(),
                    idle_injections=idle_injections,
                )

            # Compress stale tool results when context is tight
            cum_tokens = total_input_tokens + total_output_tokens
            messages = compress_messages(messages, turn_count, self.config, cum_tokens)

            # Call LLM
            response = self.client.chat(messages, tools=TOOL_DEFINITIONS)
            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens

            # Add assistant message
            assistant_msg = {"role": "assistant", "content": response.content}
            if response.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                    }
                    for tc in response.tool_calls
                ]
            messages.append(assistant_msg)

            self._log_event(transcript_path, {
                "type": "assistant",
                "turn": turn_count,
                "content": response.content[:500],
                "tool_calls": [(tc.name, tc.arguments) for tc in response.tool_calls],
                "stop_reason": response.stop_reason,
                "usage": {
                    "input": response.usage.input_tokens,
                    "output": response.usage.output_tokens,
                    "cumulative_input": total_input_tokens,
                    "cumulative_output": total_output_tokens,
                },
            })

            # Update budget tracking
            budget.tokens_used = total_input_tokens + total_output_tokens
            budget.turns_used = turn_count

            # Check stop conditions
            if response.stop_reason == "end_turn" and not response.tool_calls:
                # Model went idle — ask orchestrator if we should continue
                if on_idle:
                    action = on_idle(messages, turn_count, total_input_tokens + total_output_tokens)
                    if action.should_continue:
                        idle_injections += 1
                        self._log_event(transcript_path, {
                            "type": "idle_injection",
                            "injection_num": idle_injections,
                            "prompt": action.prompt[:300],
                        })
                        messages.append({"role": "user", "content": action.prompt})
                        continue  # Keep the session alive, work on next feature

                self._log_event(transcript_path, {
                    "type": "session_end",
                    "reason": "end_turn_idle",
                    "turns": turn_count,
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "idle_injections": idle_injections,
                })
                return SessionResult(
                    session_id=session_id,
                    transcript_path=transcript_path,
                    turns=turn_count,
                    tokens_input=total_input_tokens,
                    tokens_output=total_output_tokens,
                    stop_reason="idle_no_work",
                    feature_status_after="completed_or_stalled",
                    start_time=session_start,
                    end_time=time.time(),
                    idle_injections=idle_injections,
                )

            if not response.tool_calls:
                break

            # Execute tool calls
            turn_count += 1
            for tc in response.tool_calls:
                result = self.tools.run(tc.name, tc.arguments)

                tool_msg = {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result.to_message(),
                }
                messages.append(tool_msg)

                self._log_event(transcript_path, {
                    "type": "tool_result",
                    "turn": turn_count,
                    "tool": tc.name,
                    "arguments": tc.arguments,
                    "success": result.success,
                    "exit_code": result.exit_code,
                    "stdout_len": len(result.stdout),
                    "stderr_len": len(result.stderr),
                    "truncated": result.truncated,
                    "error": result.error,
                    "estimated_tokens": result.estimate_tokens(),
                })

        self._log_event(transcript_path, {
            "type": "session_end",
            "reason": "no_tool_calls",
            "turns": turn_count,
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
        })
        return SessionResult(
            session_id=session_id,
            transcript_path=transcript_path,
            turns=turn_count,
            tokens_input=total_input_tokens,
            tokens_output=total_output_tokens,
            stop_reason="end_turn",
            feature_status_after="completed_per_model",
            start_time=session_start,
            end_time=time.time(),
            idle_injections=idle_injections,
        )

    def _log_event(self, path: str, event: Dict[str, Any]):
        """Append one event to the JSONL transcript."""
        event.setdefault("timestamp", time.time())
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
