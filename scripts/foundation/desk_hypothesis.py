#!/usr/bin/env python3
"""Weekly desk hypothesis loop (Desk v2 wave 4, RD-Agent pattern).

The RESEARCH ANALYST agent proposes ONE falsifiable desk-threshold hypothesis
from measured evidence (credibility, calibration, prior verdicts); CODE
evaluates it against the desk's own stamped decision corpus — forward evidence
only, the desk itself is never backtested (Profit Mirage). Verdict + effect
journaled to desk_hypotheses; next week's proposal is conditioned on it.
Adoption stays an FM action (flagged in the memo, never automatic).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _db
from desk_run import llm_call

from atlas.desk import build_hypo_messages, validate_hypo

M = "atlas_foundation"

# keys the analyst may question, each with a code evaluator over REAL decisions
_ALLOWED = ("desk_min_rr", "desk_stance_consensus_min")


def _allowed() -> dict[str, dict]:
    df = _db.read_df(
        f"""select threshold_key k, threshold_value v, min_allowed lo, max_allowed hi
            from {M}.atlas_thresholds where threshold_key = any(array{list(_ALLOWED)})"""
    )
    return {
        r["k"]: {"current": float(r["v"]), "lo": float(r["lo"]), "hi": float(r["hi"])}
        for r in df.to_dict("records")
    }


def _corpus_rr() -> list[dict]:
    """Booked buys with a trade plan and a matured alpha stamp."""
    return _db.read_df(
        f"""select (c->>'rr')::float rr, coalesce(o.t20_alpha, o.t5_alpha)::float alpha
            from {M}.desk_journal dj
            cross join lateral jsonb_array_elements(dj.applied) c
            join {M}.desk_outcomes o
              on o.portfolio_id = dj.portfolio_id and o.symbol = c->>'symbol'
             and o.decision_date = dj.cycle_date and o.kind = 'order'
            where c->>'side' = 'buy' and c ? 'rr'
              and coalesce(o.t20_alpha, o.t5_alpha) is not null"""
    ).to_dict("records")


def _corpus_consensus() -> list[dict]:
    """Booked buys with a stance-consensus count and a matured alpha stamp."""
    return _db.read_df(
        f"""select (v->>'consensus')::float rr, coalesce(o.t20_alpha, o.t5_alpha)::float alpha
            from {M}.desk_journal dj
            cross join lateral jsonb_array_elements(dj.risk->'verdicts') v
            join {M}.desk_outcomes o
              on o.portfolio_id = dj.portfolio_id and o.symbol = v->>'symbol'
             and o.decision_date = dj.cycle_date and o.kind = 'order'
            where v->>'verdict' = 'approve' and v ? 'consensus'
              and coalesce(o.t20_alpha, o.t5_alpha) is not null"""
    ).to_dict("records")


def evaluate(key: str, proposed: float, min_n: int) -> tuple[str, dict]:
    """Would filtering the desk's OWN realized decisions at `proposed` have
    raised mean alpha? Direction: both allowed keys filter by metric >= value."""
    corpus = _corpus_rr() if key == "desk_min_rr" else _corpus_consensus()
    if len(corpus) < min_n:
        return "insufficient_data", {"n": len(corpus), "needed": min_n}
    kept = [r["alpha"] for r in corpus if r["rr"] >= proposed]
    all_alpha = [r["alpha"] for r in corpus]
    if len(kept) < max(3, min_n // 4):
        return "insufficient_data", {"n": len(corpus), "kept": len(kept)}
    mean_kept = sum(kept) / len(kept)
    mean_all = sum(all_alpha) / len(all_alpha)
    effect = {
        "n": len(corpus),
        "kept": len(kept),
        "mean_alpha_kept": round(mean_kept, 2),
        "mean_alpha_all": round(mean_all, 2),
    }
    return ("supported" if mean_kept > mean_all else "unsupported"), effect


def main() -> None:
    allowed = _allowed()
    raw_min_n = _db.scalar(
        f"select threshold_value from {M}.atlas_thresholds where threshold_key='desk_hypo_min_n'"
    )
    if raw_min_n is None:
        raise RuntimeError("threshold desk_hypo_min_n missing")
    min_n = int(raw_min_n)
    evidence = {
        "allowed_thresholds": allowed,
        "credibility": _db.read_df(
            f"select dim, dim_value, n, hit_rate, avg_alpha from {M}.desk_credibility"
        ).to_dict("records"),
        "calibration": _db.read_df(
            f"select tier, n, avg_alpha, hit_rate from {M}.desk_calibration"
        ).to_dict("records"),
        "prior_hypotheses": _db.read_df(
            f"""select hypothesis, threshold_key, proposed_value, verdict, effect
                from {M}.desk_hypotheses order by ts desc limit 10"""
        ).to_dict("records"),
    }
    reply = llm_call(build_hypo_messages(evidence), max_tokens=2000)
    errs = validate_hypo(reply, allowed)
    if errs:
        print(f"[hypo] rejected: {errs}", flush=True)
        return
    key = reply["threshold_key"]
    verdict, effect = evaluate(key, float(reply["proposed_value"]), min_n)
    _db.exec_sql(
        f"""insert into {M}.desk_hypotheses
            (hypothesis, threshold_key, proposed_value, current_value, verdict, effect)
            values (:h, :k, :pv, :cv, :vd, cast(:ef as jsonb))""",
        {
            "h": reply["hypothesis"],
            "k": key,
            "pv": reply["proposed_value"],
            "cv": allowed[key]["current"],
            "vd": verdict,
            "ef": __import__("json").dumps(effect),
        },
    )
    print(f"[hypo] {key} -> {reply['proposed_value']}: {verdict} {effect}", flush=True)


if __name__ == "__main__":
    main()
