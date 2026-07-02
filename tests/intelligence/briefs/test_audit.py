"""Integration test for daily-brief persistence. Hits real DB."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from atlas.intelligence.briefs.audit import persist_brief
from atlas.intelligence.briefs.context import DailyMarketContext
from atlas.intelligence.briefs.generator import DailyBrief
from sqlalchemy import text

from atlas.db import get_engine


@pytest.mark.integration
class TestPersistBrief:
    @pytest.fixture(autouse=True)
    def clean_test_rows(self):
        eng = get_engine()
        with eng.connect() as c:
            c.execute(
                text("DELETE FROM atlas.atlas_daily_briefs WHERE as_of_date = :d"),
                {"d": date(1999, 1, 1)},
            )
            c.commit()
        yield
        with eng.connect() as c:
            c.execute(
                text("DELETE FROM atlas.atlas_daily_briefs WHERE as_of_date = :d"),
                {"d": date(1999, 1, 1)},
            )
            c.commit()

    def _sample_ctx(self) -> DailyMarketContext:
        return DailyMarketContext(
            as_of=date(1999, 1, 1),
            regime="Risk-On",
            regime_delta="unchanged",
            deployment_multiplier=Decimal("1.00"),
            breadth={
                "pct_above_ema_50": Decimal("78.4"),
                "india_vix": Decimal("13.2"),
            },
            top_sectors=["NIFTY IT"],
            rotating_out=["NIFTY FMCG"],
            new_breakouts=[],
            new_deteriorations=[],
        )

    def _sample_brief(self) -> DailyBrief:
        return DailyBrief(
            narrative="x " * 220,
            key_themes=["a", "b", "c"],
            regime_summary="bullish",
            top_sector_mentions=["NIFTY IT"],
            model="claude-sonnet-4-6",
            prompt_version="v1",
            input_tokens=1200,
            output_tokens=380,
        )

    def test_insert_round_trip(self):
        eng = get_engine()
        persist_brief(eng, context=self._sample_ctx(), brief=self._sample_brief())

        with eng.connect() as c:
            row = c.execute(
                text("""
                    SELECT regime_state, regime_delta, narrative, key_themes,
                           regime_summary, top_sector_mentions, model,
                           prompt_version, input_tokens, output_tokens
                    FROM atlas.atlas_daily_briefs
                    WHERE as_of_date = :d
                """),
                {"d": date(1999, 1, 1)},
            ).fetchone()
        assert row is not None
        assert row[0] == "Risk-On"
        assert row[1] == "unchanged"
        assert row[4] == "bullish"
        assert row[6] == "claude-sonnet-4-6"
        assert row[7] == "v1"
        assert row[8] == 1200
        assert row[9] == 380

    def test_upsert_on_duplicate_date(self):
        eng = get_engine()
        b1 = self._sample_brief()
        b2 = DailyBrief(
            narrative="updated narrative " * 30,
            key_themes=["x", "y", "z"],
            regime_summary="neutral",
            top_sector_mentions=["NIFTY BANK"],
            model="claude-sonnet-4-6",
            prompt_version="v1",
            input_tokens=1300,
            output_tokens=400,
        )
        persist_brief(eng, context=self._sample_ctx(), brief=b1)
        persist_brief(eng, context=self._sample_ctx(), brief=b2)

        with eng.connect() as c:
            rows = c.execute(
                text(
                    "SELECT regime_summary, input_tokens FROM atlas.atlas_daily_briefs "
                    "WHERE as_of_date = :d"
                ),
                {"d": date(1999, 1, 1)},
            ).fetchall()
        # UNIQUE on as_of_date - exactly one row, with updated values.
        assert len(rows) == 1
        assert rows[0][0] == "neutral"
        assert rows[0][1] == 1300
