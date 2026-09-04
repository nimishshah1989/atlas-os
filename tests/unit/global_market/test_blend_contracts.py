"""Error contracts of blend() — the no-hardcoded-numbers guarantees, exercised WITHOUT
computing a score.

Every lens value here is None (absent), so no composite is ever computed. The weights and
tiers a call needs are built by the real loaders from the FM's seed table
(``scripts/global_market/seed_thresholds.SEEDS`` — the plan's numbers, not values invented
for a test), so nothing here is a fixture, and a key the loaders need that the seed table
lacks fails here first. Anything numeric about scores is the integration parity test on
real rows.
"""

from __future__ import annotations

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from atlas.global_market.scoring.blend import (
    NO_SIGNAL_TIER,
    blend,
    tiers_from_thresholds,
    weights_from_thresholds,
)

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[3]
_SCRIPTS = _REPO / "scripts" / "global_market"

# The lens sets the plan blends (Methodology §B stocks, §C ETFs) — structure, not numbers.
STOCK_LENSES = ("technical", "fundamental", "catalyst", "flow")
ETF_LENSES = ("technical", "risk", "cost_liquidity", "flow", "quality")


def _seed_thresholds() -> dict[str, Decimal]:
    """The seed table as ``load_thresholds`` would return it once seeded."""
    if str(_SCRIPTS) not in sys.path:  # seed_thresholds does `import _gdb` (a sibling module)
        sys.path.insert(0, str(_SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "seed_thresholds", _SCRIPTS / "seed_thresholds.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return {str(r["threshold_key"]): Decimal(str(r["threshold_value"])) for r in mod.SEEDS}


@pytest.fixture(scope="module")
def seeds() -> dict[str, Decimal]:
    return _seed_thresholds()


def test_the_seed_table_carries_every_key_the_stock_blend_needs(seeds) -> None:
    weights = weights_from_thresholds(seeds, STOCK_LENSES)
    assert set(weights) == set(STOCK_LENSES)
    assert sum(weights.values()) == Decimal("1")
    tiers = tiers_from_thresholds(seeds)
    assert NO_SIGNAL_TIER in tiers


def test_the_seed_table_carries_every_etf_lens_weight(seeds) -> None:
    weights = weights_from_thresholds(seeds, ETF_LENSES, prefix="etf_lens_weight_")
    assert set(weights) == set(ETF_LENSES)
    assert sum(weights.values()) == Decimal("1")


def test_a_lens_without_a_weight_key_is_a_keyerror_even_when_absent(seeds) -> None:
    with pytest.raises(KeyError, match="lens_weight_"):
        blend({"technical": None}, weights={}, tiers=tiers_from_thresholds(seeds))


def test_an_order_entry_missing_from_tiers_is_a_keyerror(seeds) -> None:
    with pytest.raises(KeyError, match="tiers has no entry"):
        blend({"technical": None}, weights=weights_from_thresholds(seeds, ["technical"]), tiers={})


def test_nothing_present_is_no_signal_not_a_zero(seeds) -> None:
    result = blend(
        {"technical": None, "flow": None},
        weights=weights_from_thresholds(seeds, ["technical", "flow"]),
        tiers=tiers_from_thresholds(seeds),
    )
    assert result.composite is None
    assert result.conviction_tier == NO_SIGNAL_TIER == "BELOW_THRESHOLD"
    assert result.lenses_active == 0
    assert result.evidence["lenses_present"] == []
    assert result.evidence["lenses_active_names"] == []


def test_weights_from_thresholds_raises_on_a_missing_key() -> None:
    with pytest.raises(KeyError, match="lens_weight_technical"):
        weights_from_thresholds({}, ["technical"])


def test_weights_from_thresholds_honours_the_prefix() -> None:
    with pytest.raises(KeyError, match="etf_lens_weight_risk"):
        weights_from_thresholds({}, ["risk"], prefix="etf_lens_weight_")


def test_tiers_from_thresholds_raises_on_a_missing_key() -> None:
    with pytest.raises(KeyError, match="lens_conviction_highest_score"):
        tiers_from_thresholds({})


def test_tiers_from_thresholds_names_every_missing_key() -> None:
    with pytest.raises(KeyError) as excinfo:
        tiers_from_thresholds({}, prefix="etf_conviction_")
    message = str(excinfo.value)
    for suffix in (
        "highest_score",
        "highest_min_layers",
        "high_score",
        "high_min_layers",
        "medium_score",
        "watch_score",
    ):
        assert f"etf_conviction_{suffix}" in message
