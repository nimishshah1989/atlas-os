"""Indian hard-exclusion governance filters for v6 trading model.

Six fail-open filters applied before portfolio construction. Missing data is
NOT a reason to exclude — the burden of proof is on confirmed bad data.

Filters (in priority order):
  1. pledge       — pledge_ratio_pct > 30% (atlas_governance_daily)
  2. auditor_quality — mcap > ₹5,000cr AND auditor not top-10 (atlas_governance_master)
                       NOTE: mcap column not yet available; filter disabled until
                       a market_cap column lands. TODO(v0.2): enable mcap guard.
  3. fno_ban      — in_fno_ban_list = true (atlas_governance_daily)
  4. sme          — tier = 'SME' (atlas_universe_stocks; exchange_segment column
                    absent from schema — using 'tier' as proxy per approach doc)
  5. group_cap    — portfolio-level concern; not enforced here, handled in portfolio.py
  6. audit_qualification — last_qualified_audit_date older than 365 days from ref_date

Every exclusion is written to atlas_v6_exclusions_log for transparency.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

log = structlog.get_logger()

_PLEDGE_THRESHOLD = Decimal("30")  # percent
_AUDIT_DAYS_WINDOW = 365


def is_excluded(
    session: Session,
    instrument_id: uuid.UUID,
    ref_date: date,
) -> tuple[bool, str | None]:
    """Check a single instrument against all six hard-exclusion filters.

    Returns (excluded, reason). Reason is one of:
    'pledge', 'auditor_quality', 'fno_ban', 'sme', 'group_cap',
    'audit_qualification', or None if not excluded.

    All filters are fail-open: missing data row or NULL field -> not excluded.
    group_cap is never True here (portfolio-level only).
    """
    iid = str(instrument_id)

    # --- Filter 1: pledge ---
    row = session.execute(
        text("""
            SELECT pledge_ratio_pct
              FROM atlas.atlas_governance_daily
             WHERE instrument_id = :iid AND date = :d
             LIMIT 1
        """),
        {"iid": iid, "d": ref_date},
    ).fetchone()
    if row is not None and row.pledge_ratio_pct is not None:
        if Decimal(str(row.pledge_ratio_pct)) > _PLEDGE_THRESHOLD:
            _log_exclusion(session, instrument_id, ref_date, "pledge")
            return True, "pledge"

    # --- Filter 2: auditor_quality ---
    # mcap guard is disabled until a market_cap column lands.
    # TODO(v0.2): re-enable mcap > 5000cr gate once column is available.
    row_m = session.execute(
        text("""
            SELECT auditor_is_top_10
              FROM atlas.atlas_governance_master
             WHERE instrument_id = :iid
             LIMIT 1
        """),
        {"iid": iid},
    ).fetchone()
    # Current: only flag if auditor_is_top_10 IS EXPLICITLY FALSE (not NULL).
    # mcap check deferred to v0.2.
    if row_m is not None and row_m.auditor_is_top_10 is False:
        log.debug(
            "governance.auditor_quality_soft_flag",
            instrument_id=iid,
            note="mcap gate disabled; not excluding until mcap column available",
        )
        # NOT excluding yet — leave note in log but fail-open
        # _log_exclusion(session, instrument_id, ref_date, "auditor_quality")
        # return True, "auditor_quality"

    # --- Filter 3: fno_ban ---
    row_fno = session.execute(
        text("""
            SELECT in_fno_ban_list
              FROM atlas.atlas_governance_daily
             WHERE instrument_id = :iid AND date = :d
             LIMIT 1
        """),
        {"iid": iid, "d": ref_date},
    ).fetchone()
    if row_fno is not None and row_fno.in_fno_ban_list is True:
        _log_exclusion(session, instrument_id, ref_date, "fno_ban")
        return True, "fno_ban"

    # --- Filter 4: sme ---
    # exchange_segment column is absent from atlas_universe_stocks schema.
    # Using tier = 'SME' as proxy (approach doc §Schema deviations).
    row_u = session.execute(
        text("""
            SELECT tier
              FROM atlas.atlas_universe_stocks
             WHERE instrument_id = :iid
             LIMIT 1
        """),
        {"iid": iid},
    ).fetchone()
    if row_u is not None and row_u.tier is not None:
        if row_u.tier.upper() == "SME":
            _log_exclusion(session, instrument_id, ref_date, "sme")
            return True, "sme"

    # --- Filter 5: group_cap --- (portfolio-level; skip per spec note)

    # --- Filter 6: audit_qualification ---
    row_aq = session.execute(
        text("""
            SELECT last_qualified_audit_date
              FROM atlas.atlas_governance_master
             WHERE instrument_id = :iid
             LIMIT 1
        """),
        {"iid": iid},
    ).fetchone()
    if row_aq is not None and row_aq.last_qualified_audit_date is not None:
        cutoff = ref_date - timedelta(days=_AUDIT_DAYS_WINDOW)
        if row_aq.last_qualified_audit_date < cutoff:
            _log_exclusion(session, instrument_id, ref_date, "audit_qualification")
            return True, "audit_qualification"

    return False, None


@dataclass(frozen=True)
class ExclusionLog:
    instrument_id: uuid.UUID
    date: date
    reason: str


def apply_exclusions(
    session: Session,
    universe: list[uuid.UUID],
    ref_date: date,
) -> tuple[set[uuid.UUID], list[ExclusionLog]]:
    """Batch-check all instruments in universe and return excluded set.

    Uses IN clauses for efficiency — avoids per-instrument round trips.
    Returns (excluded_ids, exclusion_log_entries).

    Fail-open: instruments with no governance data are NOT excluded.
    """
    if not universe:
        return set(), []

    iid_strs = [str(i) for i in universe]
    excluded: set[uuid.UUID] = set()
    logs: list[ExclusionLog] = []

    # --- Batch Filter 1: pledge ---
    pledge_rows = session.execute(
        text("""
            SELECT instrument_id
              FROM atlas.atlas_governance_daily
             WHERE instrument_id = ANY(CAST(:iids AS uuid[]))
               AND date = :d
               AND pledge_ratio_pct > :threshold
        """),
        {"iids": iid_strs, "d": ref_date, "threshold": float(_PLEDGE_THRESHOLD)},
    ).fetchall()
    for row in pledge_rows:
        iid = uuid.UUID(str(row.instrument_id))
        excluded.add(iid)
        logs.append(ExclusionLog(iid, ref_date, "pledge"))

    # --- Batch Filter 3: fno_ban ---
    fno_rows = session.execute(
        text("""
            SELECT instrument_id
              FROM atlas.atlas_governance_daily
             WHERE instrument_id = ANY(CAST(:iids AS uuid[]))
               AND date = :d
               AND in_fno_ban_list = true
        """),
        {"iids": iid_strs, "d": ref_date},
    ).fetchall()
    for row in fno_rows:
        iid = uuid.UUID(str(row.instrument_id))
        if iid not in excluded:
            excluded.add(iid)
            logs.append(ExclusionLog(iid, ref_date, "fno_ban"))

    # --- Batch Filter 4: sme (using tier column) ---
    sme_rows = session.execute(
        text("""
            SELECT instrument_id
              FROM atlas.atlas_universe_stocks
             WHERE instrument_id = ANY(CAST(:iids AS uuid[]))
               AND UPPER(tier) = 'SME'
        """),
        {"iids": iid_strs},
    ).fetchall()
    for row in sme_rows:
        iid = uuid.UUID(str(row.instrument_id))
        if iid not in excluded:
            excluded.add(iid)
            logs.append(ExclusionLog(iid, ref_date, "sme"))

    # --- Batch Filter 6: audit_qualification ---
    cutoff = ref_date - timedelta(days=_AUDIT_DAYS_WINDOW)
    audit_rows = session.execute(
        text("""
            SELECT instrument_id
              FROM atlas.atlas_governance_master
             WHERE instrument_id = ANY(CAST(:iids AS uuid[]))
               AND last_qualified_audit_date IS NOT NULL
               AND last_qualified_audit_date < :cutoff
        """),
        {"iids": iid_strs, "cutoff": cutoff},
    ).fetchall()
    for row in audit_rows:
        iid = uuid.UUID(str(row.instrument_id))
        if iid not in excluded:
            excluded.add(iid)
            logs.append(ExclusionLog(iid, ref_date, "audit_qualification"))

    # Persist all exclusions to atlas_v6_exclusions_log
    if logs:
        _persist_exclusion_logs(session, logs)

    log.info(
        "governance.apply_exclusions",
        ref_date=str(ref_date),
        universe_size=len(universe),
        excluded_count=len(excluded),
        reasons={entry.reason for entry in logs},
    )

    return excluded, logs


def _log_exclusion(
    session: Session,
    instrument_id: uuid.UUID,
    ref_date: date,
    reason: str,
) -> None:
    """Write a single exclusion row to atlas_v6_exclusions_log."""
    session.execute(
        text("""
            INSERT INTO atlas.atlas_v6_exclusions_log
                (instrument_id, date, reason, weight_before, weight_after)
            VALUES (:iid, :d, :reason, NULL, 0)
            ON CONFLICT (instrument_id, date, reason) DO NOTHING
        """),
        {"iid": str(instrument_id), "d": ref_date, "reason": reason},
    )
    log.info(
        "governance.excluded",
        instrument_id=str(instrument_id),
        ref_date=str(ref_date),
        reason=reason,
    )


def _persist_exclusion_logs(
    session: Session,
    entries: list[ExclusionLog],
) -> None:
    """Batch-insert exclusion log entries."""
    for entry in entries:
        session.execute(
            text("""
                INSERT INTO atlas.atlas_v6_exclusions_log
                    (instrument_id, date, reason, weight_before, weight_after)
                VALUES (:iid, :d, :reason, NULL, 0)
                ON CONFLICT (instrument_id, date, reason) DO NOTHING
            """),
            {
                "iid": str(entry.instrument_id),
                "d": entry.date,
                "reason": entry.reason,
            },
        )
