"""blend() must reproduce compute_composite EXACTLY on real atlas_foundation rows.

The US platform replaces India's module-constant composite with a function that takes
lenses, weights and tiers as arguments. The only acceptable proof that nothing changed in
the arithmetic is running both on the same REAL inputs — the latest session's lens journal
and the LIVE thresholds table — and demanding equality on every row (rule #0: no fixtures).

Read-only. Skips (does not fail) when no ATLAS_DB_URL is available.
"""

from __future__ import annotations

import math
import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts" / "foundation"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import _db  # noqa: E402  # pyright: ignore[reportMissingImports]

from atlas.db import load_thresholds  # noqa: E402
from atlas.global_market.scoring.blend import (  # noqa: E402
    DEFAULT_ORDER,
    blend,
    tiers_from_thresholds,
    weights_from_thresholds,
)
from atlas.lenses.compute.composite import compute_composite  # noqa: E402
from atlas.lenses.compute.thresholds_view import nest_thresholds  # noqa: E402

pytestmark = pytest.mark.integration

try:
    _db.db_url()
except RuntimeError:
    pytest.skip("ATLAS_DB_URL not set — the parity test needs the live DB", allow_module_level=True)

# India's _LENS_NAMES order. Float summation is order-sensitive, so the parity claim is
# made in the order compute_composite itself iterates.
LENSES = ("technical", "fundamental", "catalyst", "flow")
MIN_ROWS = 500


def _dec(v: object) -> Decimal | None:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return Decimal(str(v))


def _flt(v: object) -> float | None:
    d = _dec(v)
    return None if d is None else float(d)


@pytest.fixture(scope="module")
def latest_rows() -> pd.DataFrame:
    mx = _db.scalar(
        "select max(date) from atlas_foundation.atlas_lens_scores_daily where asset_class = 'stock'"
    )
    assert mx is not None, "lens journal is empty"
    df = _db.read_df(
        """select instrument_id, technical, fundamental, catalyst, flow,
                  composite, conviction_tier, lenses_active
           from atlas_foundation.atlas_lens_scores_daily
           where asset_class = 'stock' and date = :d""",
        {"d": mx},
    )
    assert len(df) >= MIN_ROWS, f"only {len(df)} rows on {mx}; need ≥ {MIN_ROWS} for a real claim"
    return df


@pytest.fixture(scope="module")
def flat_thresholds() -> dict[str, Decimal]:
    return load_thresholds("atlas_foundation", engine=_db.engine())


def test_live_weight_keys_exist_and_are_positive(flat_thresholds: dict[str, Decimal]) -> None:
    """Precondition for the parity claim: blend() counts only WEIGHTED lenses as active,
    India counts every present lens. They agree iff every live weight is > 0 — if the FM
    ever zeroes one, this says so instead of the row comparison failing obscurely."""
    weights = weights_from_thresholds(flat_thresholds, LENSES)
    assert all(w > 0 for w in weights.values()), weights


def test_blend_matches_compute_composite_on_every_latest_row(
    latest_rows: pd.DataFrame, flat_thresholds: dict[str, Decimal]
) -> None:
    th = nest_thresholds(flat_thresholds)
    weights = weights_from_thresholds(flat_thresholds, LENSES)
    tiers = tiers_from_thresholds(flat_thresholds)

    mismatches: list[tuple[object, ...]] = []
    n_signal = 0
    for row in latest_rows.to_dict("records"):
        india = compute_composite(
            technical=_flt(row["technical"]),
            fundamental=_flt(row["fundamental"]),
            valuation_score=None,
            catalyst=_flt(row["catalyst"]),
            flow=_flt(row["flow"]),
            policy=None,
            valuation_multiplier=1.0,
            smart_money_score=0.0,
            degradation_score=0.0,
            thresholds=th,
        )
        us = blend({lens: _dec(row[lens]) for lens in LENSES}, weights, tiers)
        if india.lenses_active == 0:
            # India's no-signal sentinel is 0.00; ours is None. Same tier, same count.
            ok = us.composite is None and us.lenses_active == 0
            ok = ok and us.conviction_tier == india.conviction_tier
        else:
            n_signal += 1
            ok = (
                us.composite == india.final_score
                and us.conviction_tier == india.conviction_tier
                and us.lenses_active == india.lenses_active
            )
        if not ok:
            mismatches.append(
                (
                    row["instrument_id"],
                    india.final_score,
                    india.conviction_tier,
                    india.lenses_active,
                    us.composite,
                    us.conviction_tier,
                    us.lenses_active,
                )
            )

    assert n_signal >= MIN_ROWS, f"only {n_signal} rows carry a weighted lens; need ≥ {MIN_ROWS}"
    assert not mismatches, (
        f"{len(mismatches)} of {len(latest_rows)} rows differ "
        "(instrument, india_score, india_tier, india_active, us_score, us_tier, us_active):\n"
        + "\n".join(str(m) for m in mismatches[:10])
    )


def test_every_conviction_tier_in_the_journal_is_one_blend_can_emit(
    latest_rows: pd.DataFrame,
) -> None:
    """The stored tiers are what the board serves; blend()'s vocabulary must cover them."""
    stored = set(latest_rows["conviction_tier"].dropna())
    assert stored, "no conviction tiers stored on the latest date"
    assert stored <= set(DEFAULT_ORDER), stored - set(DEFAULT_ORDER)
