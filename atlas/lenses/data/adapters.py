"""Data adapters for the six-lens scoring engine.

Read from atlas_foundation, feed data to pure scorers,
write results to atlas_foundation.atlas_lens_scores_daily.
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
# (atlas_foundation.index_prices) rather than raw technical_daily DISTINCT
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
        "SELECT max(date) FROM atlas_foundation.index_prices "
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
        "SELECT EXISTS(SELECT 1 FROM atlas_foundation.index_prices "
        "WHERE index_code = :idx AND date = :d)"
    )
    with open_compute_session(engine) as conn:
        return bool(conn.execute(sql, {"idx": _NSE_CAL_INDEX, "d": d}).scalar())


# Financial reporting availability lags (FM-proposed, DECISIONS D-LoopC): a quarter
# / annual filing is treated as KNOWABLE only `lag` days after its period_end (the
# only honest as-of proxy without a filing-date column). Conservative so the journal
# never uses a result before a human could have. Persisted to atlas_thresholds in
# the IC step; defaulted here so the rebuild needs no DB write.
REPORTING_LAG_Q = 60  # quarterly income statement
REPORTING_LAG_A = 90  # annual balance sheet (filed later than quarterlies)
# Screener ready-ratio snapshot validity: overlay only lens dates within this many
# days of the snapshot (PIT guard for historical re-scoring — older dates use the
# ROE derived from Screener's historical financials instead).
SCREENER_SNAPSHOT_WINDOW = 75


def load_technical_data(engine: Engine, as_of: date) -> pd.DataFrame:
    """Point-in-time technical inputs for all instruments on *as_of*.

    EMA/RSI/RS/ATR/BB/vol_ratio/pos_52w/rs_*_sector come from technical_daily ON
    that date (all PIT). The as-of price comes from ohlcv_stock on that date:
    `price_adj` (adjusted close, the basis EMA/ATR were computed on — used by the
    technical lens) and `close_raw` (actual traded close — used for the valuation
    PE). This replaces the old LEFT JOIN to the legacy tv_metrics SNAPSHOT, which
    stamped today's price/52w/volume/ATR on every historical date (the Loop C leak).
    """
    sql = text("""
        SELECT t.instrument_id, t.symbol, t.asset_class,
               t.ema_21, t.ema_50, t.ema_200, t.rsi_14, t.ret_1w,
               t.rs_1m_n500, t.rs_3m_n500, t.rs_6m_n500, t.rs_12m_n500,
               t.rs_1m_sector, t.rs_3m_sector, t.rs_6m_sector, t.rs_12m_sector,
               t.atr_14, t.bb_width, t.vol_ratio_30d, t.vol_ratio_60d, t.pos_52w,
               d.delivery_pct, d.delivery_avg_30d, d.delivery_avg_60d,
               d.delivery_trend, d.delivery_updown_asym,
               COALESCE(o.close_adj, o.close) AS price_adj,
               o.close AS close_raw, o.volume
        FROM atlas_foundation.technical_daily t
        LEFT JOIN atlas_foundation.ohlcv_stock o
          ON o.instrument_id = t.instrument_id AND o.date = t.date
        -- Delivery feed lags the price/EMA feed by a few sessions, so an exact d.date = t.date
        -- join nulls out delivery for the whole universe on a fresh scoring date. Take each
        -- name's MOST RECENT delivery snapshot on or before the scoring date instead — PIT-safe
        -- (never future) and lag-resilient, so the (now delivery-only) Flow lens still scores.
        LEFT JOIN LATERAL (
          SELECT dd.delivery_pct, dd.delivery_avg_30d, dd.delivery_avg_60d,
                 dd.delivery_trend, dd.delivery_updown_asym
          FROM atlas_foundation.delivery_daily dd
          WHERE dd.instrument_id = t.instrument_id AND dd.date <= :dt
          ORDER BY dd.date DESC LIMIT 1
        ) d ON true
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
            row = dict(derived["kwargs"])
            row["instrument_id"] = iid
            rows.append(row)
    return pd.DataFrame(rows)


def load_fundamental_data(
    engine: Engine,
    as_of: date,
    lag_q: int = REPORTING_LAG_Q,
    lag_a: int = REPORTING_LAG_A,
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
          FROM atlas_foundation.financials_quarterly
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
        FROM atlas_foundation.financials_annual
        WHERE period_end <= :cut AND equity IS NOT NULL
        ORDER BY instrument_id, period_end DESC, consolidated DESC
    """)
    with open_compute_session(engine) as conn:
        qdf = pd.read_sql(q_sql, conn, params={"cut": as_of - timedelta(days=lag_q)})
        adf = pd.read_sql(a_sql, conn, params={"cut": as_of - timedelta(days=lag_a)})
        # Screener ready-ratios are a CURRENT snapshot (one as_of), so they may only
        # overlay lens dates within the snapshot's validity window — stamping today's
        # ROE on a 2020 score would be non-PIT. Historical backfill dates fall outside
        # the window and keep their PIT-derived ROE (from Screener historical financials).
        snap = conn.execute(
            text("SELECT max(as_of) FROM atlas_foundation.screener_ratios")
        ).scalar()
        sr = None
        if snap is not None and as_of >= snap - timedelta(days=SCREENER_SNAPSHOT_WINDOW):
            sr = pd.read_sql(
                text(
                    "SELECT instrument_id, roe AS scr_roe, roce AS scr_roce, pb AS scr_pb, "
                    "ev_ebitda AS scr_ev_ebitda, stock_pe AS scr_pe "
                    "FROM atlas_foundation.screener_ratios"
                ),
                conn,
            )
    return _merge_screener_ratios(_fundamental_rows(qdf, adf), sr)


def _merge_screener_ratios(fdf: pd.DataFrame, sr: pd.DataFrame) -> pd.DataFrame:
    """Overlay Screener's ready ratios (FM decision D1) onto the derived frame.

    RULE #0: Screener ROE (a sane, ready value) REPLACES the XBRL-derived ROE whose
    near-zero/negative-equity denominators produced the −3,754%…+1,598% tails; ROCE,
    P/B, EV/EBITDA and Screener P/E are added for the profitability + valuation lenses.
    LEFT join — an instrument with no Screener snapshot keeps its derived values and
    gets None for the Screener-only fields (never imputed).
    """
    if fdf is None or fdf.empty:
        return fdf
    if "roce" not in fdf.columns:
        fdf["roce"] = None
    for c in ("scr_pb", "scr_ev_ebitda", "scr_pe"):
        fdf[c] = None
    if sr is None or sr.empty:
        return fdf
    fdf = fdf.copy()
    fdf["_k"] = fdf["instrument_id"].astype(str)
    sr = sr.copy()
    sr["_k"] = sr["instrument_id"].astype(str)
    sr = sr.drop(columns=["instrument_id"])
    m = (
        fdf.drop(columns=["roce", "scr_pb", "scr_ev_ebitda", "scr_pe"])
        .merge(sr, on="_k", how="left")
        .drop(columns=["_k"])
    )
    # Screener ROE wins where present; else keep the derived ROE.
    m["roe"] = m["scr_roe"].where(m["scr_roe"].notna(), m["roe"])
    m["roce"] = m["scr_roce"]
    return m


def load_catalyst_data(
    engine: Engine,
    lookback_days: int = 365,
    as_of: date | None = None,
) -> pd.DataFrame:
    """Load filings from lens_filings for each instrument (last N days).

    When *as_of* is given, uses it as the upper bound instead of CURRENT_DATE
    so that historical runs are point-in-time correct.
    """
    if as_of is not None:
        sql = text("""
            SELECT instrument_id, symbol, filing_date, category,
                   category_bucket, signal_priority, subject_text, source_url
            FROM atlas_foundation.lens_filings
            WHERE filing_date >= :as_of - :lb AND filing_date <= :as_of
            ORDER BY instrument_id, filing_date DESC
        """)
        params: dict[str, Any] = {"lb": lookback_days, "as_of": as_of}
    else:
        sql = text("""
            SELECT instrument_id, symbol, filing_date, category,
                   category_bucket, signal_priority, subject_text, source_url
            FROM atlas_foundation.lens_filings
            WHERE filing_date >= CURRENT_DATE - :lb
            ORDER BY instrument_id, filing_date DESC
        """)
        params = {"lb": lookback_days}
    with open_compute_session(engine) as conn:
        return pd.read_sql(sql, conn, params=params)


def load_flow_data(
    engine: Engine,
    as_of: date | None = None,
) -> dict[str, pd.DataFrame]:
    """Load insider transactions, shareholding, and bulk deals.

    When *as_of* is given, all date filters use it as the ceiling so that
    historical runs are point-in-time correct.
    """
    with open_compute_session(engine) as conn:
        if as_of is not None:
            insider = pd.read_sql(
                text("""
                SELECT instrument_id, symbol, signal_type, value_cr, person_name,
                       pledge_pct_after, transaction_date, price_per_share
                FROM atlas_foundation.lens_insider
                WHERE transaction_date >= :as_of - INTERVAL '365 days'
                  AND transaction_date <= :as_of
                ORDER BY instrument_id, transaction_date DESC
            """),
                conn,
                params={"as_of": as_of},
            )

            shareholding = pd.read_sql(
                text("""
                SELECT instrument_id, symbol, period_end, promoter_pct, public_pct
                FROM atlas_foundation.lens_shareholding
                WHERE period_end <= :as_of
                ORDER BY instrument_id, period_end DESC
            """),
                conn,
                params={"as_of": as_of},
            )

            bulk_deals = pd.read_sql(
                text("""
                SELECT instrument_id, symbol, deal_date, client_name, buy_sell,
                       qty, price, is_institutional, is_superstar, superstar_name
                FROM atlas_foundation.lens_bulk_deals
                WHERE deal_date >= :as_of - INTERVAL '90 days'
                  AND deal_date <= :as_of
                ORDER BY instrument_id, deal_date DESC
            """),
                conn,
                params={"as_of": as_of},
            )
        else:
            insider = pd.read_sql(
                text("""
                SELECT instrument_id, symbol, signal_type, value_cr, person_name,
                       pledge_pct_after, transaction_date, price_per_share
                FROM atlas_foundation.lens_insider
                WHERE transaction_date >= CURRENT_DATE - INTERVAL '365 days'
                ORDER BY instrument_id, transaction_date DESC
            """),
                conn,
            )

            shareholding = pd.read_sql(
                text("""
                SELECT instrument_id, symbol, period_end, promoter_pct, public_pct
                FROM atlas_foundation.lens_shareholding
                ORDER BY instrument_id, period_end DESC
            """),
                conn,
            )

            bulk_deals = pd.read_sql(
                text("""
                SELECT instrument_id, symbol, deal_date, client_name, buy_sell,
                       qty, price, is_institutional, is_superstar, superstar_name
                FROM atlas_foundation.lens_bulk_deals
                WHERE deal_date >= CURRENT_DATE - INTERVAL '90 days'
                ORDER BY instrument_id, deal_date DESC
            """),
                conn,
            )

    mf = load_mf_flow(engine, as_of)
    return {"insider": insider, "shareholding": shareholding, "bulk_deals": bulk_deals, "mf": mf}


def load_mf_flow(engine: Engine, as_of: date | None = None) -> pd.DataFrame:
    """Mutual-fund month-on-month institutional flow per instrument (real signal).

    de_mf_holdings carries monthly snapshots of every fund's weight_pct in each
    stock. A naive Σ(weight_pct) MoM delta is biased by how many funds reported
    that month (e.g. 2026-04-06 reported 550 funds vs 2026-05-04's 1,306). So we
    use a MATCHED-FUND delta: over only the funds present in BOTH the latest two
    well-covered snapshots (≥800 funds, ≤ as_of), Σ(weight_now − weight_prev). This
    isolates genuine accumulation/distribution by the same funds and is centred at
    ~0 (no fund-count artifact). RULE #0: a stock with no MF holding gets no row →
    the flow scorer treats it as genuine neutral, never a stub.
    """
    ceil = as_of or datetime.now(_IST).date()
    with open_compute_session(engine) as conn:
        # Pick the latest two real monthly snapshots ≤ as_of. The fund-coverage floor
        # only excludes junk partial snapshots (e.g. 2026-01-31 had 1 fund); real
        # snapshots carry ~550-1,300 funds. The matched-fund INNER JOIN below compares
        # only funds present in BOTH, so an uneven fund count between the two months
        # introduces no bias.
        snaps = pd.read_sql(
            text("""
            SELECT as_of_date FROM atlas_foundation.de_mf_holdings
            WHERE as_of_date <= :ceil
            GROUP BY as_of_date HAVING count(DISTINCT mstar_id) >= 400
            ORDER BY as_of_date DESC LIMIT 2
        """),
            conn,
            params={"ceil": ceil},
        )
        if len(snaps) < 2:
            return pd.DataFrame(columns=["instrument_id", "mf_mom_delta", "mf_matched_funds"])
        cur_d, prv_d = snaps["as_of_date"].iloc[0], snaps["as_of_date"].iloc[1]
        mf = pd.read_sql(
            text("""
            WITH cur AS (SELECT instrument_id, mstar_id, weight_pct
                         FROM atlas_foundation.de_mf_holdings WHERE as_of_date = :cur),
                 prv AS (SELECT instrument_id, mstar_id, weight_pct
                         FROM atlas_foundation.de_mf_holdings WHERE as_of_date = :prv)
            SELECT c.instrument_id,
                   sum(c.weight_pct - p.weight_pct) AS mf_mom_delta,
                   count(*) AS mf_matched_funds
            FROM cur c JOIN prv p
              ON p.instrument_id = c.instrument_id AND p.mstar_id = c.mstar_id
            GROUP BY c.instrument_id
        """),
            conn,
            params={"cur": cur_d, "prv": prv_d},
        )
    return mf


def load_policy_registry(engine: Engine) -> list[dict[str, Any]]:
    """Load active policies from atlas_foundation.policy_registry."""
    sql = text("""
        SELECT policy_id, policy_name, description, impact,
               beneficiary_sectors, beneficiary_keywords
        FROM atlas_foundation.policy_registry
        WHERE is_active = TRUE
    """)
    with open_compute_session(engine) as conn:
        rows = conn.execute(sql).mappings().all()
    return [dict(r) for r in rows]


def load_instrument_sectors(engine: Engine) -> pd.DataFrame:
    """Load sector/industry for all active stocks from instrument_master.

    Sector + industry are native columns on instrument_master (the single
    universe/sector reference); instruments outside the curated universe are
    excluded by the is_active filter below.
    """
    # Bound to the Atlas coverage universe (is_active = NIFTY 500, FM 2026-06-25).
    # This is the durable single-universe fix: the lens journal equals exactly the
    # 498 scored names, instead of every kite_token instrument (the old 2,093).
    sql = text("""
        SELECT im.instrument_id, im.symbol, im.sector, im.industry
        FROM atlas_foundation.instrument_master im
        WHERE im.asset_class = 'stock' AND im.kite_token IS NOT NULL
          AND im.is_active
    """)
    with open_compute_session(engine) as conn:
        return pd.read_sql(sql, conn)


def write_lens_scores(
    engine: Engine,
    results: list[dict[str, Any]],
    run_id: uuid.UUID | None = None,
) -> int:
    """Upsert scored results into atlas_foundation.atlas_lens_scores_daily."""
    if not results:
        return 0
    columns = [
        "instrument_id",
        "date",
        "asset_class",
        "technical",
        "fundamental",
        "valuation",
        "catalyst",
        "flow",
        "policy",
        "tech_trend",
        "tech_rs",
        "tech_vol_contraction",
        "tech_volume",
        "fund_profitability",
        "fund_margin",
        "fund_growth",
        "fund_balance_sheet",
        "fund_op_leverage",
        "val_pe_vs_sector",
        "val_absolute_pe",
        "val_pb",
        "val_ev_ebitda",
        "val_52w_position",
        "cat_earnings_strategy",
        "cat_capital_action",
        "cat_governance",
        "flow_promoter",
        "flow_institutional",
        "flow_smart_money",
        "flow_accumulation",
        "policy_tailwind",
        "composite",
        "conviction_tier",
        "valuation_zone",
        "valuation_multiplier",
        "smart_money_score",
        "degradation_score",
        "risk_flags",
        "evidence",
        "lenses_active",
        "coverage_factor",
        "compute_run_id",
        "computed_at",
    ]
    rows = []
    now = datetime.now(_IST)
    rid = run_id or uuid.uuid4()
    for r in results:
        row = tuple(
            r.get(c, rid if c == "compute_run_id" else now if c == "computed_at" else None)
            for c in columns
        )
        rows.append(row)
    return bulk_upsert(
        engine,
        # Write DIRECTLY to atlas_foundation — the single table the frontend reads. Kills the
        # old atlas.* → atlas_foundation.* sync step (and the divergence it caused).
        "atlas_foundation.atlas_lens_scores_daily",
        columns,
        rows,
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
        "DELETE FROM atlas_foundation.atlas_lens_scores_daily "
        "WHERE date = :dt AND asset_class = :ac AND compute_run_id <> :rid"
    )
    with open_compute_session(engine) as conn:
        res = conn.execute(sql, {"dt": dt, "ac": asset_class, "rid": run_id})
        conn.commit()
        return res.rowcount or 0
