from decimal import Decimal

from atlas.signals.processor import _determine_confirmation_level


def test_confirmation_dual_when_conviction_high():
    result = _determine_confirmation_level(
        tier=1,
        conviction_score=Decimal("7.5"),
        cts_state="BUY Stage 2",
        rs_percentile=Decimal("85.0"),
    )
    assert result == "dual"


def test_confirmation_tv_only_when_conviction_low():
    result = _determine_confirmation_level(
        tier=1,
        conviction_score=Decimal("3.0"),
        cts_state="HOLD",
        rs_percentile=Decimal("40.0"),
    )
    assert result == "tv_only"


def test_confirmation_tv_only_when_no_conviction():
    result = _determine_confirmation_level(
        tier=1,
        conviction_score=None,
        cts_state=None,
        rs_percentile=None,
    )
    assert result == "tv_only"


def test_confirmation_dual_requires_both_conviction_and_rs():
    result = _determine_confirmation_level(
        tier=1,
        conviction_score=Decimal("8.0"),
        cts_state="BUY Stage 2",
        rs_percentile=Decimal("30.0"),
    )
    assert result == "tv_only"


def test_confirmation_tv_only_when_missing_rs():
    result = _determine_confirmation_level(
        tier=1,
        conviction_score=Decimal("8.0"),
        cts_state="BUY Stage 2",
        rs_percentile=None,
    )
    assert result == "tv_only"


def test_build_condition_label_known_code():
    from atlas.signals.processor import _build_condition_label

    assert _build_condition_label("breakout_52w_volume") == "52-week high breakout with 1.5x volume"


def test_build_condition_label_unknown_code_titlecases():
    from atlas.signals.processor import _build_condition_label

    assert _build_condition_label("some_unknown_code") == "Some Unknown Code"


def test_verdict_bullish_for_tier_1():
    from atlas.signals.processor import _verdict_from_tier

    assert _verdict_from_tier(1) == "bullish"


def test_verdict_bearish_for_tier_5():
    from atlas.signals.processor import _verdict_from_tier

    assert _verdict_from_tier(5) == "bearish"


def test_verdict_watch_for_other_tiers():
    from atlas.signals.processor import _verdict_from_tier

    assert _verdict_from_tier(3) == "watch"
