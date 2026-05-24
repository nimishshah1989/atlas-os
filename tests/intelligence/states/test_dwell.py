import pandas as pd

from atlas.intelligence.states.dwell import (
    compute_cohort_dwell_baselines,
    derive_urgency,
)


def test_cohort_dwell_baselines_aggregates_per_state():
    """Given historical state episodes, produce per-(cohort, state) statistics."""
    panel = pd.DataFrame(
        [
            # 3 historical stage_2a episodes for large_cap
            {"instrument_id": "a", "state": "stage_2a", "dwell_days": 0, "cohort_key": "large_cap"},
            {"instrument_id": "a", "state": "stage_2a", "dwell_days": 1, "cohort_key": "large_cap"},
            {"instrument_id": "a", "state": "stage_2a", "dwell_days": 2, "cohort_key": "large_cap"},
            {"instrument_id": "a", "state": "stage_2a", "dwell_days": 3, "cohort_key": "large_cap"},
            # episode 1: 5 days (dwell 0..4)
            {"instrument_id": "a", "state": "stage_2a", "dwell_days": 4, "cohort_key": "large_cap"},
            {"instrument_id": "b", "state": "stage_2a", "dwell_days": 0, "cohort_key": "large_cap"},
            {"instrument_id": "b", "state": "stage_2a", "dwell_days": 1, "cohort_key": "large_cap"},
            # episode 2: 3 days (dwell 0..2)
            {"instrument_id": "b", "state": "stage_2a", "dwell_days": 2, "cohort_key": "large_cap"},
            {"instrument_id": "c", "state": "stage_2a", "dwell_days": 0, "cohort_key": "large_cap"},
            {"instrument_id": "c", "state": "stage_2a", "dwell_days": 1, "cohort_key": "large_cap"},
            {"instrument_id": "c", "state": "stage_2a", "dwell_days": 2, "cohort_key": "large_cap"},
            {"instrument_id": "c", "state": "stage_2a", "dwell_days": 3, "cohort_key": "large_cap"},
            {"instrument_id": "c", "state": "stage_2a", "dwell_days": 4, "cohort_key": "large_cap"},
            {"instrument_id": "c", "state": "stage_2a", "dwell_days": 5, "cohort_key": "large_cap"},
            {"instrument_id": "c", "state": "stage_2a", "dwell_days": 6, "cohort_key": "large_cap"},
            # episode 3: 8 days (dwell 0..7)
            {"instrument_id": "c", "state": "stage_2a", "dwell_days": 7, "cohort_key": "large_cap"},
        ]
    )
    stats = compute_cohort_dwell_baselines(panel)
    rows = stats[(stats["cohort_key"] == "large_cap") & (stats["state"] == "stage_2a")]
    assert len(rows) == 1
    row = rows.iloc[0]
    assert row["n_observations"] == 3  # 3 episodes
    assert row["median_dwell_days"] == 5  # median of [3,5,8]
    assert row["p25_dwell_days"] == 4  # 25th percentile of [3,5,8]
    assert row["p75_dwell_days"] in (6, 7)  # depends on interpolation; both acceptable


def test_cohort_dwell_baselines_empty():
    """Empty panel returns empty DataFrame with correct shape."""
    empty = pd.DataFrame(columns=["instrument_id", "state", "dwell_days", "cohort_key"])
    stats = compute_cohort_dwell_baselines(empty)
    expected = {
        "cohort_key",
        "state",
        "mean_dwell_days",
        "median_dwell_days",
        "p25_dwell_days",
        "p75_dwell_days",
        "p95_dwell_days",
        "n_observations",
    }
    assert expected <= set(stats.columns)
    assert len(stats) == 0


def test_derive_urgency_stage_2a_fresh():
    """Stage 2A with dwell <= p25 → URGENT (fresh window)."""
    urgency = derive_urgency(
        state="stage_2a",
        dwell_days=2,
        cohort_baseline={"median": 5, "p25": 3, "p75": 8, "p95": 14},
    )
    assert urgency == "urgent"


def test_derive_urgency_stage_2a_late():
    """Stage 2A with dwell >= p75 → LATE (window expired)."""
    urgency = derive_urgency(
        state="stage_2a",
        dwell_days=10,
        cohort_baseline={"median": 5, "p25": 3, "p75": 8, "p95": 14},
    )
    assert urgency == "late"


def test_derive_urgency_stage_2a_normal_in_middle():
    """Dwell between p25 and p75 → normal."""
    urgency = derive_urgency(
        state="stage_2a",
        dwell_days=5,
        cohort_baseline={"median": 5, "p25": 3, "p75": 8, "p95": 14},
    )
    assert urgency == "normal"


def test_derive_urgency_stage_2c_inverts_polarity():
    """Stage 2C with LONG dwell → urgent to trim; short dwell → late (reversion soon)."""
    long_dwell = derive_urgency(
        state="stage_2c",
        dwell_days=120,
        cohort_baseline={"median": 60, "p25": 30, "p75": 90, "p95": 180},
    )
    assert long_dwell == "urgent"  # trim now
    short_dwell = derive_urgency(
        state="stage_2c",
        dwell_days=20,
        cohort_baseline={"median": 60, "p25": 30, "p75": 90, "p95": 180},
    )
    assert short_dwell == "late"  # reversion soon


def test_derive_urgency_stage_4_not_actionable():
    """Stage 4 always returns n/a."""
    urgency = derive_urgency(
        state="stage_4",
        dwell_days=50,
        cohort_baseline={"median": 30, "p25": 15, "p75": 60, "p95": 120},
    )
    assert urgency == "n/a"


def test_derive_urgency_stage_1_not_actionable():
    """Stage 1 always returns n/a."""
    urgency = derive_urgency(
        state="stage_1",
        dwell_days=10,
        cohort_baseline={"median": 30, "p25": 15, "p75": 60, "p95": 120},
    )
    assert urgency == "n/a"


def test_derive_urgency_uninvestable_not_actionable():
    urgency = derive_urgency(
        state="uninvestable",
        dwell_days=0,
        cohort_baseline={"median": 0, "p25": 0, "p75": 0, "p95": 0},
    )
    assert urgency == "n/a"


def test_derive_urgency_missing_baseline_keys_defaults_to_normal_or_na():
    """If cohort_baseline missing keys, function shouldn't crash."""
    urgency = derive_urgency(
        state="stage_2a",
        dwell_days=5,
        cohort_baseline={},
    )
    assert urgency in ("urgent", "normal", "late", "n/a")
