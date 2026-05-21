# pragma: finance-critical
from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog

from atlas.signals.models import TVSignalPayload

log = structlog.get_logger()

# Thresholds in display scale: conviction 0–10, rs_percentile 0–100.
# DB stores both as 0–1 fractions; callers must scale before passing here.
_DUAL_CONFIRM_CONVICTION_MIN = Decimal("6.0")
_DUAL_CONFIRM_RS_PERCENTILE_MIN = Decimal("60.0")
# CTS stage is 1–4; stages 1–3 = accumulation/momentum (buy); 4 = distribution.
# Accepts integers OR label strings like "BUY Stage 2" / "CTS Stage 2 — mid-cycle".
_DUAL_CONFIRM_CTS_BUY_STAGES = frozenset({1, 2, 3})
_CTS_STAGE_LABELS = {
    1: "CTS Stage 1 — early accumulation",
    2: "CTS Stage 2 — mid-cycle",
    3: "CTS Stage 3 — momentum phase",
    4: "CTS Stage 4 — distribution / avoid",
}


def _parse_cts_stage(cts_state: str | int | None) -> int | None:
    if cts_state is None:
        return None
    if isinstance(cts_state, int):
        return cts_state
    m = re.search(r"\b([1-4])\b", str(cts_state))
    return int(m.group(1)) if m else None


def _determine_confirmation_level(
    tier: int,  # pyright: ignore[reportUnusedParameter] — reserved for per-tier thresholds
    conviction_score: Decimal | None,
    cts_state: str | int | None,
    rs_percentile: Decimal | None,
) -> str:
    if conviction_score is None or rs_percentile is None:
        return "tv_only"
    conviction_ok = conviction_score >= _DUAL_CONFIRM_CONVICTION_MIN
    rs_ok = rs_percentile >= _DUAL_CONFIRM_RS_PERCENTILE_MIN
    cts_ok = _parse_cts_stage(cts_state) in _DUAL_CONFIRM_CTS_BUY_STAGES
    if conviction_ok and rs_ok and cts_ok:
        return "dual"
    return "tv_only"


def _resolve_instrument_id(ticker: str, conn: Any) -> str | None:
    """Resolve ticker symbol to instrument_id UUID. Uses atlas_universe_stocks.symbol."""
    from sqlalchemy import text

    row = conn.execute(
        text(
            "SELECT instrument_id FROM atlas.atlas_universe_stocks "
            "WHERE symbol = :symbol AND effective_to IS NULL LIMIT 1"
        ),
        {"symbol": ticker},
    ).fetchone()
    return str(row.instrument_id) if row else None


def _fetch_atlas_intelligence(instrument_id: str, conn: Any) -> dict:
    """Fetch conviction score, CTS state, RS state, and regime from Atlas DB."""
    from sqlalchemy import text

    row = conn.execute(
        text(
            "SELECT c.conviction_score, c.confidence_label AS conviction_trend, "
            "cts.stage AS cts_state, "
            "s.rs_state, "
            "mr.regime_state AS market_regime, "
            "ss.sector_state AS sector_regime "
            "FROM atlas.atlas_stock_conviction_daily c "
            "LEFT JOIN atlas.atlas_cts_signals_daily cts "
            "  ON cts.instrument_id = c.instrument_id AND cts.date = c.date "
            "LEFT JOIN atlas.atlas_stock_states_daily s "
            "  ON s.instrument_id = c.instrument_id AND s.date = c.date "
            "LEFT JOIN atlas.atlas_market_regime_daily mr ON mr.date = c.date "
            "LEFT JOIN atlas.atlas_sector_states_daily ss "
            "  ON ss.sector_name = ("
            "    SELECT sector FROM atlas.atlas_universe_stocks "
            "    WHERE instrument_id = c.instrument_id AND effective_to IS NULL LIMIT 1"
            "  ) AND ss.date = c.date "
            "WHERE c.instrument_id = :iid "
            "ORDER BY c.date DESC LIMIT 1"
        ),
        {"iid": instrument_id},
    ).fetchone()
    if row is None:
        return {}
    return dict(row._mapping)


def _fetch_performance(instrument_id: str, conn: Any) -> dict:
    """Fetch performance returns from atlas_stock_metrics_daily."""
    from sqlalchemy import text

    row = conn.execute(
        text(
            "SELECT ret_1m AS perf_1m, ret_3m AS perf_3m, ret_6m AS perf_6m, "
            "ret_12m AS perf_ytd, "
            "rs_1m_nifty500 AS perf_vs_nifty_1m, "
            "rs_3m_nifty500 AS perf_vs_nifty_ytd, "
            "rs_pctile_1m AS rs_percentile "
            "FROM atlas.atlas_stock_metrics_daily "
            "WHERE instrument_id = :iid "
            "ORDER BY date DESC LIMIT 1"
        ),
        {"iid": instrument_id},
    ).fetchone()
    return dict(row._mapping) if row else {}


def _fetch_company_meta(ticker: str, conn: Any) -> dict:
    """Fetch company name and sector from atlas_universe_stocks."""
    from sqlalchemy import text

    row = conn.execute(
        text(
            "SELECT company_name, sector FROM atlas.atlas_universe_stocks "
            "WHERE symbol = :symbol AND effective_to IS NULL LIMIT 1"
        ),
        {"symbol": ticker},
    ).fetchone()
    return dict(row._mapping) if row else {}


def _build_condition_label(code: str) -> str:
    labels = {
        "breakout_52w_volume": "52-week high breakout with 1.5x volume",
        "rs_breakout_52w": "RS line vs Nifty hits 52-week high",
        "rs_sector_breakout_52w": "RS line vs Sector hits 52-week high",
        "false_breakdown_recovery": "Price reclaims broken support within 5 bars",
        "higher_high": "New swing high above prior pivot high",
        "higher_high_higher_low": "HH + HL within 20 bars (confirmed uptrend)",
        "cross_above_ema200": "Price crosses above 200-day EMA",
        "cross_above_ema50": "Price crosses above 50-day EMA",
        "golden_cross": "50-day EMA crosses above 200-day EMA",
        "all_emas_aligned": "Price > 20/50/200 EMA simultaneously",
        "rsi_cross_50": "RSI crosses above 50 from below",
        "rsi_breakout_3m_high": "RSI breaks above prior 3-month high",
        "macd_bullish_cross_above_zero": "MACD bullish crossover above zero line",
        "lower_low": "New swing low below prior pivot low",
        "rs_breakdown_52w": "RS line vs Nifty hits 52-week low",
        "cross_below_ema200": "Price crosses below 200-day EMA",
        "death_cross": "50-day EMA crosses below 200-day EMA",
    }
    return labels.get(code, code.replace("_", " ").title())


def _verdict_from_tier(tier: int) -> str:
    if tier == 5:
        return "bearish"
    if tier == 1:
        return "bullish"
    return "watch"


async def run_signal_pipeline(payload: TVSignalPayload) -> None:
    from sqlalchemy import text

    from atlas.config import Config
    from atlas.db import get_engine
    from atlas.signals.narrative import generate_narrative
    from atlas.signals.screenshot import capture_chart_screenshots
    from atlas.signals.technical import compute_technical_snapshot

    log.info("signal_pipeline_start", ticker=payload.ticker, code=payload.code)
    engine = get_engine()

    with engine.connect() as conn:
        instrument_id = _resolve_instrument_id(payload.ticker, conn)
        intel = _fetch_atlas_intelligence(instrument_id, conn) if instrument_id else {}
        perf = _fetch_performance(instrument_id, conn) if instrument_id else {}
        meta = _fetch_company_meta(payload.ticker, conn)

        conviction_score = intel.get("conviction_score")
        # cts.stage may be int 1–4 or a label string like "BUY Stage 2"
        cts_stage_raw = intel.get("cts_state")
        stage_int = _parse_cts_stage(cts_stage_raw)
        cts_state = _CTS_STAGE_LABELS.get(stage_int) if stage_int is not None else None
        rs_percentile = perf.get("rs_percentile")

        # DB stores conviction 0–1 and rs_percentile 0–1; thresholds use display scale.
        conviction_disp = (
            Decimal(str(round(float(conviction_score) * 10, 4)))
            if conviction_score is not None
            else None
        )
        rs_pctile_disp = (
            Decimal(str(round(float(rs_percentile) * 100, 4)))
            if rs_percentile is not None
            else None
        )
        confirmation = _determine_confirmation_level(
            tier=payload.tier,
            conviction_score=conviction_disp,
            cts_state=cts_stage_raw,
            rs_percentile=rs_pctile_disp,
        )

        snap = compute_technical_snapshot(payload.ticker, conn)

    screenshots = await capture_chart_screenshots(
        ticker=payload.ticker,
        exchange=payload.exchange,
        layout_id_nifty=Config.TV_LAYOUT_ID_VS_NIFTY,
        layout_id_sector=Config.TV_LAYOUT_ID_VS_SECTOR,
    )

    verdict = _verdict_from_tier(payload.tier)
    context = {
        "ticker": payload.ticker,
        "exchange": payload.exchange,
        "company_name": meta.get("company_name", payload.ticker),
        "condition_label": _build_condition_label(payload.code),
        "confirmation_level": confirmation,
        "verdict": verdict,
        "conviction_score": conviction_score,
        "conviction_trend": intel.get("conviction_trend"),
        "cts_state": cts_state,
        "rs_rank": intel.get("rs_rank"),
        "rs_rank_total": intel.get("rs_rank_total"),
        "rs_percentile": rs_percentile,
        "sector": meta.get("sector"),
        "sector_regime": intel.get("sector_regime"),
        "market_regime": intel.get("market_regime"),
        "rsi_14": float(snap.rsi_14),
        "macd_signal": snap.macd_signal,
        "ema_alignment": snap.ema_alignment,
        "hh_hl_state": snap.hh_hl_state,
        "volume_vs_avg": float(snap.volume_vs_avg),
        "perf_1m": float(perf.get("perf_1m") or 0),
        "perf_3m": float(perf.get("perf_3m") or 0),
        "perf_6m": float(perf.get("perf_6m") or 0),
        "perf_ytd": float(perf.get("perf_ytd") or 0),
        "perf_vs_nifty_1m": float(perf.get("perf_vs_nifty_1m") or 0),
        "perf_vs_nifty_ytd": float(perf.get("perf_vs_nifty_ytd") or 0),
    }

    narrative = await generate_narrative(context)

    triggered_at = datetime.now(UTC)
    with engine.begin() as wconn:
        result = wconn.execute(
            text(
                """INSERT INTO tv_signal_reports (
                    ticker, exchange, company_name, sector,
                    triggered_at, condition_tier, condition_code, condition_label, chart_type,
                    trigger_price, trigger_volume,
                    confirmation_level,
                    conviction_score, conviction_trend, cts_state,
                    rs_rank, rs_rank_total, rs_percentile,
                    sector_regime, market_regime,
                    rsi_14, macd_signal, ema_alignment, hh_hl_state, pattern_label,
                    perf_1m, perf_3m, perf_6m, perf_ytd, perf_vs_nifty_1m, perf_vs_nifty_ytd,
                    chart_daily_url, chart_weekly_url, chart_vs_sector_url,
                    screenshot_daily, screenshot_weekly, screenshot_sector,
                    narrative, verdict
                ) VALUES (
                    :ticker, :exchange, :company_name, :sector,
                    :triggered_at, :tier, :code, :label, :chart,
                    :price, :volume,
                    :confirmation,
                    :conviction_score, :conviction_trend, :cts_state,
                    :rs_rank, :rs_rank_total, :rs_percentile,
                    :sector_regime, :market_regime,
                    :rsi_14, :macd_signal, :ema_alignment, :hh_hl_state, :pattern_label,
                    :perf_1m, :perf_3m, :perf_6m, :perf_ytd, :perf_vs_nifty_1m, :perf_vs_nifty_ytd,
                    :chart_daily_url, :chart_weekly_url, :chart_vs_sector_url,
                    :screenshot_daily, :screenshot_weekly, :screenshot_sector,
                    :narrative, :verdict
                ) RETURNING id"""
            ),
            {
                "ticker": payload.ticker,
                "exchange": payload.exchange,
                "company_name": meta.get("company_name"),
                "sector": meta.get("sector"),
                "triggered_at": triggered_at,
                "tier": payload.tier,
                "code": payload.code,
                "label": _build_condition_label(payload.code),
                "chart": payload.chart,
                "price": payload.close,
                "volume": payload.volume,
                "confirmation": confirmation,
                "conviction_score": conviction_score,
                "conviction_trend": intel.get("conviction_trend"),
                "cts_state": cts_state,
                "rs_rank": intel.get("rs_rank"),
                "rs_rank_total": intel.get("rs_rank_total"),
                "rs_percentile": rs_percentile,
                "sector_regime": intel.get("sector_regime"),
                "market_regime": intel.get("market_regime"),
                "rsi_14": snap.rsi_14,
                "macd_signal": snap.macd_signal,
                "ema_alignment": snap.ema_alignment,
                "hh_hl_state": snap.hh_hl_state,
                "pattern_label": snap.pattern_label,
                "perf_1m": perf.get("perf_1m"),
                "perf_3m": perf.get("perf_3m"),
                "perf_6m": perf.get("perf_6m"),
                "perf_ytd": perf.get("perf_ytd"),
                "perf_vs_nifty_1m": perf.get("perf_vs_nifty_1m"),
                "perf_vs_nifty_ytd": perf.get("perf_vs_nifty_ytd"),
                "chart_daily_url": screenshots.get("daily_url"),
                "chart_weekly_url": screenshots.get("weekly_url"),
                "chart_vs_sector_url": screenshots.get("sector_url"),
                "screenshot_daily": screenshots.get("daily_path"),
                "screenshot_weekly": screenshots.get("weekly_path"),
                "screenshot_sector": screenshots.get("sector_path"),
                "narrative": narrative,
                "verdict": verdict,
            },
        )
        report_row = result.fetchone()

        if report_row:
            severity = (
                "high" if payload.tier == 1 else ("medium" if payload.tier in (2, 5) else "low")
            )
            wconn.execute(
                text(
                    "INSERT INTO atlas_signal_alerts "
                    "(report_id, ticker, alert_type, severity, title, summary) "
                    "VALUES (:rid, :ticker, 'tv_signal', :severity, :title, :summary)"
                ),
                {
                    "rid": report_row.id,
                    "ticker": payload.ticker,
                    "severity": severity,
                    "title": f"{payload.ticker}: {_build_condition_label(payload.code)}",
                    "summary": f"Tier {payload.tier} signal — {confirmation} confirmation",
                },
            )

    log.info("signal_pipeline_complete", ticker=payload.ticker, confirmation=confirmation)
