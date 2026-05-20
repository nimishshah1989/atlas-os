"""Tests for atlas.intelligence.ranking — hybrid rank + absolute-floor classifier.

TDD: this file was written before ranking.py existed.
"""

from decimal import Decimal

from atlas.intelligence.ranking import RankConfig, hybrid_rank_labels

_CFG = RankConfig(
    labels=["Avoid", "Underweight", "Neutral", "Overweight"],
    band_pcts=[Decimal("0.20"), Decimal("0.50"), Decimal("0.80")],
    floor_label="Overweight",
    floor_min=Decimal("10"),
)


def test_always_produces_a_spread():
    scores = {f"s{i}": Decimal(i) for i in range(10)}
    floors = {f"s{i}": Decimal("50") for i in range(10)}
    out = hybrid_rank_labels(scores, floors, _CFG)
    assert len(set(out.values())) > 1  # never all-one-label


def test_percentile_bands_assign_expected_labels():
    scores = {"a": Decimal(1), "b": Decimal(2), "c": Decimal(3), "d": Decimal(4), "e": Decimal(5)}
    floors = {k: Decimal("99") for k in scores}
    out = hybrid_rank_labels(scores, floors, _CFG)
    # percentile rank: a=0.0, b=0.25, c=0.5, d=0.75, e=1.0
    assert out["a"] == "Avoid"  # <0.20
    assert out["b"] == "Underweight"  # 0.20-0.50 (0.25 lands here)
    assert out["c"] == "Neutral"  # 0.50-0.80 (0.5 lands in Neutral: >=0.50 but <0.80)
    assert out["e"] == "Overweight"  # >=0.80


def test_absolute_floor_caps_top_label():
    scores = {"a": Decimal(1), "b": Decimal(2), "c": Decimal(3), "d": Decimal(4), "e": Decimal(5)}
    floors = {
        "a": Decimal("99"),
        "b": Decimal("99"),
        "c": Decimal("99"),
        "d": Decimal("99"),
        "e": Decimal("5"),  # e below floor_min 10
    }
    out = hybrid_rank_labels(scores, floors, _CFG)
    assert out["e"] == "Neutral"  # would be Overweight; floored down one


def test_empty_input_returns_empty():
    assert hybrid_rank_labels({}, {}, _CFG) == {}


def test_ties_handled_deterministically_and_no_crash():
    """Two entities with identical scores must not crash and must produce
    consistent, reproducible output. The tie-break is by entity_id string order,
    so 'alpha' < 'beta' → 'alpha' gets the lower index (lower percentile).
    With n=2 and both scores equal: idx 0 → pct 0.0 (Avoid), idx 1 → pct 1.0 (Overweight).
    """
    scores = {"beta": Decimal("42"), "alpha": Decimal("42")}
    floors = {k: Decimal("99") for k in scores}

    # Call twice — must produce identical result (deterministic)
    out1 = hybrid_rank_labels(scores, floors, _CFG)
    out2 = hybrid_rank_labels(scores, floors, _CFG)
    assert out1 == out2

    # With n=2: pct(idx=0)=0.0 → Avoid, pct(idx=1)=1.0 → Overweight
    # Sorted by (score, entity_id): ("alpha", 42) < ("beta", 42) → alpha is idx 0
    assert out1["alpha"] == "Avoid"
    assert out1["beta"] == "Overweight"

    # Not all the same label
    assert out1["alpha"] != out1["beta"]


def test_missing_floor_value_treated_as_floor_failure():
    """If floor_values dict is missing an entity key, treat it as failing the floor."""
    scores = {"x": Decimal(1), "y": Decimal(2)}
    # y would get Overweight (pct=1.0) but its floor_value is missing
    floors = {"x": Decimal("99")}  # no entry for "y"
    cfg = RankConfig(
        labels=["Avoid", "Overweight"],
        band_pcts=[Decimal("0.50")],
        floor_label="Overweight",
        floor_min=Decimal("10"),
    )
    out = hybrid_rank_labels(scores, floors, cfg)
    assert out["y"] == "Avoid"  # stepped down from Overweight


def test_single_entity_gets_bottom_band():
    """Single entity has percentile 0.0 → bottom band, regardless of score."""
    scores = {"solo": Decimal("999")}
    floors = {"solo": Decimal("999")}
    out = hybrid_rank_labels(scores, floors, _CFG)
    assert out["solo"] == "Avoid"


def test_floor_label_at_index_zero_does_not_crash():
    """If floor_label is the worst label (index 0), stepping down must not produce
    a negative index. The floor gate only fires for entities assigned floor_label,
    so entity 'a' (pct=0.0 → Avoid = floor_label) fails the floor and stays at
    Avoid (max(0, 0-1) = 0). Entity 'b' (pct=1.0 → Overweight) is not affected
    by the floor gate at all, so it stays Overweight.
    """
    cfg = RankConfig(
        labels=["Avoid", "Overweight"],
        band_pcts=[Decimal("0.50")],
        floor_label="Avoid",
        floor_min=Decimal("100"),
    )
    scores = {"a": Decimal(1), "b": Decimal(2)}
    floors = {"a": Decimal("0"), "b": Decimal("0")}  # both fail floor, but floor only gates "Avoid"
    out = hybrid_rank_labels(scores, floors, cfg)
    # "a" → pct=0.0 → Avoid (== floor_label), floor fails → stays Avoid (index max(0,-1)=0)
    assert out["a"] == "Avoid"
    # "b" → pct=1.0 → Overweight (not floor_label) → floor gate not triggered
    assert out["b"] == "Overweight"
    # Critical: the max(0, ...) guard means no IndexError or negative index
    assert len(out) == 2
