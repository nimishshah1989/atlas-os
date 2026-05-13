"""Widen NUMERIC(10,8) columns in us_atlas.atlas_stock_metrics_daily to NUMERIC(20,8).

NUMERIC(10,8) allows max absolute value of 99.99... which overflows for:
- ret_12m on stocks with >9900% gains (2008-2010 recovery, meme stocks)
- rs_12m_* = stock_ret - bench_ret, same overflow risk
- extension_pct on extreme bubbles

NUMERIC(20,8) gives 12 integer digits (max ≈ 999 billion), safe for all realistic returns.

Revision ID: 063
Revises: 062
Create Date: 2026-05-13
"""

from alembic import op

revision = "063"
down_revision = "062"
branch_labels = None
depends_on = None

_COLS = [
    "ret_1d",
    "ret_1w",
    "ret_1m",
    "ret_3m",
    "ret_6m",
    "ret_12m",
    "ret_12m_1m",
    "ema_10_ratio",
    "ema_20_ratio",
    "realized_vol_63",
    "vol_ratio_63",
    "max_drawdown_252",
    "extension_pct",
    "atr_21",
    # RS vs ACWI
    "rs_1w_acwi",
    "rs_1m_acwi",
    "rs_3m_acwi",
    "rs_6m_acwi",
    "rs_12m_acwi",
    # RS vs VT
    "rs_1w_vt",
    "rs_1m_vt",
    "rs_3m_vt",
    "rs_6m_vt",
    "rs_12m_vt",
    # RS vs EEM
    "rs_1w_eem",
    "rs_1m_eem",
    "rs_3m_eem",
    "rs_6m_eem",
    "rs_12m_eem",
    # RS vs GOLD
    "rs_1w_gold",
    "rs_1m_gold",
    "rs_3m_gold",
    "rs_6m_gold",
    "rs_12m_gold",
    # Volume ratios
    "volume_expansion",
    "effort_ratio_63",
]


def upgrade() -> None:
    alters = ",\n        ".join(
        f"ALTER COLUMN {col} TYPE NUMERIC(20, 8)" for col in _COLS
    )
    op.execute(f"""
        ALTER TABLE us_atlas.atlas_stock_metrics_daily
            {alters}
    """)


def downgrade() -> None:
    alters = ",\n        ".join(
        f"ALTER COLUMN {col} TYPE NUMERIC(10, 8)" for col in _COLS
    )
    op.execute(f"""
        ALTER TABLE us_atlas.atlas_stock_metrics_daily
            {alters}
    """)
