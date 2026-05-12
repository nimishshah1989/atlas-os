"""SP05: DailyMarketContext - structured input for the daily brief.

Reads the SP02 materialized views (with one regime-history lookup against
atlas_market_regime_daily for the regime_delta diff). Pure SQL reader; no
business judgement, no Claude, no side effects.

When SP04 lands, swap in graded scores at the call sites that compute
top_sectors / new_breakouts - the dataclass shape stays the same so the
generator, prompts, audit, and frontend are unchanged.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

log = structlog.get_logger()

_TOP_SECTOR_LIMIT = 3
_BREAKOUT_LIMIT = 5
_DETERIORATION_LIMIT = 5


@dataclass(frozen=True)
class DailyMarketContext:
    """Immutable structured input for the daily brief generator."""

    as_of: date
    regime: str
    regime_delta: str  # 'unchanged' | 'upgraded' | 'downgraded'
    deployment_multiplier: Decimal
    breadth: dict[str, Decimal | int | None]
    top_sectors: list[str]
    rotating_out: list[str]
    new_breakouts: list[dict[str, Any]]
    new_deteriorations: list[dict[str, Any]]
    # SP04 Stage 3+: top conviction names per industry-grade tier. Empty
    # list if mv_top_conviction_daily has no rows for as_of.
    top_conviction: list[dict[str, Any]] = field(default_factory=list)
    raw_regime_row: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict for prompt rendering + audit log."""
        out = asdict(self)
        return _jsonify(out)


def _jsonify(value: Any) -> Any:
    """Recursively convert Decimal/date to JSON-safe primitives."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonify(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonify(v) for v in value]
    return value


_BREADTH_KEYS = (
    "pct_above_ema_50",
    "mcclellan_oscillator",
    "ad_ratio",
    "net_new_highs",
    "india_vix",
)


def _classify_regime_delta(today: str, yesterday: str | None) -> str:
    """Classify regime change. SEBI-safe vocabulary."""
    ordering = {
        "Risk-Off": 0,
        "Defensive": 1,
        "Neutral": 2,
        "Risk-On": 3,
    }
    if yesterday is None or yesterday == today:
        return "unchanged"
    a = ordering.get(today, -1)
    b = ordering.get(yesterday, -1)
    if a > b:
        return "upgraded"
    if a < b:
        return "downgraded"
    return "unchanged"


def build_daily_context(engine: Engine, as_of: date) -> DailyMarketContext:
    """Build the structured input snapshot for the daily brief generator.

    Reads five SP02 materialized views plus one regime-history lookup.
    Returns an immutable DailyMarketContext.
    """
    with engine.connect() as conn:
        # 1. Current regime - mv_current_market_regime is a single-row view.
        regime_row = (
            conn.execute(
                text(
                    "SELECT date, regime_state, deployment_multiplier, "
                    "pct_above_ema_50, mcclellan_oscillator, ad_ratio, "
                    "net_new_highs, india_vix "
                    "FROM atlas.mv_current_market_regime LIMIT 1"
                )
            )
            .mappings()
            .fetchone()
        )

        # 2. Yesterday's regime - from atlas_market_regime_daily.
        yesterday_row = (
            conn.execute(
                text(
                    "SELECT regime_state, deployment_multiplier "
                    "FROM atlas.atlas_market_regime_daily "
                    "WHERE date < :as_of "
                    "ORDER BY date DESC LIMIT 1"
                ),
                {"as_of": as_of},
            )
            .mappings()
            .fetchone()
        )

        # 3. Sector rotation - top 3 by RS percentile, bottom 3 by RS velocity.
        sector_rows = (
            conn.execute(
                text(
                    "SELECT sector_name, rs_pctile_cross_sector, rs_velocity "
                    "FROM atlas.mv_sector_rotation_state "
                    "ORDER BY rs_pctile_cross_sector DESC NULLS LAST"
                )
            )
            .mappings()
            .fetchall()
        )

        # 4. Breakout candidates - top 5 by RS percentile.
        breakout_rows = (
            conn.execute(
                text(
                    "SELECT symbol, company_name, sector, new_rs_state "
                    "FROM atlas.mv_breakout_candidates "
                    "ORDER BY rs_pctile_3m DESC NULLS LAST "
                    "LIMIT :lim"
                ),
                {"lim": _BREAKOUT_LIMIT},
            )
            .mappings()
            .fetchall()
        )

        # 5. Deterioration watch - top 5 by prior RS percentile.
        deterioration_rows = (
            conn.execute(
                text(
                    "SELECT symbol, company_name, sector, prior_rs_state "
                    "FROM atlas.mv_deterioration_watch "
                    "ORDER BY rs_pctile_3m DESC NULLS LAST "
                    "LIMIT :lim"
                ),
                {"lim": _DETERIORATION_LIMIT},
            )
            .mappings()
            .fetchall()
        )

        # 6. Top conviction names — SP04 Stage 3 overlay. Restrict to
        # industry-grade tiers (T1 mega-cap + T3 upper mid) so the brief
        # never quotes a low-confidence pick as if it were high-grade.
        try:
            conviction_rows = (
                conn.execute(
                    text(
                        "SELECT u.symbol, u.sector, c.tier, "
                        "ROUND((c.conviction_score * 100)::numeric, 1) AS conviction "
                        "FROM atlas.mv_top_conviction_daily c "
                        "LEFT JOIN atlas.atlas_universe_stocks u "
                        "       ON u.instrument_id = c.instrument_id "
                        "WHERE c.confidence_label = 'industry_grade' "
                        "ORDER BY c.conviction_score DESC "
                        "LIMIT 5"
                    )
                )
                .mappings()
                .fetchall()
            )
        except Exception as exc:
            # mv_top_conviction_daily may be empty on a fresh DB.
            log.warning("conviction_mv_unavailable", err=str(exc)[:120])
            conviction_rows = []

    if regime_row is None:
        # Graceful degradation: no MV data. Return a stub context that the
        # generator will refuse to send to Claude.
        log.warning("daily_brief_no_regime_row", as_of=as_of.isoformat())
        return DailyMarketContext(
            as_of=as_of,
            regime="Unknown",
            regime_delta="unchanged",
            deployment_multiplier=Decimal("0"),
            breadth={k: None for k in _BREADTH_KEYS},
            top_sectors=[],
            rotating_out=[],
            new_breakouts=[],
            new_deteriorations=[],
            raw_regime_row={},
        )

    regime = str(regime_row["regime_state"] or "Unknown")
    yesterday_regime = str(yesterday_row["regime_state"]) if yesterday_row else None
    regime_delta = _classify_regime_delta(regime, yesterday_regime)

    breadth: dict[str, Decimal | int | None] = {k: regime_row.get(k) for k in _BREADTH_KEYS}

    top_sectors = [str(r["sector_name"]) for r in sector_rows[:_TOP_SECTOR_LIMIT]]

    # Rotating out = 3 sectors with most negative rs_velocity. Re-sort ascending.
    def _vel_key(r: dict) -> float:
        v = r.get("rs_velocity")
        return float(v) if v is not None else 0.0

    sorted_by_velocity = sorted(sector_rows, key=_vel_key)
    rotating_out = [str(r["sector_name"]) for r in sorted_by_velocity[:_TOP_SECTOR_LIMIT]]

    new_breakouts = [dict(r) for r in breakout_rows]
    new_deteriorations = [dict(r) for r in deterioration_rows]
    top_conviction = [dict(r) for r in conviction_rows]

    log.info(
        "daily_context_built",
        as_of=as_of.isoformat(),
        regime=regime,
        regime_delta=regime_delta,
        n_breakouts=len(new_breakouts),
        n_deteriorations=len(new_deteriorations),
        n_top_conviction=len(top_conviction),
    )

    return DailyMarketContext(
        as_of=as_of,
        regime=regime,
        regime_delta=regime_delta,
        deployment_multiplier=Decimal(str(regime_row["deployment_multiplier"])),
        breadth=breadth,
        top_sectors=top_sectors,
        rotating_out=rotating_out,
        new_breakouts=new_breakouts,
        top_conviction=top_conviction,
        new_deteriorations=new_deteriorations,
        raw_regime_row=dict(regime_row),
    )
