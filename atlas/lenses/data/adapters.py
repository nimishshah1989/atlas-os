"""Data adapters for the six-lens scoring engine.

Read from foundation_staging + atlas tables, feed data to pure scorers,
write results to atlas.atlas_lens_scores_daily.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.compute._session import bulk_upsert, df_to_pg_rows, open_compute_session
from atlas.db import get_engine, load_thresholds

log = structlog.get_logger()
_IST = ZoneInfo("Asia/Kolkata")

# NSE trading-calendar source of truth. We use index-level NIFTY 50 sessions
# (foundation_staging.index_prices) rather than raw technical_daily DISTINCT
# dates (which carry sparse 2-/10-row junk rows on holidays) or
# public.de_trading_calendar (which mislabels the Budget-day special Sunday
# session as a weekend and is synthetically future-dated). Membership-by-presence
# is what correctly KEEPS the Budget-Sunday session (2026-02-01) while rejecting
# weekends and NSE holidays — never use weekday arithmetic.
_NSE_CAL_INDEX = "NIFTY 50"


def latest_trading_day(engine: Engine, ref: date | None = None) -> date:
    """Latest real NSE trading day on or before *ref* (default today).

    Resolves against the NIFTY 50 session calendar. Raises if no session
    exists on/before *ref* (e.g. a ref before the calendar's first date).
    """
    ref = ref or datetime.now(_IST).date()
    sql = text(
        "SELECT max(date) FROM foundation_staging.index_prices "
        "WHERE index_code = :idx AND date <= :ref"
    )
    with open_compute_session(engine) as conn:
        d = conn.execute(sql, {"idx": _NSE_CAL_INDEX, "ref": ref}).scalar()
    if d is None:
        raise ValueError(f"No NSE trading day on or before {ref}")
    return d


def is_trading_day(engine: Engine, d: date) -> bool:
    """True iff *d* is a real NSE session (present in the NIFTY 50 calendar)."""
    sql = text(
        "SELECT EXISTS(SELECT 1 FROM foundation_staging.index_prices "
        "WHERE index_code = :idx AND date = :d)"
    )
    with open_compute_session(engine) as conn:
        return bool(conn.execute(sql, {"idx": _NSE_CAL_INDEX, "d": d}).scalar())


def load_technical_data(engine: Engine, as_of: date) -> pd.DataFrame:
    """Load technical daily + tv_metrics for all instruments on as_of date."""
    sql = text("""
        SELECT t.instrument_id, t.symbol, t.asset_class,
               t.ema_21, t.ema_50, t.ema_200, t.rsi_14,
               t.ret_1w,
               t.rs_1m_n500, t.rs_3m_n500, t.rs_6m_n500, t.rs_12m_n500,
               tv.atr_14, tv.bb_width,
               tv.price, tv.high_52w, tv.low_52w,
               tv.volume, tv.avg_volume_30d, tv.avg_volume_60d, tv.rel_volume_10d
        FROM foundation_staging.technical_daily t
        LEFT JOIN atlas.tv_metrics tv ON tv.instrument_id = t.instrument_id
        WHERE t.date = :dt
    """)
    with open_compute_session(engine) as conn:
        return pd.read_sql(sql, conn, params={"dt": as_of})


def load_fundamental_data(engine: Engine) -> pd.DataFrame:
    """Load fundamental metrics from tv_metrics for all instruments."""
    sql = text("""
        SELECT instrument_id, symbol,
               roe, roa, roic,
               operating_margin, net_margin, gross_margin,
               revenue_growth_yoy, eps_growth_yoy,
               debt_to_equity, current_ratio, quick_ratio,
               revenue_ttm, eps_diluted_ttm
        FROM atlas.tv_metrics
        WHERE instrument_id IS NOT NULL
    """)
    with open_compute_session(engine) as conn:
        return pd.read_sql(sql, conn)


def load_valuation_data(engine: Engine) -> pd.DataFrame:
    """Load valuation metrics from tv_metrics + sector median PE."""
    sql = text("""
        WITH sector_medians AS (
            SELECT
                u.sector,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY tv.pe_ttm)
                    FILTER (WHERE tv.pe_ttm > 0 AND tv.pe_ttm < 500)
                    AS sector_median_pe
            FROM atlas.tv_metrics tv
            JOIN atlas.atlas_universe_stocks u ON u.instrument_id = tv.instrument_id
            WHERE u.sector IS NOT NULL AND u.effective_to IS NULL
            GROUP BY u.sector
        )
        SELECT tv.instrument_id, tv.symbol,
               tv.pe_ttm, tv.pb_fbs, tv.ev_ebitda,
               tv.price, tv.high_52w, tv.low_52w, tv.ema_200,
               sm.sector_median_pe
        FROM atlas.tv_metrics tv
        JOIN foundation_staging.instrument_master im ON im.instrument_id = tv.instrument_id
        LEFT JOIN atlas.atlas_universe_stocks u
            ON u.instrument_id = tv.instrument_id AND u.effective_to IS NULL
        LEFT JOIN sector_medians sm ON sm.sector = u.sector
        WHERE tv.instrument_id IS NOT NULL AND im.asset_class = 'stock' AND im.kite_token IS NOT NULL
    """)
    with open_compute_session(engine) as conn:
        return pd.read_sql(sql, conn)


def load_catalyst_data(
    engine: Engine, lookback_days: int = 365, as_of: date | None = None,
) -> pd.DataFrame:
    """Load filings from lens_filings for each instrument (last N days).

    When *as_of* is given, uses it as the upper bound instead of CURRENT_DATE
    so that historical runs are point-in-time correct.
    """
    if as_of is not None:
        sql = text("""
            SELECT instrument_id, symbol, filing_date, category,
                   category_bucket, signal_priority, subject_text, source_url
            FROM foundation_staging.lens_filings
            WHERE filing_date >= :as_of - :lb AND filing_date <= :as_of
            ORDER BY instrument_id, filing_date DESC
        """)
        params: dict[str, Any] = {"lb": lookback_days, "as_of": as_of}
    else:
        sql = text("""
            SELECT instrument_id, symbol, filing_date, category,
                   category_bucket, signal_priority, subject_text, source_url
            FROM foundation_staging.lens_filings
            WHERE filing_date >= CURRENT_DATE - :lb
            ORDER BY instrument_id, filing_date DESC
        """)
        params = {"lb": lookback_days}
    with open_compute_session(engine) as conn:
        return pd.read_sql(sql, conn, params=params)


def load_flow_data(
    engine: Engine, as_of: date | None = None,
) -> dict[str, pd.DataFrame]:
    """Load insider transactions, shareholding, and bulk deals.

    When *as_of* is given, all date filters use it as the ceiling so that
    historical runs are point-in-time correct.
    """
    with open_compute_session(engine) as conn:
        if as_of is not None:
            insider = pd.read_sql(text("""
                SELECT instrument_id, symbol, signal_type, value_cr, person_name,
                       pledge_pct_after, transaction_date, price_per_share
                FROM foundation_staging.lens_insider
                WHERE transaction_date >= :as_of - INTERVAL '365 days'
                  AND transaction_date <= :as_of
                ORDER BY instrument_id, transaction_date DESC
            """), conn, params={"as_of": as_of})

            shareholding = pd.read_sql(text("""
                SELECT instrument_id, symbol, period_end, promoter_pct, public_pct
                FROM foundation_staging.lens_shareholding
                WHERE period_end <= :as_of
                ORDER BY instrument_id, period_end DESC
            """), conn, params={"as_of": as_of})

            bulk_deals = pd.read_sql(text("""
                SELECT instrument_id, symbol, deal_date, client_name, buy_sell,
                       qty, price, is_institutional, is_superstar, superstar_name
                FROM foundation_staging.lens_bulk_deals
                WHERE deal_date >= :as_of - INTERVAL '90 days'
                  AND deal_date <= :as_of
                ORDER BY instrument_id, deal_date DESC
            """), conn, params={"as_of": as_of})
        else:
            insider = pd.read_sql(text("""
                SELECT instrument_id, symbol, signal_type, value_cr, person_name,
                       pledge_pct_after, transaction_date, price_per_share
                FROM foundation_staging.lens_insider
                WHERE transaction_date >= CURRENT_DATE - INTERVAL '365 days'
                ORDER BY instrument_id, transaction_date DESC
            """), conn)

            shareholding = pd.read_sql(text("""
                SELECT instrument_id, symbol, period_end, promoter_pct, public_pct
                FROM foundation_staging.lens_shareholding
                ORDER BY instrument_id, period_end DESC
            """), conn)

            bulk_deals = pd.read_sql(text("""
                SELECT instrument_id, symbol, deal_date, client_name, buy_sell,
                       qty, price, is_institutional, is_superstar, superstar_name
                FROM foundation_staging.lens_bulk_deals
                WHERE deal_date >= CURRENT_DATE - INTERVAL '90 days'
                ORDER BY instrument_id, deal_date DESC
            """), conn)

    return {"insider": insider, "shareholding": shareholding, "bulk_deals": bulk_deals}


def load_policy_registry(engine: Engine) -> list[dict[str, Any]]:
    """Load active policies from atlas.policy_registry."""
    sql = text("""
        SELECT policy_id, policy_name, description, impact,
               beneficiary_sectors, beneficiary_keywords
        FROM atlas.policy_registry
        WHERE is_active = TRUE
    """)
    with open_compute_session(engine) as conn:
        rows = conn.execute(sql).mappings().all()
    return [dict(r) for r in rows]


def load_instrument_sectors(engine: Engine) -> pd.DataFrame:
    """Load sector/industry for all active stocks from instrument_master.

    Sector/industry come from atlas_universe_stocks (left join), so instruments
    not yet in the curated universe still get scored but with NULL sector.
    """
    sql = text("""
        SELECT im.instrument_id, im.symbol, u.sector, u.industry
        FROM foundation_staging.instrument_master im
        LEFT JOIN atlas.atlas_universe_stocks u
            ON u.instrument_id = im.instrument_id AND u.effective_to IS NULL
        WHERE im.asset_class = 'stock' AND im.kite_token IS NOT NULL
    """)
    with open_compute_session(engine) as conn:
        return pd.read_sql(sql, conn)


def write_lens_scores(
    engine: Engine,
    results: list[dict[str, Any]],
    run_id: uuid.UUID | None = None,
) -> int:
    """Upsert scored results into atlas.atlas_lens_scores_daily."""
    if not results:
        return 0
    columns = [
        "instrument_id", "date", "asset_class",
        "technical", "fundamental", "valuation", "catalyst", "flow", "policy",
        "tech_trend", "tech_rs", "tech_vol_contraction", "tech_volume",
        "fund_profitability", "fund_margin", "fund_growth", "fund_balance_sheet", "fund_op_leverage",
        "val_pe_vs_sector", "val_absolute_pe", "val_pb", "val_ev_ebitda", "val_52w_position",
        "cat_earnings_strategy", "cat_capital_action", "cat_governance",
        "flow_promoter", "flow_institutional", "flow_smart_money",
        "policy_tailwind",
        "composite", "conviction_tier", "valuation_zone", "valuation_multiplier",
        "smart_money_score", "degradation_score",
        "risk_flags", "evidence",
        "lenses_active", "coverage_factor",
        "compute_run_id", "computed_at",
    ]
    rows = []
    now = datetime.now(_IST)
    rid = run_id or uuid.uuid4()
    for r in results:
        row = tuple(r.get(c, rid if c == "compute_run_id" else now if c == "computed_at" else None) for c in columns)
        rows.append(row)
    return bulk_upsert(
        engine, "atlas.atlas_lens_scores_daily", columns, rows,
        pk_columns=["instrument_id", "date"],
    )


def purge_stale_lens_scores(
    engine: Engine,
    dt: date,
    run_id: uuid.UUID,
    asset_class: str = "stock",
) -> int:
    """Delete rows for (date, asset_class) left behind by EARLIER runs.

    The writer upserts by (instrument_id, date); if the scored universe shrinks
    between runs, rows for instruments no longer in the universe would linger
    (the cause of the 2102-vs-2093 drift). Removing rows whose compute_run_id
    differs from the current run keeps the journal equal to exactly what this
    run produced. Scoped by asset_class so it never touches ETF/index/sector
    roll-ups written by a different process/run.
    """
    sql = text(
        "DELETE FROM atlas.atlas_lens_scores_daily "
        "WHERE date = :dt AND asset_class = :ac AND compute_run_id <> :rid"
    )
    with open_compute_session(engine) as conn:
        res = conn.execute(sql, {"dt": dt, "ac": asset_class, "rid": run_id})
        conn.commit()
        return res.rowcount or 0
