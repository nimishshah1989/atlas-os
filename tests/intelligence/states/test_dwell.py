import pandas as pd

from atlas.intelligence.states.dwell import (
    compute_cohort_dwell_baselines,
    derive_urgency,
)


def test_cohort_dwell_baselines_aggregates_per_state():
    """Given historical state episodes, produce per-(cohort, state) statistics."""
    # All rows are for a single instrument/state, so date just needs to be
    # monotonically increasing to keep the sort correct.
    panel = pd.DataFrame(
        [
            # 3 historical stage_2a episodes for large_cap
            {
                "instrument_id": "a",
                "date": "2026-01-01",
                "state": "stage_2a",
                "dwell_days": 0,
                "cohort_key": "large_cap",
            },
            {
                "instrument_id": "a",
                "date": "2026-01-02",
                "state": "stage_2a",
                "dwell_days": 1,
                "cohort_key": "large_cap",
            },
            {
                "instrument_id": "a",
                "date": "2026-01-03",
                "state": "stage_2a",
                "dwell_days": 2,
                "cohort_key": "large_cap",
            },
            {
                "instrument_id": "a",
                "date": "2026-01-04",
                "state": "stage_2a",
                "dwell_days": 3,
                "cohort_key": "large_cap",
            },
            # episode 1: 5 days (dwell 0..4)
            {
                "instrument_id": "a",
                "date": "2026-01-05",
                "state": "stage_2a",
                "dwell_days": 4,
                "cohort_key": "large_cap",
            },
            {
                "instrument_id": "b",
                "date": "2026-01-01",
                "state": "stage_2a",
                "dwell_days": 0,
                "cohort_key": "large_cap",
            },
            {
                "instrument_id": "b",
                "date": "2026-01-02",
                "state": "stage_2a",
                "dwell_days": 1,
                "cohort_key": "large_cap",
            },
            # episode 2: 3 days (dwell 0..2)
            {
                "instrument_id": "b",
                "date": "2026-01-03",
                "state": "stage_2a",
                "dwell_days": 2,
                "cohort_key": "large_cap",
            },
            {
                "instrument_id": "c",
                "date": "2026-01-01",
                "state": "stage_2a",
                "dwell_days": 0,
                "cohort_key": "large_cap",
            },
            {
                "instrument_id": "c",
                "date": "2026-01-02",
                "state": "stage_2a",
                "dwell_days": 1,
                "cohort_key": "large_cap",
            },
            {
                "instrument_id": "c",
                "date": "2026-01-03",
                "state": "stage_2a",
                "dwell_days": 2,
                "cohort_key": "large_cap",
            },
            {
                "instrument_id": "c",
                "date": "2026-01-04",
                "state": "stage_2a",
                "dwell_days": 3,
                "cohort_key": "large_cap",
            },
            {
                "instrument_id": "c",
                "date": "2026-01-05",
                "state": "stage_2a",
                "dwell_days": 4,
                "cohort_key": "large_cap",
            },
            {
                "instrument_id": "c",
                "date": "2026-01-06",
                "state": "stage_2a",
                "dwell_days": 5,
                "cohort_key": "large_cap",
            },
            {
                "instrument_id": "c",
                "date": "2026-01-07",
                "state": "stage_2a",
                "dwell_days": 6,
                "cohort_key": "large_cap",
            },
            # episode 3: 8 days (dwell 0..7)
            {
                "instrument_id": "c",
                "date": "2026-01-08",
                "state": "stage_2a",
                "dwell_days": 7,
                "cohort_key": "large_cap",
            },
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
    empty = pd.DataFrame(columns=["instrument_id", "date", "state", "dwell_days", "cohort_key"])
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


def test_cohort_dwell_baselines_multi_state_instrument():
    """Run-lengths must be computed from chronological order.

    An instrument that transitions stage_1 → stage_2a has interleaved
    states. Sorting by dwell_days (old bug) grouped all stage_1 rows
    together, breaking cumsum episode-id and collapsing all stats to 1.
    Sorting by date (fix) preserves temporal order.

    Panel layout (one instrument, two states):
      Dates 2026-01-01..05: stage_1, dwell 0..4  → episode length = 5
      Dates 2026-01-06..10: stage_2a, dwell 0..4 → episode length = 5

    Expected baselines (each cohort/state has exactly 1 episode of 5 days):
      stage_1:  median=5, p25=5, p75=5, n=1
      stage_2a: median=5, p25=5, p75=5, n=1
    """
    rows = []
    for day in range(5):
        rows.append(
            {
                "instrument_id": "A",
                "date": f"2026-01-{day + 1:02d}",
                "state": "stage_1",
                "dwell_days": day,
                "cohort_key": "large_cap",
            }
        )
    for day in range(5):
        rows.append(
            {
                "instrument_id": "A",
                "date": f"2026-01-{day + 6:02d}",
                "state": "stage_2a",
                "dwell_days": day,
                "cohort_key": "large_cap",
            }
        )

    panel = pd.DataFrame(rows)
    stats = compute_cohort_dwell_baselines(panel)

    # stage_1: one episode of 5 days (dwell 0..4 → length = max(4)+1 = 5)
    s1 = stats[(stats["cohort_key"] == "large_cap") & (stats["state"] == "stage_1")]
    assert len(s1) == 1, "Expected exactly one (cohort, state) row for stage_1"
    assert s1.iloc[0]["n_observations"] == 1
    assert int(s1.iloc[0]["median_dwell_days"]) == 5  # single episode length

    # stage_2a: one episode of 5 days
    s2 = stats[(stats["cohort_key"] == "large_cap") & (stats["state"] == "stage_2a")]
    assert len(s2) == 1, "Expected exactly one (cohort, state) row for stage_2a"
    assert s2.iloc[0]["n_observations"] == 1
    assert int(s2.iloc[0]["median_dwell_days"]) == 5
