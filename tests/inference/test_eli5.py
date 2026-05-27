"""Tests for atlas.inference.eli5.

Every archetype in the deep-search candidate generator must produce a
non-empty, <=200-char ELI5 string. Plus the generic fallback covers any
archetype not in the template library.
"""

from __future__ import annotations

import pytest

from atlas.decisions.rule_dsl import CellRule, FeaturePredicate
from atlas.inference.eli5 import eli5

# Archetypes used by atlas.discovery.deep_search_candidates. Keep in sync
# if new archetypes are added.
ARCHETYPES = [
    # POSITIVE
    "mean_reversion",
    "deep_value",
    "quality_momentum",
    "inflection",
    "consolidation_breakout",
    "liquidity_expansion",
    "structural",
    "low_vol_carry",
    "breakout_with_pullback",
    "sector_relative_leadership",
    "bab_low_beta",
    "liquidity_thrust_mfi",
    "obv_thrust",
    # NEGATIVE
    "mean_reversion_overbought",
    "distribution",
    "volatility_spike",
    "breakdown",
    "deep_value_avoid",
    "weak_quality",
    "overextension",
    "sector_drag",
    "sector_breakdown",
    "bab_high_beta_short",
    "mfi_overbought_distrib",
    "obv_divergence_neg",
]


def _make_rule(archetype: str, action: str = "POSITIVE") -> CellRule:
    from decimal import Decimal

    return CellRule(
        rule_type="placeholder",
        eligibility=[],
        entry=[
            FeaturePredicate(feature="rs_residual_6m", cmp=">", value=Decimal("0")),
        ],
        tier="Large",
        action=action,  # type: ignore[arg-type]
        tenure="3m",
        rule_version=1,
        methodology_lock_ref="TEST",
        notes=f"X | archetype={archetype} | rank=1",
    )


@pytest.mark.parametrize("archetype", ARCHETYPES)
def test_every_archetype_renders(archetype: str) -> None:
    rule = _make_rule(archetype)
    text = eli5(rule, "Large", "3m", "POSITIVE")
    assert text, f"empty ELI5 for archetype={archetype!r}"
    assert len(text) <= 200, f"ELI5 too long ({len(text)} chars) for {archetype!r}"


def test_unknown_archetype_falls_back() -> None:
    rule = _make_rule("not_a_real_archetype")
    text = eli5(rule, "Large", "3m", "NEUTRAL")
    assert text
    assert len(text) <= 200
    assert "see rule details" in text


def test_cap_tier_substituted() -> None:
    rule = _make_rule("quality_momentum")
    text = eli5(rule, "Small", "6m", "POSITIVE")
    assert "Small" in text


def test_tenure_substituted() -> None:
    rule = _make_rule("liquidity_expansion")
    text = eli5(rule, "Large", "12m", "POSITIVE")
    assert "12m" in text


def test_archetype_extracted_from_notes() -> None:
    """Regression: the parser must find archetype=<X> in the notes blob."""
    rule = _make_rule("sector_relative_leadership")
    text = eli5(rule, "Large", "3m", "POSITIVE")
    # The template contains "sector" — sanity check it rendered the right one
    assert "sector" in text.lower() or "leader" in text.lower()


def test_truncation_to_200_chars() -> None:
    """Even pathological inputs must respect the 200-char ceiling."""
    rule = _make_rule("a_very_long_archetype_name" * 10)
    text = eli5(rule, "Large", "3m", "POSITIVE")
    assert len(text) <= 200
