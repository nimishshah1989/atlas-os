"""SP07: base ``SpecialistAgent`` ABC + tool-calling loop.

The loop is the load-bearing piece. It:

1. Sends ``[system, user]`` to Groq with ``tools=`` set to this agent's
   subset of the registry.
2. If the response carries ``tool_calls``, executes each one against the
   bound query function, appends a tool-result message, and re-calls.
3. Stops when the model returns a final assistant message with no tool
   calls, OR when iterations exceed ``MAX_ITERS``.
4. Scans the final narrative for SEBI-banned words and raises
   ``SEBIComplianceError`` if any are present.

The loop is deliberately ~70 LOC and synchronous. SP07 v2 will swap this
for the full Hermes Agent runtime without changing the public interface.
"""

from __future__ import annotations

import abc
import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import structlog
from sqlalchemy.engine import Engine

from atlas.agents.specialists._sebi import BANNED_WORDS
from atlas.agents.tools.registry import Tool, build_registry

log = structlog.get_logger()

_MODEL = "llama-3.3-70b-versatile"
_MAX_TOKENS = 700
MAX_ITERS = 4


class SEBIComplianceError(RuntimeError):
    """Raised when a specialist's final narrative trips the banned-word scan."""


@dataclass(frozen=True)
class AgentResult:
    """The output of one specialist invocation."""

    agent_name: str
    narrative: str
    tool_calls: list[dict[str, Any]]
    model: str
    input_tokens: int | None
    output_tokens: int | None
    iterations: int
    data_as_of: date | None


class SpecialistAgent(abc.ABC):
    """Base class for all v1 specialists."""

    name: str = ""
    description: str = ""
    tool_names: tuple[str, ...] = ()

    @abc.abstractmethod
    def build_system_prompt(self) -> str:
        """Return the agent's system prompt (SEBI preamble + mission)."""
        raise NotImplementedError

    def invoke(
        self,
        question: str,
        *,
        engine: Engine,
        client: Any | None = None,
    ) -> AgentResult:
        """Run the tool-calling loop and return the final ``AgentResult``."""
        if not question or not question.strip():
            raise ValueError("question must be non-empty")
        registry = build_registry(engine)
        my_tools: list[Tool] = [registry[n] for n in self.tool_names]
        _client = client if client is not None else _make_groq_client()
        return _run_loop(
            agent_name=self.name,
            client=_client,
            system_prompt=self.build_system_prompt(),
            user_question=question,
            tools=my_tools,
        )


def _run_loop(
    *,
    agent_name: str,
    client: Any,
    system_prompt: str,
    user_question: str,
    tools: list[Tool],
) -> AgentResult:
    """Drive the tool-calling loop. See module docstring."""
    tools_by_name = {t.name: t for t in tools}
    groq_tools = [t.as_groq_tool() for t in tools]

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_question},
    ]
    tool_call_log: list[dict[str, Any]] = []
    total_in = 0
    total_out = 0
    final_message: str = ""
    iterations = 0

    for _i in range(MAX_ITERS):
        iterations += 1
        # Llama 3.3 70B on Groq occasionally emits XML-style function calls
        # (e.g. `<function=name {args}>`) instead of the OpenAI tool_calls JSON.
        # When Groq's validator rejects the malformed call with HTTP 400
        # `tool_use_failed`, fall back to a tool-less completion so the
        # agent can still emit a degraded narrative answer rather than crash.
        try:
            response = client.chat.completions.create(
                model=_MODEL,
                max_tokens=_MAX_TOKENS,
                messages=messages,
                tools=groq_tools,
                tool_choice="auto",
            )
        except Exception as exc:
            msg_str = str(exc)
            if "tool_use_failed" in msg_str or "Failed to call a function" in msg_str:
                log.warning("agent_tool_use_failed_fallback", err=msg_str[:200])
                response = client.chat.completions.create(
                    model=_MODEL,
                    max_tokens=_MAX_TOKENS,
                    messages=[
                        *messages,
                        {
                            "role": "system",
                            "content": (
                                "Continue without calling any more tools. "
                                "Synthesize an answer from data already available. "
                                "End with a 'Data as of YYYY-MM-DD' line."
                            ),
                        },
                    ],
                )
            else:
                raise
        choice = response.choices[0]
        usage = getattr(response, "usage", None)
        if usage is not None:
            total_in += getattr(usage, "prompt_tokens", 0) or 0
            total_out += getattr(usage, "completion_tokens", 0) or 0

        msg = choice.message
        tool_calls = getattr(msg, "tool_calls", None) or []

        if not tool_calls:
            final_message = (msg.content or "").strip()
            break

        # Echo the assistant turn (must include tool_calls) so the model can
        # reason over its own request when it sees the results.
        messages.append(_assistant_with_tool_calls(msg, tool_calls))

        for tc in tool_calls:
            t_name = tc.function.name
            t_args: dict[str, Any] = {}
            try:
                parsed = json.loads(tc.function.arguments or "{}")
                if not isinstance(parsed, dict):
                    raise ValueError("tool arguments did not parse to an object")
                t_args = parsed
                if t_name not in tools_by_name:
                    raise KeyError(f"unknown tool: {t_name}")
                result = tools_by_name[t_name].fn(**t_args)
                result_repr: Any = _shrink_result(result)
            except Exception as exc:
                log.warning("agent_tool_error", agent=agent_name, tool=t_name, err=str(exc))
                result_repr = {"error": type(exc).__name__, "message": str(exc)[:240]}

            tool_call_log.append(
                {
                    "tool": t_name,
                    "args": t_args,
                    "result_keys": _result_keys(result_repr),
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": t_name,
                    "content": json.dumps(result_repr, default=str),
                }
            )
    else:
        # MAX_ITERS hit without a final non-tool message. Use whatever
        # assistant content the last loop produced.
        log.warning("agent_max_iters", agent=agent_name, iters=iterations)
        last = messages[-1] if messages else {}
        if isinstance(last, dict) and last.get("role") == "assistant":
            final_message = str(last.get("content") or "").strip()

    if not final_message:
        raise RuntimeError(
            f"specialist {agent_name!r} produced no final narrative after {iterations} iteration(s)"
        )

    banned = _scan_banned_words(final_message)
    if banned:
        raise SEBIComplianceError(
            f"specialist {agent_name!r} emitted banned word(s): {banned}. Output not returned."
        )

    data_as_of = _extract_data_as_of(tool_call_log, messages)

    log.info(
        "agent_invocation_complete",
        agent=agent_name,
        iterations=iterations,
        n_tool_calls=len(tool_call_log),
        input_tokens=total_in,
        output_tokens=total_out,
        word_count=len(final_message.split()),
    )

    return AgentResult(
        agent_name=agent_name,
        narrative=final_message,
        tool_calls=tool_call_log,
        model=_MODEL,
        input_tokens=total_in or None,
        output_tokens=total_out or None,
        iterations=iterations,
        data_as_of=data_as_of,
    )


def _assistant_with_tool_calls(msg: Any, tool_calls: list[Any]) -> dict[str, Any]:
    """Echo the assistant turn back in OpenAI/Groq message format."""
    return {
        "role": "assistant",
        "content": msg.content or None,
        "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments or "{}",
                },
            }
            for tc in tool_calls
        ],
    }


def _shrink_result(result: Any, *, max_items: int = 20) -> Any:
    """Cap list lengths so the LLM context does not explode on big results."""
    if isinstance(result, list) and len(result) > max_items:
        return [*result[:max_items], {"_truncated": len(result) - max_items}]
    if isinstance(result, dict):
        out: dict[str, Any] = {}
        for k, v in result.items():
            out[k] = _shrink_result(v, max_items=max_items)
        return out
    return result


def _result_keys(result: Any) -> list[str]:
    """Audit-only: list top-level keys of a result for the tool-call log."""
    if isinstance(result, dict):
        return list(result.keys())[:12]
    if isinstance(result, list):
        if result and isinstance(result[0], dict):
            return list(result[0].keys())[:12]
        return [f"<list len={len(result)}>"]
    return [type(result).__name__]


def _scan_banned_words(narrative: str) -> list[str]:
    """Return any banned SEBI words present in ``narrative``."""
    lower = narrative.lower()
    hits: list[str] = []
    for word in BANNED_WORDS:
        if " " in word:
            if word in lower:
                hits.append(word)
        else:
            if re.search(rf"\b{re.escape(word)}\b", lower):
                hits.append(word)
    return hits


_DATE_KEYS = ("date", "as_of", "as_of_date", "state_since_date", "last_seen")


def _extract_data_as_of(
    tool_log: list[dict[str, Any]], messages: list[dict[str, Any]]
) -> date | None:
    """Walk tool-result messages to find the most recent date field."""
    best: date | None = None
    for m in messages:
        if m.get("role") != "tool":
            continue
        try:
            payload = json.loads(m.get("content", "null"))
        except (json.JSONDecodeError, TypeError):
            continue
        best = _max_date(best, _scan_for_date(payload))
    return best


def _scan_for_date(value: Any) -> date | None:
    """Recursively search ``value`` for the most recent date-shaped string."""
    if isinstance(value, dict):
        best: date | None = None
        for k, v in value.items():
            if k in _DATE_KEYS and isinstance(v, str):
                best = _max_date(best, _parse_iso_date(v))
            else:
                best = _max_date(best, _scan_for_date(v))
        return best
    if isinstance(value, list):
        best = None
        for item in value:
            best = _max_date(best, _scan_for_date(item))
        return best
    return None


def _parse_iso_date(s: str) -> date | None:
    """Best-effort parse of ``s`` as an ISO date or datetime; returns None."""
    try:
        if "T" in s:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
        return date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None


def _max_date(a: date | None, b: date | None) -> date | None:
    """Return the more recent of two optional dates."""
    if a is None:
        return b
    if b is None:
        return a
    return a if a >= b else b


def _make_groq_client() -> Any:
    """Construct a Groq-backed OpenAI client. Mirrors SP05 ``_make_client``."""
    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError("openai SDK not installed. Run: pip install 'openai>=1.50'") from e
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set. Get one at console.groq.com.")
    return OpenAI(base_url="https://api.groq.com/openai/v1", api_key=api_key)
