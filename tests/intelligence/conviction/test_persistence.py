"""Integration tests for persistence — UPSERT conviction + tier-membership."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from sqlalchemy import text

from atlas.db import get_engine
from atlas.intelligence.conviction.persistence import (
    persist_conviction_batch,
    persist_tier_membership_batch,
)

_SENTINEL_DATE = date(1990, 1, 1)


@pytest.mark.integration
class TestPersist:
    @pytest.fixture(autouse=True)
    def clean_rows(self):
        eng = get_engine()
        with eng.begin() as c:
            c.execute(
                text("DELETE FROM atlas.atlas_stock_conviction_daily " "WHERE date = :d"),
                {"d": _SENTINEL_DATE},
            )
            c.execute(
                text("DELETE FROM atlas.atlas_tier_membership_daily WHERE date = :d"),
                {"d": _SENTINEL_DATE},
            )
        yield
        with eng.begin() as c:
            c.execute(
                text("DELETE FROM atlas.atlas_stock_conviction_daily " "WHERE date = :d"),
                {"d": _SENTINEL_DATE},
            )
            c.execute(
                text("DELETE FROM atlas.atlas_tier_membership_daily WHERE date = :d"),
                {"d": _SENTINEL_DATE},
            )

    def test_persist_conviction_inserts(self) -> None:
        eng = get_engine()
        with eng.connect() as c:
            iid = c.execute(
                text("SELECT instrument_id::text " "FROM atlas.atlas_stock_states_daily LIMIT 1")
            ).scalar()
        assert iid is not None
        df = pd.DataFrame(
            [
                {
                    "instrument_id": iid,
                    "date": _SENTINEL_DATE,
                    "tier": "tier_1_megacap",
                    "conviction_score": 0.7321,
                    "confidence_label": "industry_grade",
                    "backing_ic": 0.0511,
                    "contributing_signals": (
                        '{"ma_30w_slope_4w":{"weight":0.5,'
                        '"flipped":false,"percentile_rank":0.9,'
                        '"contribution":0.45,"was_neutral_fill":false}}'
                    ),
                    "weight_set_version": "tier_1_megacap@2026-05-12T00:00:00",
                }
            ]
        )
        n = persist_conviction_batch(eng, df)
        assert n == 1

    def test_persist_conviction_upsert_updates(self) -> None:
        eng = get_engine()
        with eng.connect() as c:
            iid = c.execute(
                text("SELECT instrument_id::text " "FROM atlas.atlas_stock_states_daily LIMIT 1")
            ).scalar()
        assert iid is not None
        row = {
            "instrument_id": iid,
            "date": _SENTINEL_DATE,
            "tier": "tier_1_megacap",
            "conviction_score": 0.5,
            "confidence_label": "industry_grade",
            "backing_ic": 0.05,
            "contributing_signals": "{}",
            "weight_set_version": "v1",
        }
        persist_conviction_batch(eng, pd.DataFrame([row]))
        row2 = {**row, "conviction_score": 0.9, "weight_set_version": "v2"}
        persist_conviction_batch(eng, pd.DataFrame([row2]))
        with eng.connect() as c:
            r = c.execute(
                text(
                    "SELECT conviction_score, weight_set_version "
                    "FROM atlas.atlas_stock_conviction_daily "
                    "WHERE instrument_id = :iid::uuid AND date = :d"
                ),
                {"iid": iid, "d": _SENTINEL_DATE},
            ).fetchone()
        assert r is not None
        assert float(r[0]) == pytest.approx(0.9)
        assert r[1] == "v2"

    def test_persist_tier_membership_inserts(self) -> None:
        eng = get_engine()
        with eng.connect() as c:
            iid = c.execute(
                text("SELECT instrument_id::text " "FROM atlas.atlas_stock_states_daily LIMIT 1")
            ).scalar()
        assert iid is not None
        df = pd.DataFrame(
            [
                {
                    "instrument_id": iid,
                    "date": _SENTINEL_DATE,
                    "tier": "tier_1_megacap",
                    "adv_rank": 1,
                    "adv_20d": 123456789.00,
                }
            ]
        )
        n = persist_tier_membership_batch(eng, df)
        assert n == 1

    def test_persist_empty_df_is_noop(self) -> None:
        eng = get_engine()
        empty = pd.DataFrame(
            {
                c: pd.Series(dtype=object)
                for c in [
                    "instrument_id",
                    "date",
                    "tier",
                    "conviction_score",
                    "confidence_label",
                    "backing_ic",
                    "contributing_signals",
                    "weight_set_version",
                ]
            }
        )
        assert persist_conviction_batch(eng, empty) == 0
        empty_t = pd.DataFrame(
            {
                c: pd.Series(dtype=object)
                for c in ["instrument_id", "date", "tier", "adv_rank", "adv_20d"]
            }
        )
        assert persist_tier_membership_batch(eng, empty_t) == 0
