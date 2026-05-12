"""Integration tests for the optimization persistence layer."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from atlas.db import get_engine
from atlas.intelligence.conviction.optimization.ic_monitor import ICMeasurement
from atlas.intelligence.conviction.optimization.persistence import (
    apply_proposal,
    insert_proposal,
    reject_proposal,
    snooze_proposal,
    upsert_ic_batch,
)

_SENTINEL_DATE = date(1990, 1, 1)


def _cleanup() -> None:
    eng = get_engine()
    with eng.begin() as c:
        c.execute(
            text("DELETE FROM atlas.atlas_signal_ic_rolling WHERE as_of_date = :d"),
            {"d": _SENTINEL_DATE},
        )
        c.execute(
            text("DELETE FROM atlas.atlas_weight_proposals " "WHERE rationale LIKE :p"),
            {"p": "%STAGE4A_TEST%"},
        )


@pytest.fixture(autouse=True)
def _autoclean():
    _cleanup()
    yield
    _cleanup()


@pytest.mark.integration
def test_upsert_ic_batch_inserts_and_updates() -> None:
    eng = get_engine()
    measurements = [
        ICMeasurement(
            as_of_date=_SENTINEL_DATE,
            tier="tier_1_megacap",
            signal_name="ret_6m",
            lookback_window=90,
            forward_horizon=21,
            n_observations=42,
            ic=0.10,
            t_stat=2.0,
        )
    ]
    n = upsert_ic_batch(eng, measurements)
    assert n == 1
    # UPSERT: re-running with different IC should overwrite
    updated = [
        ICMeasurement(
            as_of_date=_SENTINEL_DATE,
            tier="tier_1_megacap",
            signal_name="ret_6m",
            lookback_window=90,
            forward_horizon=21,
            n_observations=42,
            ic=0.20,
            t_stat=4.0,
        )
    ]
    upsert_ic_batch(eng, updated)
    with eng.connect() as c:
        row = c.execute(
            text(
                "SELECT ic FROM atlas.atlas_signal_ic_rolling "
                "WHERE as_of_date = :d AND tier = :t AND signal_name = :s"
            ),
            {
                "d": _SENTINEL_DATE,
                "t": "tier_1_megacap",
                "s": "ret_6m",
            },
        ).fetchone()
    assert row is not None
    assert float(row[0]) == pytest.approx(0.20, abs=0.001)


@pytest.mark.integration
def test_insert_proposal_supersedes_pending() -> None:
    eng = get_engine()
    payload = {
        "tier": "tier_2_largecap",
        "regime": "all",
        "proposed_weights": {"ret_6m": Decimal("0.5"), "atr_21": Decimal("0.5")},
        "current_weights": {"ret_6m": Decimal("0.4"), "atr_21": Decimal("0.6")},
        "rationale": "STAGE4A_TEST first",
    }
    pid1 = insert_proposal(eng, payload)
    payload2 = {**payload, "rationale": "STAGE4A_TEST second"}
    pid2 = insert_proposal(eng, payload2)
    assert pid1 != pid2
    with eng.connect() as c:
        row = c.execute(
            text("SELECT status FROM atlas.atlas_weight_proposals WHERE id = CAST(:p AS uuid)"),
            {"p": pid1},
        ).fetchone()
    assert row is not None
    assert row[0] == "superseded"


@pytest.mark.integration
def test_reject_then_snooze_round_trip() -> None:
    eng = get_engine()
    payload = {
        "tier": "tier_4_lowermid",
        "regime": "all",
        "proposed_weights": {"ret_6m": Decimal("1.0")},
        "current_weights": {"ret_6m": Decimal("0.5")},
        "rationale": "STAGE4A_TEST round-trip",
    }
    pid_a = insert_proposal(eng, payload)
    reject_proposal(eng, proposal_id=pid_a, reviewer="tester", notes="not now")

    pid_b = insert_proposal(eng, {**payload, "rationale": "STAGE4A_TEST round-trip-b"})
    snooze_proposal(
        eng,
        proposal_id=pid_b,
        reviewer="tester",
        until_date=date(2099, 12, 31),
        notes="wait for more data",
    )

    with eng.connect() as c:
        r1 = c.execute(
            text(
                "SELECT status, review_notes FROM atlas.atlas_weight_proposals "
                "WHERE id = CAST(:p AS uuid)"
            ),
            {"p": pid_a},
        ).fetchone()
        r2 = c.execute(
            text(
                "SELECT status, review_notes FROM atlas.atlas_weight_proposals "
                "WHERE id = CAST(:p AS uuid)"
            ),
            {"p": pid_b},
        ).fetchone()
    assert r1 is not None and r1[0] == "rejected"
    assert r2 is not None and r2[0] == "snoozed"
    assert "2099-12-31" in (r2[1] or "")


@pytest.mark.integration
def test_apply_proposal_blends_and_bookends() -> None:
    """End-to-end: insert proposal, approve it, verify weights table updated."""
    eng = get_engine()
    # Use tier_5_smallcap to avoid clobbering the active T1/T3 industry-grade weights.
    tier = "tier_5_smallcap"
    # Load current weights to construct a small-delta proposal.
    with eng.connect() as c:
        current_rows = c.execute(
            text(
                "SELECT signal_name, weight FROM atlas.atlas_signal_weights "
                "WHERE tier = :t AND regime = 'all' AND effective_to IS NULL"
            ),
            {"t": tier},
        ).fetchall()
    if not current_rows:
        pytest.skip("tier_5_smallcap not seeded; skipping apply test")
    current = {r[0]: Decimal(str(r[1])) for r in current_rows}
    # Trivial proposal: identical to current — applying blends 100%·current + 0% drift.
    payload = {
        "tier": tier,
        "regime": "all",
        "proposed_weights": current,
        "current_weights": current,
        "rationale": "STAGE4A_TEST apply",
    }
    pid = insert_proposal(eng, payload)
    blended = apply_proposal(eng, proposal_id=pid, reviewer="test-fm", notes="apply test")
    # All blended values should remain very close to current.
    for sig, w in blended.items():
        assert abs(w - current.get(sig, Decimal("0"))) < Decimal("1e-6")
    # Old weights are bookended; new effective row exists effective_from tomorrow.
    with eng.connect() as c:
        booked = c.execute(
            text(
                "SELECT COUNT(*) FROM atlas.atlas_signal_weights "
                "WHERE tier = :t AND regime='all' AND effective_to = CURRENT_DATE"
            ),
            {"t": tier},
        ).scalar()
        active = c.execute(
            text(
                "SELECT COUNT(*) FROM atlas.atlas_signal_weights "
                "WHERE tier = :t AND regime='all' AND effective_to IS NULL"
            ),
            {"t": tier},
        ).scalar()
    assert (booked or 0) >= 1
    assert (active or 0) >= 1

    # Cleanup: roll back the apply by deleting the new active rows and
    # reverting the bookended set.
    with eng.begin() as c:
        c.execute(
            text(
                "DELETE FROM atlas.atlas_signal_weights "
                "WHERE tier = :t AND regime='all' "
                "AND effective_to IS NULL AND approved_by = 'test-fm'"
            ),
            {"t": tier},
        )
        c.execute(
            text(
                "UPDATE atlas.atlas_signal_weights SET effective_to = NULL "
                "WHERE tier = :t AND regime='all' AND effective_to = CURRENT_DATE"
            ),
            {"t": tier},
        )
