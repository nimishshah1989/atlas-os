"""Tests for the drift detector + revert executor."""

from __future__ import annotations

import os
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from atlas.db import get_engine
from atlas.intelligence.conviction.monitoring.drift_detector import (
    DEFAULT_N_DAYS_THRESHOLD,
    DEFAULT_RATIO_THRESHOLD,
    detect_drift,
)

_needs_db = pytest.mark.skipif(not os.getenv("ATLAS_DB_URL"), reason="needs ATLAS_DB_URL")


def test_constants_are_sane() -> None:
    assert DEFAULT_RATIO_THRESHOLD == Decimal("0.5")
    assert DEFAULT_N_DAYS_THRESHOLD == 60


@pytest.mark.integration
@_needs_db
def test_no_findings_when_no_perf_history() -> None:
    """With <60 days of live-perf data on EC2, detector returns []."""
    eng = get_engine()
    findings = detect_drift(eng, as_of=date(2026, 4, 9))
    assert isinstance(findings, list)
    # Stage 4c has just been bootstrapped — we have < 60 days of data.
    assert findings == []


@pytest.mark.integration
@_needs_db
def test_detector_with_synthetic_in_revert_territory() -> None:
    """Insert 60 days of bad perf for tier_5_smallcap, detect."""
    eng = get_engine()
    # Find an active version for tier_5_smallcap
    with eng.connect() as c:
        row = c.execute(
            text("""
                SELECT tier || '@' || MAX(approved_at)::text
                FROM atlas.atlas_signal_weights
                WHERE tier = 'tier_5_smallcap' AND regime = 'all'
                  AND effective_to IS NULL
                GROUP BY tier
            """)
        ).fetchone()
    if row is None:
        pytest.skip("no active tier_5_smallcap version")
    version = str(row[0])
    base_date = date(2025, 12, 31)
    # Clean prior synthetic test rows
    with eng.begin() as c:
        c.execute(
            text(
                "DELETE FROM atlas.atlas_signal_weights_live_perf "
                "WHERE weight_set_version = :v AND as_of_date >= :start"
            ),
            {"v": version, "start": base_date},
        )
    # Insert 60 daily rows with ic_ratio = 0.1 (below 0.5 threshold)
    with eng.begin() as c:
        c.execute(
            text("""
                INSERT INTO atlas.atlas_signal_weights_live_perf
                    (weight_set_version, as_of_date, tier, regime,
                     predicted_holdout_ic, realized_ic, ic_ratio, n_observations)
                VALUES (:v, :d, 'tier_5_smallcap', 'all', 0.04, 0.004, 0.1, 30)
            """),
            [{"v": version, "d": base_date + timedelta(days=i)} for i in range(60)],
        )
    findings = detect_drift(eng, as_of=base_date + timedelta(days=59))
    tier5_findings = [f for f in findings if f.tier == "tier_5_smallcap"]
    # Clean up
    with eng.begin() as c:
        c.execute(
            text(
                "DELETE FROM atlas.atlas_signal_weights_live_perf "
                "WHERE weight_set_version = :v AND as_of_date >= :start"
            ),
            {"v": version, "start": base_date},
        )
    assert len(tier5_findings) == 1
    assert tier5_findings[0].n_days_below_threshold == 60
    assert tier5_findings[0].current_version == version


@pytest.mark.integration
@_needs_db
def test_detector_skips_when_one_day_above_threshold() -> None:
    """If 59 days are below but 1 day is above, no finding."""
    eng = get_engine()
    with eng.connect() as c:
        row = c.execute(
            text("""
                SELECT tier || '@' || MAX(approved_at)::text
                FROM atlas.atlas_signal_weights
                WHERE tier = 'tier_5_smallcap' AND regime = 'all'
                  AND effective_to IS NULL
                GROUP BY tier
            """)
        ).fetchone()
    if row is None:
        pytest.skip("no active tier_5_smallcap version")
    version = str(row[0])
    base_date = date(2025, 11, 1)
    with eng.begin() as c:
        c.execute(
            text(
                "DELETE FROM atlas.atlas_signal_weights_live_perf "
                "WHERE weight_set_version = :v AND as_of_date >= :start"
            ),
            {"v": version, "start": base_date},
        )
        c.execute(
            text("""
                INSERT INTO atlas.atlas_signal_weights_live_perf
                    (weight_set_version, as_of_date, tier, regime,
                     predicted_holdout_ic, realized_ic, ic_ratio, n_observations)
                VALUES (:v, :d, 'tier_5_smallcap', 'all', 0.04, 0.004, :ratio, 30)
            """),
            [
                {
                    "v": version,
                    "d": base_date + timedelta(days=i),
                    # Day 30 of 60 above threshold
                    "ratio": 0.9 if i == 30 else 0.1,
                }
                for i in range(60)
            ],
        )
    findings = detect_drift(eng, as_of=base_date + timedelta(days=59))
    with eng.begin() as c:
        c.execute(
            text(
                "DELETE FROM atlas.atlas_signal_weights_live_perf "
                "WHERE weight_set_version = :v AND as_of_date >= :start"
            ),
            {"v": version, "start": base_date},
        )
    tier5 = [f for f in findings if f.tier == "tier_5_smallcap"]
    assert tier5 == []
