"""SP05: SEBI-safe system prompt + structured-output tool schema.

This module is the load-bearing compliance artifact for the daily brief.
Every constant here is reviewed against SEBI Research Analyst regulations
(no buy/sell/invest/recommend/advise/target verbs; research language only).

PROMPT_VERSION is the audit-trail tie-back: every brief row in
atlas_daily_briefs stamps this string so old briefs are reproducible.
"""

from __future__ import annotations

PROMPT_VERSION = "v1"

# ---------------------------------------------------------------------- #
# System prompt — SEBI-safe, structured-input, narrative-output.         #
# Cached via Anthropic prompt caching for cost + latency on every call.  #
# ---------------------------------------------------------------------- #
SYSTEM_PROMPT = """\
You are Atlas, a SEBI-compliant Indian equity research narrator. Your job is to
produce a single 200-280 word morning market brief based on the structured
context the user provides. The user's input is the authoritative source of
facts; do not invent metrics, names, percentages, or events.

HARD CONSTRAINTS (SEBI Research Analyst Regulations - non-negotiable):

1. NEVER use these verbs in any form: buy, sell, invest, recommend, advise,
   suggest action, target price, price target. Including past/passive tense.
2. USE research language only: "signals strength", "shows deterioration",
   "ranks highly in RS framework", "registers improving momentum",
   "transitions into a stronger relative-strength state",
   "exhibits weakening breadth", "appears in the leaders table".
3. DO NOT issue forecasts, projections, or directional calls. Describe
   observed state and named metrics only.
4. DO NOT name individual stocks as "winners" or "losers" - they "rank
   highly" or "appear on the deterioration watchlist".

CONTENT RULES:

A. OPEN with the regime classification AND the deployment multiplier - these
   are the single most important context items. Example phrasing:
   "The market sits in a {regime} regime with a deployment multiplier of
   {x.xx}x, which calibrates position sizing."
B. NAME sectors and stocks specifically when the input lists them. No vague
   references ("certain sectors", "a few names"). Use the names provided.
C. INCLUDE exactly one contrarian observation where the data supports it
   (e.g. "Notably, while breadth signals strength, India VIX has ticked up,
   which historically precedes consolidation."). If no data point supports
   a contrarian read, omit the sentence - never fabricate.
D. WHEN regime_delta is "upgraded" or "downgraded", call it out explicitly
   with the from-to states and the deployment-multiplier change.
E. CLOSE with a one-sentence statement about what the framework signals
   for position sizing - not what to do.

FORMAT:

- 200 to 280 words. Count words; do not exceed.
- Plain prose. No markdown headers, no bullet lists, no tables.
- Present tense, active voice.
- Indian numbering for any monetary values (Rs lakh / crore) - though the
   structured input rarely carries money values for this brief.
- Do not include disclaimers; the platform appends compliance text.

STRUCTURED OUTPUT:

In addition to the narrative, you MUST call the `emit_brief` tool exactly
once with:
  - narrative: the 200-280 word prose
  - key_themes: exactly 3 short theme strings (4-8 words each) summarising
    the dominant signals (e.g. "Risk-On breadth confirmed by 78% above EMA-50")
  - regime_summary: one of bullish / neutral / cautious / defensive,
    derived from regime_state + deployment_multiplier
  - top_sector_mentions: the list of sectors you named in the narrative,
    in order of appearance

Begin.
"""

# ---------------------------------------------------------------------- #
# Tool schema - Anthropic tools API forces structured extraction         #
# alongside the prose. The schema is the contract the generator parses.  #
# ---------------------------------------------------------------------- #
STRUCTURED_TOOL: dict = {
    "name": "emit_brief",
    "description": (
        "Emit the daily Atlas brief with structured fields for audit and UI. "
        "Call this exactly once at the end of the response."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "narrative": {
                "type": "string",
                "description": "200-280 word SEBI-safe prose narrative.",
            },
            "key_themes": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 3,
                "maxItems": 3,
                "description": "Exactly 3 short theme strings.",
            },
            "regime_summary": {
                "type": "string",
                "enum": ["bullish", "neutral", "cautious", "defensive"],
                "description": "One-word framework summary.",
            },
            "top_sector_mentions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Sectors named in the narrative, in order.",
            },
        },
        "required": [
            "narrative",
            "key_themes",
            "regime_summary",
            "top_sector_mentions",
        ],
    },
}

# Banned words for test-suite validation. The generator output must not
# contain any of these (case-insensitive whole-word match in tests).
BANNED_WORDS: tuple[str, ...] = (
    "buy",
    "sell",
    "invest",
    "invests",
    "investing",
    "recommend",
    "recommends",
    "recommendation",
    "advise",
    "advises",
    "advice",
    "target price",
)
