#!/usr/bin/env python3
"""Masked-ticker memorization audit (Desk v2 wave 4, Profit Mirage control).

The field's central failure mode: an LLM desk 'trading' on memorized name
narratives instead of the supplied data. Control: run SCOUT twice on the SAME
real cycle inputs — once as-is, once with every symbol and sector replaced by
anonymous codes — unmask, and compare proposal sets (Jaccard). High overlap ⇒
decisions come from the data; low overlap ⇒ name priors are steering the desk.
One desk per run (rotates weekly via atlas_weekly.sh). Result → desk_audit.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _db
import portfolio_data as pdata
from desk_run import _knobs, assemble_inputs, llm_call

from atlas.desk import build_scout_messages, validate_scout

M = "atlas_foundation"


def mask_inputs(inputs: dict) -> tuple[dict, dict[str, str]]:
    """Deterministically replace every symbol and sector with anonymous codes,
    everywhere they appear (including free-text invalidation notes)."""
    syms: list[str] = sorted(
        {w["symbol"] for w in inputs["watchlist_top_by_composite"]}
        | {h["symbol"] for h in inputs["portfolio"]["holdings"]}
    )
    sectors: list[str] = sorted(
        {str(w.get("sector")) for w in inputs["watchlist_top_by_composite"]}
        | {str(h.get("sector")) for h in inputs["portfolio"]["holdings"]}
    )
    sym_map = {s: f"SYM{i:03d}" for i, s in enumerate(syms, 1)}
    sec_map = {s: f"SEC{i:02d}" for i, s in enumerate(sectors, 1)}
    text = json.dumps(inputs, default=str)
    # longest names first so e.g. "MCX" never clobbers "MCXINDIA"
    for name, code in sorted((sym_map | sec_map).items(), key=lambda x: -len(x[0])):
        text = text.replace(f'"{name}"', f'"{code}"').replace(name, code)
    return json.loads(text), {v: k for k, v in sym_map.items()}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0  # both scouts agreed nothing is actionable
    return round(len(a & b) / len(a | b), 3)


def main() -> None:
    ap = argparse.ArgumentParser(description="Masked-ticker scout audit")
    ap.add_argument("--portfolio-id")
    a = ap.parse_args()
    q = f"""select portfolio_id::text pid from {M}.portfolio_master
            where status='active' and kind='basket' and origin='system'
              and params->>'desk' = 'true' order by portfolio_id"""
    ids = _db.read_df(q)["pid"].tolist()
    if not ids:
        return
    pid = a.portfolio_id or ids[dt.date.today().isocalendar().week % len(ids)]
    p = pdata.load_portfolio(pid)
    charter = p["params"].get("charter", "sector_leaders")
    inputs = assemble_inputs(p, _knobs())
    inputs.pop("_universe_sym2key", None)
    known = {w["symbol"] for w in inputs["watchlist_top_by_composite"]} | {
        h["symbol"] for h in inputs["portfolio"]["holdings"]
    }

    real = llm_call(build_scout_messages(charter, inputs))
    if validate_scout(real, known):
        print("[audit] real scout reply invalid — aborting", flush=True)
        return
    masked_inputs, unmask = mask_inputs(inputs)
    masked = llm_call(build_scout_messages(charter, masked_inputs))
    if validate_scout(masked, set(unmask)):
        print("[audit] masked scout reply invalid — aborting", flush=True)
        return

    real_set = {str(x["symbol"]) for x in real["proposals"] if x["action"] in ("add", "exit")}
    masked_set = {
        str(unmask.get(x["symbol"], x["symbol"]))
        for x in masked["proposals"]
        if x["action"] in ("add", "exit")
    }
    j = jaccard(real_set, masked_set)
    _db.exec_sql(
        f"""insert into {M}.desk_audit (portfolio_id, cycle_date, jaccard, real_set, masked_set)
            values (:p, :d, :j, cast(:r as jsonb), cast(:m as jsonb))""",
        {
            "p": pid,
            "d": _db.eod_cutoff(),
            "j": j,
            "r": json.dumps(sorted(real_set)),
            "m": json.dumps(sorted(masked_set)),
        },
    )
    print(
        f"[audit] {p['name']}: jaccard={j} real={sorted(real_set)} masked={sorted(masked_set)}",
        flush=True,
    )


if __name__ == "__main__":
    main()
