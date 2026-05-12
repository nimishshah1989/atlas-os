"""SP04 Stage 3 seeder: insert the Stage-2 validated weights.

Idempotent. The partial unique index uq_signal_weights_active enforces at
most one active row per (tier, regime, signal_name); ON CONFLICT ... DO
NOTHING means re-running the script after weights are seeded is a no-op.

Source of truth for weights: Stage 2 holdout test (2023-2025 OOS). See
docs/phase2/plans/2026-05-12-sp04-stage3-conviction-production.md.
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal

import structlog
from sqlalchemy import text

from atlas.db import get_engine

log = structlog.get_logger()


# Holdout IC per tier, measured on 2023-2025 OOS data.
TIER_HOLDOUT_IC: dict[str, Decimal] = {
    "tier_1_megacap": Decimal("0.0511"),
    "tier_2_largecap": Decimal("0.0068"),
    "tier_3_uppermid": Decimal("0.0538"),
    "tier_4_lowermid": Decimal("0.0268"),
    "tier_5_smallcap": Decimal("0.0413"),
}


# (signal_name, weight, flipped) per tier. atr_21 is flipped in every tier
# because higher ATR predicts *lower* forward returns.
WEIGHTS: dict[str, list[tuple[str, Decimal, bool]]] = {
    "tier_1_megacap": [
        ("ma_30w_slope_4w", Decimal("0.161"), False),
        ("ret_6m", Decimal("0.145"), False),
        ("ret_12m_1m", Decimal("0.131"), False),
        ("extension_pct", Decimal("0.121"), False),
        ("vol_ratio_63", Decimal("0.119"), False),
        ("effort_ratio_63", Decimal("0.095"), False),
        ("realized_vol_63", Decimal("0.082"), False),
        ("max_drawdown_252", Decimal("0.067"), False),
        ("rs_pctile_3m", Decimal("0.053"), False),
        ("ema_10_ratio", Decimal("0.019"), False),
        ("atr_21", Decimal("0.006"), True),
    ],
    "tier_2_largecap": [
        ("ma_30w_slope_4w", Decimal("0.178"), False),
        ("ret_12m_1m", Decimal("0.170"), False),
        ("ret_6m", Decimal("0.146"), False),
        ("extension_pct", Decimal("0.141"), False),
        ("rs_pctile_3m", Decimal("0.115"), False),
        ("vol_ratio_63", Decimal("0.074"), False),
        ("effort_ratio_63", Decimal("0.069"), False),
        ("atr_21", Decimal("0.058"), True),
        ("ema_10_ratio", Decimal("0.046"), False),
        ("realized_vol_63", Decimal("0.003"), False),
    ],
    "tier_3_uppermid": [
        ("ma_30w_slope_4w", Decimal("0.252"), False),
        ("ret_12m_1m", Decimal("0.234"), False),
        ("ret_6m", Decimal("0.158"), False),
        ("extension_pct", Decimal("0.152"), False),
        ("effort_ratio_63", Decimal("0.086"), False),
        ("atr_21", Decimal("0.078"), True),
        ("rs_pctile_3m", Decimal("0.041"), False),
    ],
    "tier_4_lowermid": [
        ("ma_30w_slope_4w", Decimal("0.172"), False),
        ("max_drawdown_252", Decimal("0.161"), False),
        ("ret_12m_1m", Decimal("0.149"), False),
        ("atr_21", Decimal("0.120"), True),
        ("effort_ratio_63", Decimal("0.115"), False),
        ("realized_vol_63", Decimal("0.092"), False),
        ("extension_pct", Decimal("0.076"), False),
        ("vol_ratio_63", Decimal("0.062"), False),
        ("ret_6m", Decimal("0.053"), False),
    ],
    "tier_5_smallcap": [
        ("ret_12m_1m", Decimal("0.195"), False),
        ("ma_30w_slope_4w", Decimal("0.185"), False),
        ("ret_6m", Decimal("0.155"), False),
        ("extension_pct", Decimal("0.143"), False),
        ("rs_pctile_3m", Decimal("0.103"), False),
        ("atr_21", Decimal("0.080"), True),
        ("effort_ratio_63", Decimal("0.069"), False),
        ("ema_10_ratio", Decimal("0.057"), False),
        ("vol_ratio_63", Decimal("0.013"), False),
    ],
}


NOTES = (
    "Initial seeding from SP04 Stage 2 holdout test. "
    "Train period 2019-2022, holdout 2023-2025. "
    "atr_21 flipped (high ATR = lower forward returns)."
)

INSERT_SQL = """
    INSERT INTO atlas.atlas_signal_weights
        (tier, regime, signal_name, weight, flipped,
         effective_from, effective_to, train_ic, holdout_ic,
         approved_by, notes)
    VALUES
        (:tier, 'all', :signal_name, :weight, :flipped,
         :eff_from, NULL, NULL, :holdout_ic,
         'sp04-stage2-initial', :notes)
    ON CONFLICT (tier, regime, signal_name) WHERE effective_to IS NULL
    DO NOTHING
"""


def main() -> int:
    engine = get_engine()
    today = date.today()
    inserted = 0
    skipped = 0
    with engine.begin() as conn:
        for tier, rows in WEIGHTS.items():
            for signal_name, weight, flipped in rows:
                result = conn.execute(
                    text(INSERT_SQL),
                    {
                        "tier": tier,
                        "signal_name": signal_name,
                        "weight": weight,
                        "flipped": flipped,
                        "eff_from": today,
                        "holdout_ic": TIER_HOLDOUT_IC[tier],
                        "notes": NOTES,
                    },
                )
                if result.rowcount > 0:
                    inserted += 1
                else:
                    skipped += 1
    log.info("seed_signal_weights_complete", inserted=inserted, skipped=skipped)
    print(f"Inserted {inserted} rows; skipped {skipped} (already active)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
