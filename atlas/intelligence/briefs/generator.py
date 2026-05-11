"""SP05: Claude Sonnet 4.6 wrapper for the daily Atlas brief.

- One Anthropic Messages.create call per brief.
- System prompt is cached (ephemeral) so re-runs amortise.
- Structured extraction via the emit_brief tool.
- Banned-word check on narrative output - fail-loud, never silently persist
  non-SEBI-compliant prose.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

import structlog

from atlas.intelligence.briefs.context import DailyMarketContext
from atlas.intelligence.briefs.prompts import (
    BANNED_WORDS,
    PROMPT_VERSION,
    STRUCTURED_TOOL,
    SYSTEM_PROMPT,
)

log = structlog.get_logger()

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 400


@dataclass(frozen=True)
class DailyBrief:
    """The output of one Claude generation. Persisted verbatim."""

    narrative: str
    key_themes: list[str]
    regime_summary: str
    top_sector_mentions: list[str]
    model: str
    prompt_version: str
    input_tokens: int | None
    output_tokens: int | None


def _context_is_empty(ctx: DailyMarketContext) -> bool:
    """A context is empty if the regime is Unknown AND every collection is
    empty. We do not call Claude on an empty context."""
    return (
        ctx.regime == "Unknown"
        and not ctx.top_sectors
        and not ctx.new_breakouts
        and not ctx.new_deteriorations
    )


def _render_user_message(ctx: DailyMarketContext) -> str:
    """Format the context as a labelled prose+JSON block for Claude."""
    lines = [
        "Today's Atlas market state:",
        "",
        f"As-of date: {ctx.as_of.isoformat()}",
        f"Regime: {ctx.regime}",
        f"Regime delta vs yesterday: {ctx.regime_delta}",
        f"Deployment multiplier: {float(ctx.deployment_multiplier):.2f}x",
        "",
        "Breadth signals:",
    ]
    for k, v in ctx.breadth.items():
        if v is None:
            lines.append(f"  - {k}: n/a")
        else:
            try:
                fv = float(v)
                lines.append(f"  - {k}: {fv:.2f}")
            except (TypeError, ValueError):
                lines.append(f"  - {k}: {v}")

    lines.append("")
    lines.append(f"Top sectors by RS percentile: {', '.join(ctx.top_sectors) or 'n/a'}")
    lines.append(
        f"Sectors rotating out (most negative RS velocity): {', '.join(ctx.rotating_out) or 'n/a'}"
    )
    lines.append("")
    if ctx.new_breakouts:
        lines.append("Breakouts (transitioned into Leader/Strong today):")
        for b in ctx.new_breakouts:
            lines.append(
                f"  - {b.get('symbol')} ({b.get('company_name')}) "
                f"in {b.get('sector')} -> {b.get('new_rs_state')}"
            )
    else:
        lines.append("Breakouts: none today.")

    lines.append("")
    if ctx.new_deteriorations:
        lines.append("Deteriorations (dropped from Strong/Leader today):")
        for d in ctx.new_deteriorations:
            lines.append(
                f"  - {d.get('symbol')} ({d.get('company_name')}) "
                f"in {d.get('sector')}; prior state {d.get('prior_rs_state')}"
            )
    else:
        lines.append("Deteriorations: none today.")

    lines.append("")
    lines.append(
        "Produce the brief in 200-280 words following the system prompt rules. "
        "Call emit_brief with the structured fields."
    )
    return "\n".join(lines)


def _scan_banned_words(narrative: str) -> list[str]:
    """Return any banned words present in the narrative (whole-word, ci)."""
    lower = narrative.lower()
    hits: list[str] = []
    for word in BANNED_WORDS:
        # Multi-word phrases use substring; single words use whole-word regex.
        if " " in word:
            if word in lower:
                hits.append(word)
        else:
            pattern = rf"\b{re.escape(word)}\b"
            if re.search(pattern, lower):
                hits.append(word)
    return hits


def _make_client() -> Any:
    """Construct an Anthropic client from env. Raises if SDK or key missing."""
    try:
        import anthropic
    except ImportError as e:
        raise RuntimeError("anthropic SDK not installed. Run: pip install 'anthropic>=0.40'") from e
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set in the environment. "
            "Export it before running the brief generator."
        )
    return anthropic.Anthropic(api_key=api_key)


def generate_brief(
    context: DailyMarketContext,
    *,
    client: Any | None = None,
) -> DailyBrief:
    """Generate the daily brief by calling Claude with structured extraction.

    ``client`` is the injection point: tests pass a MagicMock; production
    passes None and we construct a real anthropic.Anthropic instance.
    """
    if _context_is_empty(context):
        raise ValueError(
            "DailyMarketContext is empty - refusing to call Claude on a "
            "blank market state. Verify SP02 materialized views are refreshed."
        )

    if client is None:
        client = _make_client()

    user_text = _render_user_message(context)

    log.info(
        "daily_brief_generating",
        as_of=context.as_of.isoformat(),
        regime=context.regime,
        model=_MODEL,
    )

    response = client.messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=[STRUCTURED_TOOL],
        tool_choice={"type": "tool", "name": "emit_brief"},
        messages=[
            {"role": "user", "content": user_text},
        ],
    )

    # Find the emit_brief tool_use block.
    tool_block = None
    for block in response.content:
        if (
            getattr(block, "type", None) == "tool_use"
            and getattr(block, "name", None) == "emit_brief"
        ):
            tool_block = block
            break

    if tool_block is None:
        raise RuntimeError(f"Claude did not call emit_brief. Raw response: {response.content!r}")

    payload = tool_block.input
    if not isinstance(payload, dict):
        # Some SDKs return JSON-string; parse defensively.
        payload = json.loads(payload)

    narrative = str(payload["narrative"])
    banned_hits = _scan_banned_words(narrative)
    if banned_hits:
        raise ValueError(
            f"Generator emitted banned word(s): {banned_hits}. "
            "SEBI compliance gate failed - brief not persisted. "
            "Re-run; if persistent, revise prompts.py."
        )

    key_themes = [str(t) for t in payload["key_themes"]]
    regime_summary = str(payload["regime_summary"])
    top_sector_mentions = [str(s) for s in payload["top_sector_mentions"]]

    usage = getattr(response, "usage", None)
    in_tok = getattr(usage, "input_tokens", None) if usage else None
    out_tok = getattr(usage, "output_tokens", None) if usage else None

    log.info(
        "daily_brief_generated",
        as_of=context.as_of.isoformat(),
        regime=context.regime,
        input_tokens=in_tok,
        output_tokens=out_tok,
        word_count=len(narrative.split()),
    )

    return DailyBrief(
        narrative=narrative,
        key_themes=key_themes,
        regime_summary=regime_summary,
        top_sector_mentions=top_sector_mentions,
        model=getattr(response, "model", _MODEL),
        prompt_version=PROMPT_VERSION,
        input_tokens=in_tok,
        output_tokens=out_tok,
    )
