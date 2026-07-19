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
from desk_orders import load_charter
from desk_run import llm_call

from atlas.desk import build_reflect_messages, validate_reflect

M = "atlas_foundation"
_CONFIDENCE_FLOOR = 0.15


def _layer_decay() -> dict[str, float]:
    df = _db.read_df(
        f"""select threshold_key k, threshold_value v from {M}.atlas_thresholds
            where threshold_key like 'desk_decay_%' and is_active"""
    )
    return {r["k"].removeprefix("desk_decay_"): float(r["v"]) for r in df.to_dict("records")}


def _contrast_candidates(outcomes) -> tuple[list[dict], list[dict]]:
    """Best/worst matured decisions by direction-aware alpha (FinCon CVRF):
    positive alpha is good for buys/adds, avoided-drawdown good for exits."""
    rows = []
    for r in outcomes.to_dict("records"):
        alpha = r.get("t20_alpha") if r.get("t20_alpha") is not None else r.get("t5_alpha")
        if alpha is None:
            continue
        score = float(alpha) if r["side"] in ("buy", "add") else -float(alpha)
        rows.append(
            {
                "symbol": r["symbol"],
                "side": r["side"],
                "kind": r["kind"],
                "decision_date": r["decision_date"],
                "realized_alpha_score": round(score, 2),
            }
        )
    rows.sort(key=lambda r: r["realized_alpha_score"])
    if len(rows) < 4:
        return [], []
    return rows[-3:][::-1], rows[:3]


def reflect_one(pid: str) -> dict:
    p = _db.read_df(
        f"select name, params from {M}.portfolio_master where portfolio_id = :p", {"p": pid}
    ).iloc[0]
    charter = (p["params"] or {}).get("charter", "sector_leaders")

    # ponytail: 40 rows / 6 cols — the full 60×9 payload 413s Groq's 8k request cap
    outcomes = _db.read_df(
        f"""select kind, symbol, side, decision_date, t5_alpha, t20_alpha
            from {M}.desk_outcomes where portfolio_id = :p
            order by decision_date desc limit 40""",
        {"p": pid},
    )
    lessons = _db.read_df(
        f"select id, lesson, tags, confidence, layer from {M}.desk_lessons "
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

    best, worst = _contrast_candidates(outcomes)
    contrast_syms = ({r["symbol"] for r in best}, {r["symbol"] for r in worst}) if best else None
    charter_text, _sha = load_charter(charter)
    reply = llm_call(
        build_reflect_messages(
            charter,
            {
                "decisions_with_outcomes": outcomes.to_dict("records"),
                "existing_lessons": lessons.to_dict("records"),
                "recent_cycle_notes": notes.to_dict("records"),
                "contrast_candidates": {"best": best, "worst": worst} if best else None,
                "regime_now": _db.scalar(
                    f"select regime_state from {M}.atlas_market_regime_daily "
                    "order by date desc limit 1"
                ),
            },
            charter_text,
        ),
        max_tokens=6000,  # gpt-oss reasons before emitting; 3000 starved the JSON (400 json_validate_failed)
    )
    errs = validate_reflect(reply, set(lessons["id"].tolist()), contrast_syms)
    if errs:
        return {"desk": p["name"], "errors": errs}

    decay = _layer_decay()
    updated = {u["id"]: float(u["confidence"]) for u in reply.get("updates", [])}
    retired = 0
    for r in lessons.to_dict("records"):
        prior = float(r["confidence"])
        if r["id"] in updated:
            # the prompt's ±0.1/week contract, enforced in code not prose
            conf = max(prior - 0.1, min(prior + 0.1, updated[r["id"]]))
        else:
            conf = prior * decay.get(r["layer"], 0.97)
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
    new_rows = list(reply.get("new_lessons", []))
    ci = reply.get("contrast_insight")
    if contrast_syms is None:
        ci = None  # no candidates were offered — an unsolicited insight is ungrounded
    if isinstance(ci, dict):  # the contrastive rule is itself a lesson, tagged as such
        new_rows.append(
            {
                "lesson": ci["insight"],
                "layer": ci["layer"],
                "tags": {"contrast": {"best": ci["best_cited"], "worst": ci["worst_cited"]}},
                "basis": "contrast of best-vs-worst stamped outcomes",
            }
        )
    for n in new_rows:
        _db.exec_sql(
            f"""insert into {M}.desk_lessons (portfolio_id, lesson, tags, layer)
                values (:p, :l, cast(:t as jsonb), :ly)""",
            {
                "p": pid,
                "l": f"{n['lesson']} [basis: {n['basis']}]",
                "t": json.dumps(n.get("tags") or {}),
                "ly": n["layer"],
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
        try:  # one desk's reflection crash must never starve the others
            print(f"[reflect] {json.dumps(reflect_one(pid), default=str)}", flush=True)
        except Exception as e:
            print(f"[reflect] {pid}: {type(e).__name__}: {e}", flush=True)
    from desk_credibility import build_calibration  # weekly conviction-vs-outcome report

    build_calibration()


if __name__ == "__main__":
    main()
