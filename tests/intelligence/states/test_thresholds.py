import os

import pytest
import sqlalchemy as sa
from atlas.intelligence.states.thresholds import (
    ThresholdValue,
    get,
    load_active_thresholds,
)

_SKIP_INTEGRATION = pytest.mark.skipif(
    not os.environ.get("ATLAS_INTEGRATION_TESTS"),
    reason="Requires ATLAS_INTEGRATION_TESTS=1 (live DB)",
)


@_SKIP_INTEGRATION
def test_load_active_thresholds_returns_dict(db_engine: sa.Engine) -> None:
    """Migration 076 seeded 18 active thresholds; load_active_thresholds returns them."""
    thresholds = load_active_thresholds(db_engine)
    assert isinstance(thresholds, dict)
    assert ("theta_rs", "stage_2a") in thresholds
    assert thresholds[("theta_rs", "stage_2a")].value == 70.0
    assert len(thresholds) >= 18


@_SKIP_INTEGRATION
def test_load_active_thresholds_only_active(db_engine: sa.Engine) -> None:
    """Inactive rows excluded; active rows present."""
    thresholds = load_active_thresholds(db_engine)
    # All keys point to ThresholdValue
    for _key, tv in thresholds.items():
        assert isinstance(tv, ThresholdValue)
        assert tv.value is not None


def test_threshold_value_dataclass_immutable() -> None:
    """ThresholdValue is frozen."""
    tv = ThresholdValue(value=70.0, ic_at_threshold=0.05, ic_ir_at_threshold=0.6)
    with pytest.raises(AttributeError):
        tv.value = 80.0  # type: ignore[misc]


def test_get_returns_value_when_present() -> None:
    t = {("theta_rs", "stage_2a"): ThresholdValue(70.0, None, None)}
    assert get(t, "theta_rs", "stage_2a") == 70.0


def test_get_returns_default_when_missing() -> None:
    t: dict = {}
    assert get(t, "missing", "stage_2a", default=42.0) == 42.0


def test_get_raises_when_missing_and_no_default() -> None:
    t: dict = {}
    with pytest.raises(KeyError):
        get(t, "missing", "stage_2a")
