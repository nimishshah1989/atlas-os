"""Unit tests for DailyMarketContext builder. No DB - engine is mocked."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from atlas.intelligence.briefs.context import (
    DailyMarketContext,
    build_daily_context,
)


def _mock_engine_with_rows(view_rows: dict[str, list[dict]]) -> MagicMock:
    """Return an engine whose .connect().__enter__() returns a conn where
    conn.execute(stmt) returns a Result whose .mappings().fetchall() /
    .fetchone() returns the rows mapped from the SQL string substring.

    view_rows keys are substrings of the SQL that route to row lists.
    """

    def _execute_side_effect(stmt, params=None):
        sql_text = str(stmt)
        rows = []
        for key, value in view_rows.items():
            if key in sql_text:
                rows = value
                break
        mapping_proxy = MagicMock()
        mapping_proxy.fetchall.return_value = rows
        mapping_proxy.fetchone.return_value = rows[0] if rows else None
        result = MagicMock()
        result.mappings.return_value = mapping_proxy
        return result

    conn = MagicMock()
    conn.execute.side_effect = _execute_side_effect
    cm = MagicMock()
    cm.__enter__.return_value = conn
    cm.__exit__.return_value = False
    eng = MagicMock()
    eng.connect.return_value = cm
    return eng


def test_build_context_happy_path() -> None:
    eng = _mock_engine_with_rows(
        {
            "mv_current_market_regime": [
                {
                    "date": date(2026, 5, 12),
                    "regime_state": "Risk-On",
                    "deployment_multiplier": Decimal("1.00"),
                    "pct_above_ema_50": Decimal("78.4"),
                    "mcclellan_oscillator": Decimal("45.2"),
                    "ad_ratio": Decimal("1.85"),
                    "net_new_highs": 47,
                    "india_vix": Decimal("13.2"),
                }
            ],
            "atlas_market_regime_daily": [
                {
                    "regime_state": "Risk-On",
                    "deployment_multiplier": Decimal("1.00"),
                }
            ],
            "mv_sector_rotation_state": [
                {
                    "sector_name": "NIFTY IT",
                    "rs_pctile_cross_sector": Decimal("0.92"),
                    "rs_velocity": Decimal("0.04"),
                },
                {
                    "sector_name": "NIFTY AUTO",
                    "rs_pctile_cross_sector": Decimal("0.88"),
                    "rs_velocity": Decimal("0.03"),
                },
                {
                    "sector_name": "NIFTY BANK",
                    "rs_pctile_cross_sector": Decimal("0.75"),
                    "rs_velocity": Decimal("0.02"),
                },
                {
                    "sector_name": "NIFTY PSE",
                    "rs_pctile_cross_sector": Decimal("0.20"),
                    "rs_velocity": Decimal("-0.05"),
                },
                {
                    "sector_name": "NIFTY FMCG",
                    "rs_pctile_cross_sector": Decimal("0.30"),
                    "rs_velocity": Decimal("-0.04"),
                },
                {
                    "sector_name": "NIFTY PHARMA",
                    "rs_pctile_cross_sector": Decimal("0.35"),
                    "rs_velocity": Decimal("-0.03"),
                },
            ],
            "mv_breakout_candidates": [
                {
                    "symbol": "TCS",
                    "company_name": "Tata Consultancy",
                    "sector": "NIFTY IT",
                    "new_rs_state": "Leader",
                },
            ],
            "mv_deterioration_watch": [
                {
                    "symbol": "HUL",
                    "company_name": "Hindustan Unilever",
                    "sector": "NIFTY FMCG",
                    "prior_rs_state": "Strong",
                },
            ],
        }
    )

    ctx = build_daily_context(eng, as_of=date(2026, 5, 12))

    assert isinstance(ctx, DailyMarketContext)
    assert ctx.as_of == date(2026, 5, 12)
    assert ctx.regime == "Risk-On"
    assert ctx.regime_delta == "unchanged"
    assert ctx.deployment_multiplier == Decimal("1.00")
    assert ctx.breadth["pct_above_ema_50"] == Decimal("78.4")
    assert ctx.breadth["india_vix"] == Decimal("13.2")
    assert ctx.top_sectors == ["NIFTY IT", "NIFTY AUTO", "NIFTY BANK"]
    # rotating_out = bottom 3 by rs_velocity (most negative first)
    assert ctx.rotating_out[0] == "NIFTY PSE"
    assert len(ctx.new_breakouts) == 1
    assert ctx.new_breakouts[0]["symbol"] == "TCS"
    assert ctx.new_deteriorations[0]["symbol"] == "HUL"


def test_build_context_regime_upgrade_detected() -> None:
    eng = _mock_engine_with_rows(
        {
            "mv_current_market_regime": [
                {
                    "date": date(2026, 5, 12),
                    "regime_state": "Risk-On",
                    "deployment_multiplier": Decimal("1.00"),
                    "pct_above_ema_50": Decimal("78.4"),
                    "mcclellan_oscillator": Decimal("45.2"),
                    "ad_ratio": Decimal("1.85"),
                    "net_new_highs": 47,
                    "india_vix": Decimal("13.2"),
                }
            ],
            "atlas_market_regime_daily": [
                {
                    "regime_state": "Neutral",
                    "deployment_multiplier": Decimal("0.70"),
                }
            ],
            "mv_sector_rotation_state": [],
            "mv_breakout_candidates": [],
            "mv_deterioration_watch": [],
        }
    )

    ctx = build_daily_context(eng, as_of=date(2026, 5, 12))
    assert ctx.regime_delta == "upgraded"


def test_build_context_regime_downgrade_detected() -> None:
    eng = _mock_engine_with_rows(
        {
            "mv_current_market_regime": [
                {
                    "date": date(2026, 5, 12),
                    "regime_state": "Risk-Off",
                    "deployment_multiplier": Decimal("0.40"),
                    "pct_above_ema_50": Decimal("32.1"),
                    "mcclellan_oscillator": Decimal("-30.5"),
                    "ad_ratio": Decimal("0.55"),
                    "net_new_highs": -15,
                    "india_vix": Decimal("21.4"),
                }
            ],
            "atlas_market_regime_daily": [
                {
                    "regime_state": "Neutral",
                    "deployment_multiplier": Decimal("0.70"),
                }
            ],
            "mv_sector_rotation_state": [],
            "mv_breakout_candidates": [],
            "mv_deterioration_watch": [],
        }
    )

    ctx = build_daily_context(eng, as_of=date(2026, 5, 12))
    assert ctx.regime_delta == "downgraded"


def test_build_context_to_dict_is_json_serialisable() -> None:
    import json

    eng = _mock_engine_with_rows(
        {
            "mv_current_market_regime": [
                {
                    "date": date(2026, 5, 12),
                    "regime_state": "Neutral",
                    "deployment_multiplier": Decimal("0.70"),
                    "pct_above_ema_50": Decimal("55.0"),
                    "mcclellan_oscillator": Decimal("0.0"),
                    "ad_ratio": Decimal("1.0"),
                    "net_new_highs": 0,
                    "india_vix": Decimal("15.0"),
                }
            ],
            "atlas_market_regime_daily": [],
            "mv_sector_rotation_state": [],
            "mv_breakout_candidates": [],
            "mv_deterioration_watch": [],
        }
    )

    ctx = build_daily_context(eng, as_of=date(2026, 5, 12))
    payload = ctx.to_dict()
    # Must round-trip through JSON without TypeError
    serialised = json.dumps(payload)
    restored = json.loads(serialised)
    assert restored["regime"] == "Neutral"
    assert restored["as_of"] == "2026-05-12"
