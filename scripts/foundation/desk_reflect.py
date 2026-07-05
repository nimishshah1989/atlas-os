#!/usr/bin/env python3
"""Atlas Desk weekly reflection (Phase B2) — the desk gets smarter from OUTCOMES.

    python desk_reflect.py            # every active desk
    python desk_reflect.py --portfolio-id X

Per desk: load decisions with forward outcome stamps (T+5/20/60 for booked orders
AND for the roads not taken) + current lessons → the reflection agent updates each
lesson's confidence (confirmed rises, contradicted falls, untested decays) and
writes ≤3 new outcome-grounded lessons → lessons below the floor are retired.

Standing constraints: desk_run already enforces params.standing_constraints
(require_rs_positive / require_above_200 / min_composite_60) on every buy.
Automated lesson→constraint promotion (backtest-validated via the twin) needs a
few months of stamped outcomes to judge against — until then promotion is an FM
action: add the constraint key to the desk's params after reading the lessons.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _db
from desk_run import llm_call

from atlas.desk import build_reflect_messages, validate_reflect

M = "atlas_foundation"
_CONFIDENCE_FLOOR = 0.15
_UNTESTED_DECAY = 0.97


def reflect_one(pid: str) -> dict:
    p = _db.read_df(
        f"select name, params from {M}.portfolio_master where portfolio_id = :p", {"p": pid}
    ).iloc[0]
    charter = (p["params"] or {}).get("charter", "sector_leaders")

    outcomes = _db.read_df(
        f"""select kind, symbol, side, decision_date, t5_pct, t20_pct, t60_pct
            from {M}.desk_outcomes where portfolio_id = :p
            order by decision_date desc limit 60""",
        {"p": pid},
    )
    lessons = _db.read_df(
        f"select id, lesson, tags, confidence from {M}.desk_lessons "
        "where portfolio_id = :p and active",
        {"p": pid},
    )
    notes = _db.read_df(
        f"""select cycle_date, pm->>'note' note, errors from {M}.desk_journal
            where portfolio_id = :p order by cycle_date desc limit 10""",
        {"p": pid},
    )
    if outcomes.empty and lessons.empty:
        return {"desk": p["name"], "skipped": "no outcomes yet"}

    reply = llm_call(
        build_reflect_messages(
            charter,
            {
                "decisions_with_outcomes": outcomes.to_dict("records"),
                "existing_lessons": lessons.to_dict("records"),
                "recent_cycle_notes": notes.to_dict("records"),
                "regime_now": _db.scalar(
                    f"select regime_state from {M}.atlas_market_regime_daily "
                    "order by date desc limit 1"
                ),
            },
        ),
        max_tokens=3000,
    )
    errs = validate_reflect(reply, set(lessons["id"].tolist()))
    if errs:
        return {"desk": p["name"], "errors": errs}

    updated = {u["id"]: float(u["confidence"]) for u in reply.get("updates", [])}
    retired = 0
    for r in lessons.to_dict("records"):
        conf = updated.get(r["id"], float(r["confidence"]) * _UNTESTED_DECAY)
        if conf < _CONFIDENCE_FLOOR:
            _db.exec_sql(
                f"update {M}.desk_lessons set active = false, confidence = :c where id = :i",
                {"c": round(conf, 3), "i": r["id"]},
            )
            retired += 1
        else:
            _db.exec_sql(
                f"update {M}.desk_lessons set confidence = :c where id = :i",
                {"c": round(conf, 3), "i": r["id"]},
            )
    added = 0
    for n in reply.get("new_lessons", []):
        _db.exec_sql(
            f"""insert into {M}.desk_lessons (portfolio_id, lesson, tags)
                values (:p, :l, cast(:t as jsonb))""",
            {
                "p": pid,
                "l": f"{n['lesson']} [basis: {n['basis']}]",
                "t": json.dumps(n.get("tags") or {}),
            },
        )
        added += 1
    return {"desk": p["name"], "lessons_added": added, "retired": retired, "updated": len(updated)}


def main() -> None:
    ap = argparse.ArgumentParser(description="Atlas Desk weekly reflection")
    ap.add_argument("--portfolio-id")
    a = ap.parse_args()
    q = f"""select portfolio_id::text pid from {M}.portfolio_master
            where status='active' and kind='basket' and origin='system'
              and params->>'desk' = 'true'"""
    ids = [a.portfolio_id] if a.portfolio_id else _db.read_df(q)["pid"].tolist()
    for pid in ids:
        print(f"[reflect] {json.dumps(reflect_one(pid), default=str)}", flush=True)


if __name__ == "__main__":
    main()
