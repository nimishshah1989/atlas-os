"""Groq Llama narration of nightly optimization results.

Uses openai SDK pointed at Groq's API (same pattern as atlas/signals/narrative.py).
The LLM narrates what the engine is learning — it does NOT make trading decisions.
"""

from __future__ import annotations

import json
import os

import structlog

log = structlog.get_logger()

_MODEL = "llama-3.3-70b-versatile"
_MAX_TOKENS = 400

_PROMPT_TEMPLATE = """\
You are analyzing a portfolio optimization engine's nightly learning report.
Summarize what the engine is learning in 3-5 plain-English bullet points.
Be specific about which parameters are shifting and what that means for strategy behavior.
Do NOT make stock recommendations. Focus on what the optimization is discovering.

Parameter importance scores (higher = more impact on Sortino ratio):
{importance_json}

Top genome parameter shifts this week:
{delta_json}

Write 3-5 bullet points. Start each with a number (1., 2., etc.). Be concrete and specific.
"""


def _get_groq_client():
    api_key = os.environ.get("GROQ_API_KEY", "")
    try:
        from openai import OpenAI

        return OpenAI(base_url="https://api.groq.com/openai/v1", api_key=api_key)
    except ImportError as exc:
        raise RuntimeError("openai SDK not installed") from exc


def generate_insights(
    parameter_importance: dict[str, float],
    top_genome_deltas: list[dict],
) -> list[str]:
    """Generate plain-English insight bullets from optimization results.

    Returns 3-5 insight strings. Falls back to [] if Groq is unavailable.
    """
    prompt = _PROMPT_TEMPLATE.format(
        importance_json=json.dumps(parameter_importance, indent=2),
        delta_json=json.dumps(top_genome_deltas[:5], indent=2),
    )
    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=_MAX_TOKENS,
            temperature=0.3,
        )
        raw = response.choices[0].message.content.strip()
        bullets = [
            line.strip() for line in raw.split("\n") if line.strip() and line.strip()[0].isdigit()
        ]
        log.info("insights_generated", count=len(bullets))
        return bullets[:6]
    except Exception as exc:
        log.warning("insight_generation_failed", error=str(exc))
        return []
