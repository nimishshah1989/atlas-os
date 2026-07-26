"""Client 360, part 2: fund-pair overlap heatmap + fees/cut-list slice,
behaviour section (crisis flows / switches / SIP streams / dividend
leakage), what-ifs, and the client_360_all(conn) composer. Split from
data_client360.py to stay under the 600-LOC file limit. Same contract:
real query output only, no fixtures.
"""

from __future__ import annotations

from client_analytics import INDEX_ER

from .data import _f, lcr_py
from .data_client360 import (
    client_funds_table,
    client_header,
    client_label_check,
    client_sector_lookthrough,
    client_timeline,
    crisis_windows_once,
)
from .data_holdings_fees import _chips_from_reason
from .data_holdings_overlap import _seed_overlap_threshold


def client_overlap_heatmap(conn, client_id: int, threshold: float) -> dict:
    """Fund-pair overlap heatmap for one client: wealth.client_fund_overlap
    pairs, scheme names, and their own held value (same threshold as book Q3,
    passed in rather than re-seeded per client)."""
    cur = conn.cursor()
    cur.execute(
        """select o.scheme_a, sa.display_name, o.scheme_b, sb.display_name, o.overlap_pct::float
           from wealth.client_fund_overlap o
           join wealth.schemes sa on sa.scheme_id = o.scheme_a
           join wealth.schemes sb on sb.scheme_id = o.scheme_b
           where o.client_id = %s order by o.overlap_pct desc""",
        (client_id,),
    )
    rows = cur.fetchall()
    above = [r for r in rows if r[4] > threshold]

    verdict = (
        f"{len(above)} of {len(rows)} fund pairs held by this client overlap more than "
        f"{int(threshold)}%."
        if rows
        else "no overlapping fund pairs for this client."
    )

    return {
        "client_id": client_id,
        "threshold_pct": threshold,
        "n_pairs": len(rows),
        "n_pairs_above_threshold": len(above),
        "pairs": [
            {"scheme_a": a, "fund_a": na, "scheme_b": b, "fund_b": nb, "overlap_pct": _f(pct)}
            for a, na, b, nb, pct in rows
        ],
        "verdict": verdict,
        "honesty": "estimate",
        "working": {
            "inputs": [
                {"label": "Duplicate-pair threshold (atlas_thresholds)", "value": threshold},
                {"label": "Pairs for this client", "value": len(rows)},
                {"label": "Pairs above threshold", "value": len(above)},
            ],
            "rule": (
                "wealth.client_fund_overlap only stores this client's fund pairs with "
                "overlap_pct >= 20 (build_overlap.py's storage cutoff); 'duplicate' = "
                "overlap_pct above the same atlas_thresholds cutoff used book-wide in Q3."
            ),
            "assumptions": [
                {
                    "text": "overlap_pct is a stock-weight overlap (sum of min shared "
                    "weights), not a literal rupee-for-rupee duplication measure",
                    "bias": "estimate — approximates duplication rather than tracing each "
                    "rupee to a specific stock",
                }
            ],
            "steps": [{"label": "Pairs returned", "value": len(rows)}],
            "sample_rows": [
                {"fund_a": na, "fund_b": nb, "overlap_pct": _f(pct)}
                for _a, na, _b, nb, pct in rows[:20]
            ],
            "sample_of": len(rows),
            "honesty": "estimate",
        },
    }


def client_fees_and_cuts(conn, client_id: int) -> dict:
    """This client's own fee-save figure (Q4 slice) + their own cut_list row
    (Q7 slice) with the same evidence chips build_cut_list.weak_funds()'s
    reason text supports. No recompute of the heuristics — plain per-client
    reads."""
    cur = conn.cursor()
    cur.execute(
        "select fee_save_yr_rs::float from wealth.value_statements where client_id = %s",
        (client_id,),
    )
    r = cur.fetchone()
    fee_save = r[0] if r else 0.0

    cur.execute(
        """select s.display_name, m.expense_ratio::float, h.market_value::float
           from wealth.holdings h
           join wealth.schemes s using (scheme_id)
           join atlas_foundation.de_mf_master m on m.mstar_id = s.mstar_id
           where h.client_id = %s and h.market_value > 0 and m.expense_ratio is not null""",
        (client_id,),
    )
    held_er = cur.fetchall()

    cur.execute("select keep, cut from wealth.cut_list where client_id = %s", (client_id,))
    cl = cur.fetchone()
    keep, cut = cl if cl else ([], [])
    evidence = [
        {
            "fund": c.get("fund"),
            "reason": c.get("reason"),
            "chips": _chips_from_reason(c.get("reason", "")),
            "exit_tax_rs": _f(c.get("exit_tax_rs")),
            "unwind_order": c.get("unwind_order"),
        }
        for c in (cut or [])
    ]

    verdict = (
        f"{lcr_py(fee_save)}/yr in avoidable fund fees; {len(evidence)} funds we'd cut, "
        f"{len(keep or [])} to keep."
    )

    return {
        "client_id": client_id,
        "fee_save_yr_rs": _f(fee_save),
        "held_fund_ers": [
            {"fund": name, "expense_ratio_pct": _f(er), "value_rs": _f(v)}
            for name, er, v in held_er
        ],
        "index_er_assumed_pct": INDEX_ER,
        "keep": keep or [],
        "cut_evidence": evidence,
        "verdict": verdict,
        "honesty": "estimate",
        "working": {
            "inputs": [
                {"label": "Fee-save/yr (value_statements)", "value": _f(fee_save)},
                {"label": "Funds to cut", "value": len(evidence)},
                {"label": "Funds to keep", "value": len(keep or [])},
            ],
            "rule": (
                "wealth.value_statements.fee_save_yr_rs (client_analytics.py's closet-indexer "
                "heuristic, R2>=0.93 & expense_ratio>=0.8 & asset_class=='Equity', ER "
                f"replacement assumed at INDEX_ER={INDEX_ER}%). wealth.cut_list.cut entries "
                "carry {fund, scheme_id, reason, exit_tax_rs, unwind_order}; evidence chips "
                "derived from build_cut_list.weak_funds()'s own reason-text vocabulary (no "
                "'expensive' chip exists — fee/ER is not a cut_list criterion)."
            ),
            "assumptions": [
                {
                    "text": "fee_save_yr_rs rests on the closet-indexer heuristic and the "
                    f"assumed INDEX_ER={INDEX_ER}%, not a certainty this specific fund is a "
                    "closet indexer",
                    "bias": "estimate",
                }
            ],
            "steps": [{"label": "Held funds with a real ER", "value": len(held_er)}],
            "sample_rows": [
                {"fund": name, "expense_ratio_pct": _f(er)} for name, er, _v in held_er[:20]
            ],
            "sample_of": len(held_er),
            "honesty": "estimate",
        },
    }


def client_behaviour_section(conn, client_id: int, crisis_windows: list[dict]) -> dict:
    """Behaviour section: crisis flows, switch verdicts, SIP streams,
    dividend leakage — per-client slices of book-level B2/B3/B4."""
    cur = conn.cursor()
    cur.execute(
        """select panic_out_rs::float, panic_loss_out_rs::float, panic_share::float,
                  div_leak_rs::float, sip_streams, sip_active, sip_stopped,
                  sip_stops_in_drawdown
           from wealth.client_behaviour where client_id = %s""",
        (client_id,),
    )
    cb = cur.fetchone()

    cur.execute(
        """select switch_date, from_name, to_name, alpha_1y_pp::float, alpha_1y_rs::float
           from wealth.advice_ledger where client_id = %s order by switch_date""",
        (client_id,),
    )
    switches = cur.fetchall()

    cur.execute(
        """select scheme_id, mwr_pct::float, twr_pct::float, gap_pp::float, gap_rs::float
           from wealth.behaviour_gap where client_id = %s""",
        (client_id,),
    )
    gaps = cur.fetchall()

    if cb is None and not switches and not gaps:
        return {
            "client_id": client_id,
            "insufficient": True,
            "message": "no behaviour, switch, or gap rows for this client",
            "working": {
                "inputs": [],
                "rule": "wealth.client_behaviour/advice_ledger/behaviour_gap have no rows",
                "assumptions": [],
                "steps": [],
                "sample_rows": [],
                "sample_of": 0,
                "honesty": None,
            },
        }

    (
        panic_out,
        panic_loss,
        panic_share,
        div_leak,
        sip_streams,
        sip_active,
        sip_stopped,
        sip_stops_dd,
    ) = cb or (0.0, 0.0, 0.0, 0.0, 0, 0, 0, 0)

    verdict = (
        f"{lcr_py(panic_loss or 0.0)} sold below cost, {lcr_py(div_leak or 0.0)} dividend "
        f"leakage, {sip_stopped} SIP(s) stopped ({sip_stops_dd} mid-drawdown), "
        f"{len(switches)} advised switches."
    )

    return {
        "client_id": client_id,
        "panic_out_rs": _f(panic_out),
        "panic_loss_out_rs": _f(panic_loss),
        "panic_share": _f(panic_share),
        "div_leak_rs": _f(div_leak),
        "sip_streams": sip_streams,
        "sip_active": sip_active,
        "sip_stopped": sip_stopped,
        "sip_stops_in_drawdown": sip_stops_dd,
        "switches": [
            {
                "switch_date": str(sd),
                "from_fund": fn,
                "to_fund": tn,
                "extra_growth_1y_pp": _f(a1),
                "extra_growth_1y_rs": _f(a1rs),
            }
            for sd, fn, tn, a1, a1rs in switches
        ],
        "gap_pp_by_scheme": [
            {"scheme_id": sid, "mwr_pct": _f(m), "twr_pct": _f(t), "gap_pp": _f(g)}
            for sid, m, t, g, _grs in gaps
        ],
        "crisis_windows": crisis_windows,
        "verdict": verdict,
        "honesty": "estimate",
        "working": {
            "inputs": [
                {"label": "Panic-loss sold rs", "value": _f(panic_loss)},
                {"label": "Dividend leakage rs", "value": _f(div_leak)},
                {"label": "Switches", "value": len(switches)},
            ],
            "rule": (
                "Per-client slices of book-level rows: wealth.client_behaviour "
                "(behaviour_fingerprints.py, crisis flows/SIP streams/dividend leakage against "
                "the shared drawdown windows), wealth.advice_ledger (paired switches, "
                "estimate-tagged per B4 since forward verdicts rest on a benchmark-comparison "
                "assumption), wealth.behaviour_gap (MWR vs TWR per held scheme, exact per B2)."
            ),
            "assumptions": [
                {
                    "text": "switch outcomes compare the two named funds' forward returns, "
                    "not what else the client could have done with the money",
                    "bias": "estimate",
                }
            ],
            "steps": [{"label": "Sub-tables checked", "value": 3}],
            "sample_rows": [
                {"switch_date": str(sd), "extra_growth_1y_pp": _f(a1)}
                for sd, _fn, _tn, a1, _a1rs in switches[:20]
            ],
            "sample_of": len(switches),
            "honesty": "estimate",
        },
    }


def client_what_ifs(conn, client_id: int) -> dict:
    """This one client's four what-if scenarios (B5 slice) — same
    assumption-card honesty tags as the book-level function, since the
    per-client math is the identical stored row, just not summed."""
    cur = conn.cursor()
    cur.execute(
        """select cf_index_rs::float, cf_no_panic_rs::float, panic_sells,
                  cf_sip_alive_rs::float, sip_cash::float, sip_streams,
                  cf_no_switch_rs::float, switches
           from wealth.counterfactuals where client_id = %s""",
        (client_id,),
    )
    row = cur.fetchone()
    if row is None:
        return {
            "client_id": client_id,
            "insufficient": True,
            "message": "no what-if scenarios row for this client",
            "working": {
                "inputs": [],
                "rule": "the what-if-scenario table has no row for this client_id",
                "assumptions": [],
                "steps": [],
                "sample_rows": [],
                "sample_of": 0,
                "honesty": None,
            },
        }

    ci, cp, ps, cs, sc, _ss, cw, sw = row
    scenarios = {
        "cf_index_rs": {"total_rs": _f(ci), "honesty": "estimate"},
        "cf_no_panic_rs": {"total_rs": _f(cp), "n_panic_sells": ps, "honesty": "upper bound"},
        "cf_sip_alive_rs": {"total_rs": _f(cs), "sip_cash_rs": _f(sc), "honesty": "estimate"},
        "cf_no_switch_rs": {"total_rs": _f(cw), "n_switches": sw, "honesty": "estimate"},
    }
    verdict = (
        f"index-everything {lcr_py(ci)}, no-panic-sells (upper bound) {lcr_py(cp)}, "
        f"SIPs-alive (estimate) {lcr_py(cs)}, no-switches (estimate) {lcr_py(cw)}."
    )
    return {
        "client_id": client_id,
        "scenarios": scenarios,
        "verdict": verdict,
        "honesty": "estimate",
        "working": {
            "inputs": [{"label": k, "value": v["total_rs"]} for k, v in scenarios.items()],
            "rule": (
                "the what-if-scenario table row for this client_id — same four historical-replay "
                "formulas as book-level B5, just not summed across "
                "clients. Assumption-card honesty tags match B5 exactly: cf_no_panic_rs = "
                "upper bound (idle-cash assumption); cf_index_rs/cf_sip_alive_rs/"
                "cf_no_switch_rs = estimate (each assumes unchanged client cash-flow "
                "behaviour under the what-if scenario)."
            ),
            "assumptions": [
                {
                    "text": "we assume panic-sold units are simply held today; proceeds are "
                    "NOT reinvested elsewhere",
                    "bias": "upper bound",
                },
                {
                    "text": "the other three scenarios assume this client's own deposit/SIP/"
                    "switch timing would have stayed identical under the what-if scenario",
                    "bias": "estimate",
                },
            ],
            "steps": [{"label": "Row found", "value": 1}],
            "sample_rows": [
                {"client_id": client_id, **{k: v["total_rs"] for k, v in scenarios.items()}}
            ],
            "sample_of": 1,
            "honesty": "estimate",
        },
    }


def client_360(conn, client_id: int, *, crisis_windows: list[dict], threshold: float) -> dict:
    """Composes every per-client section into one page payload. crisis_windows
    and threshold are computed ONCE by client_360_all and passed in — never
    recomputed per client (both are book-wide constants)."""
    return {
        "client_id": client_id,
        "header": client_header(conn, client_id),
        "timeline": client_timeline(conn, client_id, crisis_windows),
        "funds_table": client_funds_table(conn, client_id),
        "label_check": client_label_check(conn, client_id),
        "sector_lookthrough": client_sector_lookthrough(conn, client_id),
        "overlap": client_overlap_heatmap(conn, client_id, threshold),
        "fees_and_cuts": client_fees_and_cuts(conn, client_id),
        "behaviour": client_behaviour_section(conn, client_id, crisis_windows),
        "what_ifs": client_what_ifs(conn, client_id),
    }


def client_360_all(conn) -> dict:
    """Top-level: computes the two book-wide shared inputs (crisis windows,
    overlap threshold) ONCE, then builds one page per client with real
    holdings. Keyed by client_id (int) for the render layer."""
    crisis_windows = crisis_windows_once(conn)
    threshold = _seed_overlap_threshold(conn)
    cur = conn.cursor()
    cur.execute("select distinct client_id from wealth.holdings where market_value > 0 order by 1")
    client_ids = [r[0] for r in cur.fetchall()]
    return {
        cid: client_360(conn, cid, crisis_windows=crisis_windows, threshold=threshold)
        for cid in client_ids
    }
