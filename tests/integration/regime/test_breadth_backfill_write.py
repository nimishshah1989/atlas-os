"""Integration test for the breadth backfill's write path.

Regression (2026-05-31): the backfill wrote via ``INSERT ... ON CONFLICT (date)
DO UPDATE`` while omitting ``regime_state`` (NOT NULL, no default). PostgreSQL
validates NOT NULL on the candidate insert row *before* the ON CONFLICT arbiter
redirects to DO UPDATE, so the write failed with a ``regime_state`` NOT-NULL
violation even though the date row already existed. The write must be UPDATE-only
(never construct an INSERT candidate): update existing regime rows, skip dates
that don't exist.

Rollback-wrapped — writes nothing persistent.
"""

from __future__ import annotations

from datetime import date

import pytest
from scripts.backfill_breadth_ema_4wh import _write_breadth_updates

from atlas.db import get_engine


@pytest.mark.integration
def test_write_breadth_updates_updates_existing_and_never_inserts() -> None:
    raw = get_engine().raw_connection()
    try:
        cur = raw.cursor()
        cur.execute("SET statement_timeout = 0")

        existing = date(2016, 4, 29)  # known to exist in atlas_market_regime_daily
        ghost = date(2099, 1, 1)  # does not exist; must NOT be inserted
        # (date, pct_above_ema_20, pct_above_ema_100, pct_4w_high)
        rows = [(existing, 0.55, 0.66, 0.123), (ghost, 0.1, 0.1, 0.1)]

        updated = _write_breadth_updates(raw, rows)

        # Existing row updated with the supplied breadth values.
        cur.execute(
            "SELECT pct_above_ema_20, pct_above_ema_100, pct_4w_high "
            "FROM atlas.atlas_market_regime_daily WHERE date = %s",
            (existing,),
        )
        got = cur.fetchone()
        # numeric columns come back as Decimal; compare as floats
        assert [float(x) for x in got] == pytest.approx([0.55, 0.66, 0.123])

        # Non-existent date was skipped, not inserted (no NOT-NULL violation).
        cur.execute(
            "SELECT count(*) FROM atlas.atlas_market_regime_daily WHERE date = %s",
            (ghost,),
        )
        assert cur.fetchone()[0] == 0
        assert updated == 1  # only the existing row counts as written
    finally:
        raw.rollback()
        raw.close()
