"""Drift detector for auto-revert of underperforming weight sets.

Scans ``atlas_signal_weights_live_perf`` for currently-active weight sets
whose realized IC has been below ``ratio_threshold * predicted`` for the
last ``n_days_threshold`` consecutive days. Such sets are candidates for
revert: bookend the current weights, restore the immediately-preceding
approved version, and write an audit row to ``atlas_weight_revert_log``.

The detector reports findings; the caller decides whether to ``apply``
them. ``execute_revert`` is the apply path — it runs inside a single
transaction so the bookend + restore + audit row are atomic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Final

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

log = structlog.get_logger()

DEFAULT_RATIO_THRESHOLD: Final[Decimal] = Decimal("0.5")
DEFAULT_N_DAYS_THRESHOLD: Final[int] = 60


@dataclass(frozen=True)
class DriftFinding:
    """One active weight set in revert territory."""

    tier: str
    regime: str
    current_version: str
    n_days_below_threshold: int
    n_days_window: int
    avg_realized_ic: float
    avg_predicted_ic: float
    restore_target_version: str | None


_RECENT_PERF_SQL = text("""
    SELECT tier, regime, weight_set_version, as_of_date,
           realized_ic, ic_ratio, predicted_holdout_ic
    FROM atlas.atlas_signal_weights_live_perf
    WHERE as_of_date >= :since
    ORDER BY tier, regime, as_of_date DESC
""")

_ACTIVE_VERSIONS_SQL = text("""
    SELECT DISTINCT tier, regime,
           tier || '@' || MAX(approved_at)::text AS version
    FROM atlas.atlas_signal_weights
    WHERE effective_to IS NULL
    GROUP BY tier, regime
""")

_RESTORE_TARGET_SQL = text("""
    SELECT tier || '@' || MAX(approved_at)::text AS version
    FROM atlas.atlas_signal_weights
    WHERE tier = :tier
      AND regime = :regime
      AND effective_to IS NOT NULL
""")


def _load_active_versions(engine: Engine) -> dict[tuple[str, str], str]:
    """Return {(tier, regime): currently-active version-stamp}."""
    with engine.connect() as conn:
        rows = conn.execute(_ACTIVE_VERSIONS_SQL).fetchall()
    return {(r[0], r[1]): str(r[2]) for r in rows}


def detect_drift(
    engine: Engine,
    *,
    as_of: date,
    ratio_threshold: Decimal = DEFAULT_RATIO_THRESHOLD,
    n_days_threshold: int = DEFAULT_N_DAYS_THRESHOLD,
) -> list[DriftFinding]:
    """Return one DriftFinding per active weight set in revert territory.

    A finding fires only when the active set has at least
    ``n_days_threshold`` recent rows AND every one of those rows has
    ``ic_ratio < ratio_threshold``.
    """
    active = _load_active_versions(engine)
    if not active:
        return []

    # Pull a bit more than the threshold to be safe against weekends/holidays.
    pull_window_days = n_days_threshold * 2 + 14
    since = as_of.fromordinal(as_of.toordinal() - pull_window_days)
    with engine.connect() as conn:
        rows = conn.execute(_RECENT_PERF_SQL, {"since": since}).fetchall()

    by_version: dict[str, list[tuple[float | None, float | None, float | None]]] = {}
    for r in rows:
        version = str(r[2])
        ic_ratio = float(r[5]) if r[5] is not None else None
        realized = float(r[4]) if r[4] is not None else None
        predicted = float(r[6]) if r[6] is not None else None
        by_version.setdefault(version, []).append((ic_ratio, realized, predicted))

    out: list[DriftFinding] = []
    for (tier, regime), version in active.items():
        history = by_version.get(version, [])[:n_days_threshold]
        if len(history) < n_days_threshold:
            continue
        ratios = [r for r, _, _ in history if r is not None]
        if len(ratios) < n_days_threshold:
            continue
        if all(r < float(ratio_threshold) for r in ratios):
            realized_vals = [v for _, v, _ in history if v is not None]
            predicted_vals = [p for _, _, p in history if p is not None]
            avg_real = sum(realized_vals) / len(realized_vals) if realized_vals else 0.0
            avg_pred = sum(predicted_vals) / len(predicted_vals) if predicted_vals else 0.0
            # Find the immediately-preceding superseded version to restore.
            with engine.connect() as conn:
                row = conn.execute(_RESTORE_TARGET_SQL, {"tier": tier, "regime": regime}).fetchone()
            restore = str(row[0]) if row and row[0] else None
            out.append(
                DriftFinding(
                    tier=tier,
                    regime=regime,
                    current_version=version,
                    n_days_below_threshold=len(ratios),
                    n_days_window=n_days_threshold,
                    avg_realized_ic=avg_real,
                    avg_predicted_ic=avg_pred,
                    restore_target_version=restore,
                )
            )

    log.info(
        "drift_check_complete",
        as_of=str(as_of),
        n_findings=len(out),
        threshold=float(ratio_threshold),
        n_days=n_days_threshold,
    )
    return out


_LOAD_RESTORE_WEIGHTS_SQL = text("""
    SELECT signal_name, weight, flipped, holdout_ic
    FROM atlas.atlas_signal_weights
    WHERE tier = :tier AND regime = :regime
      AND approved_at = CAST(:stamp AS timestamptz)
""")

_BOOKEND_SQL = text("""
    UPDATE atlas.atlas_signal_weights
       SET effective_to = CURRENT_DATE
     WHERE tier = :tier AND regime = :regime AND effective_to IS NULL
""")

_INSERT_RESTORED_WEIGHT_SQL = text("""
    INSERT INTO atlas.atlas_signal_weights
        (tier, regime, signal_name, weight, flipped,
         effective_from, effective_to, holdout_ic,
         approved_by, notes)
    VALUES
        (:tier, :regime, :signal_name, :weight, :flipped,
         CURRENT_DATE + INTERVAL '1 day', NULL, :holdout_ic,
         'auto-revert', :notes)
""")


def execute_revert(
    engine: Engine,
    finding: DriftFinding,
    *,
    triggered_by: str = "auto-detector",
    notes: str | None = None,
) -> str | None:
    """Apply a revert atomically. Returns the revert-log id, or None if no
    restore target was available."""
    if finding.restore_target_version is None:
        log.warning(
            "revert_skipped_no_target",
            tier=finding.tier,
            version=finding.current_version,
        )
        return None
    # Parse the "tier@iso-timestamp" version stamp to extract the timestamp.
    stamp = finding.restore_target_version.split("@", 1)[1]

    with engine.begin() as conn:
        # 1. Load the restore-target weight rows.
        rows = conn.execute(
            _LOAD_RESTORE_WEIGHTS_SQL,
            {"tier": finding.tier, "regime": finding.regime, "stamp": stamp},
        ).fetchall()
        if not rows:
            log.warning(
                "revert_skipped_target_empty",
                tier=finding.tier,
                target=finding.restore_target_version,
            )
            return None

        # 2. Bookend the currently-active set.
        conn.execute(_BOOKEND_SQL, {"tier": finding.tier, "regime": finding.regime})

        # 3. Insert the restored weights as a new active set (effective tomorrow).
        new_rows = [
            {
                "tier": finding.tier,
                "regime": finding.regime,
                "signal_name": r[0],
                "weight": r[1],
                "flipped": bool(r[2]),
                "holdout_ic": r[3],
                "notes": (
                    notes
                    or f"Auto-revert from {finding.current_version} after "
                    f"{finding.n_days_below_threshold}d below threshold"
                ),
            }
            for r in rows
        ]
        conn.execute(_INSERT_RESTORED_WEIGHT_SQL, new_rows)

        # 4. Audit row.
        log_row = conn.execute(
            text("""
                INSERT INTO atlas.atlas_weight_revert_log
                    (tier, regime, reverted_from_version, restored_to_version,
                     days_below_threshold, realized_ic_avg,
                     predicted_holdout_ic, triggered_by, notes)
                VALUES
                    (:tier, :regime, :from_v, :to_v,
                     :days, :real_avg, :pred, :trigger, :notes)
                RETURNING id::text
            """),
            {
                "tier": finding.tier,
                "regime": finding.regime,
                "from_v": finding.current_version,
                "to_v": finding.restore_target_version,
                "days": finding.n_days_below_threshold,
                "real_avg": finding.avg_realized_ic,
                "pred": finding.avg_predicted_ic,
                "trigger": triggered_by,
                "notes": notes,
            },
        ).fetchone()

    revert_id = str(log_row[0]) if log_row else None
    log.info(
        "revert_executed",
        revert_id=revert_id,
        tier=finding.tier,
        from_version=finding.current_version,
        to_version=finding.restore_target_version,
    )
    return revert_id
