"""Per-client audit-pack assembly: 8 named sections in one JSON payload per
client, pure SELECT + dict-building over already-computed wealth.* tables —
NO NEW MATH (every number here was already produced by an earlier engine
module; this file only reads it and shapes it for narration/frontend).

Sections, in this exact order (shared contract with Tasks 8/9 — narration
and the frontend both key off this list, spell it exactly):

    map          who they are — household chip, book MV, n_funds/n_stocks, tenure
    label_check  their held funds' SEBI-category verdicts (T2)
    overlap      effective bets, top stock exposure, worst overlapping fund pair
    fees         closet-index flags + estimated annual fee saving
    benchmark    exact ledger-flow replay vs a Nifty-50 index fund
    habits       behaviour fingerprint (panic/chase/SIP shares + cost inputs)
    value        the 6 value-statement components, realized vs upper-bound
    actions      call-list entries + tax-harvest gain candidates + rule flags

Missing-data honesty: when a section's source table has no row for the
client, the section is `{"insufficient": true, "reason": "<plain reason>"}`
instead of a fake zero — EXCEPT where zero genuinely is the honest value
(wealth.value_statements gives every client a row with defaulted-0
components; "no client_flags row" means a clean client, not missing data).
Every non-insufficient section carries a `headline_value` (the one number
the frontend shows big) and a `method` note (how we know it).

Output: wealth.audit_packs(client_id bigint primary key, payload jsonb,
prose jsonb) — prose left NULL; Task 8's narrate_audit_packs.py fills it.

Usage: .venv/bin/python scripts/wealth/build_audit_packs.py
"""
from __future__ import annotations

import json
import math
import sys
from datetime import date, datetime
from decimal import Decimal

import pandas as pd
from psycopg2.extras import Json, execute_values

from engine_common import connect

MISMATCH_COVERAGE_CATEGORIES = {"Small Cap", "Multi Cap"}
COVERAGE_NOTE = (
    "Small/Multi-cap verdicts are coverage-limited: a meaningful share of "
    "these funds' holdings don't match to an equity market-cap rank "
    "(foreign/unlisted/cash/debt sleeves), so 'mismatch' here is "
    "lower-confidence than a Large/Mid/Flexi-cap verdict."
)


def _num(x):
    """Decimal/None -> float/None, NaN/Inf -> None (strict-JSON safety)."""
    if x is None:
        return None
    f = float(x)
    return f if math.isfinite(f) else None


def _clean(obj):
    """Recursively coerce Decimal/date/NaN so json.dumps(payload) is strict JSON."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    if isinstance(obj, Decimal):
        return _num(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj


def _insufficient(reason: str) -> dict:
    return {"insufficient": True, "reason": reason}


def _index_by_client(df: pd.DataFrame) -> dict:
    return {r["client_id"]: {k: v for k, v in r.items() if k != "client_id"} for r in df.to_dict("records")}


# ---------------------------------------------------------------- loaders --

def load_frames(conn) -> dict:
    f = {}
    f["clients"] = _index_by_client(pd.read_sql(
        "select client_id, full_name from wealth.clients", conn))

    f["reports"] = _index_by_client(pd.read_sql(
        """select distinct on (client_id) client_id, mv_total, as_on_date
           from wealth.client_reports order by client_id, as_on_date desc""", conn))

    f["tenure"] = _index_by_client(pd.read_sql(
        """select client_id, min(inv_since) inv_since,
                  count(distinct scheme_id) n_schemes_held
           from wealth.holdings group by 1""", conn))

    f["households"] = _index_by_client(pd.read_sql(
        "select client_id, household_name, members, household_mv, succession_flag "
        "from wealth.households", conn))

    f["overlap"] = _index_by_client(pd.read_sql(
        """select client_id, eff_bets, top_stock_name, top_stock_rs, top10_share,
                  n_funds, n_stocks from wealth.client_overlap""", conn))

    worst_pair = pd.read_sql(
        """select distinct on (cfo.client_id) cfo.client_id,
                  sa.display_name fund_a, sb.display_name fund_b, cfo.overlap_pct
           from wealth.client_fund_overlap cfo
           join wealth.schemes sa on sa.scheme_id = cfo.scheme_a
           join wealth.schemes sb on sb.scheme_id = cfo.scheme_b
           order by cfo.client_id, cfo.overlap_pct desc""", conn)
    f["worst_pair"] = _index_by_client(worst_pair)

    labels = pd.read_sql(
        """select distinct h.client_id, s.display_name fund, flc.category,
                  flc.verdict, flc.detail
           from wealth.holdings h
           join wealth.schemes s on s.scheme_id = h.scheme_id
           join wealth.fund_label_check flc on flc.scheme_id = h.scheme_id
           order by h.client_id, flc.verdict desc, s.display_name""", conn)
    f["labels"] = {cid: g.drop(columns="client_id").to_dict("records")
                   for cid, g in labels.groupby("client_id")}

    f["value"] = _index_by_client(pd.read_sql(
        """select client_id, sip_discipline_rs, staying_power_rs, advice_outcome_rs,
                  fee_save_yr_rs, tax_headroom_rs, coaching_opportunity_rs, summary
           from wealth.value_statements""", conn))

    flags = pd.read_sql(
        "select client_id, rule, evidence, action, est_value, basis from wealth.client_flags", conn)
    # flag evidence is rendered verbatim in the UI action list — swap the one
    # bit of jargon the rules-engine emits ("XIRR n%") for plain language so no
    # banned term reaches a client-facing screen (validator enforces this).
    for _col in ("rule", "evidence", "action"):
        flags[_col] = flags[_col].astype("object").where(flags[_col].notna(), None)
        flags[_col] = flags[_col].map(
            lambda s: None if s is None else __import__("re").sub(
                r"(?i)\bXIRR\b", "yearly growth", s))
    f["flags"] = {cid: g.drop(columns="client_id").to_dict("records")
                  for cid, g in flags.groupby("client_id")}
    closet = flags[flags.rule.str.contains("closet", case=False, na=False)]
    f["closet_flags"] = {cid: g.drop(columns="client_id").to_dict("records")
                          for cid, g in closet.groupby("client_id")}

    f["benchmark"] = _index_by_client(pd.read_sql(
        """select client_id, xirr_client, xirr_bench, alpha, first_flow, last_flow,
                  n_flows, approx, bench_overdrawn from wealth.client_benchmark""", conn))

    f["behaviour"] = _index_by_client(pd.read_sql(
        """select client_id, panic_share, chase_hot_share, sip_active, sip_streams,
                  div_leak_rs, pgr, plr, disposition from wealth.client_behaviour""", conn))

    f["counterfactuals"] = _index_by_client(pd.read_sql(
        """select client_id, cf_no_panic_rs, cf_sip_alive_rs, cf_index_rs
           from wealth.counterfactuals""", conn))

    f["tax_harvest"] = _index_by_client(pd.read_sql(
        """select client_id, fy, headroom, gain_value, tax_saved_if_harvested,
                  gain_candidates, loss_note, carry_forward from wealth.tax_harvest""", conn))

    calls = pd.read_sql(
        "select client_id, list_type, rank, reason, script, score from wealth.call_lists", conn)
    f["call_lists"] = {cid: g.drop(columns="client_id").to_dict("records")
                        for cid, g in calls.groupby("client_id")}

    return f


# --------------------------------------------------------------- sections --

def sec_map(cid, f) -> dict:
    rep = f["reports"].get(cid)
    if rep is None:
        return _insufficient("no valuation report parsed for this client — only ledger "
                              "transactions on file, no MV/holdings snapshot to report")
    ten = f["tenure"].get(cid, {})
    ov = f["overlap"].get(cid, {})
    hh = f["households"].get(cid, {})
    total_mv = _num(rep["mv_total"])
    tenure_years = None
    if ten.get("inv_since") is not None:
        tenure_years = round((rep["as_on_date"] - ten["inv_since"]).days / 365.25, 1)
    return {
        "household": {
            "name": hh.get("household_name"),
            "members": hh.get("members"),
            "household_mv": _num(hh.get("household_mv")),
            "succession_flag": hh.get("succession_flag"),
        },
        "total_mv": total_mv,
        "as_on_date": rep["as_on_date"],
        "n_funds": ov.get("n_funds"),
        "n_stocks": ov.get("n_stocks"),
        "tenure_years": tenure_years,
        "headline_value": total_mv,
        "method": "Book MV = header total on the client's latest valuation report; "
                  "household = surname + joint-holder roll-up (build_household.py); "
                  "fund/stock counts = look-through overlap engine.",
    }


def sec_label_check(cid, f) -> dict:
    rows = f["labels"].get(cid)
    if not rows:
        return _insufficient("none of this client's held funds have a mapped SEBI "
                              "label-check row (unmatched to Morningstar look-through)")
    out_rows = []
    for r in rows:
        item = dict(r)
        if r["verdict"] == "mismatch" and r["category"] in MISMATCH_COVERAGE_CATEGORIES:
            item["coverage_note"] = COVERAGE_NOTE
        out_rows.append(item)
    n_mismatch = sum(1 for r in rows if r["verdict"] == "mismatch")
    return {
        "funds": out_rows,
        "n_funds_checked": len(rows),
        "n_mismatch": n_mismatch,
        "headline_value": n_mismatch,
        "method": "Actual large/mid/small-cap equity split (Morningstar look-through, SEBI "
                  "100/250 market-cap-rank bands) vs the fund's own category-name mandate.",
    }


def sec_overlap(cid, f) -> dict:
    ov = f["overlap"].get(cid)
    if ov is None:
        return _insufficient("fewer than the minimum mapped fund holdings with "
                              "look-through data to compute an overlap")
    pair = f["worst_pair"].get(cid)
    worst_pair = None
    if pair is not None:
        worst_pair = {"fund_a": pair["fund_a"], "fund_b": pair["fund_b"],
                       "overlap_pct": _num(pair["overlap_pct"])}
    return {
        "eff_bets": _num(ov["eff_bets"]),
        "top_stock_name": ov["top_stock_name"],
        "top_stock_rs": _num(ov["top_stock_rs"]),
        "top10_share": _num(ov["top10_share"]),
        "n_funds": ov["n_funds"],
        "n_stocks": ov["n_stocks"],
        "worst_fund_pair": worst_pair,
        "headline_value": _num(ov["eff_bets"]),
        "method": "Effective independent bets = 1/HHI over true look-through stock weights "
                  "across all held funds; worst pair = highest pairwise min-weight overlap %.",
    }


def sec_fees(cid, f) -> dict:
    vs = f["value"].get(cid)
    fee_save = _num(vs["fee_save_yr_rs"]) if vs else 0.0
    flags = f["closet_flags"].get(cid, [])
    return {
        "fee_save_yr_rs": fee_save,
        "flags": flags,
        "headline_value": fee_save,
        "method": "Sum of est_value on closet-index-style rule flags (wealth.client_flags) "
                  "= wealth.value_statements.fee_save_yr_rs; 0 with no flag is a clean result, "
                  "not missing data.",
    }


def sec_benchmark(cid, f) -> dict:
    b = f["benchmark"].get(cid)
    if b is None:
        return _insufficient("not enough external cash-flow history (need at least one real "
                              "inflow and one outflow) to run the exact index-fund replay")
    return {
        "xirr_client": _num(b["xirr_client"]),
        "xirr_bench": _num(b["xirr_bench"]),
        "alpha": _num(b["alpha"]),
        "n_flows": b["n_flows"],
        "first_flow": b["first_flow"],
        "last_flow": b["last_flow"],
        "approx": bool(b["approx"]) if b["approx"] is not None else None,
        "bench_overdrawn": bool(b["bench_overdrawn"]) if b["bench_overdrawn"] is not None else None,
        "headline_value": _num(b["alpha"]),
        "method": "Every real deposit and withdrawal replayed date-matched into an ICICI Pru "
                  "Nifty-50 index fund; your yearly growth and the index fund's yearly growth "
                  "computed on the identical set of cashflows.",
    }


def sec_habits(cid, f) -> dict:
    beh = f["behaviour"].get(cid)
    if beh is None:
        return _insufficient("no behaviour-fingerprint row (client has no scored buy/sell "
                              "or SIP history to fingerprint)")
    cf = f["counterfactuals"].get(cid, {})
    sip_active_share = None
    if beh.get("sip_streams"):
        sip_active_share = round(beh["sip_active"] / beh["sip_streams"], 4)
    panic_share = _num(beh["panic_share"]) or 0.0
    return {
        "panic_share": panic_share,
        "sip_active_share": sip_active_share,
        "chase_hot_share": _num(beh["chase_hot_share"]),
        "div_leak_rs": _num(beh["div_leak_rs"]),
        "pgr": _num(beh["pgr"]),
        "plr": _num(beh["plr"]),
        "disposition": _num(beh["disposition"]),
        "cf_no_panic_rs": _num(cf.get("cf_no_panic_rs")),
        "cf_sip_alive_rs": _num(cf.get("cf_sip_alive_rs")),
        "headline_value": panic_share,
        "method": "Behaviour fingerprint (share of lifetime withdrawals sold inside a "
                  "market-fall window, SIP-active share, chase-the-hot-fund share) plus "
                  "what-if cost replays of those same habits.",
    }


def sec_value(cid, f) -> dict:
    vs = f["value"][cid]  # guaranteed: every client_id has a row (build_value_statement.py)
    realized = {
        "sip_discipline_rs": _num(vs["sip_discipline_rs"]),
        "staying_power_rs": _num(vs["staying_power_rs"]),
        "advice_outcome_rs": _num(vs["advice_outcome_rs"]),  # signed
        "fee_save_yr_rs": _num(vs["fee_save_yr_rs"]),
        "tax_headroom_rs": _num(vs["tax_headroom_rs"]),
    }
    realized_total = sum(v for v in realized.values() if v is not None)
    return {
        "realized": realized,
        "realized_total_rs": realized_total,
        "coaching_opportunity_rs": _num(vs["coaching_opportunity_rs"]),
        "summary": vs["summary"],
        "headline_value": realized_total,
        "method": "wealth.value_statements: 5 realized components (SIP-discipline, "
                  "staying-power, signed advice-outcome, fee-save, tax-headroom) summed; "
                  "coaching_opportunity_rs is a labelled upper bound, not realized.",
    }


def sec_actions(cid, f) -> dict:
    calls = f["call_lists"].get(cid, [])
    flags = f["flags"].get(cid, [])
    th = f["tax_harvest"].get(cid)
    tax_line = None
    if th is not None:
        candidates = th["gain_candidates"] or []
        tax_line = {
            "fy": th["fy"],
            "headroom": _num(th["headroom"]),
            "gain_value": _num(th["gain_value"]),
            "tax_saved_if_harvested": _num(th["tax_saved_if_harvested"]),
            "n_gain_candidates": len(candidates),
            "loss_note": th["loss_note"],
        }
    n_actions = len(calls) + len(flags) + (1 if tax_line and tax_line["n_gain_candidates"] else 0)
    return {
        "calls": calls,
        "flags": flags,
        "tax": tax_line,
        "n_actions": n_actions,
        "headline_value": n_actions,
        "method": "Call-list entries (wealth.call_lists), rule-engine flags "
                  "(wealth.client_flags), and this-FY harvest candidates "
                  "(wealth.tax_harvest) for this client; 0 is a genuinely clean client, "
                  "not missing data.",
    }


SECTION_BUILDERS = [
    ("map", sec_map),
    ("label_check", sec_label_check),
    ("overlap", sec_overlap),
    ("fees", sec_fees),
    ("benchmark", sec_benchmark),
    ("habits", sec_habits),
    ("value", sec_value),
    ("actions", sec_actions),
]

# Single source of truth for the 8-section order, shared with Tasks 8/9
# (narrate_audit_packs.py, build_capability_app.py). NOTE: the `payload`
# column is `jsonb`, which does NOT preserve object-key order on round-trip
# (Postgres re-serializes jsonb) — code that needs the canonical order
# (narration order, frontend section order) must import SECTION_NAMES from
# here, not rely on dict-iteration order after reading the row back.
SECTION_NAMES = [name for name, _ in SECTION_BUILDERS]


def compute_all(conn) -> list[dict]:
    f = load_frames(conn)
    rows = []
    for cid in sorted(f["clients"]):
        payload = {name: builder(cid, f) for name, builder in SECTION_BUILDERS}
        rows.append({"client_id": cid, "payload": _clean(payload)})
    return rows


def main() -> int:
    conn = connect()
    rows = compute_all(conn)

    cur = conn.cursor()
    # Non-destructive refresh: upsert payloads, PRESERVE existing prose (a plain
    # drop-and-recreate would wipe narrate_audit_packs.py's prose column).
    cur.execute(
        """create table if not exists wealth.audit_packs (
             client_id bigint primary key references wealth.clients(client_id),
             payload jsonb not null,
             prose jsonb
           )"""
    )
    execute_values(
        cur,
        """insert into wealth.audit_packs (client_id, payload) values %s
           on conflict (client_id) do update set payload = excluded.payload""",
        [(r["client_id"], Json(r["payload"])) for r in rows],
        page_size=200,
    )
    cur.execute("revoke all on wealth.audit_packs from anon, authenticated")
    conn.commit()

    full = sum(1 for r in rows if all(
        "insufficient" not in r["payload"][s] for s, _ in SECTION_BUILDERS))
    max_bytes = max(len(json.dumps(r["payload"])) for r in rows)
    print(f"audit packs: {len(rows)} clients x 8 sections ({full} clients all-8-sufficient)")
    print(f"largest payload: {max_bytes / 1024:.1f} KB")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
