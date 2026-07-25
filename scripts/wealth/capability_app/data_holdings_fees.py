"""Q4 (fees), Q5 (fund performance vs benchmark), Q7 (cut list) — the three
remaining Holdings-page exhibits, split from data_behaviour.py to stay under
the 600-LOC file limit (Task 2 brief's file-layout guidance). Same contract
as data_holdings.py: every function takes a live `conn`, returns real query
output, no fixtures.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date

from build_fund_performance import _benchmark_note
from client_analytics import INDEX_ER  # 0.20 — assumed achievable index ER, not re-derived

from .data import _f, lcr_py
from .data_holdings_overlap import _seed_overlap_threshold


def _chips_from_reason(reason: str) -> list[str]:
    """Evidence chips derivable from build_cut_list.weak_funds()'s own
    reason-text vocabulary. Shared by q7_cut_list (book) and the client-360
    per-client cut-list slice so the chip rules never diverge between the
    two call sites."""
    chips = []
    if "label mismatch" in reason:
        chips.append("off-label")
    if "redundant vs held peer" in reason:
        chips.append("duplicate")
    if "bottom-quartile fund_rank" in reason or "beat benchmark only" in reason:
        chips.append("laggard")
    return chips


def _held_scheme_expense_ratios(conn) -> dict[int, tuple[str, float]]:
    """scheme_id -> (category_name, expense_ratio_pct) for every held scheme
    with a resolvable real expense_ratio (own mstar_id -> de_mf_master).
    Shared by q4_fees (dumbbell's regular-plan side) and q7_cut_list
    (per-cut-fund TER-implied annual cost) so the two never diverge on what
    counts as a held scheme's "real" ER."""
    cur = conn.cursor()
    cur.execute(
        """select distinct s.scheme_id, m.category_name, m.expense_ratio::float
           from wealth.holdings h
           join wealth.schemes s using (scheme_id)
           join atlas_foundation.de_mf_master m on m.mstar_id = s.mstar_id
           where h.market_value > 0 and m.expense_ratio is not null and m.category_name is not null"""
    )
    return {sid: (cat, er) for sid, cat, er in cur.fetchall()}


def q4_fees(conn) -> dict:
    """What do you actually pay? Book rollup = sum(wealth.value_statements.
    fee_save_yr_rs) — that column is ALREADY the closet-indexer fee-saving
    heuristic (client_analytics.py's R3 rule: r2>=0.93 & expense_ratio>=0.8 &
    asset_class=='Equity', replacement ER assumed = INDEX_ER) rolled up per
    client by build_value_statement.py from wealth.client_flags. No new fee
    math is performed here — see that module's docstring for the exact
    derivation. Evidence sample = the real per-client flag rows (rule ilike
    '%closet%'), not a recomputed per-fund r2 (which isn't persisted anywhere
    and recomputing it independently risks silently diverging from what's
    actually flagged)."""
    cur = conn.cursor()
    cur.execute(
        """select coalesce(sum(fee_save_yr_rs), 0)::float, count(*) filter (where fee_save_yr_rs > 0)
           from wealth.value_statements"""
    )
    total_fee_save, n_clients_paying = cur.fetchone()

    cur.execute(
        """select f.client_id, c.full_name, f.evidence, f.est_value::float
           from wealth.client_flags f join wealth.clients c using (client_id)
           where f.rule ilike '%%closet%%'
           order by f.est_value desc"""
    )
    closet_rows = cur.fetchall()

    # dumbbell: regular-plan side = REAL per-scheme actual ER (each held fund's
    # own mstar_id -> de_mf_master.expense_ratio); direct-plan side = a
    # category-median ESTIMATE (de_mf_master population median restricted to
    # fund_name ilike '%dir%', map_schemes.py's existing is_direct convention),
    # bucketed by de_mf_master.category_name so both sides share one category
    # vocabulary — no crosswalk to wealth.schemes.sub_category is needed or
    # attempted (their vocabularies don't match 1:1; confirmed via psql).
    #
    # NOTE — this inverts the brief's literal wording ("only direct-plan TERs
    # exist ... label the regular side as the estimate"). Empirically the
    # opposite is true: wealth.schemes.plan_type is 100% 'Regular', and every
    # held scheme's own mstar_id resolves to a REAL Regular-plan expense_ratio
    # row in de_mf_master (verified e.g. Axis Large Cap Reg-G -> F000005HAY ->
    # ER 0.68, distinct from the Direct sibling F00000PDM3 -> ER 0.15). Flagged
    # in the task report as a verified brief correction.
    held_er = _held_scheme_expense_ratios(conn)
    by_cat_regular: dict[str, list[float]] = defaultdict(list)
    for _cat, _er in held_er.values():
        by_cat_regular[_cat].append(_er)

    cur.execute(
        """select category_name, expense_ratio::float
           from atlas_foundation.de_mf_master
           where fund_name ilike '%%dir%%' and expense_ratio is not null
             and category_name is not null"""
    )
    direct_er = cur.fetchall()
    by_cat_direct: dict[str, list[float]] = defaultdict(list)
    for cat, er in direct_er:
        by_cat_direct[cat].append(er)

    dumbbell = []
    for cat in sorted(by_cat_regular):
        reg = by_cat_regular[cat]
        dumbbell.append(
            {
                "category": cat,
                "regular_actual_pct": _f(statistics.median(reg)),
                "n_held_funds": len(reg),
                "direct_estimate_pct": _f(statistics.median(by_cat_direct[cat]))
                if by_cat_direct.get(cat)
                else None,
                "n_direct_population": len(by_cat_direct.get(cat, [])),
            }
        )
    dumbbell.sort(key=lambda r: -(r["regular_actual_pct"] or 0))

    verdict = f"{lcr_py(total_fee_save)}/yr sits in avoidable fund fees across {n_clients_paying} clients."

    sample_rows = [
        {"client_id": cid, "name": name, "evidence": ev, "est_value_rs": _f(v)}
        for cid, name, ev, v in closet_rows[:20]
    ]

    return {
        "total_fee_save_yr_rs": _f(total_fee_save),
        "n_clients_paying": n_clients_paying,
        "dumbbell": dumbbell,
        "verdict": verdict,
        "honesty": "estimate",
        "working": {
            "inputs": [
                {
                    "label": "Book fee-save (wealth.value_statements sum)",
                    "value": _f(total_fee_save),
                },
                {"label": "Clients flagged", "value": n_clients_paying},
                {
                    "label": "Index ER assumed achievable (client_analytics.INDEX_ER)",
                    "value": INDEX_ER,
                },
            ],
            "rule": (
                "fee_save_yr_rs per client = sum(est_value) over wealth.client_flags rows whose "
                "rule mentions 'closet' — the closet-indexer heuristic from client_analytics.py "
                f"(R² >= 0.93 vs Nifty-50, expense_ratio >= 0.8%, asset_class == 'Equity'), fee "
                f"saving = market_value * (actual expense_ratio - {INDEX_ER}%) / 100. Book total is "
                "a plain sum over all clients (build_value_statement.py already floors each "
                "client's figure at 0). Dumbbell categories use de_mf_master.category_name for "
                "BOTH sides: regular = median of REAL held-scheme expense_ratio (own mstar_id "
                "join); direct = median expense_ratio across ALL de_mf_master rows in that "
                "category whose fund_name contains 'dir' (map_schemes.py's own is_direct pattern) "
                "— a population estimate, not tied to the specific held scheme's sibling (no "
                "reliable regular->direct sibling bridge exists)."
            ),
            "assumptions": [
                {
                    "text": "closet-indexer classification and INDEX_ER replacement rate are a "
                    "heuristic (R²/ER/asset-class thresholds), not a certainty that every "
                    "flagged fund is truly a closet indexer",
                    "bias": "estimate — could over- or under-count depending on how close a "
                    "fund sits to the threshold",
                },
                {
                    "text": "the direct-plan side of the dumbbell is a category-median across "
                    "the whole fund universe, not the specific held scheme's own direct sibling",
                    "bias": "estimate — a specific held fund's real direct-plan ER could differ "
                    "from its category median",
                },
            ],
            "steps": [
                {"label": "Clients with fee_save_yr_rs > 0", "value": n_clients_paying},
                {"label": "Sum of fee_save_yr_rs", "value": _f(total_fee_save)},
            ],
            "sample_rows": sample_rows,
            "sample_of": len(closet_rows),
            "honesty": "estimate",
        },
    }


def q5_fund_performance(conn) -> dict:
    """Did the funds beat their benchmark? Source: wealth.fund_performance
    (real return numbers, verdict='insufficient_history' rendered as an
    honest gap, never a zero). 'Excess return' bars use the fund's own
    full_period_pct against a plain (non-smoothed) CAGR of its mapped index
    over the SAME calendar window as the fund's own NAV history — simpler
    than build_fund_performance's internal 12-anchor rolling machinery, kept
    that way deliberately (ponytail: two-point CAGR, ceiling = a single
    volatile start/end point can skew it vs the smoothed roll_5y/roll_3y
    numbers shown alongside it; upgrade path = import
    build_fund_performance._roll_cagr with the same anchor set if this ever
    needs to match that precision)."""
    cur = conn.cursor()
    cur.execute(
        """select fp.scheme_id, s.display_name, fp.roll_3y_pct::float, fp.roll_5y_pct::float,
                  fp.dn_capture_pct::float, fp.full_period_pct::float, fp.beat_count, fp.windows,
                  fp.benchmark_note, fp.verdict, m.primary_benchmark,
                  hv.value_rs
           from wealth.fund_performance fp
           join wealth.schemes s using (scheme_id)
           left join atlas_foundation.de_mf_master m on m.mstar_id = fp.mstar_id
           join (select scheme_id, sum(market_value)::float value_rs from wealth.holdings
                 where market_value > 0 group by 1) hv using (scheme_id)"""
    )
    rows = cur.fetchall()

    codes = sorted({code for (code, _note) in (_benchmark_note(r[10]) for r in rows) if code})

    idx_series: dict[str, list[tuple]] = {}
    if codes:
        cur.execute(
            """select index_code, date, close::float close from atlas_foundation.index_prices
               where index_code = any(%s) and close > 0 order by index_code, date""",
            (codes,),
        )
        for code, d, close in cur.fetchall():
            idx_series.setdefault(code, []).append((d, close))

    def _cagr(v0: float, d0: date, v1: float, d1: date) -> float | None:
        yrs = (d1 - d0).days / 365.25
        if yrs <= 0 or v0 <= 0 or v1 <= 0:
            return None
        return (v1 / v0) ** (1 / yrs) - 1

    def _index_window_cagr(code: str, first_d: date, last_d: date) -> float | None:
        series = idx_series.get(code)
        if not series:
            return None
        in_window = [(d, v) for d, v in series if first_d <= d <= last_d]
        if len(in_window) < 2:
            return None
        d0, v0 = in_window[0]
        d1, v1 = in_window[-1]
        return _cagr(v0, d0, v1, d1)

    # fund NAV first/last dates (needed to window-match the index leg)
    cur.execute(
        """select fp.scheme_id, min(n.nav_date), max(n.nav_date)
           from wealth.fund_performance fp
           join wealth.schemes s using (scheme_id)
           join atlas_foundation.de_mf_nav_daily n on n.mstar_id = s.mstar_id and n.nav > 0
           group by 1"""
    )
    fund_span = {sid: (d0, d1) for sid, d0, d1 in cur.fetchall()}

    funds = []
    laggard_value = 0.0
    n_laggard_funds = 0
    for (
        sid,
        name,
        roll3,
        roll5,
        dncap,
        full,
        beat,
        windows,
        _bnote,
        verdict,
        pb,
        value_rs,
    ) in rows:
        code, note = _benchmark_note(pb)
        excess_pct = None
        if code and full is not None and sid in fund_span:
            d0, d1 = fund_span[sid]
            idx_cagr = _index_window_cagr(code, d0, d1)
            if idx_cagr is not None:
                excess_pct = _f(full - idx_cagr * 100.0)
        is_laggard = beat is not None and windows and beat < windows / 2.0
        if is_laggard:
            n_laggard_funds += 1
            laggard_value += value_rs or 0.0
        funds.append(
            {
                "scheme_id": sid,
                "fund": name,
                "verdict": verdict,
                "roll_3y_pct": _f(roll3),
                "roll_5y_pct": _f(roll5),
                "dn_capture_pct": _f(dncap),
                "excess_return_pct": excess_pct,
                "beat_count": beat,
                "windows": windows,
                "beat_ratio": _f(beat / windows) if beat is not None and windows else None,
                "is_laggard": is_laggard,
                "benchmark_note": note,
                "value_rs": _f(value_rs),
            }
        )
    funds.sort(key=lambda r: (r["excess_return_pct"] is None, -(r["excess_return_pct"] or 0)))

    verdict_str = (
        f"{n_laggard_funds} of {len(funds)} held funds are chronic laggards "
        "(beat their benchmark in fewer than half of the evaluated rolling windows); "
        f"{lcr_py(laggard_value)} sits in them."
    )

    sample_rows = [
        {"scheme_id": f["scheme_id"], "fund": f["fund"], "verdict": f["verdict"]}
        for f in funds[:20]
    ]

    return {
        "funds": funds,
        "n_funds": len(funds),
        "n_laggard_funds": n_laggard_funds,
        "laggard_value_rs": _f(laggard_value),
        "verdict": verdict_str,
        "honesty": "exact",
        "working": {
            "inputs": [
                {"label": "Funds scored", "value": len(funds)},
                {"label": "Chronic laggards (beat_count < windows/2)", "value": n_laggard_funds},
                {"label": "₹ in chronic laggards", "value": _f(laggard_value)},
            ],
            "rule": (
                "wealth.fund_performance: verdict='scored' has a real roll_5y_pct; "
                "'insufficient_history' means <5y NAV history or a stale fund, rendered as a gap "
                "not a zero. beat_count/windows = wins out of up to 20 trailing monthly-spaced "
                "rolling-1y windows vs the fund's mapped NSE index (build_fund_performance.py), "
                "NOT calendar years. Laggard = beat_count < windows/2, the same cutoff "
                "build_cut_list.py's weak_funds() uses. 'Excess return' bars = the fund's own "
                "full_period_pct minus a plain two-point CAGR of its mapped index computed over "
                "the fund's own NAV-history window (not the smoothed 12-anchor rolling CAGR used "
                "for roll_3y/roll_5y elsewhere)."
            ),
            "assumptions": [
                {
                    "text": "every mapped benchmark leg is an NSE PRICE-return index standing "
                    "in for the fund's TOTAL-return benchmark (benchmark_note flags this per "
                    "fund) — PR indices run lower than TR over long periods, so excess_return "
                    "and beat_count are both flattered vs a true TR comparison",
                    "bias": "estimate — overstates how often/by how much funds actually beat "
                    "their real (TR) benchmark",
                },
                {
                    "text": "excess_return_pct uses a simple two-point CAGR for the index leg, "
                    "not the smoothed rolling-anchor CAGR used for the fund's own roll_3y/roll_5y",
                    "bias": "estimate — a single volatile start/end NAV point can skew this "
                    "number more than the smoothed figures shown alongside it",
                },
            ],
            "steps": [
                {"label": "Held equity funds in wealth.fund_performance", "value": len(funds)},
                {
                    "label": "Scored (roll_5y present)",
                    "value": sum(1 for f in funds if f["verdict"] == "scored"),
                },
            ],
            "sample_rows": sample_rows,
            "sample_of": len(funds),
            "honesty": "exact",
        },
    }


def q7_cut_list(conn) -> dict:
    """What would we cut? Source: wealth.cut_list (keep/cut jsonb per client).
    Evidence chips derived from build_cut_list.weak_funds()'s own reason-text
    vocabulary: 'label mismatch' -> off-label, 'redundant vs held peer'
    (always appended to every cut reason) -> duplicate, 'bottom-quartile
    fund_rank'/'beat benchmark only' -> laggard. There is NO 'expensive'
    reason string anywhere in weak_funds() — fee/ER is not a cut_list
    criterion at all, so that chip is never emitted (an honest gap, not a
    fabricated one; noted in the task report as a brief-vocabulary mismatch).

    The from->to consolidation sankey is RE-DERIVED (build_cut_list.py
    discards which specific kept fund a cut fund was redundant against): for
    each cut fund, look at wealth.client_fund_overlap pairs above the seeded
    duplicate threshold involving that fund; if one of the pair's OTHER
    members is in that same client's keep set, emit an edge to the
    highest-overlap such partner. Cut funds with no qualifying partner are
    OMITTED from the sankey — an incomplete sankey is honest, a fabricated
    edge is not.

    Fee-save and duplication figures reuse existing pieces rather than
    re-deriving them: TER-implied annual cost of the cut funds comes from
    the SAME held-scheme expense-ratio lookup q4_fees uses
    (_held_scheme_expense_ratios), and the duplication percentage is
    derived from the SAME highest-overlap keep-partner already computed
    for the sankey edges — no new math, no cross-task import."""
    threshold = _seed_overlap_threshold(conn)
    held_er = _held_scheme_expense_ratios(conn)
    cur = conn.cursor()
    cur.execute("select client_id, keep, cut, min_fund_count, note from wealth.cut_list")
    cl_rows = cur.fetchall()

    cur.execute(
        "select client_id, scheme_a, scheme_b, overlap_pct::float from wealth.client_fund_overlap "
        "where overlap_pct > %s",
        (threshold,),
    )
    pairs_by_client: dict[int, list[tuple[int, int, float]]] = defaultdict(list)
    for cid, a, b, pct in cur.fetchall():
        pairs_by_client[cid].append((a, b, pct))

    n_with_cut = 0
    n_kept_rows = 0
    total_cut_value_rs = 0.0
    total_exit_tax_rs = 0.0
    total_cut_fee_rs = 0.0
    dup_value_rs = 0.0
    chip_counts: dict[str, int] = defaultdict(int)
    evidence_rows = []
    edge_agg: dict[tuple[str, str], dict] = {}

    cur.execute(
        """select scheme_id, sum(market_value)::float from wealth.holdings
           where market_value > 0 group by 1"""
    )
    scheme_value = dict(cur.fetchall())

    for cid, keep_json, cut_json, _min_fund_count, _note in cl_rows:
        keep = keep_json or []
        cut = cut_json or []
        keep_by_sid = {k["scheme_id"]: k for k in keep}
        n_kept_rows += len(keep)
        if cut:
            n_with_cut += 1
        for c in cut:
            sid = c["scheme_id"]
            value = scheme_value.get(sid, 0.0) or 0.0
            total_cut_value_rs += value
            total_exit_tax_rs += float(c.get("exit_tax_rs") or 0.0)
            reason = c.get("reason", "")
            chips = _chips_from_reason(reason)
            for chip in chips:
                chip_counts[chip] += 1

            # TER-implied annual cost of this cut fund — same held-scheme ER
            # lookup q4_fees uses, no separate/re-derived expense math.
            cat_er = held_er.get(sid)
            fund_fee_rs = value * cat_er[1] / 100.0 if cat_er else None
            if fund_fee_rs is not None:
                total_cut_fee_rs += fund_fee_rs

            evidence_rows.append(
                {
                    "client_id": cid,
                    "fund": c.get("fund"),
                    "reason": reason,
                    "chips": chips,
                    "exit_tax_rs": _f(c.get("exit_tax_rs")),
                    "unwind_order": c.get("unwind_order"),
                    "fee_save_yr_rs": _f(fund_fee_rs),
                }
            )

            # sankey edge: best (highest-overlap) keep partner for this cut fund
            best = None
            for a, b, pct in pairs_by_client.get(cid, []):
                other = b if a == sid else (a if b == sid else None)
                if other is None or other not in keep_by_sid:
                    continue
                if best is None or pct > best[1]:
                    best = (other, pct)
            if best is not None:
                to_sid, pct = best
                # this cut fund's value is `pct`% overlapped with a fund we're
                # keeping — count that share of its value as duplication removed.
                dup_value_rs += value * pct / 100.0
                to_name = keep_by_sid[to_sid]["fund"]
                key = (c.get("fund"), to_name)
                agg = edge_agg.setdefault(
                    key, {"from": c.get("fund"), "to": to_name, "n_clients": 0, "overlaps": []}
                )
                agg["n_clients"] += 1
                agg["overlaps"].append(pct)

    sankey = []
    for (_f_name, _t_name), agg in edge_agg.items():
        sankey.append(
            {
                "from": agg["from"],
                "to": agg["to"],
                "n_clients": agg["n_clients"],
                "median_overlap_pct": _f(statistics.median(agg["overlaps"])),
            }
        )
    sankey.sort(key=lambda e: -e["n_clients"])

    n_cut_rows = len(evidence_rows)
    n_total_rows = n_cut_rows + n_kept_rows
    duplication_removed_pct = (
        _f(100 * dup_value_rs / total_cut_value_rs) if total_cut_value_rs else 0.0
    )

    verdict = (
        f"Cutting {n_cut_rows} of {n_total_rows} funds ({n_with_cut} of {len(cl_rows)} clients "
        f"affected) — saves {lcr_py(total_cut_fee_rs)}/yr in fees, removes "
        f"{duplication_removed_pct:.0f}% duplication ({lcr_py(total_cut_value_rs)} in "
        f"redundant-and-weak positions, {lcr_py(total_exit_tax_rs)} of estimated exit tax)."
    )

    return {
        "n_clients": len(cl_rows),
        "n_with_cut": n_with_cut,
        "total_cut_value_rs": _f(total_cut_value_rs),
        "total_exit_tax_rs": _f(total_exit_tax_rs),
        "total_cut_fee_rs": _f(total_cut_fee_rs),
        "duplication_removed_pct": duplication_removed_pct,
        "chip_counts": dict(chip_counts),
        "sankey": sankey,
        "verdict": verdict,
        "honesty": "estimate",
        "working": {
            "inputs": [
                {"label": "Clients with a cut recommendation", "value": n_with_cut},
                {"label": "₹ in cut positions", "value": _f(total_cut_value_rs)},
                {"label": "Estimated exit tax", "value": _f(total_exit_tax_rs)},
                {
                    "label": "Fee save from cutting (TER-implied, /yr)",
                    "value": _f(total_cut_fee_rs),
                },
                {"label": "Duplication removed", "value": duplication_removed_pct},
            ],
            "rule": (
                "wealth.cut_list: cut = redundant ∩ weak funds (build_cut_list.py), redundant = "
                "the smaller-unique-exposure member of an overlap pair above the duplicate "
                f"threshold ({threshold}%, atlas_thresholds), weak = label mismatch OR "
                "bottom-quartile fund_rank OR poor scored fund_performance. keep = the greedy "
                "min set-cover of look-through exposure (>=90% coverage target). The sankey "
                "re-derives, per cut fund, its highest-overlap partner among that SAME client's "
                "keep set (via wealth.client_fund_overlap above the same threshold) — "
                "build_cut_list.py itself discards this mapping once it decides cut/keep, so it "
                "is reconstructed here, not read from a stored column. Cut funds with no "
                "qualifying keep-side partner are omitted from the sankey. Fee save = each cut "
                "fund's own market_value * its real expense_ratio / 100, using the SAME "
                "held-scheme ER lookup as q4_fees (_held_scheme_expense_ratios) — summed "
                "book-wide, cut funds with no resolvable ER contribute 0, not a guess. "
                "Duplication removed % = value-weighted share of cut-fund money that has a "
                "highest-overlap keep-side partner (the SAME pairing used for the sankey edges) "
                "divided by total cut value."
            ),
            "assumptions": [
                {
                    "text": "the sankey only draws an edge when a cut fund's highest-overlap "
                    "partner is itself in the keep set — some cut funds have no such partner "
                    "and are silently absent from the diagram",
                    "bias": "estimate — the sankey undercounts consolidation flows for those "
                    "funds rather than guessing a destination",
                },
                {
                    "text": "the 'expensive' evidence chip (mentioned in the exhibit spec) has "
                    "no counterpart in build_cut_list.py's weak_funds() reason vocabulary — fee "
                    "level is not a cut_list criterion — so it is never emitted",
                    "bias": "floor — likely undercounts fee-driven cut rationale versus what a "
                    "fee-aware cut engine might also flag",
                },
                {
                    "text": "a cut fund with no resolvable de_mf_master expense_ratio (own "
                    "mstar_id join) contributes ₹0 to the fee-save total rather than an "
                    "estimated/imputed ER",
                    "bias": "floor — the fee-save figure undercounts if any cut fund's real ER "
                    "isn't resolvable, never overstates it",
                },
            ],
            "steps": [
                {"label": "Clients scanned", "value": len(cl_rows)},
                {"label": "Cut fund rows", "value": len(evidence_rows)},
                {"label": "Kept fund rows", "value": n_kept_rows},
                {"label": "Sankey edges", "value": len(sankey)},
            ],
            "sample_rows": evidence_rows[:20],
            "sample_of": len(evidence_rows),
            "honesty": "estimate",
        },
    }
