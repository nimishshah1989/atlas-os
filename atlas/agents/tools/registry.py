"""SP07: tool registry — the contract between specialist agents and atlas data.

A ``Tool`` wraps one read-only query function with:
- a stable ``name`` (LLM-visible)
- a one-line ``description`` (LLM-visible)
- a JSON Schema ``parameters`` block (Groq/OpenAI tool-calling format)
- the bound ``fn(engine, **kwargs)`` callable

``build_registry(engine)`` returns ``dict[str, Tool]`` with the live engine
captured per tool. This lets tests inject a fake engine without monkey-
patching module state.

The 10 v1 tools cover SP02 MVs (5), regime history (1), validator findings
(2), distribution stats (1), and the latest daily brief (1). When SP04
lands, a single ``get_composite_signal_score`` entry is added here without
touching specialists or callers.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Any

from sqlalchemy.engine import Engine

from atlas.agents.tools.atlas_queries import (
    query_breakout_candidates,
    query_current_regime,
    query_deterioration_watch,
    query_distribution_stats,
    query_finding_summary,
    query_latest_brief,
    query_recent_findings,
    query_regime_history,
    query_sector_rotation_quadrants,
    query_top_conviction,
    query_top_rs_stocks,
    query_tv_analysis,
)


@dataclass(frozen=True)
class Tool:
    """One read-only tool exposed to an LLM specialist."""

    name: str
    description: str
    parameters: dict[str, Any]
    fn: Callable[..., Any]

    def as_groq_tool(self) -> dict[str, Any]:
        """Render this tool in Groq / OpenAI function-calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


# ---------------------------------------------------------------------- #
# Parameter schemas — one entry per tool. JSON Schema (Draft 2020-12).   #
# Keys MUST match the function kwargs in atlas_queries.py.               #
# ---------------------------------------------------------------------- #
_NO_ARGS: dict[str, Any] = {"type": "object", "properties": {}, "additionalProperties": False}

_PARAMETER_SCHEMAS: dict[str, dict[str, Any]] = {
    "get_current_regime": _NO_ARGS,
    "get_regime_history": {
        "type": "object",
        "properties": {
            "n_days": {
                "type": "integer",
                "minimum": 1,
                "maximum": 30,
                "default": 5,
                "description": "Number of recent days to return.",
            }
        },
        "additionalProperties": False,
    },
    "get_sector_rotation_quadrants": _NO_ARGS,
    "get_top_rs_stocks": {
        "type": "object",
        "properties": {
            "n": {
                "type": "integer",
                "minimum": 1,
                "maximum": 50,
                "default": 10,
                "description": "Number of stocks to return.",
            },
            "sector": {
                "type": "string",
                "description": (
                    "Optional sector hint, substring-matched case-insensitively "
                    "against the sector column (e.g. 'IT', 'Bank', 'Pharma')."
                ),
            },
        },
        "additionalProperties": False,
    },
    "get_breakout_candidates": {
        "type": "object",
        "properties": {
            "n": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
        },
        "additionalProperties": False,
    },
    "get_deterioration_watch": {
        "type": "object",
        "properties": {
            "n": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
        },
        "additionalProperties": False,
    },
    "get_recent_findings": {
        "type": "object",
        "properties": {
            "severity": {
                "type": "string",
                "enum": ["P0", "P1", "P2", "P3"],
                "description": "Optional severity filter.",
            },
            "n": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
        },
        "additionalProperties": False,
    },
    "get_finding_summary": {
        "type": "object",
        "properties": {
            "n_days": {
                "type": "integer",
                "minimum": 1,
                "maximum": 90,
                "default": 7,
                "description": "Aggregation window in days.",
            }
        },
        "additionalProperties": False,
    },
    "get_distribution_stats": {
        "type": "object",
        "properties": {
            "table": {
                "type": "string",
                "enum": [
                    "atlas_stock_metrics_daily",
                    "atlas_sector_metrics_daily",
                    "atlas_market_regime_daily",
                ],
            },
            "metric_column": {
                "type": "string",
                "enum": [
                    "rs_pctile_3m",
                    "ema_ratio_50_200",
                    "rs_pctile_cross_sector",
                    "rs_velocity",
                    "pct_above_ema_50",
                    "ad_ratio",
                ],
            },
        },
        "required": ["table", "metric_column"],
        "additionalProperties": False,
    },
    "get_latest_brief": _NO_ARGS,
    "get_top_conviction": {
        "type": "object",
        "properties": {
            "n": {
                "type": "integer",
                "minimum": 1,
                "maximum": 50,
                "default": 10,
                "description": "Number of stocks to return.",
            },
            "tier": {
                "type": "string",
                "enum": [
                    "tier_1_megacap",
                    "tier_2_largecap",
                    "tier_3_uppermid",
                    "tier_4_lowermid",
                    "tier_5_smallcap",
                ],
                "description": (
                    "Optional liquidity tier. tier_1_megacap = top 50 by ADV; "
                    "tier_3_uppermid = ranks 151-300 (industry-grade). "
                    "Omit to scan all tiers."
                ),
            },
            "confidence_label": {
                "type": "string",
                "enum": ["industry_grade", "baseline"],
                "description": (
                    "Filter to 'industry_grade' for tiers where the composite "
                    "has measured holdout IC >= 0.05 (T1 mega-cap and T3 upper "
                    "mid-cap as of Stage 2). 'baseline' surfaces directionally "
                    "positive but weaker tiers."
                ),
            },
        },
        "additionalProperties": False,
    },
    "get_tv_analysis": {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "NSE symbol (e.g. 'RELIANCE', 'TCS'). Case-insensitive.",
            }
        },
        "required": ["symbol"],
        "additionalProperties": False,
    },
}


# ---------------------------------------------------------------------- #
# Tool descriptions — load-bearing because the LLM reads these.          #
# Keep them short, action-verb-led, and unambiguous.                     #
# ---------------------------------------------------------------------- #
_DESCRIPTIONS: dict[str, str] = {
    "get_current_regime": (
        "Return the current Atlas market regime (Risk-On/Neutral/Defensive/Risk-Off) "
        "with deployment multiplier and breadth signals (pct above EMA 50/200, "
        "advance-decline ratio, McClellan, India VIX). One row from "
        "mv_current_market_regime."
    ),
    "get_regime_history": (
        "Return the last N daily regime rows so the analyst can see whether the "
        "regime has been stable or transitioning. Defaults to 5 days."
    ),
    "get_sector_rotation_quadrants": (
        "Return all NIFTY sectors grouped by RRG quadrant (Leading, Improving, "
        "Weakening, Lagging) with their RS level, RS velocity, and cross-sector "
        "percentile. Source: mv_sector_rotation_state."
    ),
    "get_top_rs_stocks": (
        "Return the top-N stocks by 3-month RS percentile, optionally filtered "
        "by sector (case-insensitive substring). Defaults to N=10, all sectors."
    ),
    "get_breakout_candidates": (
        "Return stocks that transitioned INTO Leader or Strong RS state on the "
        "most recent trading day. Source: mv_breakout_candidates."
    ),
    "get_deterioration_watch": (
        "Return stocks that transitioned OUT of Leader or Strong RS state on the "
        "most recent trading day. Source: mv_deterioration_watch."
    ),
    "get_recent_findings": (
        "Return recent data-quality findings from the validator agent, "
        "optionally filtered by severity (P0/P1/P2/P3). "
        "Source: atlas_validator_findings."
    ),
    "get_finding_summary": (
        "Aggregate validator findings by severity and finding_class over the "
        "last N days. Useful for spotting universe-wide anomalies."
    ),
    "get_distribution_stats": (
        "Return basic distribution stats (n, mean, median, p95, min, max) for a "
        "whitelisted (table, metric_column) pair over the last 30 days. Used by "
        "the drift detector to compare today's distribution to recent history."
    ),
    "get_latest_brief": (
        "Return the most recent persisted Atlas daily brief (narrative + key "
        "themes + regime summary) from atlas_daily_briefs."
    ),
    "get_top_conviction": (
        "Return the top N stocks by conviction_score from the production "
        "conviction composite (atlas_stock_conviction_daily). Prefer this "
        "over get_top_rs_stocks when the user asks for 'best', 'highest "
        "conviction', or 'top picks' — the composite is an IC-weighted "
        "blend of momentum, trend, drawdown, and volatility signals "
        "measured on out-of-sample 2023-2025 data. Use "
        "confidence_label='industry_grade' to restrict to T1 and T3 "
        "(measured IC >= 0.05)."
    ),
    "get_tv_analysis": (
        "Return cached TradingView screener metrics for one NSE symbol: "
        "tv_recommend_label (STRONG_BUY/BUY/NEUTRAL/SELL/STRONG_SELL), "
        "recommend_all, RSI-14, MACD, EMA-20/50/200, ATR-14, price, "
        "52-week high/low, and fetched_at. Returns null when the symbol "
        "is not in the Atlas universe or screener data is absent."
    ),
}


# ---------------------------------------------------------------------- #
# Tool name → query function. Bound to the engine inside build_registry. #
# ---------------------------------------------------------------------- #
_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "get_current_regime": query_current_regime,
    "get_regime_history": query_regime_history,
    "get_sector_rotation_quadrants": query_sector_rotation_quadrants,
    "get_top_rs_stocks": query_top_rs_stocks,
    "get_breakout_candidates": query_breakout_candidates,
    "get_deterioration_watch": query_deterioration_watch,
    "get_recent_findings": query_recent_findings,
    "get_finding_summary": query_finding_summary,
    "get_distribution_stats": query_distribution_stats,
    "get_latest_brief": query_latest_brief,
    "get_top_conviction": query_top_conviction,
    "get_tv_analysis": query_tv_analysis,
}

# Tuple of all tool names — tests pin against this.
TOOL_NAMES: tuple[str, ...] = tuple(_FUNCTIONS.keys())


def build_registry(engine: Engine) -> dict[str, Tool]:
    """Build the registry with each tool's ``fn`` bound to ``engine``.

    Args:
        engine: The SQLAlchemy engine used by every tool. Bound via
            ``functools.partial`` so tools take ``**kwargs`` only.

    Returns:
        Mapping from tool name to ``Tool``. Same length as ``TOOL_NAMES``.
    """
    registry: dict[str, Tool] = {}
    for name in TOOL_NAMES:
        fn = _FUNCTIONS[name]
        registry[name] = Tool(
            name=name,
            description=_DESCRIPTIONS[name],
            parameters=_PARAMETER_SCHEMAS[name],
            fn=partial(fn, engine),
        )
    return registry
