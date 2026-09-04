"""Error contracts of blend() — the rule-#4 guarantees, exercised WITHOUT market numbers.

Every lens value here is None (absent), so no score is ever computed; the weights and
tier tuples that appear are structural placeholders the contract under test never reads.
Anything numeric about scores is the integration parity test on real rows.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from atlas.global_market.scoring.blend import (
    DEFAULT_ORDER,
    NO_SIGNAL_TIER,
    blend,
    tiers_from_thresholds,
    weights_from_thresholds,
)

pytestmark = pytest.mark.unit

_NEVER_REACHED_TIERS = {tier: (Decimal(0), 0) for tier in DEFAULT_ORDER}


def test_a_lens_without_a_weight_key_is_a_keyerror_even_when_absent() -> None:
    with pytest.raises(KeyError, match="lens_weight_"):
        blend({"technical": None}, weights={}, tiers=_NEVER_REACHED_TIERS)


def test_an_order_entry_missing_from_tiers_is_a_keyerror() -> None:
    with pytest.raises(KeyError, match="tiers has no entry"):
        blend({"technical": None}, weights={"technical": Decimal(1)}, tiers={})


def test_nothing_present_is_no_signal_not_a_zero() -> None:
    result = blend(
        {"technical": None, "flow": None},
        weights={"technical": Decimal(1), "flow": Decimal(1)},
        tiers=_NEVER_REACHED_TIERS,
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
