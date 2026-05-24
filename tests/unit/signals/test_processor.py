import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from atlas.signals.processor import _determine_confirmation_level


def test_confirmation_dual_when_conviction_high():
    result = _determine_confirmation_level(
        tier=1,
        conviction_score=Decimal("7.5"),
        cts_state="BUY Stage 2",
        rs_percentile=Decimal("85.0"),
    )
    assert result == "dual"


def test_confirmation_tv_only_when_conviction_low():
    result = _determine_confirmation_level(
        tier=1,
        conviction_score=Decimal("3.0"),
        cts_state="HOLD",
        rs_percentile=Decimal("40.0"),
    )
    assert result == "tv_only"


def test_confirmation_tv_only_when_no_conviction():
    result = _determine_confirmation_level(
        tier=1,
        conviction_score=None,
        cts_state=None,
        rs_percentile=None,
    )
    assert result == "tv_only"


def test_confirmation_dual_requires_both_conviction_and_rs():
    result = _determine_confirmation_level(
        tier=1,
        conviction_score=Decimal("8.0"),
        cts_state="BUY Stage 2",
        rs_percentile=Decimal("30.0"),
    )
    assert result == "tv_only"


def test_confirmation_tv_only_when_missing_rs():
    result = _determine_confirmation_level(
        tier=1,
        conviction_score=Decimal("8.0"),
        cts_state="BUY Stage 2",
        rs_percentile=None,
    )
    assert result == "tv_only"


def test_build_condition_label_known_code():
    from atlas.signals.processor import _build_condition_label

    assert _build_condition_label("breakout_52w_volume") == "52-week high breakout with 1.5x volume"


def test_build_condition_label_unknown_code_titlecases():
    from atlas.signals.processor import _build_condition_label

    assert _build_condition_label("some_unknown_code") == "Some Unknown Code"


def test_verdict_bullish_for_tier_1():
    from atlas.signals.processor import _verdict_from_tier

    assert _verdict_from_tier(1) == "bullish"


def test_verdict_bearish_for_tier_5():
    from atlas.signals.processor import _verdict_from_tier

    assert _verdict_from_tier(5) == "bearish"


def test_verdict_watch_for_other_tiers():
    from atlas.signals.processor import _verdict_from_tier

    assert _verdict_from_tier(3) == "watch"


# ---------------------------------------------------------------------------
# _parse_cts_stage
# ---------------------------------------------------------------------------


def test_parse_cts_stage_none_returns_none():
    from atlas.signals.processor import _parse_cts_stage

    assert _parse_cts_stage(None) is None


def test_parse_cts_stage_int_returns_int():
    from atlas.signals.processor import _parse_cts_stage

    assert _parse_cts_stage(3) == 3


def test_parse_cts_stage_label_extracts_digit():
    from atlas.signals.processor import _parse_cts_stage

    assert _parse_cts_stage("BUY Stage 2") == 2


def test_parse_cts_stage_unrecognised_returns_none():
    from atlas.signals.processor import _parse_cts_stage

    assert _parse_cts_stage("HOLD") is None


# ---------------------------------------------------------------------------
# DB helper functions
# ---------------------------------------------------------------------------


def _make_mock_conn(fetchone_return=None, fetchall_return=None):
    mock_result = MagicMock()
    mock_result.fetchone.return_value = fetchone_return
    if fetchall_return is not None:
        mock_result.fetchall.return_value = fetchall_return
    mock_conn = MagicMock()
    mock_conn.execute.return_value = mock_result
    return mock_conn


def test_resolve_instrument_id_found():
    from atlas.signals.processor import _resolve_instrument_id

    mock_row = MagicMock()
    mock_row.instrument_id = "abc-uuid-123"
    conn = _make_mock_conn(fetchone_return=mock_row)
    result = _resolve_instrument_id("HDFCBANK", conn)
    assert result == "abc-uuid-123"


def test_resolve_instrument_id_not_found():
    from atlas.signals.processor import _resolve_instrument_id

    conn = _make_mock_conn(fetchone_return=None)
    result = _resolve_instrument_id("UNKNOWN", conn)
    assert result is None


def test_fetch_atlas_intelligence_found():
    from atlas.signals.processor import _fetch_atlas_intelligence

    mock_row = MagicMock()
    mock_row._mapping = {
        "conviction_score": 0.75,
        "cts_state": "BUY Stage 2",
        "rs_state": "LEADER",
        "market_regime": "risk_on",
        "sector_regime": "constructive",
        "conviction_trend": "rising",
    }
    conn = _make_mock_conn(fetchone_return=mock_row)
    result = _fetch_atlas_intelligence("abc-uuid-123", conn)
    assert result["conviction_score"] == 0.75


def test_fetch_atlas_intelligence_not_found():
    from atlas.signals.processor import _fetch_atlas_intelligence

    conn = _make_mock_conn(fetchone_return=None)
    result = _fetch_atlas_intelligence("abc-uuid-123", conn)
    assert result == {}


def test_fetch_performance_found():
    from atlas.signals.processor import _fetch_performance

    mock_row = MagicMock()
    mock_row._mapping = {
        "perf_1m": 0.05,
        "perf_3m": 0.12,
        "perf_6m": 0.20,
        "perf_ytd": 0.30,
        "perf_vs_nifty_1m": 0.03,
        "perf_vs_nifty_ytd": 0.10,
        "rs_percentile": 0.85,
    }
    conn = _make_mock_conn(fetchone_return=mock_row)
    result = _fetch_performance("abc-uuid-123", conn)
    assert result["rs_percentile"] == 0.85


def test_fetch_performance_not_found():
    from atlas.signals.processor import _fetch_performance

    conn = _make_mock_conn(fetchone_return=None)
    result = _fetch_performance("abc-uuid-123", conn)
    assert result == {}


def test_fetch_company_meta_found():
    from atlas.signals.processor import _fetch_company_meta

    mock_row = MagicMock()
    mock_row._mapping = {"company_name": "HDFC Bank", "sector": "Banking"}
    conn = _make_mock_conn(fetchone_return=mock_row)
    result = _fetch_company_meta("HDFCBANK", conn)
    assert result["company_name"] == "HDFC Bank"


def test_fetch_company_meta_not_found():
    from atlas.signals.processor import _fetch_company_meta

    conn = _make_mock_conn(fetchone_return=None)
    result = _fetch_company_meta("UNKNOWN", conn)
    assert result == {}


# ---------------------------------------------------------------------------
# run_signal_pipeline
# ---------------------------------------------------------------------------


def _make_full_pipeline_mocks() -> MagicMock:
    """Build a complete set of mocks for run_signal_pipeline."""
    mock_row = MagicMock()
    mock_row._mapping = {
        "conviction_score": 0.75,
        "cts_state": "BUY Stage 2",
        "rs_state": "LEADER",
        "market_regime": "risk_on",
        "sector_regime": "constructive",
        "conviction_trend": "rising",
    }
    perf_row = MagicMock()
    perf_row._mapping = {
        "perf_1m": 0.05,
        "perf_3m": 0.12,
        "perf_6m": 0.20,
        "perf_ytd": 0.30,
        "perf_vs_nifty_1m": 0.03,
        "perf_vs_nifty_ytd": 0.10,
        "rs_percentile": 0.85,
    }
    meta_row = MagicMock()
    meta_row._mapping = {"company_name": "HDFC Bank", "sector": "Banking"}
    iid_row = MagicMock()
    iid_row.instrument_id = "abc-uuid-123"

    insert_result = MagicMock()
    insert_result.fetchone.return_value = MagicMock(id="report-uuid-456")

    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.execute.side_effect = [
        MagicMock(fetchone=MagicMock(return_value=iid_row)),
        MagicMock(fetchone=MagicMock(return_value=mock_row)),
        MagicMock(fetchone=MagicMock(return_value=perf_row)),
        MagicMock(fetchone=MagicMock(return_value=meta_row)),
        insert_result,
        MagicMock(),
    ]

    engine = MagicMock()
    engine.connect.return_value = conn
    engine.begin.return_value.__enter__ = MagicMock(return_value=conn)
    engine.begin.return_value.__exit__ = MagicMock(return_value=False)
    return engine


def test_run_signal_pipeline_completes() -> None:
    from atlas.signals.models import TVSignalPayload
    from atlas.signals.processor import run_signal_pipeline

    payload = TVSignalPayload(
        tier=1,
        code="breakout_52w_volume",
        chart="vs_nifty",
        ticker="HDFCBANK",
        exchange="NSE",
        close=Decimal("1820.50"),
        volume=4500000,
        time="2026-05-13T09:20:00Z",
    )
    engine = _make_full_pipeline_mocks()

    mock_snap = MagicMock()
    mock_snap.rsi_14 = Decimal("55.0")
    mock_snap.macd_signal = "bullish"
    mock_snap.ema_alignment = "all_bullish"
    mock_snap.hh_hl_state = "confirmed_uptrend"
    mock_snap.volume_vs_avg = Decimal("1.5")
    mock_snap.pattern_label = "breakout"

    with (
        patch("atlas.db.get_engine", return_value=engine),
        patch(
            "atlas.signals.technical.compute_technical_snapshot",
            return_value=mock_snap,
        ),
        patch(
            "atlas.signals.screenshot.capture_chart_screenshots",
            new_callable=AsyncMock,
            return_value={},
        ),
        patch(
            "atlas.signals.narrative.generate_narrative",
            new_callable=AsyncMock,
            return_value="Test narrative",
        ),
        patch("atlas.config.Config"),
    ):
        asyncio.run(run_signal_pipeline(payload))
