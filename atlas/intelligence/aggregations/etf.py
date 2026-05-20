"""Bottom-up ETF state aggregator — real holdings path.

Reads ``public.de_etf_holdings`` (constituent UUID instrument_ids + weights)
and joins to ``atlas.atlas_stock_state_daily`` to produce a true holdings-
weighted aggregate for each ETF.

Bridge key (confirmed 2026-05-20 audit):
    de_etf_holdings.instrument_id (UUID) → atlas_stock_state_daily.instrument_id (UUID)
    Joins directly; no intermediate F-id mapping needed.
    NSE tickers in de_etf_holdings.ticker may carry a ".NS" suffix — stripped for match.

Commodity ETFs (theme in {Gold, Silver}) hold no equity constituents. They are
detected via atlas_universe_etfs.theme and returned with NULL dominant_state /
n_holdings = 0. Their ticker-level RS/momentum state (from atlas_etf_states_daily)
is still available to callers that want commodity-ETF momentum — but this
aggregator does NOT produce a constituent rollup for them.

Forward-fill: de_etf_holdings has a single snapshot (2026-05-04). The load
function returns as-of the most recent available snapshot on or before the
requested date. The populate script handles daily forward-fill at the
application level by iterating dates and calling load for each.

Public API (callers unchanged):
    load_etf_holdings_panel(engine, as_of_date) -> pd.DataFrame
    aggregate_etf_states(panel) -> pd.DataFrame
"""
# allow-large: single-responsibility module with one SQL query + one aggregator

from __future__ import annotations

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.intelligence.aggregations.base import (
    AggregateState,
    weighted_state_distribution,
)

log = structlog.get_logger()

# Commodity ETF themes: no equity constituents — skip the holdings rollup.
_COMMODITY_THEMES: frozenset[str] = frozenset({"Gold", "Silver"})

# States in atlas_etf_states_daily that indicate no investable data.
_SKIP_RS_STATES = frozenset({"ILLIQUID", "INSUFFICIENT_HISTORY"})

# Approximate rs_rank_12m implied by each rs_state (kept for the ticker-level
# fallback path and for backward compatibility in tests).
_RS_STATE_TO_RANK: dict[str, float] = {
    "Leader": 0.95,
    "Strong": 0.80,
    "Average": 0.50,
    "Weak": 0.20,
    "Laggard": 0.05,
}

# Required columns in the panel passed to aggregate_etf_states.
_REQUIRED_PANEL_COLS: frozenset[str] = frozenset(
    {"etf_ticker", "date", "instrument_id", "weight", "state", "rs_rank_12m"}
)

# SQL: load constituent-level holdings panel.
# de_etf_holdings.ticker may be NIFTYBEES or NIFTYBEES.NS — normalise with REPLACE.
# Holdings snapshot: use MAX(as_of_date) on or before :as_of_date (forward-fill).
# Equity ETFs only: exclude tickers whose universe theme is Gold or Silver.
_HOLDINGS_SQL = text("""
    WITH snapshot_date AS (
        -- Most recent holdings snapshot on or before the requested date.
        -- NULL as_of_date -> use the most recent snapshot available (full reload mode).
        SELECT MAX(h.as_of_date) AS snap
        FROM public.de_etf_holdings h
        WHERE (:as_of_date IS NULL OR h.as_of_date <= CAST(:as_of_date AS date))
    ),
    equity_etfs AS (
        -- Active ETFs in the universe, excluding commodity ETFs.
        SELECT ticker
        FROM atlas.atlas_universe_etfs
        WHERE effective_to IS NULL
          AND (theme NOT IN ('Gold', 'Silver') OR theme IS NULL)
    ),
    holdings AS (
        SELECT
            REPLACE(h.ticker, '.NS', '')  AS etf_ticker,
            h.instrument_id,
            h.weight
        FROM public.de_etf_holdings h
        CROSS JOIN snapshot_date sd
        WHERE h.as_of_date = sd.snap
          AND REPLACE(h.ticker, '.NS', '') IN (SELECT ticker FROM equity_etfs)
    )
    SELECT
        ho.etf_ticker,
        ssd.date,
        ho.instrument_id::text       AS instrument_id,
        ho.weight,
        ssd.state,
        ssd.rs_rank_12m
    FROM holdings ho
    JOIN atlas.atlas_stock_state_daily ssd
        ON ssd.instrument_id = ho.instrument_id
       AND (:as_of_date IS NULL OR ssd.date = CAST(:as_of_date AS date))
       AND ssd.classifier_version = 'v2.0-validated'
    ORDER BY ho.etf_ticker, ssd.date, ho.weight DESC
""")


def _is_commodity_etf(ticker: str, theme: str | None) -> bool:
    """Return True if this ETF holds commodities (Gold/Silver) — no equity constituents."""
    return theme in _COMMODITY_THEMES


def _map_etf_to_weinstein(rs_state: str, momentum_state: str) -> str:
    """Map (rs_state, momentum_state) to a Weinstein stage string.

    Kept for backward compatibility and for tests. Not used in the main
    holdings-based aggregation path (which uses stock states directly).

    Returns one of: stage_2a, stage_2b, stage_2c, stage_3, stage_4,
    stage_1, uninvestable.
    """
    if rs_state in _SKIP_RS_STATES:
        return "uninvestable"
    if rs_state == "Leader" and momentum_state in ("Accelerating", "Improving", "Flat"):
        return "stage_2a"
    if rs_state == "Strong" and momentum_state in ("Accelerating", "Improving"):
        return "stage_2a"
    if rs_state == "Strong" and momentum_state == "Flat":
        return "stage_2b"
    if rs_state == "Average" and momentum_state == "Improving":
        return "stage_2c"
    if rs_state in ("Strong", "Average") and momentum_state == "Deteriorating":
        return "stage_3"
    if rs_state == "Average" and momentum_state in ("Flat", "Accelerating"):
        return "stage_1"
    if rs_state in ("Average", "Weak", "Laggard") and momentum_state == "Collapsing":
        return "stage_4"
    if rs_state in ("Weak", "Laggard") and momentum_state in ("Deteriorating", "Flat"):
        return "stage_4"
    return "stage_1"


def load_etf_holdings_panel(engine: Engine, as_of_date: str | None = None) -> pd.DataFrame:
    """Load a constituent-level ETF holdings panel.

    Each row represents one constituent stock of one equity ETF on one date.
    Commodity ETFs (Gold/Silver theme) are excluded — they hold no equities.

    For a full-range reload (as_of_date=None), the most recent holdings
    snapshot is used for ALL dates where stock state data exists. The populate
    script calls load_etf_holdings_panel per date to achieve forward-filling.

    Returns DataFrame with columns:
        etf_ticker, date, instrument_id, weight, state, rs_rank_12m

    Commodity ETFs not in the result — filter them at the universe level.
    """
    before_rows = None
    with engine.connect() as c:
        df = pd.read_sql(_HOLDINGS_SQL, c, params={"as_of_date": as_of_date})

    before_rows = len(df)
    # Guard: log NA counts in financial columns.
    na_state = int(df["state"].isna().sum()) if "state" in df.columns else 0
    na_rs = int(df["rs_rank_12m"].isna().sum()) if "rs_rank_12m" in df.columns else 0
    if na_state:
        log.warning("etf_holdings.null_state", count=na_state)
    if na_rs:
        log.info("etf_holdings.null_rs_rank", count=na_rs, note="normal for new listings")

    log.info(
        "etf_holdings.loaded",
        rows=before_rows,
        as_of_date=as_of_date,
        distinct_etfs=int(df["etf_ticker"].nunique()) if not df.empty else 0,
    )
    return df


def aggregate_etf_states(panel: pd.DataFrame) -> pd.DataFrame:
    """Aggregate constituent-level holdings panel into atlas_etf_state_v2 shape.

    Expects panel columns: etf_ticker, date, instrument_id, weight, state, rs_rank_12m.
    Raises ValueError if required columns are missing (guards against old ticker-level
    panel being passed by mistake).

    For each (etf_ticker, date) group:
    - n_holdings = count of distinct instrument_ids
    - dominant_state / dominant_share from weight-normalised state distribution
    - pct_stage_2 = sum of weights in stage_2a/2b/2c
    - pct_stage_3 = sum of weights in stage_3
    - pct_stage_4 = sum of weights in stage_4
    - mean_rs_rank_12m = weight-average of rs_rank_12m (NULL-safe; NULL weight ignored)

    Returns DataFrame with columns:
        etf_ticker, date, dominant_state, dominant_share, n_holdings,
        mean_rs_rank_12m, pct_stage_2, pct_stage_3, pct_stage_4
    """
    # Validate required columns (skip on truly empty DataFrame with no columns).
    if not panel.empty or len(panel.columns) > 0:
        missing = _REQUIRED_PANEL_COLS - set(panel.columns)
        if missing:
            raise ValueError(
                f"aggregate_etf_states: panel missing required columns: {sorted(missing)}. "
                "Pass a holdings panel from load_etf_holdings_panel(), not the old "
                "ticker-level panel from atlas_etf_states_daily."
            )

    if panel.empty:
        return pd.DataFrame(
            columns=[
                "etf_ticker",
                "date",
                "dominant_state",
                "dominant_share",
                "n_holdings",
                "mean_rs_rank_12m",
                "pct_stage_2",
                "pct_stage_3",
                "pct_stage_4",
            ]
        )

    panel = panel.copy()
    # Cast weight and rs_rank_12m to float (they may arrive as Decimal from Postgres).
    panel["weight"] = panel["weight"].astype(float)
    # rs_rank_12m: keep NaN for NULL-safe weighted mean.
    panel["rs_rank_12m"] = pd.to_numeric(panel["rs_rank_12m"], errors="coerce")

    before_rows = len(panel)
    rows: list[dict[str, object]] = []
    for (ticker, dt), group in panel.groupby(["etf_ticker", "date"]):
        n_holdings = int(group["instrument_id"].nunique())

        # State distribution by weight.
        state_weight_df = group[["state", "weight"]].dropna(subset=["state"])
        dist = weighted_state_distribution(state_weight_df)
        agg = AggregateState.from_distribution(dist)

        pct_stage_2 = (
            dist.get("stage_2a", 0.0) + dist.get("stage_2b", 0.0) + dist.get("stage_2c", 0.0)
        )

        # Weight-averaged RS rank — exclude constituents with NULL rs_rank_12m.
        valid_rs = group.dropna(subset=["rs_rank_12m"])
        if not valid_rs.empty:
            total_w = float(valid_rs["weight"].sum())
            if total_w > 0:
                mean_rs: float | None = float(
                    (valid_rs["rs_rank_12m"] * valid_rs["weight"]).sum() / total_w
                )
            else:
                mean_rs = None
        else:
            mean_rs = None

        rows.append(
            {
                "etf_ticker": ticker,
                "date": dt,
                "dominant_state": agg.dominant_state,
                "dominant_share": agg.dominant_share,
                "n_holdings": n_holdings,
                "mean_rs_rank_12m": mean_rs,
                "pct_stage_2": pct_stage_2,
                "pct_stage_3": dist.get("stage_3", 0.0),
                "pct_stage_4": dist.get("stage_4", 0.0),
            }
        )

    out = pd.DataFrame(rows)
    log.info(
        "etf.aggregate_done",
        input_rows=before_rows,
        output_rows=len(out),
        distinct_etfs=len(out["etf_ticker"].unique()) if not out.empty else 0,
    )
    return out
