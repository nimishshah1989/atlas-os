"""Sector aggregation pipeline (M3 Phase B).

Per ``docs/00_METHODOLOGY_LOCK.md`` §10 and ``docs/02_DATABASE_SCHEMA.md``
§3.4 (``atlas_sector_metrics_daily``) + §4.3 (``atlas_sector_states_daily``).

Two-pronged aggregation per sector per date:

* **Bottom-up:** weighted-mean of constituent-stock metrics (RS, returns)
  using ``avg_volume_20 * close_approx`` as a traded-value proxy, plus three
  breadth measures (participation_50, participation_rs,
  leadership_concentration).
* **Top-down:** read pre-computed metrics for the sector's
  ``primary_nse_index`` from :mod:`atlas.compute.indices` output.

The reconstructed close (``ema_200_stock * (1 + extension_pct)``) is the
foundation for both bottom-up RS-vs-Nifty500 and breadth measures —
``atlas_stock_metrics_daily`` does not store raw ``close``.

All weighted helpers and orchestration live in this single module — no
``aggregation.py`` per locked decision #1.
"""
# allow-large: single cohesive pipeline module — loaders, bottom-up/top-down
# aggregation, breadth, state classification, and DB writers form one
# indivisible computation unit per locked decision #1 (no aggregation.py split).

from __future__ import annotations

import time
import uuid
from collections.abc import Mapping
from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
import structlog
from sqlalchemy.engine import Engine

from atlas.compute._session import bulk_upsert, df_to_pg_rows, open_compute_session
from atlas.compute.primitives import RS_WINDOWS
from atlas.config import Config
from atlas.db import get_engine, load_thresholds

log = structlog.get_logger()


METRICS_COLUMNS: tuple[str, ...] = (
    "sector_name",
    "date",
    "bottomup_ret_1w",  # added: 1-week bottom-up return
    "bottomup_ret_1m",
    "bottomup_ret_3m",
    "bottomup_ret_6m",
    "bottomup_rs_1d_nifty500",
    "bottomup_rs_1w_nifty500",
    "bottomup_rs_1m_nifty500",
    "bottomup_rs_3m_nifty500",
    "bottomup_rs_6m_nifty500",
    "bottomup_rs_12m_nifty500",
    "bottomup_rs_24m_nifty500",
    "bottomup_ema_10_ratio",
    "bottomup_ema_20_ratio",
    "topdown_index_code",
    "topdown_ret_1m",
    "topdown_ret_3m",
    "topdown_rs_3m_nifty500",
    "constituent_count",
    "participation_50",
    "participation_rs",
    "leadership_concentration",
    "rs_velocity",  # SP02: 4-week rate-of-change of bottomup_rs_3m_nifty500
    "compute_run_id",
)
"""Mirrors ``docs/02_DATABASE_SCHEMA.md`` §3.4 — order matters for psycopg2
``execute_values`` because rows are written as positional tuples."""


STATES_COLUMNS: tuple[str, ...] = (
    "sector_name",
    "date",
    "sector_state",
    "bottomup_state",
    "topdown_state",
    "divergence_flag",
    "bottomup_rs_state",
    "bottomup_momentum_state",
    "participation_rs_pct",
    "compute_run_id",
)
"""Mirrors ``docs/02_DATABASE_SCHEMA.md`` §4.3."""


# Methodology §10.5 sector RS state thresholds — keep in lockstep with stock
# RS state quintiles so a sector's RS classification reads naturally as
# "this sector behaves like a Leader / Laggard would on the stock side".
RS_QUINTILE_TOP = 0.80
RS_QUINTILE_BOTTOM = 0.20


# --------------------------------------------------------------------------- #
# Loaders                                                                     #
# --------------------------------------------------------------------------- #


def load_sector_stock_data(
    engine: Engine,
    start_date: date,
    end_date: date,
    lookback_days: int = 900,
) -> pd.DataFrame:
    """Load stock-level metrics, joined to universe sector + tier.

    Reads ``atlas_stock_metrics_daily`` rows (NOT ``de_equity_ohlcv`` — the
    aggregation runs on already-computed metrics; raw OHLCV would re-do work).
    The lookback buffer keeps rolling-window context warm but is small here
    because the heavy rolling lives in the upstream stock pipeline.

    Returns a long-form frame with one row per (instrument_id, date) and the
    columns needed by every downstream helper:

        instrument_id, date, sector, tier, primary_nse_index,
        ema_50_stock, ema_200_stock, extension_pct, avg_volume_20,
        ret_1d, ret_1w, ret_1m, ret_3m, ret_6m, ret_12m, ret_24m,
        rs_1w_tier, rs_1m_tier, rs_3m_tier,
        ema_10_ratio, ema_20_ratio,
        rs_state, momentum_state,
        close_approx (computed in-memory)
    """
    load_start = start_date - timedelta(days=lookback_days)
    eng = engine

    with open_compute_session(eng) as conn:
        df = pd.read_sql(
            """
            SELECT
                m.instrument_id,
                m.date,
                u.sector AS sector_name,
                u.tier,
                m.ema_50_stock,
                m.ema_200_stock,
                m.extension_pct,
                m.avg_volume_20,
                m.ret_1d,
                m.ret_1w,
                m.ret_1m,
                m.ret_3m,
                m.ret_6m,
                m.ret_12m,
                m.ret_24m,
                m.rs_1w_tier,
                m.rs_1m_tier,
                m.rs_3m_tier,
                m.ema_10_ratio,
                m.ema_20_ratio,
                s.rs_state,
                s.momentum_state
            FROM atlas.atlas_stock_metrics_daily m
            JOIN atlas.atlas_universe_stocks u
                ON u.instrument_id = m.instrument_id
                AND u.effective_to IS NULL
            LEFT JOIN atlas.atlas_stock_states_daily s
                ON s.instrument_id = m.instrument_id
                AND s.date = m.date
            WHERE m.date BETWEEN %(start)s AND %(end)s
            ORDER BY m.instrument_id, m.date
            """,
            conn,
            params={"start": load_start, "end": end_date},
        )

    if df.empty:
        log.warning(
            "sector_stock_data_empty",
            start=str(load_start),
            end=str(end_date),
        )
        return df

    df["date"] = pd.to_datetime(df["date"]).dt.date
    # Decimal arithmetic — extension_pct is stored as decimal (0.40 = 40%);
    # see locked decision #2. Do NOT multiply by 100.
    ema_200 = df["ema_200_stock"].astype("float64")
    ext = df["extension_pct"].astype("float64")
    df["close_approx"] = ema_200 * (1.0 + ext)

    log.info(
        "sector_stock_data_loaded",
        rows=len(df),
        instruments=df["instrument_id"].nunique(),
        sectors=df["sector_name"].nunique(),
    )
    return df


def load_sector_master(engine: Engine) -> pd.DataFrame:
    """Read ``atlas_sector_master``.

    Returns: ``sector_name, primary_nse_index, fallback_benchmark`` for active
    sectors. Sectors with NULL ``primary_nse_index`` fall back to NIFTY 500
    for top-down (per schema §2.5 notes).
    """
    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            """
            SELECT sector_name, primary_nse_index, fallback_benchmark
            FROM atlas.atlas_sector_master
            WHERE is_active = TRUE
            """,
            conn,
        )
    log.info("sector_master_loaded", count=len(df))
    return df


def load_index_metrics(
    engine: Engine,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Read ``atlas_index_metrics_daily`` for top-down sector aggregation.

    Pulls the columns we need: returns, EMA ratios, and RS-vs-Nifty500 for
    every index in the date range. Filtering down to sector primary indices
    happens later via merge.
    """
    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            """
            SELECT
                index_code, date,
                ret_1w, ret_1m, ret_3m,
                rs_3m_nifty500,
                ema_10_ratio_nifty500,
                ema_20_ratio_nifty500
            FROM atlas.atlas_index_metrics_daily
            WHERE date BETWEEN %(start)s AND %(end)s
            """,
            conn,
            params={"start": start_date, "end": end_date},
        )
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"]).dt.date
    log.info("index_metrics_loaded", rows=len(df))
    return df


def load_nifty500_returns(
    engine: Engine,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Per-date Nifty500 ``ret_<w>`` for all 7 RS windows — the bottom-up RS denominator.

    Bottom-up RS-vs-Nifty500 for a sector is computed as the weighted-mean of
    constituent stock ``ret_<w>`` divided by Nifty500 ``ret_<w>``. We read
    Nifty500 returns once and merge by date.
    """
    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            """
            SELECT date, ret_1d, ret_1w, ret_1m, ret_3m, ret_6m, ret_12m, ret_24m
            FROM atlas.atlas_index_metrics_daily
            WHERE index_code = 'NIFTY 500'
              AND date BETWEEN %(start)s AND %(end)s
            ORDER BY date
            """,
            conn,
            params={"start": start_date, "end": end_date},
        )
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df = df.rename(columns={f"ret_{w}": f"_n500_ret_{w}" for w in RS_WINDOWS})
    log.info("nifty500_returns_loaded", rows=len(df))
    return df


# --------------------------------------------------------------------------- #
# Bottom-up aggregation                                                       #
# --------------------------------------------------------------------------- #


def _compute_traded_value_weight(df: pd.DataFrame) -> pd.Series:
    """Traded-value proxy weight: ``avg_volume_20 * close_approx``.

    ``de_market_cap_history`` is empty in v0 (verified via EC2 query — see
    M3 build plan key facts), so we use traded value as the weight. Stocks
    where either input is NaN/0 get weight=NaN (so they fall to the
    equal-weight fallback inside :func:`_weighted_mean`).
    """
    vol = pd.to_numeric(df.get("avg_volume_20"), errors="coerce")
    close = pd.to_numeric(df.get("close_approx"), errors="coerce")
    weight = vol * close  # type: ignore[operator]
    weight = weight.where(weight > 0, other=np.nan)  # type: ignore[union-attr]
    return weight


def compute_bottom_up_sector_metrics(
    df_stocks: pd.DataFrame,
    df_sector_master: pd.DataFrame,
    df_nifty500_returns: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Per (sector, date) bottom-up weighted aggregations.

    Args:
        df_stocks: output of :func:`load_sector_stock_data`. Must have
            ``close_approx`` already computed.
        df_sector_master: output of :func:`load_sector_master`. Used to drop
            stocks whose sector isn't in the master list (defensive — every
            universe row should have a valid sector).
        df_nifty500_returns: per-date Nifty500 returns frame from
            :func:`load_nifty500_returns`. If None, the
            ``bottomup_rs_*_nifty500`` columns come through as NaN.

    Returns:
        Long-form frame with columns:

        ``sector_name, date, bottomup_ret_1w, bottomup_ret_1m, bottomup_ret_3m,
          bottomup_ret_6m, bottomup_rs_1w_nifty500, bottomup_rs_1m_nifty500,
          bottomup_rs_3m_nifty500, bottomup_ema_10_ratio,
          bottomup_ema_20_ratio, constituent_count``.

    NOTE: ``atlas_stock_metrics_daily`` has ``rs_*_tier`` (RS vs tier
    benchmark) but NOT ``rs_*_nifty500``. The bottom-up RS-vs-Nifty500 is
    therefore computed from raw ``ret_<w>`` divided by the Nifty500
    ``ret_<w>`` for that date.
    """
    if df_stocks.empty:
        return pd.DataFrame(
            columns=[
                "sector_name",
                "date",
                "bottomup_ret_1d",
                "bottomup_ret_1w",
                "bottomup_ret_1m",
                "bottomup_ret_3m",
                "bottomup_ret_6m",
                "bottomup_ret_12m",
                "bottomup_ret_24m",
                *[f"bottomup_rs_{w}_nifty500" for w in RS_WINDOWS],
                "bottomup_ema_10_ratio",
                "bottomup_ema_20_ratio",
                "constituent_count",
            ]
        )

    valid_sectors = set(df_sector_master["sector_name"].unique())
    work = df_stocks[df_stocks["sector_name"].isin(valid_sectors)].copy()
    work["weight"] = _compute_traded_value_weight(work)

    # Per (sector, date) weighted-mean over the listed metrics. Operate on a
    # plain Python loop *over metrics* — only ~7 metrics — but the per-row
    # work inside each metric is fully vectorised via groupby.apply. No
    # per-row Python loops.
    # M3 full-7-window: aggregate every RS-window return present on the frame.
    # ``ret_1d``/``ret_12m``/``ret_24m`` were added to the stock loader for the
    # 1d/12m/24m sector RS surfaces; guarded below so partial frames (older
    # fixtures, daily slices) skip absent windows rather than KeyError.
    metric_cols = (
        "ret_1d",
        "ret_1w",
        "ret_1m",
        "ret_3m",
        "ret_6m",
        "ret_12m",
        "ret_24m",
        "ema_10_ratio",
        "ema_20_ratio",
    )

    # Build a long DataFrame keyed by (sector_name, date) using vectorised
    # aggregation primitives. We avoid a per-group apply by computing
    # numerator/denominator separately.

    # Constituent count — number of stocks with non-NaN close_approx (i.e.
    # a usable row) per sector / date.
    counts = (
        work.assign(_present=work["close_approx"].notna().astype(int))
        .groupby(["sector_name", "date"], observed=True)["_present"]
        .sum()
        .rename("constituent_count")
        .astype(int)
    )

    aggregated: dict[str, pd.Series] = {"constituent_count": counts}

    for metric in metric_cols:
        if metric not in work.columns:
            continue
        v = pd.to_numeric(work[metric], errors="coerce")
        w = work["weight"]
        # Numerator = sum(v * w) where both are finite.
        valid_mask = v.notna() & w.notna()
        weighted_value = (v * w).where(valid_mask, other=0.0)
        weight_sum = w.where(valid_mask, other=0.0)

        num = weighted_value.groupby([work["sector_name"], work["date"]], observed=True).sum()
        den = weight_sum.groupby([work["sector_name"], work["date"]], observed=True).sum()

        weighted_mean = num / den.where(den > 0, other=np.nan)

        # Equal-weight fallback for cohorts with zero total weight.
        eq_mean = v.groupby([work["sector_name"], work["date"]], observed=True).mean()
        result = weighted_mean.fillna(eq_mean).rename(metric)
        aggregated[metric] = result

    out = pd.concat(aggregated.values(), axis=1)
    out.columns = list(aggregated.keys())
    out = out.reset_index()

    # Rename to bottomup_* + add window-specific bottomup_rs_<w>_nifty500.
    rename_map = {
        "ret_1d": "bottomup_ret_1d",
        "ret_1w": "bottomup_ret_1w",
        "ret_1m": "bottomup_ret_1m",
        "ret_3m": "bottomup_ret_3m",
        "ret_6m": "bottomup_ret_6m",
        "ret_12m": "bottomup_ret_12m",
        "ret_24m": "bottomup_ret_24m",
        "ema_10_ratio": "bottomup_ema_10_ratio",
        "ema_20_ratio": "bottomup_ema_20_ratio",
    }
    out = out.rename(columns=rename_map)

    # ---- Bottom-up RS vs Nifty 500 -----------------------------------------
    # Price-relative RS: (1 + sector_ret) / (1 + nifty500_ret) - 1.
    # This formula preserves sign semantics when the benchmark return is
    # negative (simple ratio ret_s/ret_b inverts the economic interpretation
    # in bear markets — e.g. a sector up 30% when Nifty500 is down 1% would
    # get a large negative RS value with the simple ratio).
    # M3 full-7-window lock: 1d/1w/1m/3m/6m/12m/24m (RS_WINDOWS).
    if df_nifty500_returns is not None and not df_nifty500_returns.empty:
        out = out.merge(df_nifty500_returns, on="date", how="left")
        for w_label in RS_WINDOWS:
            num_col = f"bottomup_ret_{w_label}"
            denom_col = f"_n500_ret_{w_label}"
            # Skip windows the sector/Nifty500 frames don't carry (partial slices).
            if num_col not in out.columns or denom_col not in out.columns:
                out[f"bottomup_rs_{w_label}_nifty500"] = np.nan
                continue
            bench_price_rel = 1.0 + out[denom_col].astype("float64")
            with np.errstate(divide="ignore", invalid="ignore"):
                rs = np.where(
                    out[denom_col].notna() & (bench_price_rel.abs() > 1e-9),
                    (1.0 + out[num_col].astype("float64")) / bench_price_rel - 1.0,
                    np.nan,
                )
            out[f"bottomup_rs_{w_label}_nifty500"] = rs.astype("float64")
        out = out.drop(columns=[c for c in out.columns if c.startswith("_n500_")])
    else:
        for w_label in RS_WINDOWS:
            out[f"bottomup_rs_{w_label}_nifty500"] = np.nan

    return out


# --------------------------------------------------------------------------- #
# Sector breadth measures                                                     #
# --------------------------------------------------------------------------- #


def compute_sector_breadth(
    df_stocks: pd.DataFrame,
    df_sector_master: pd.DataFrame,
) -> pd.DataFrame:
    """Per (sector, date) breadth measures (methodology §10.4).

    * ``participation_50`` — fraction of stocks where
      ``close_approx > ema_50_stock``. Stocks with NULL ``ema_50_stock``
      (warm-up rows before 50 trading days) are excluded from numerator AND
      denominator.
    * ``participation_rs`` — fraction with ``rs_1m_tier > 0``. ``rs_1m_tier``
      is a DIFFERENCE (stock_ret − benchmark_ret), not a ratio, so the
      "positive RS" cut is at 0 (outperforming the tier) not 1.0.
    * ``leadership_concentration`` — share of total ``rs_3m_tier`` magnitude
      held by the top-quintile constituents (top 20% of stocks by
      ``rs_3m_tier`` within the sector that day).

    Returns long-form frame with ``sector_name, date, participation_50,
    participation_rs, leadership_concentration``.
    """
    if df_stocks.empty:
        return pd.DataFrame(
            columns=[
                "sector_name",
                "date",
                "participation_50",
                "participation_rs",
                "leadership_concentration",
            ]
        )

    valid_sectors = set(df_sector_master["sector_name"].unique())
    work = df_stocks[df_stocks["sector_name"].isin(valid_sectors)].copy()

    # ---- participation_50 ---------------------------------------------------
    p50_work = work.dropna(subset=["close_approx", "ema_50_stock"])
    is_above_50 = (p50_work["close_approx"] > p50_work["ema_50_stock"]).astype(int)
    p50 = (
        is_above_50.groupby([p50_work["sector_name"], p50_work["date"]], observed=True)
        .mean()
        .rename("participation_50")
    )

    # ---- participation_rs — methodology §10.4 ----------------------------------
    # Count of stocks with rs_state ∈ {Leader, Strong, Emerging} per methodology.
    # Previous implementation used rs_1m_tier > 0 as a proxy; using the actual
    # state column avoids Weinstein-gate discrepancies at the quintile boundary.
    _positive_rs_states = {"Leader", "Strong", "Emerging"}
    rs_work = work.dropna(subset=["rs_state"])
    is_pos_rs = rs_work["rs_state"].isin(_positive_rs_states).astype(int)
    p_rs = (
        is_pos_rs.groupby([rs_work["sector_name"], rs_work["date"]], observed=True)
        .mean()
        .rename("participation_rs")
    )

    # ---- leadership_concentration -----------------------------------------
    # Per sector/date: rank stocks by rs_3m_tier descending; sum of top-quintile
    # rs_3m_tier divided by sum of all rs_3m_tier (using absolute magnitude so
    # negative-RS sectors still produce a finite ratio).
    lc_work = work.dropna(subset=["rs_3m_tier"]).copy()
    lc_work["abs_rs_3m"] = lc_work["rs_3m_tier"].abs()

    grp = lc_work.groupby(["sector_name", "date"], observed=True)
    # rank descending (absolute, not pct) so we can compute n_top = max(1, ceil(n*0.20)).
    # Percentile rank fails for small sectors: with 3 stocks the minimum rank is
    # 0.333 which is already > 0.20, so no stock would qualify. The floor-of-1
    # ensures at least the top stock is always counted.
    lc_work["rank_abs"] = grp["rs_3m_tier"].rank(method="min", ascending=False)
    lc_work["n_total"] = grp["rs_3m_tier"].transform("count")
    lc_work["n_top"] = (lc_work["n_total"] * 0.20).clip(lower=1.0).apply(np.ceil).astype(int)
    lc_work["is_top_quintile"] = (lc_work["rank_abs"] <= lc_work["n_top"]).astype(int)

    sum_top = (
        (lc_work["abs_rs_3m"] * lc_work["is_top_quintile"])
        .groupby([lc_work["sector_name"], lc_work["date"]], observed=True)
        .sum()
        .rename("sum_top")
    )
    sum_all = (
        lc_work["abs_rs_3m"]
        .groupby([lc_work["sector_name"], lc_work["date"]], observed=True)
        .sum()
        .rename("sum_all")
    )
    lc_df = pd.concat([sum_top, sum_all], axis=1)
    lc_df["leadership_concentration"] = lc_df["sum_top"] / lc_df["sum_all"].where(
        lc_df["sum_all"] > 0, other=np.nan
    )
    lc = lc_df["leadership_concentration"]

    out = pd.concat([p50, p_rs, lc], axis=1).reset_index()
    return out


# --------------------------------------------------------------------------- #
# Top-down aggregation                                                        #
# --------------------------------------------------------------------------- #


def compute_top_down_sector_metrics(
    df_index_metrics: pd.DataFrame,
    df_sector_master: pd.DataFrame,
) -> pd.DataFrame:
    """Per-sector top-down metrics from the sector's primary NSE index.

    Joins ``atlas_sector_master`` to ``atlas_index_metrics_daily`` on
    ``primary_nse_index = index_code``. Sectors with NULL ``primary_nse_index``
    fall back to ``fallback_benchmark`` (typically NIFTY 500). The returned
    ``topdown_index_code`` reflects whichever code was actually used.

    Args:
        df_index_metrics: from :func:`load_index_metrics`.
        df_sector_master: from :func:`load_sector_master`.

    Returns:
        Long-form frame: ``sector_name, date, topdown_index_code,
        topdown_ret_1m, topdown_ret_3m, topdown_rs_3m_nifty500``.
    """
    if df_index_metrics.empty or df_sector_master.empty:
        return pd.DataFrame(
            columns=[
                "sector_name",
                "date",
                "topdown_index_code",
                "topdown_ret_1m",
                "topdown_ret_3m",
                "topdown_rs_3m_nifty500",
            ]
        )

    master = df_sector_master.copy()
    # If primary is null, fall back to NIFTY 500.
    master["resolved_index"] = master["primary_nse_index"].fillna(master["fallback_benchmark"])

    merged = master.merge(
        df_index_metrics,
        left_on="resolved_index",
        right_on="index_code",
        how="left",
    )

    out = merged[
        [
            "sector_name",
            "date",
            "resolved_index",
            "ret_1m",
            "ret_3m",
            "rs_3m_nifty500",
        ]
    ].rename(
        columns={
            "resolved_index": "topdown_index_code",
            "ret_1m": "topdown_ret_1m",
            "ret_3m": "topdown_ret_3m",
            "rs_3m_nifty500": "topdown_rs_3m_nifty500",
        }
    )
    # Drop rows where the date didn't materialise (sector had no matching index)
    out = out.dropna(subset=["date"])
    return out


# --------------------------------------------------------------------------- #
# Sector states                                                               #
# --------------------------------------------------------------------------- #


def _classify_bottomup_rs_state(
    df_metrics: pd.DataFrame,
) -> pd.Series:
    """Per-date cross-sector percentile rank of ``bottomup_rs_3m_nifty500``.

    Returns one of {Overweight_RS, Neutral_RS, Avoid_RS} per row, matching
    the locked decision #4 (cross-sector percentile, top 80%ile = Overweight,
    bottom 20%ile = Avoid).
    """
    rs = df_metrics["bottomup_rs_3m_nifty500"]
    pct = rs.groupby(df_metrics["date"]).rank(method="average", pct=True)

    state = np.where(
        pct >= RS_QUINTILE_TOP,
        "Overweight_RS",
        np.where(pct <= RS_QUINTILE_BOTTOM, "Avoid_RS", "Neutral_RS"),
    )
    # rank() returns NaN for all-NaN cohorts; preserve as Neutral_RS so we don't
    # over-classify pre-history rows.
    state = np.where(pct.isna(), "Neutral_RS", state)
    return pd.Series(state, index=df_metrics.index, name="bottomup_rs_state")


def compute_sector_states(
    df_metrics: pd.DataFrame,
    df_thresholds: Mapping[str, Decimal],
) -> pd.DataFrame:
    """Per-sector four-state classification (methodology §10.5).

    Combines bottom-up RS state, momentum proxy (``bottomup_ema_10_ratio`` >
    1 → Improving/Accelerating-equivalent), and breadth (``participation_rs``)
    to land on Overweight / Neutral / Underweight / Avoid per the rule table.

    Threshold keys (atlas_thresholds, all percent → divide by 100):
        * ``sector_overweight_participation_min_pct`` (default 50)
        * ``sector_underweight_participation_max_pct`` (default 30)
        * ``sector_avoid_participation_max_pct`` (default 25)

    Also computes:
        * ``divergence_flag`` — abs rank diff between bottomup and topdown
          ret_3m exceeds 1 (cross-sector ranks). GUARDED: when the sector's
          ``topdown_index_code`` is the same code shared by another sector
          (Power+Energy both use NIFTY ENERGY → identical top-down series),
          divergence is forced to FALSE because the rank-difference test is
          meaningless when two sectors have the same top-down series.
    """
    if df_metrics.empty:
        return pd.DataFrame(columns=list(STATES_COLUMNS))

    out = df_metrics.copy()

    # Threshold keys are percent values per docs/04 — convert to fraction.
    # Cast to float: Decimal / float raises TypeError; pandas comparisons need float scalars.
    overweight_min = float(df_thresholds["sector_overweight_participation_min_pct"]) / 100.0
    underweight_max = float(df_thresholds["sector_underweight_participation_max_pct"]) / 100.0
    avoid_max = float(df_thresholds["sector_avoid_participation_max_pct"]) / 100.0

    # ---- Bottom-up RS state ------------------------------------------------
    out["bottomup_rs_state"] = _classify_bottomup_rs_state(out)

    # ---- Bottom-up momentum proxy -----------------------------------------
    # Methodology §10.5 references "bottom_up.momentum ∈ {Accelerating,
    # Improving}" — neither is computed at sector grain, so we use the
    # bottom-up ema_10_ratio > 1 as the proxy (the same EMA-ratio convention
    # that drives stock-level Improving/Accelerating per methodology §7.2).
    out["bottomup_momentum_state"] = np.where(
        out["bottomup_ema_10_ratio"] > out["bottomup_ema_20_ratio"],
        "Improving",
        np.where(
            out["bottomup_ema_10_ratio"] < out["bottomup_ema_20_ratio"],
            "Deteriorating",
            "Flat",
        ),
    )

    # ---- Bottom-up state combo ---------------------------------------------
    # Avoid: Avoid_RS bottom-up AND participation_rs < avoid_max
    # Underweight: bottomup RS is Avoid_RS (Weak-equivalent) OR participation < underweight_max
    # Overweight: Overweight_RS AND momentum 'Improving' AND participation_rs >= overweight_min
    # Neutral: default
    #
    # participation_rs uses CROSS-SECTOR PERCENTILE RANK (grouped by date), not
    # absolute value. Absolute breadth collapses in bear markets — every sector
    # ends up Underweight even as relative leaders still lead. Percentile rank
    # preserves the distribution: thresholds (50/30/25) become percentile cutoffs,
    # so the top half always remains eligible for Overweight regardless of market
    # conditions. (Decision: 2026-05-14, replacing absolute threshold that caused
    # all funds to show Misaligned/Reduce since Jan 2026.)
    rs_state = out["bottomup_rs_state"]
    mom = out["bottomup_momentum_state"]
    p_rs_rank = out.groupby("date")["participation_rs"].rank(pct=True)

    is_avoid = (rs_state == "Avoid_RS") & (p_rs_rank < avoid_max)
    is_underweight = (rs_state == "Avoid_RS") | (p_rs_rank < underweight_max)
    is_overweight = (
        (rs_state == "Overweight_RS") & (mom == "Improving") & (p_rs_rank >= overweight_min)
    )

    # Avoid takes priority; Underweight before Overweight so a sector that
    # meets both conditions (threshold edge-case) defaults to the more
    # conservative classification.
    out["bottomup_state"] = np.select(
        [is_avoid, is_underweight, is_overweight],
        ["Avoid", "Underweight", "Overweight"],
        default="Neutral",
    )

    # ---- Top-down state classification ------------------------------------
    # Use top-down ret_3m / RS-vs-Nifty500 as a simple proxy. Top-down state
    # is informational; final sector_state is bottomup-driven per methodology
    # priority. RS is price-relative delta form: (1+index_ret)/(1+bench_ret) - 1,
    # centered around 0. >0.05 = meaningful outperformance, <-0.05 = meaningful
    # underperformance. Using ratio-form thresholds (1.05/0.95) was wrong — those
    # values can never be reached in delta form.
    td_rs = out["topdown_rs_3m_nifty500"]
    td_ret = out["topdown_ret_3m"]
    # RS is price-relative delta form: (1+index_ret)/(1+bench_ret) - 1,
    # centered around 0. >0.05 = meaningful outperformance, <-0.05 = meaningful underperformance.
    out["topdown_state"] = np.select(
        [
            td_rs > 0.05,
            td_rs < -0.05,
            (td_ret < 0),
        ],
        ["Overweight", "Avoid", "Underweight"],
        default="Neutral",
    )
    # Where top-down inputs are NaN, mark as Neutral rather than carry numeric
    # state through (avoid silent miscoding).
    no_topdown = td_rs.isna() & td_ret.isna()
    out.loc[no_topdown, "topdown_state"] = "Neutral"

    # ---- Final sector_state ------------------------------------------------
    # Sector_state takes the bottom-up classification (per methodology §10.5
    # Sector States table — the four states are bottom-up driven). Top-down
    # is captured for divergence reporting only.
    out["sector_state"] = out["bottomup_state"]

    # ---- Divergence flag ---------------------------------------------------
    # rank both bottomup_ret_3m and topdown_ret_3m cross-sectorally per date,
    # flag when |rank_bu - rank_td| > 1 (i.e., they're more than 1 rank apart).
    bu_rank = out.groupby("date")["bottomup_ret_3m"].rank(method="average")
    td_rank = out.groupby("date")["topdown_ret_3m"].rank(method="average")
    rank_diff = (bu_rank - td_rank).abs()
    out["divergence_flag"] = (rank_diff > 1).fillna(False).astype(bool)

    # GUARD: per-locked-decision #6, when two sectors share the same top-down
    # primary_nse_index (e.g. Power + Energy both = NIFTY ENERGY), the rank
    # difference is meaningless. Detect duplicates within each date and zero
    # the flag for those rows.
    dup_mask = out.groupby(["date", "topdown_index_code"])["sector_name"].transform("count") > 1
    out.loc[dup_mask, "divergence_flag"] = False

    out["participation_rs_pct"] = (out["participation_rs"] * 100).astype("float64")

    return out


# --------------------------------------------------------------------------- #
# Pure pipeline orchestrator                                                  #
# --------------------------------------------------------------------------- #


def compute_rs_velocity(
    df_metrics: pd.DataFrame,
    window_days: int = 28,
) -> pd.DataFrame:
    """Compute ``rs_velocity``: 4-week rate-of-change of ``bottomup_rs_3m_nifty500``.

    Formula::

        rs_velocity = (RS_today - RS_N_days_ago) / |RS_N_days_ago|

    where ``N = window_days`` (default 28 calendar days, tunable via
    ``atlas_thresholds`` key ``rs_velocity_window_days``).

    Division guard: if ``RS_N_days_ago == 0``, ``rs_velocity`` is NaN
    (not ``inf``).

    Args:
        df_metrics: long-form DataFrame with columns ``sector_name``,
            ``date``, ``bottomup_rs_3m_nifty500``. May contain other
            columns — they are preserved unchanged.
        window_days: look-back window in calendar days. Caller passes
            ``int(thresholds.get("rs_velocity_window_days", 28))``.

    Returns:
        The same DataFrame with a new ``rs_velocity`` column added (float,
        NaN for dates with insufficient lookback).
    """
    if df_metrics.empty:
        return df_metrics.assign(rs_velocity=pd.NA)

    # Work on a copy keyed by sector + date so we don't disturb the caller's frame.
    work = df_metrics[["sector_name", "date", "bottomup_rs_3m_nifty500"]].copy()
    work["date"] = pd.to_datetime(work["date"])
    work = work.sort_values(["sector_name", "date"]).reset_index(drop=True)

    # For each (sector, date) find the most-recent row whose date is at most
    # ``window_days`` calendar days earlier. We use merge_asof per sector
    # so that one sector's lagged RS cannot leak into another.
    prior_frames: list[pd.DataFrame] = []
    for _, grp in work.groupby("sector_name", sort=False):
        grp_sorted = grp.sort_values("date").reset_index(drop=True)

        # Build a lagged frame whose ``date`` is shifted forward by
        # ``window_days`` — merge_asof BACKWARD on this gives the most
        # recent row whose original date is at most window_days before.
        lagged = grp_sorted[["date", "bottomup_rs_3m_nifty500"]].copy()
        lagged = lagged.rename(columns={"bottomup_rs_3m_nifty500": "rs_prior"})
        lagged["date"] = lagged["date"] + pd.Timedelta(days=window_days)
        lagged = lagged.sort_values("date").reset_index(drop=True)

        merged = pd.merge_asof(
            grp_sorted,
            lagged,
            on="date",
            direction="backward",
            tolerance=pd.Timedelta(days=5),  # ±5d slack for trading-day gaps
        )
        prior_frames.append(merged[["sector_name", "date", "bottomup_rs_3m_nifty500", "rs_prior"]])

    prior_df = pd.concat(prior_frames, ignore_index=True)

    # Rate-of-change with near-zero guard. Replace any denominator with absolute
    # value < 0.001 with NA so tiny RS bases (common in early/volatile history)
    # don't produce 10000+ velocities that overflow NUMERIC(10,6).
    # Clip result to ±10 (±1000% ROC) for the same reason.
    rs_base = prior_df["rs_prior"].abs()
    rs_base = rs_base.where(rs_base >= 0.001, other=pd.NA)
    raw_velocity = (prior_df["bottomup_rs_3m_nifty500"] - prior_df["rs_prior"]) / rs_base
    prior_df["rs_velocity"] = raw_velocity.clip(-10, 10)

    # Join velocity back onto the original frame. Drop any pre-existing
    # rs_velocity column first (assemble_sector_metrics seeds it as NaN via
    # reindex) so pandas merge doesn't produce rs_velocity_x / rs_velocity_y.
    velocity_col = prior_df[["sector_name", "date", "rs_velocity"]]
    out = df_metrics.drop(columns=["rs_velocity"], errors="ignore").copy()
    # Align dtypes for the merge key so caller frames using ``date`` as Python
    # ``date`` objects still join correctly.
    out["date"] = pd.to_datetime(out["date"])
    out = out.merge(velocity_col, on=["sector_name", "date"], how="left")
    return out


def assemble_sector_metrics(
    df_bottomup: pd.DataFrame,
    df_topdown: pd.DataFrame,
    df_breadth: pd.DataFrame,
) -> pd.DataFrame:
    """Outer-join the three frames into the schema layout.

    Output columns match :data:`METRICS_COLUMNS` minus ``compute_run_id``.
    """
    if df_bottomup.empty:
        return pd.DataFrame(columns=[c for c in METRICS_COLUMNS if c != "compute_run_id"])

    keys = ["sector_name", "date"]
    out = df_bottomup.merge(df_topdown, on=keys, how="left")
    out = out.merge(df_breadth, on=keys, how="left")

    schema_cols = [c for c in METRICS_COLUMNS if c != "compute_run_id"]
    return out.reindex(columns=schema_cols)


# --------------------------------------------------------------------------- #
# New v6 sector columns (B.2 — rs windows, breadth EMA, 52wh, HHI)          #
# --------------------------------------------------------------------------- #


def compute_rs_windows(
    sector_returns: pd.DataFrame,
    nifty500_returns: pd.DataFrame,
) -> pd.DataFrame:
    """Compute sector RS vs Nifty 500 for 1w / 1m / 6m / 12m windows.

    RS definition: simple difference — sector bottom-up return minus Nifty 500
    return for the same window and date.  Simple diff (not price-relative ratio)
    because the column spec says "sector return - Nifty 500 return"; the
    price-relative version is already in ``bottomup_rs_*_nifty500``.

    Args:
        sector_returns: DataFrame with columns ``sector_name``, ``date``,
            ``bottomup_ret_1w``, ``bottomup_ret_1m``, ``bottomup_ret_6m``,
            ``bottomup_ret_12m``.  Output of an extended
            :func:`compute_bottom_up_sector_metrics` that includes ret_6m/12m.
        nifty500_returns: DataFrame with columns ``date``,
            ``_n500_ret_1w``, ``_n500_ret_1m``, ``_n500_ret_6m``,
            ``_n500_ret_12m``.  May be empty — all RS cols come out NaN.

    Returns:
        Long-form DataFrame with ``sector_name``, ``date``,
        ``rs_1w``, ``rs_1m``, ``rs_6m``, ``rs_12m``.
    """
    expected_out_cols = ["sector_name", "date", "rs_1w", "rs_1m", "rs_6m", "rs_12m"]
    if sector_returns.empty:
        return pd.DataFrame(columns=expected_out_cols)

    work = sector_returns[
        [
            "sector_name",
            "date",
            "bottomup_ret_1w",
            "bottomup_ret_1m",
            "bottomup_ret_6m",
            "bottomup_ret_12m",
        ]
    ].copy()

    if nifty500_returns.empty:
        for col in ("rs_1w", "rs_1m", "rs_6m", "rs_12m"):
            work[col] = np.nan
        return work[expected_out_cols]

    merged = work.merge(nifty500_returns, on="date", how="left")
    merged["rs_1w"] = merged["bottomup_ret_1w"].astype("float64") - merged["_n500_ret_1w"].astype(
        "float64"
    )
    merged["rs_1m"] = merged["bottomup_ret_1m"].astype("float64") - merged["_n500_ret_1m"].astype(
        "float64"
    )
    merged["rs_6m"] = merged["bottomup_ret_6m"].astype("float64") - merged["_n500_ret_6m"].astype(
        "float64"
    )
    merged["rs_12m"] = merged["bottomup_ret_12m"].astype("float64") - merged[
        "_n500_ret_12m"
    ].astype("float64")
    log.info(
        "rs_windows_computed",
        sectors=merged["sector_name"].nunique(),
        dates=merged["date"].nunique(),
    )
    return merged[expected_out_cols]


def compute_breadth_per_sector(
    constituents_metrics: pd.DataFrame,
) -> pd.DataFrame:
    """Per (sector, date) EMA breadth: fraction above EMA-20 and EMA-200.

    Args:
        constituents_metrics: DataFrame with columns ``sector_name``, ``date``,
            ``ema_20_ratio`` (close / ema20; >1 means close above ema20),
            ``extension_pct`` (close/ema200 - 1; >0 means above ema200).
            NULL rows are excluded from both numerator and denominator.

    Returns:
        Long-form DataFrame with ``sector_name``, ``date``,
        ``pct_above_ema20``, ``pct_above_ema200``.
        Values are floats in [0, 1]; NaN if no valid rows for that cohort.
    """
    expected_cols = ["sector_name", "date", "pct_above_ema20", "pct_above_ema200"]
    if constituents_metrics.empty:
        return pd.DataFrame(columns=expected_cols)

    # ---- pct_above_ema20 ---------------------------------------------------
    ema20_work = constituents_metrics.dropna(subset=["ema_20_ratio"]).copy()
    is_above_ema20 = (ema20_work["ema_20_ratio"].astype("float64") > 1.0).astype(int)
    pct_ema20 = (
        is_above_ema20.groupby([ema20_work["sector_name"], ema20_work["date"]], observed=True)
        .mean()
        .rename("pct_above_ema20")
    )

    # ---- pct_above_ema200 --------------------------------------------------
    ema200_work = constituents_metrics.dropna(subset=["extension_pct"]).copy()
    is_above_ema200 = (ema200_work["extension_pct"].astype("float64") > 0.0).astype(int)
    pct_ema200 = (
        is_above_ema200.groupby([ema200_work["sector_name"], ema200_work["date"]], observed=True)
        .mean()
        .rename("pct_above_ema200")
    )

    out = pd.concat([pct_ema20, pct_ema200], axis=1).reset_index()
    log.info(
        "ema_breadth_computed",
        sectors=out["sector_name"].nunique(),
        dates=out["date"].nunique(),
    )
    return out[expected_cols]


def compute_52wh_per_sector(
    constituents_metrics: pd.DataFrame,
    proximity_threshold: float = 0.05,
) -> pd.DataFrame:
    """Per (sector, date) fraction of constituents within N% of 52-week high.

    ``pct_52wh`` = fraction of constituents where
    ``close_approx / rolling_max_252 > (1 - proximity_threshold)``.

    The caller must supply ``rolling_max_252`` (252-day rolling maximum of
    close_adj per instrument) in the DataFrame — this function is pure
    computation, not data loading.

    Args:
        constituents_metrics: DataFrame with columns ``sector_name``, ``date``,
            ``close_approx``, ``rolling_max_252``.
            Rows with NULL in either column are excluded.
        proximity_threshold: default 0.05 (5%). Stock qualifies when
            ``close / max > 1 - threshold``, i.e. within 5% of the high.

    Returns:
        Long-form DataFrame with ``sector_name``, ``date``, ``pct_52wh``.
    """
    expected_cols = ["sector_name", "date", "pct_52wh"]
    if constituents_metrics.empty:
        return pd.DataFrame(columns=expected_cols)

    work = constituents_metrics.dropna(subset=["close_approx", "rolling_max_252"]).copy()
    if work.empty:
        return pd.DataFrame(columns=expected_cols)

    close = work["close_approx"].astype("float64")
    peak = work["rolling_max_252"].astype("float64")
    # Guard against zero-peak (shouldn't happen with real prices, but be safe)
    ratio = np.where(peak > 0, close / peak, np.nan)
    work["_near_52wh"] = (ratio > (1.0 - proximity_threshold)).astype("float64")
    # rows where ratio is NaN → _near_52wh becomes 0 due to comparison, but we
    # want them excluded. Re-null them.
    work.loc[np.isnan(ratio), "_near_52wh"] = np.nan

    pct_52wh = (
        work["_near_52wh"]
        .groupby([work["sector_name"], work["date"]], observed=True)
        .mean()
        .rename("pct_52wh")
    )
    out = pct_52wh.reset_index()
    log.info(
        "pct_52wh_computed",
        sectors=out["sector_name"].nunique(),
        dates=out["date"].nunique(),
    )
    return out[expected_cols]


def compute_concentration_per_sector(
    constituents_metrics: pd.DataFrame,
) -> pd.DataFrame:
    """Per (sector, date) Herfindahl-Hirschman Index (HHI) of market concentration.

    HHI = sum(s_i^2) where s_i is constituent i's share of total sector
    traded value.  Traded value proxy: ``avg_volume_20 * close_approx``
    (same proxy used in :func:`_compute_traded_value_weight`).

    ``de_market_cap_history`` is empty (verified 2026-05-27); traded value is
    the canonical proxy per the existing sector pipeline design.

    Range: [1/n, 1]. Single stock → 1.0. Equal weight → 1/n.

    Args:
        constituents_metrics: DataFrame with columns ``sector_name``, ``date``,
            ``avg_volume_20``, ``close_approx``.  Rows with NULL in either
            column (or non-positive traded value) are excluded.

    Returns:
        Long-form DataFrame with ``sector_name``, ``date``, ``hhi``.
        NaN if no constituents with valid traded value for that cohort.
    """
    expected_cols = ["sector_name", "date", "hhi"]
    if constituents_metrics.empty:
        return pd.DataFrame(columns=expected_cols)

    work = constituents_metrics.dropna(subset=["close_approx", "avg_volume_20"]).copy()
    if work.empty:
        return pd.DataFrame(columns=expected_cols)

    vol = pd.to_numeric(work["avg_volume_20"], errors="coerce")
    close = pd.to_numeric(work["close_approx"], errors="coerce")
    work["_tv"] = vol * close
    # Exclude non-positive traded values (0 or negative are data errors)
    work = work[work["_tv"] > 0].copy()
    if work.empty:
        return pd.DataFrame(columns=expected_cols)

    grp = work.groupby(["sector_name", "date"], observed=True)
    tv_total = grp["_tv"].transform("sum")
    work["_share"] = work["_tv"] / tv_total
    work["_share_sq"] = work["_share"] ** 2

    hhi = (
        work["_share_sq"]
        .groupby([work["sector_name"], work["date"]], observed=True)
        .sum()
        .rename("hhi")
    )
    out = hhi.reset_index()
    log.info(
        "hhi_computed",
        sectors=out["sector_name"].nunique(),
        dates=out["date"].nunique(),
    )
    return out[expected_cols]


# --------------------------------------------------------------------------- #
# DB writers                                                                  #
# --------------------------------------------------------------------------- #


def _write_metrics(
    engine: Engine,
    df: pd.DataFrame,
    run_id: uuid.UUID,
) -> int:
    if df.empty:
        return 0
    df = df.copy()
    df = df.replace([np.inf, -np.inf], np.nan)
    df["compute_run_id"] = str(run_id)
    payload = df.reindex(columns=list(METRICS_COLUMNS))
    return bulk_upsert(
        engine,
        table="atlas.atlas_sector_metrics_daily",
        columns=list(METRICS_COLUMNS),
        rows=df_to_pg_rows(payload),
        pk_columns=["sector_name", "date"],
    )


def _write_states(
    engine: Engine,
    df: pd.DataFrame,
    run_id: uuid.UUID,
) -> int:
    if df.empty:
        return 0
    df = df.copy()
    df["compute_run_id"] = str(run_id)
    payload = df.reindex(columns=list(STATES_COLUMNS))
    # NOT NULL columns per schema §4.3
    payload = payload.dropna(subset=["sector_state", "divergence_flag"])
    return bulk_upsert(
        engine,
        table="atlas.atlas_sector_states_daily",
        columns=list(STATES_COLUMNS),
        rows=df_to_pg_rows(payload),
        pk_columns=["sector_name", "date"],
    )


# --------------------------------------------------------------------------- #
# Top-level runners                                                           #
# --------------------------------------------------------------------------- #


def _run_pipeline(
    engine: Engine,
    *,
    start: date,
    end: date,
    write_start: date | None = None,
) -> dict[str, object]:
    """Shared orchestration for both backfill + daily.

    Loads stock metrics with ``[start, end]`` (lookback already applied
    inside :func:`load_sector_stock_data`), computes bottom-up / top-down /
    breadth / states, and writes only rows where ``date >= write_start``.
    """
    run_id = uuid.uuid4()
    started = time.time()

    log.info(
        "sector_pipeline_start",
        run_id=str(run_id),
        start=str(start),
        end=str(end),
    )

    sector_master = load_sector_master(engine)
    thresholds = load_thresholds("atlas", engine)
    stock_data = load_sector_stock_data(engine, start_date=start, end_date=end)
    index_metrics = load_index_metrics(engine, start_date=start, end_date=end)
    nifty500_returns = load_nifty500_returns(engine, start_date=start, end_date=end)

    bottomup = compute_bottom_up_sector_metrics(
        stock_data, sector_master, df_nifty500_returns=nifty500_returns
    )
    breadth = compute_sector_breadth(stock_data, sector_master)
    topdown = compute_top_down_sector_metrics(index_metrics, sector_master)

    metrics = assemble_sector_metrics(bottomup, topdown, breadth)

    # SP02: compute rs_velocity after assembly (needs full sector × date frame).
    # ``load_thresholds`` returns ``dict[str, Decimal]`` → coerce to int.
    velocity_window = int(thresholds.get("rs_velocity_window_days", Decimal("28")))
    metrics = compute_rs_velocity(metrics, window_days=velocity_window)

    states = compute_sector_states(metrics, thresholds)

    if write_start is not None:
        _ws = pd.Timestamp(write_start)
        metrics = metrics.loc[metrics["date"] >= _ws].copy()
        states = states.loc[states["date"] >= _ws].copy()

    metric_rows = _write_metrics(engine, metrics, run_id)
    state_rows = _write_states(engine, states, run_id)

    duration = round(time.time() - started, 1)
    log.info(
        "sector_pipeline_complete",
        run_id=str(run_id),
        metric_rows=metric_rows,
        state_rows=state_rows,
        duration_sec=duration,
    )
    return {
        "run_id": str(run_id),
        "metric_rows": metric_rows,
        "state_rows": state_rows,
        "duration_sec": duration,
    }


def backfill_sector_metrics(
    engine: Engine | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> int:
    """Full historical backfill (default: HISTORICAL_START_DATE → today)."""
    eng = engine or get_engine()
    start = start_date or pd.to_datetime(Config.HISTORICAL_START_DATE).date()
    end = end_date or date.today()

    result = _run_pipeline(eng, start=start, end=end, write_start=start)
    return int(str(result["metric_rows"]))


def run_daily_sector_metrics(engine: Engine | None = None) -> int:
    """Incremental run for the last ~5 trading days.

    Loads ``[today - 10cal_days, today]`` plus the lookback buffer inside
    :func:`load_sector_stock_data`, and writes only rows >= ``today - 10cal``.
    """
    eng = engine or get_engine()
    today = date.today()
    window_start = today - timedelta(days=10)
    result = _run_pipeline(eng, start=window_start, end=today, write_start=window_start)
    return int(str(result["metric_rows"]))


__all__ = [
    "METRICS_COLUMNS",
    "STATES_COLUMNS",
    "assemble_sector_metrics",
    "backfill_sector_metrics",
    "compute_52wh_per_sector",
    "compute_bottom_up_sector_metrics",
    "compute_breadth_per_sector",
    "compute_concentration_per_sector",
    "compute_rs_velocity",
    "compute_rs_windows",
    "compute_sector_breadth",
    "compute_sector_states",
    "compute_top_down_sector_metrics",
    "load_index_metrics",
    "load_nifty500_returns",
    "load_sector_master",
    "load_sector_stock_data",
    "run_daily_sector_metrics",
]
