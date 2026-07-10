"""Intraday sector relative-strength (RS = sector NSE index ÷ NIFTY 50).

Pure ratio math + the SQL the live builder uses. Deliberately free of DB/network
handles so compute_ratios() unit-tests against REAL index_prices closes with no
Kite call and no synthetic fixtures (CLAUDE.md rule #0).

Ratio ≡ sector_index_ltp / nifty50_ltp — the SAME quantity getSectorRatioSeries()
plots at EOD, so the intraday tail is continuous with the daily close history.

The live builder (scripts/foundation/build_sector_rs_intraday.py) resolves each
active sector's NSE-index kite_token + the NIFTY 50 token (all 21 active sectors
carry a quotable token in instrument_master), pulls one batched kite.quote(), and
turns the ticks into (sector_name, ts, ratio) rows.
"""

from __future__ import annotations

from dataclasses import dataclass

NIFTY50_SYMBOL = "NIFTY 50"

# Every active sector → its primary NSE index kite_token. Indices carry a token in
# instrument_master (same owner as OHLCV), so no separate symbol-mapping table.
RESOLVE_TARGETS_SQL = """
SELECT sm.sector_name, im.kite_token::bigint AS index_token
FROM atlas_foundation.atlas_sector_master sm
JOIN atlas_foundation.instrument_master im
  ON im.symbol = sm.primary_nse_index AND im.asset_class = 'index'
WHERE sm.is_active = true AND im.kite_token IS NOT NULL
ORDER BY sm.sector_name
"""

NIFTY_INDEX_SQL = """
SELECT kite_token::bigint FROM atlas_foundation.instrument_master
WHERE asset_class = 'index' AND symbol = 'NIFTY 50' AND kite_token IS NOT NULL
LIMIT 1
"""

# Its own table (never index_prices) so the EOD-only ingest guard is untouched.
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS atlas_foundation.atlas_sector_rs_intraday (
  sector_name text NOT NULL,
  ts timestamptz NOT NULL,
  ratio numeric NOT NULL,
  PRIMARY KEY (sector_name, ts)
)
"""

# Today-only retention: drop everything before the start of the current IST day, so
# the table holds just today's live path (the chart already owns the daily history).
PRUNE_SQL = """
DELETE FROM atlas_foundation.atlas_sector_rs_intraday
WHERE ts < (date_trunc('day', now() AT TIME ZONE 'Asia/Kolkata') AT TIME ZONE 'Asia/Kolkata')
"""


@dataclass(frozen=True)
class SectorTarget:
    sector_name: str
    index_token: int


def compute_ratios(
    last_price: dict[int, float],
    targets: list[SectorTarget],
    nifty_token: int,
) -> list[tuple[str, float]]:
    """(sector_name, ratio) for every target whose sector LTP and the NIFTY 50 LTP
    are both present and > 0. A missing or non-positive quote is skipped, never
    defaulted to a stand-in ratio (CLAUDE.md rule #0)."""
    nifty = last_price.get(nifty_token)
    if not nifty or nifty <= 0:
        return []
    out: list[tuple[str, float]] = []
    for t in targets:
        px = last_price.get(t.index_token)
        if px is None or px <= 0:
            continue
        out.append((t.sector_name, px / nifty))
    return out
