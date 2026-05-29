"""Peer matrix: parent stock + top-4 sector peers with 8 pre-computed metrics."""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.db import get_engine

log = structlog.get_logger(__name__)

_PEER_SQL = text("""
WITH latest_metrics AS (
    SELECT DISTINCT ON (instrument_id)
        instrument_id, date,
        ret_3m, rs_pctile_3m, ema_20_ratio, extension_pct,
        vol_ratio_63, effort_ratio_63
    FROM atlas.atlas_stock_metrics_daily
    ORDER BY instrument_id, date DESC
),
latest_state AS (
    SELECT DISTINCT ON (instrument_id)
        instrument_id, state, dwell_days, within_state_rank
    FROM atlas.atlas_stock_state_daily
    WHERE classifier_version = 'v2.0-validated'
    ORDER BY instrument_id, date DESC
),
latest_conviction AS (
    SELECT DISTINCT ON (instrument_id)
        instrument_id, verdict, ic
    FROM atlas.atlas_conviction_daily
    WHERE tenure = '3m'
    ORDER BY instrument_id, snapshot_date DESC
),
sector_peers AS (
    SELECT u.instrument_id, u.symbol, u.company_name, u.sector, u.mcap_inr
    FROM atlas.atlas_universe_stocks u
    WHERE u.sector = (
        SELECT sector FROM atlas.atlas_universe_stocks
        WHERE symbol = :sym AND effective_to IS NULL LIMIT 1
    )
    AND u.effective_to IS NULL
    AND u.instrument_id != (
        SELECT instrument_id FROM atlas.atlas_universe_stocks
        WHERE symbol = :sym AND effective_to IS NULL LIMIT 1
    )
    ORDER BY u.mcap_inr DESC NULLS LAST
    LIMIT 4
),
parent AS (
    SELECT u.instrument_id, u.symbol, u.company_name, u.sector, u.mcap_inr,
           TRUE AS is_parent
    FROM atlas.atlas_universe_stocks u
    WHERE u.symbol = :sym AND u.effective_to IS NULL
    LIMIT 1
),
all_stocks AS (
    SELECT *, FALSE AS is_parent FROM sector_peers
    UNION ALL
    SELECT * FROM parent
)
SELECT
    a.symbol, a.company_name, a.is_parent,
    ls.state, ls.dwell_days,
    lc.verdict AS conviction_verdict, lc.ic AS conviction_ic,
    lm.rs_pctile_3m, lm.ret_3m, lm.ema_20_ratio, lm.extension_pct,
    lm.vol_ratio_63, lm.effort_ratio_63
FROM all_stocks a
LEFT JOIN latest_metrics lm ON lm.instrument_id = a.instrument_id
LEFT JOIN latest_state ls ON ls.instrument_id = a.instrument_id
LEFT JOIN latest_conviction lc ON lc.instrument_id = a.instrument_id
ORDER BY a.is_parent DESC, a.mcap_inr DESC NULLS LAST
""")


def _classify_ema_slope(ema_ratio: float | None) -> str:
    """Classify EMA20/price momentum from ema_20_ratio (price / EMA20).

    > 1.02 → Rising
    < 0.98 → Declining
    else   → Flat
    """
    if ema_ratio is None:
        return "—"
    if ema_ratio > 1.02:
        return "Rising"
    if ema_ratio < 0.98:
        return "Declining"
    return "Flat"


def _classify_volume(vol_ratio: float | None) -> str:
    """Classify volume trend from vol_ratio_63 (20D avg / 63D avg).

    > 1.30  → Expanding
    <= 0.80 → Fading
    else    → Stable
    """
    if vol_ratio is None:
        return "—"
    if vol_ratio > 1.30:
        return "Expanding"
    if vol_ratio <= 0.80:
        return "Fading"
    return "Stable"


def _classify_conviction(verdict: str | None) -> str:
    """Map conviction verdict to human-readable label."""
    if verdict == "POSITIVE":
        return "Bullish"
    if verdict == "NEGATIVE":
        return "Bearish"
    return "Neutral"


def get_peer_matrix(symbol: str, engine: Engine | None = None) -> dict[str, Any]:
    """Return parent stock + top-4 sector peers with 8 pre-computed metrics each.

    Returns {"error": "no_data", "symbol": symbol} when the parent symbol is not found.
    """
    engine = engine or get_engine()
    with engine.connect() as conn:
        rows = conn.execute(_PEER_SQL, {"sym": symbol}).mappings().all()

    if not rows:
        return {"error": "no_data", "symbol": symbol}

    peers: list[dict[str, Any]] = []
    for row in rows:
        rs_pctile = float(row["rs_pctile_3m"]) if row["rs_pctile_3m"] is not None else None
        ret_3m = float(row["ret_3m"]) if row["ret_3m"] is not None else None
        ext = float(row["extension_pct"]) if row["extension_pct"] is not None else None
        ema = float(row["ema_20_ratio"]) if row["ema_20_ratio"] is not None else None
        vol = float(row["vol_ratio_63"]) if row["vol_ratio_63"] is not None else None
        ic = float(row["conviction_ic"]) if row["conviction_ic"] is not None else None

        peers.append(
            {
                "symbol": row["symbol"],
                "company_name": row["company_name"],
                "is_parent": bool(row["is_parent"]),
                "stage": row["state"] or "—",
                "conviction": _classify_conviction(row["conviction_verdict"]),
                "conviction_ic": round(ic, 4) if ic is not None else None,
                "rs_vs_nifty": round(rs_pctile * 100, 1) if rs_pctile is not None else None,
                "ema20_slope": _classify_ema_slope(ema),
                "volume": _classify_volume(vol),
                "ret_3m_pct": round(ret_3m * 100, 1) if ret_3m is not None else None,
                "extension_pct": round(ext * 100, 1) if ext is not None else None,
            }
        )

    return {"symbol": symbol, "peers": peers}
