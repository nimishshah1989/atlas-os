"""Data adapters for the six-lens scoring engine.

Read from foundation_staging + atlas tables, feed data to pure scorers,
write results to atlas.atlas_lens_scores_daily.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.compute._session import bulk_upsert, open_compute_session

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


# Financial reporting availability lags (FM-proposed, DECISIONS D-LoopC): a quarter
# / annual filing is treated as KNOWABLE only `lag` days after its period_end (the
# only honest as-of proxy without a filing-date column). Conservative so the journal
# never uses a result before a human could have. Persisted to atlas_thresholds in
# the IC step; defaulted here so the rebuild needs no DB write.
REPORTING_LAG_Q = 60   # quarterly income statement
REPORTING_LAG_A = 90   # annual balance sheet (filed later than quarterlies)


def load_technical_data(engine: Engine, as_of: date) -> pd.DataFrame:
    """Point-in-time technical inputs for all instruments on *as_of*.

    EMA/RSI/RS/ATR/BB/vol_ratio/pos_52w/rs_*_sector come from technical_daily ON
    that date (all PIT). The as-of price comes from ohlcv_stock on that date:
    `price_adj` (adjusted close, the basis EMA/ATR were computed on — used by the
    technical lens) and `close_raw` (actual traded close — used for the valuation
    PE). This replaces the old LEFT JOIN to the atlas.tv_metrics SNAPSHOT, which
    stamped today's price/52w/volume/ATR on every historical date (the Loop C leak).
    """
    sql = text("""
        SELECT t.instrument_id, t.symbol, t.asset_class,
               t.ema_21, t.ema_50, t.ema_200, t.rsi_14, t.ret_1w,
               t.rs_1m_n500, t.rs_3m_n500, t.rs_6m_n500, t.rs_12m_n500,
               t.rs_1m_sector, t.rs_3m_sector, t.rs_6m_sector, t.rs_12m_sector,
               t.atr_14, t.bb_width, t.vol_ratio_30d, t.vol_ratio_60d, t.pos_52w,
               COALESCE(o.close_adj, o.close) AS price_adj,
               o.close AS close_raw, o.volume
        FROM foundation_staging.technical_daily t
        LEFT JOIN foundation_staging.ohlcv_stock o
          ON o.instrument_id = t.instrument_id AND o.date = t.date
        WHERE t.date = :dt
    """)
    with open_compute_session(engine) as conn:
        return pd.read_sql(sql, conn, params={"dt": as_of})


def _fundamental_rows(qdf: pd.DataFrame, adf: pd.DataFrame) -> pd.DataFrame:
    """Build per-instrument fundamental kwargs from an as-of quarterly panel + annual.

    Pure assembly over already-as-of-filtered frames, so it is reused by both the
    nightly single-date loader and the chunked historical backfill.
    """
    from atlas.lenses.compute.fundamental_pit import derive_fundamentals_asof
    annual_by: dict = {}
    if adf is not None and not adf.empty:
        for r in adf.to_dict("records"):
            annual_by.setdefault(r["instrument_id"], r)  # first = latest (DISTINCT ON)
    rows: list[dict] = []
    if qdf is not None and not qdf.empty:
        for iid, grp in qdf.groupby("instrument_id"):
            quarters = grp.sort_values("period_end", ascending=False).to_dict("records")
            derived = derive_fundamentals_asof(quarters, annual_by.get(iid))
            row = dict(derived["kwargs"]); row["instrument_id"] = iid
            rows.append(row)
    return pd.DataFrame(rows)


def load_fundamental_data(
    engine: Engine, as_of: date,
    lag_q: int = REPORTING_LAG_Q, lag_a: int = REPORTING_LAG_A,
) -> pd.DataFrame:
    """As-of fundamental metrics derived from financials_quarterly + _annual.

    Uses ONLY quarters with period_end ≤ as_of−lag_q and the latest annual with
    period_end ≤ as_of−lag_a (dedup consolidated-else-standalone), so the result is
    genuinely point-in-time — no future filing, no today-snapshot (Loop C 2a).
    """
    q_sql = text("""
        WITH dedup AS (
          SELECT DISTINCT ON (instrument_id, period_end)
                 instrument_id, period_end, revenue, ebit, pat, eps,
                 net_margin, finance_costs, debt_equity_ratio
          FROM foundation_staging.financials_quarterly
          WHERE period_end <= :cut
          ORDER BY instrument_id, period_end DESC, consolidated DESC),
        ranked AS (
          SELECT *, row_number() OVER (PARTITION BY instrument_id ORDER BY period_end DESC) rn
          FROM dedup)
        SELECT * FROM ranked WHERE rn <= 8
    """)
    a_sql = text("""
        SELECT DISTINCT ON (instrument_id)
               instrument_id, period_end, equity, total_borrowings
        FROM foundation_staging.financials_annual
        WHERE period_end <= :cut AND equity IS NOT NULL
        ORDER BY instrument_id, period_end DESC, consolidated DESC
    """)
    with open_compute_session(engine) as conn:
        qdf = pd.read_sql(q_sql, conn, params={"cut": as_of - timedelta(days=lag_q)})
        adf = pd.read_sql(a_sql, conn, params={"cut": as_of - timedelta(days=lag_a)})
    return _fundamental_rows(qdf, adf)


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
