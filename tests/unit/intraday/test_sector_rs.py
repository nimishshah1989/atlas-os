"""Intraday sector-RS ratio math — verified against REAL index_prices closes.

Marked `integration` (needs the DB): CLAUDE.md rule #0 forbids synthetic unit-test
inputs, so compute_ratios() is exercised on real sector-index + NIFTY 50 closes
pulled from the data layer, and its output is checked to equal the same
sector_close / nifty_close ratio the EOD chart plots. The DB-less `-m unit` CI job
skips this; it runs in the integration tier and locally.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# _db lives in scripts/foundation (not an installed package) — same access path the
# foundation scripts use.
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "foundation"))
import _db  # pyright: ignore[reportMissingImports]  (added to path above at runtime)

from atlas.intraday.sector_rs import (
    NIFTY_INDEX_SQL,
    RESOLVE_TARGETS_SQL,
    SectorTarget,
    compute_ratios,
)


def _real_inputs():
    """Resolve real (sector → index_token) targets, the NIFTY 50 token, and the
    latest real close for each of those indices from index_prices."""
    tgt_df = _db.read_df(RESOLVE_TARGETS_SQL)
    targets = [
        SectorTarget(str(sector), int(token))
        for sector, token in zip(tgt_df["sector_name"], tgt_df["index_token"], strict=False)
    ]
    nifty_token = int(_db.scalar(NIFTY_INDEX_SQL))

    # Latest close per index (symbol == primary_nse_index), keyed by kite_token.
    closes = _db.read_df(
        """
        SELECT im.kite_token::bigint AS token, ip.close::float AS close
        FROM atlas_foundation.instrument_master im
        JOIN LATERAL (
          SELECT close FROM atlas_foundation.index_prices p
          WHERE p.index_code = im.symbol ORDER BY p.date DESC LIMIT 1
        ) ip ON true
        WHERE im.asset_class = 'index' AND im.kite_token IS NOT NULL
        """
    )
    last_price = {
        int(r.token): float(r.close)
        for r in closes.itertuples(index=False)
        if r.close and r.close > 0
    }
    return targets, nifty_token, last_price


@pytest.mark.integration
def test_ratio_equals_sector_close_over_nifty_close_on_real_data():
    targets, nifty_token, last_price = _real_inputs()
    assert nifty_token in last_price, "NIFTY 50 close missing — cannot verify"
    nifty_close = last_price[nifty_token]

    out = dict(compute_ratios(last_price, targets, nifty_token))
    assert out, "no sector ratios computed from real closes"

    for t in targets:
        if t.index_token in last_price:
            assert t.sector_name in out
            assert out[t.sector_name] == pytest.approx(last_price[t.index_token] / nifty_close)


@pytest.mark.integration
def test_no_nifty_quote_yields_no_rows():
    targets, nifty_token, last_price = _real_inputs()
    without_nifty = {k: v for k, v in last_price.items() if k != nifty_token}
    assert compute_ratios(without_nifty, targets, nifty_token) == []


@pytest.mark.integration
def test_sector_with_missing_or_zero_quote_is_skipped_not_defaulted():
    targets, nifty_token, last_price = _real_inputs()
    assert targets, "no targets resolved"
    dropped = targets[0]
    partial = {k: v for k, v in last_price.items() if k != dropped.index_token}
    out = dict(compute_ratios(partial, targets, nifty_token))
    assert dropped.sector_name not in out  # skipped, never stood-in with a fake ratio
