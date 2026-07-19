#!/usr/bin/env python3
"""Desk v2 correctness gate — asserts on REAL produced output (rule #0).

Wave gates for docs/desk-v2-waves.md; run nightly by atlas_daily.sh after
desk_run (and ad hoc):

    python validate_desk.py            # exit 1 on any failure

Checks (Wave 1):
  A. every active desk portfolio journaled the last cycle date
  B. every plan on a booked/queued buy is geometrically sound and R:R >= desk_min_rr
  C. queue state machine sound (age limits, settlement, audit timestamps)
  D. every booked order >= 15 days old carries a T+5 outcome stamp
  E. trader liveness — recent cycles with booked buys produced at least one plan
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _db

M = "atlas_foundation"

FAILURES: list[str] = []


def fail(msg: str) -> None:
    FAILURES.append(msg)
    print(f"  FAIL: {msg}", flush=True)


def _knob(key: str) -> Decimal:
    v = _db.scalar(
        f"select threshold_value from {M}.atlas_thresholds where threshold_key = :k and is_active",
        {"k": key},
    )
    if v is None:
        raise RuntimeError(f"threshold {key} missing")
    return Decimal(str(v))


def check_a_journal_freshness() -> None:
    df = _db.read_df(
        f"""select m.name, max(j.cycle_date) last
            from {M}.portfolio_master m
            left join {M}.desk_journal j using (portfolio_id)
            where m.status = 'active' and m.params->>'desk' = 'true'
            group by 1"""
    )
    latest = _db.scalar(f"select max(cycle_date) from {M}.desk_journal")
    for r in df.to_dict("records"):
        if r["last"] != latest:
            fail(f"A: {r['name']} last journal {r['last']} != latest cycle {latest}")


def check_b_plan_integrity() -> None:
    min_rr = _knob("desk_min_rr")
    cards = _db.read_df(
        f"""select dj.cycle_date, c->>'symbol' sym, c->>'entry_ref' e, c->>'stop' st,
                   c->>'target' tg, c->>'rr' rr
            from {M}.desk_journal dj,
                 jsonb_array_elements(dj.applied || coalesce(dj.queued, '[]')) c
            where c->>'side' = 'buy' and c ? 'stop'"""
    )
    for r in cards.to_dict("records"):
        e, st, tg = (Decimal(r[k]) for k in ("e", "st", "tg"))
        if not (st < e < tg):
            fail(f"B: {r['sym']} {r['cycle_date']} plan geometry broken {st}/{e}/{tg}")
        elif Decimal(r["rr"]) < min_rr:
            fail(f"B: {r['sym']} {r['cycle_date']} R:R {r['rr']} < {min_rr}")


def check_c_queue_state() -> None:
    expiry = int(_knob("desk_pending_expiry_days"))
    rows = _db.read_df(
        f"""select symbol, status, cycle_date, decided_at, booked_at
            from {M}.desk_pending_orders
            where (status = 'pending' and cycle_date < current_date - {expiry + 2})
               or (status = 'approved' and decided_at < now() - interval '2 days')
               or (status = 'booked' and booked_at is null)
               or (status in ('approved', 'rejected', 'expired') and decided_at is null)"""
    )
    for r in rows.to_dict("records"):
        fail(f"C: {r['symbol']} {r['status']} ({r['cycle_date']}) violates queue state machine")


def check_d_stamps_advance() -> None:
    rows = _db.read_df(
        f"""select dj.cycle_date, a->>'symbol' sym
            from {M}.desk_journal dj, jsonb_array_elements(dj.applied) a
            where dj.cycle_date <= current_date - 15
              and not exists (
                  select 1 from {M}.desk_outcomes o
                  where o.portfolio_id = dj.portfolio_id and o.kind = 'order'
                    and o.symbol = a->>'symbol' and o.decision_date = dj.cycle_date
                    and o.t5_pct is not null)"""
    )
    for r in rows.to_dict("records"):
        fail(f"D: {r['sym']} booked {r['cycle_date']} has no T+5 stamp")


def check_f_queue_settlement() -> None:
    rows = _db.read_df(
        f"""select p.symbol, p.status from {M}.desk_pending_orders p
            where (p.status in ('approved', 'rejected', 'expired') and p.decided_by is null)
               or (p.status = 'approved' and exists (
                     select 1 from {M}.desk_journal j
                     where j.portfolio_id = p.portfolio_id and j.ts > p.decided_at))"""
    )
    for r in rows.to_dict("records"):
        fail(f"F: {r['symbol']} {r['status']} lacks audit trail or missed settlement")


def check_g_alert_validity() -> None:
    rows = _db.read_df(
        f"""select symbol, kind, level, quote from {M}.desk_alerts
            where (kind = 'stop' and quote > level) or (kind = 'target' and quote < level)"""
    )
    for r in rows.to_dict("records"):
        fail(f"G: {r['symbol']} {r['kind']} alert quote {r['quote']} never crossed {r['level']}")


def check_e_trader_liveness() -> None:
    # only meaningful once Desk v2 cycles exist (trader column populated)
    row = _db.read_df(
        f"""select count(*) filter (where c->>'side' = 'buy') buys,
                   count(*) filter (where c->>'side' = 'buy' and c ? 'stop') planned
            from {M}.desk_journal dj, jsonb_array_elements(dj.applied) c
            where dj.cycle_date > current_date - 7 and dj.trader is not null"""
    ).iloc[0]
    if int(row["buys"]) > 0 and int(row["planned"]) == 0:
        fail(f"E: {row['buys']} buys booked in last 7 days, zero carry plans — trader dead")


def main() -> int:
    for check in (
        check_a_journal_freshness,
        check_b_plan_integrity,
        check_c_queue_state,
        check_d_stamps_advance,
        check_e_trader_liveness,
        check_f_queue_settlement,
        check_g_alert_validity,
    ):
        print(f"[validate_desk] {check.__name__}", flush=True)
        check()
    if FAILURES:
        print(f"[validate_desk] {len(FAILURES)} FAILURE(S)", flush=True)
        return 1
    print("[validate_desk] all green", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
