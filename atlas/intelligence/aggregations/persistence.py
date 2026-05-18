"""UPSERT writers for atlas_*_state_v2 aggregate tables.

Each function accepts a pandas DataFrame of aggregate rows produced by the
sector/fund/etf aggregators and upserts them into the corresponding v2 table.
ON CONFLICT DO UPDATE ensures idempotency — re-running the nightly compute
with the same data is safe.

NULL handling: mean_within_state_rank and mean_rs_rank_12m are nullable in
the schema. Pass Python None; SQLAlchemy maps it to SQL NULL correctly.

Returns the row count inserted/updated so callers can log before/after counts.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

_SECTOR_UPSERT_SQL = text("""
    INSERT INTO atlas.atlas_sector_state_v2 (
        sector, date, dominant_state, dominant_share, n_constituents,
        mean_within_state_rank, pct_stage_2, pct_stage_3, pct_stage_4,
        pct_stage_1, pct_uninvestable
    ) VALUES (
        :sector, :date, :dominant_state, :dominant_share, :n_constituents,
        :mean_within_state_rank, :pct_stage_2, :pct_stage_3, :pct_stage_4,
        :pct_stage_1, :pct_uninvestable
    )
    ON CONFLICT (sector, date) DO UPDATE SET
        dominant_state         = EXCLUDED.dominant_state,
        dominant_share         = EXCLUDED.dominant_share,
        n_constituents         = EXCLUDED.n_constituents,
        mean_within_state_rank = EXCLUDED.mean_within_state_rank,
        pct_stage_2            = EXCLUDED.pct_stage_2,
        pct_stage_3            = EXCLUDED.pct_stage_3,
        pct_stage_4            = EXCLUDED.pct_stage_4,
        pct_stage_1            = EXCLUDED.pct_stage_1,
        pct_uninvestable       = EXCLUDED.pct_uninvestable,
        computed_at            = CURRENT_TIMESTAMP
""")


def persist_sector_state_v2(engine: Engine, df: pd.DataFrame) -> int:
    """UPSERT sector aggregate rows into atlas_sector_state_v2.

    Args:
        engine: SQLAlchemy engine connected to the atlas DB.
        df: DataFrame with columns matching atlas_sector_state_v2 (sector, date,
            dominant_state, dominant_share, n_constituents, mean_within_state_rank,
            pct_stage_2, pct_stage_3, pct_stage_4, pct_stage_1, pct_uninvestable).

    Returns:
        Number of rows upserted.
    """
    if df.empty:
        return 0
    records = df.to_dict(orient="records")
    with engine.begin() as c:
        c.execute(_SECTOR_UPSERT_SQL, records)
    return len(records)


_FUND_UPSERT_SQL = text("""
    INSERT INTO atlas.atlas_fund_state_v2 (
        mstar_id, date, composition_state, holdings_state,
        pct_holdings_stage_2, pct_holdings_stage_3, pct_holdings_stage_4,
        mean_within_state_rank, n_holdings
    ) VALUES (
        :mstar_id, :date, :composition_state, :holdings_state,
        :pct_holdings_stage_2, :pct_holdings_stage_3, :pct_holdings_stage_4,
        :mean_within_state_rank, :n_holdings
    )
    ON CONFLICT (mstar_id, date) DO UPDATE SET
        composition_state      = EXCLUDED.composition_state,
        holdings_state         = EXCLUDED.holdings_state,
        pct_holdings_stage_2   = EXCLUDED.pct_holdings_stage_2,
        pct_holdings_stage_3   = EXCLUDED.pct_holdings_stage_3,
        pct_holdings_stage_4   = EXCLUDED.pct_holdings_stage_4,
        mean_within_state_rank = EXCLUDED.mean_within_state_rank,
        n_holdings             = EXCLUDED.n_holdings,
        computed_at            = CURRENT_TIMESTAMP
""")


def persist_fund_state_v2(engine: Engine, df: pd.DataFrame) -> int:
    """UPSERT fund composition aggregate rows into atlas_fund_state_v2.

    Args:
        engine: SQLAlchemy engine connected to the atlas DB.
        df: DataFrame with columns matching atlas_fund_state_v2 (mstar_id, date,
            composition_state, holdings_state, pct_holdings_stage_2,
            pct_holdings_stage_3, pct_holdings_stage_4, mean_within_state_rank,
            n_holdings).

    Returns:
        Number of rows upserted.
    """
    if df.empty:
        return 0
    records = df.to_dict(orient="records")
    with engine.begin() as c:
        c.execute(_FUND_UPSERT_SQL, records)
    return len(records)


_ETF_UPSERT_SQL = text("""
    INSERT INTO atlas.atlas_etf_state_v2 (
        etf_ticker, date, dominant_state, dominant_share,
        n_holdings, mean_rs_rank_12m,
        pct_stage_2, pct_stage_3, pct_stage_4
    ) VALUES (
        :etf_ticker, :date, :dominant_state, :dominant_share,
        :n_holdings, :mean_rs_rank_12m,
        :pct_stage_2, :pct_stage_3, :pct_stage_4
    )
    ON CONFLICT (etf_ticker, date) DO UPDATE SET
        dominant_state    = EXCLUDED.dominant_state,
        dominant_share    = EXCLUDED.dominant_share,
        n_holdings        = EXCLUDED.n_holdings,
        mean_rs_rank_12m  = EXCLUDED.mean_rs_rank_12m,
        pct_stage_2       = EXCLUDED.pct_stage_2,
        pct_stage_3       = EXCLUDED.pct_stage_3,
        pct_stage_4       = EXCLUDED.pct_stage_4,
        computed_at       = CURRENT_TIMESTAMP
""")


def persist_etf_state_v2(engine: Engine, df: pd.DataFrame) -> int:
    """UPSERT ETF aggregate rows into atlas_etf_state_v2.

    Args:
        engine: SQLAlchemy engine connected to the atlas DB.
        df: DataFrame with columns matching atlas_etf_state_v2 (etf_ticker, date,
            dominant_state, dominant_share, n_holdings, mean_rs_rank_12m,
            pct_stage_2, pct_stage_3, pct_stage_4).

    Returns:
        Number of rows upserted.
    """
    if df.empty:
        return 0
    records = df.to_dict(orient="records")
    with engine.begin() as c:
        c.execute(_ETF_UPSERT_SQL, records)
    return len(records)
