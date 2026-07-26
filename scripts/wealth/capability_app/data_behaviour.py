"""Behaviour-side book rollups: B1 (advice vs index), B2 (behaviour gap),
B3 (the panic pattern), B4 (advice switches), B5 (what-if machine), plus a
second-pass client_index annotation (chronic-laggard / fees-above-median
flags deferred from Task 1). Same contract as data_holdings.py: every
function takes a live `conn`, returns real query output, no fixtures.
"""

from __future__ import annotations

import statistics

from behaviour_fingerprints import drawdown_windows
from engine_common import BENCH_ID, nav_series

from .data import _f, _hist, client_names, lcr_py


def b1_advice_vs_index(conn) -> dict:
    """Did advice beat the index? Source: wealth.client_benchmark (exact
    ledger-flow replay into the Nifty-50 index fund, exact_benchmark.py).
    Never say 'alpha' in UI text — this is "extra growth vs index, per
    year". approx=True clients (opening-balance/transfer-in units with no
    cash-flow history) are surfaced separately, not silently folded in."""
    names = client_names(conn)
    cur = conn.cursor()
    cur.execute(
        """select client_id, xirr_client::float, xirr_bench::float, alpha::float, approx
           from wealth.client_benchmark where alpha is not null"""
    )
    rows = cur.fetchall()
    clean = [r for r in rows if not r[4]]
    extra = [r[3] for r in clean]
    beating = sum(1 for v in extra if v > 0)

    verdict = (
        f"{beating} of {len(clean)} clients (flow-complete) grew faster than the index; "
        f"median extra growth vs index = {statistics.median(extra):+.2f}pp/yr."
        if clean
        else "no flow-complete clients to compare."
    )

    sample_rows = [
        {
            "client_id": cid,
            "name": names.get(cid),
            "client_growth_pct": _f(cx),
            "index_growth_pct": _f(bx),
            "extra_growth_pp": _f(al),
            "approx": bool(ap),
        }
        for cid, cx, bx, al, ap in rows[:20]
    ]

    return {
        "n_clients": len(rows),
        "n_clean": len(clean),
        "n_beating_clean": beating,
        "median_extra_growth_pp": _f(statistics.median(extra)) if extra else None,
        # build-time reshape of the same `extra` list already computed above
        # (no new query) — feeds B1's hero distribution chart.
        "extra_growth_hist": _hist(extra),
        "verdict": verdict,
        "honesty": "exact",
        "working": {
            "inputs": [
                {"label": "Clients compared", "value": len(rows)},
                {"label": "Flow-complete clients", "value": len(clean)},
                {"label": "Beating the index (flow-complete)", "value": beating},
            ],
            "rule": (
                "wealth.client_benchmark replays every real external cash flow (Folio Ledgers) "
                "into the ICICI Pru Nifty 50 Index (Reg-G) fund at the same dates/amounts, then "
                "compares the client's own annualized growth rate to that benchmark's annualized "
                "growth rate on the identical flow set — apples-to-apples, per client "
                "(exact_benchmark.py). approx=True clients "
                "carry opening-balance/transfer-in units with no cash-flow history behind part "
                "of the book."
            ),
            "assumptions": [
                {
                    "text": "approx=True clients are excluded from the 'clean' comparison "
                    "because part of their book has no real flow history to replay",
                    "bias": "estimate — the excluded clients' true vs-index performance is "
                    "unknown, not assumed zero",
                }
            ],
            "steps": [
                {"label": "Rows with a computed extra-growth figure", "value": len(rows)},
                {"label": "Flow-complete (approx=False)", "value": len(clean)},
            ],
            "sample_rows": sample_rows,
            "sample_of": len(rows),
            "honesty": "exact",
        },
    }


def b2_behaviour_gap(conn) -> dict:
    """How investors cost themselves. Source: wealth.behaviour_gap (MWR via
    XIRR on unit-flows vs TWR via scheme-NAV CAGR, Morningstar 'Mind the
    Gap' methodology, client x scheme). The Hayley (2014) caveat — part of
    any MWR-TWR gap is mechanical, not skill-driven — must ship with the
    number, not just a tooltip. avg_capital uses behaviour_gap.py's own flat
    ponytail proxy (invested/2), inherited here verbatim, not recomputed."""
    names = client_names(conn)
    cur = conn.cursor()
    cur.execute(
        """select client_id, scheme_id, mwr_pct::float, twr_pct::float, gap_pp::float,
                  gap_rs::float, invested::float, years::float, partial
           from wealth.behaviour_gap"""
    )
    rows = cur.fetchall()
    gaps = [r[4] for r in rows if r[4] is not None]
    invested_w = [(r[4], r[6]) for r in rows if r[4] is not None and r[6]]
    wavg = (
        sum(g * inv for g, inv in invested_w) / sum(inv for _g, inv in invested_w)
        if invested_w
        else None
    )
    total_gap_rs = sum(r[5] for r in rows if r[5] is not None)

    verdict = (
        f"median investor-vs-fund gap {statistics.median(gaps):+.2f}pp/yr "
        f"(invested-weighted {_f(wavg):+.2f}pp); {lcr_py(total_gap_rs)} of foregone-or-extra "
        "growth from timing across the book."
        if gaps
        else "no scored client x scheme rows."
    )

    sample_rows = [
        {
            "client_id": cid,
            "name": names.get(cid),
            "scheme_id": sid,
            "mwr_pct": _f(mwr),
            "twr_pct": _f(twr),
            "gap_pp": _f(gap),
            "gap_rs": _f(gap_rs),
            "partial": bool(partial),
        }
        for cid, sid, mwr, twr, gap, gap_rs, _inv, _yrs, partial in rows[:20]
    ]

    return {
        "n_rows": len(rows),
        "median_gap_pp": _f(statistics.median(gaps)) if gaps else None,
        "invested_weighted_gap_pp": _f(wavg),
        "total_gap_rs": _f(total_gap_rs),
        # build-time reshape of the same `gaps` list already computed above
        # (no new query) — feeds B2's per-client×scheme gap histogram.
        "gap_hist": _hist(gaps),
        "verdict": verdict,
        "honesty": "exact",
        "working": {
            "inputs": [
                {"label": "Client x scheme rows scored", "value": len(rows)},
                {
                    "label": "Median gap (investor return - fund return)",
                    "value": _f(statistics.median(gaps)) if gaps else None,
                },
                {"label": "Invested-weighted gap", "value": _f(wavg)},
            ],
            "rule": (
                "wealth.behaviour_gap: investor return (MWR) = annualized growth rate of the client's own "
                "unit-moving flows in that scheme (buys negative, sells positive, terminal = "
                "final units x latest NAV); fund return (TWR) = CAGR of the scheme's own NAV "
                "over the same first-txn -> last-NAV window (no flows, time-weighted). "
                "gap_pp = mwr - twr; gap_rs = gap_pp x avg_capital x years held, where "
                "avg_capital = invested / 2 — behaviour_gap.py's own flat-average proxy "
                "(ponytail: upgrade to a true daily-capital-weighted average if this needs more "
                "precision). Hayley (2014): part of any MWR-TWR gap is mechanical (a falling NAV "
                "after any inflow drags MWR below TWR regardless of skill) — this is a "
                "decomposition input, not a verdict on investor behaviour."
            ),
            "assumptions": [
                {
                    "text": "gap_rs uses a flat invested/2 average-capital proxy, not a true "
                    "day-weighted average of capital actually at risk over the holding window",
                    "bias": "estimate — can over- or under-state the rupee impact versus a "
                    "true daily-capital-weighted calculation",
                },
                {
                    "text": "part of any MWR-TWR gap is mechanical per Hayley (2014), not proof "
                    "of bad timing by itself",
                    "bias": "estimate — the ₹ figure is a decomposition input, not a certain "
                    "behavioural cost",
                },
            ],
            "steps": [
                {"label": "Rows with a computed gap_pp", "value": len(gaps)},
                {"label": "Sum of gap_rs", "value": _f(total_gap_rs)},
            ],
            "sample_rows": sample_rows,
            "sample_of": len(rows),
            "honesty": "exact",
        },
    }


def b3_panic_pattern(conn) -> dict:
    """The panic pattern. wealth.client_behaviour already carries each
    client's aggregated panic_out_rs/panic_loss_out_rs/div_leak_rs/SIP-stop
    counts (behaviour_fingerprints.py). The crisis-anatomy chart needs the
    actual drawdown WINDOWS to plot against — those are never hardcoded
    (constraint 15): drawdown_windows() is called live here against the same
    Nifty-50 index-fund NAV series behaviour_fingerprints.py itself uses."""
    bench = nav_series(conn, BENCH_ID)
    windows = drawdown_windows(bench)
    crisis_windows = [
        {"start": str(a.date()), "trough_or_end": str(b.date()), "still_open": b == bench.index[-1]}
        for a, b in windows
    ]
    # build-time reshape of the same `bench` series already fetched above
    # (no new query, no new math) — monthly-resampled so the crisis-anatomy
    # chart's line series stays small (~240 points over the fund's history
    # instead of ~5000 daily points).
    monthly = bench.resample("MS").last().dropna()
    bench_monthly = [
        {"x": round(t.year + (t.month - 1) / 12, 4), "y": _f(v)} for t, v in monthly.items()
    ]

    names = client_names(conn)
    cur = conn.cursor()
    cur.execute(
        """select client_id, panic_out_rs::float, panic_loss_out_rs::float, total_out_rs::float,
                  panic_share::float, div_leak_rs::float, sip_streams, sip_active, sip_stopped,
                  sip_stops_in_drawdown
           from wealth.client_behaviour"""
    )
    rows = cur.fetchall()
    total_panic_loss = sum(r[2] or 0.0 for r in rows)
    total_div_leak = sum(r[5] or 0.0 for r in rows)
    n_panic_heavy = sum(1 for r in rows if (r[4] or 0) > 0.25)
    n_sip_stops_in_dd = sum(r[9] or 0 for r in rows)

    verdict = (
        f"{len(windows)} market drawdown windows (>10% fall) identified; "
        f"{lcr_py(total_panic_loss)} sold below cost inside them, {n_panic_heavy} clients took "
        f">25% of lifetime outflows during a crash, {n_sip_stops_in_dd} SIPs stopped mid-drawdown."
    )

    sample_rows = [
        {
            "client_id": cid,
            "name": names.get(cid),
            "panic_out_rs": _f(pout),
            "panic_loss_out_rs": _f(ploss),
            "panic_share": _f(pshare),
            "div_leak_rs": _f(dleak),
            "sip_stops_in_drawdown": sdd,
        }
        for cid, pout, ploss, _tout, pshare, dleak, _ss, _sa, _sp, sdd in rows[:20]
    ]

    return {
        "crisis_windows": crisis_windows,
        "bench_monthly": bench_monthly,
        "n_windows": len(windows),
        "total_panic_loss_rs": _f(total_panic_loss),
        "total_div_leak_rs": _f(total_div_leak),
        "n_panic_heavy_clients": n_panic_heavy,
        "n_sip_stops_in_drawdown": n_sip_stops_in_dd,
        "verdict": verdict,
        "honesty": "exact",
        "working": {
            "inputs": [
                {"label": "Drawdown windows (live)", "value": len(windows)},
                {"label": "₹ sold below cost in drawdowns", "value": _f(total_panic_loss)},
                {"label": "Clients >25% of outflows in a crash", "value": n_panic_heavy},
            ],
            "rule": (
                "Drawdown windows = peak-to-trough-to-recovery stretches where the ICICI Pru "
                "Nifty 50 Index (Reg-G) NAV fell >10% from its running peak (drawdown_windows(), "
                "same function and same live NAV series behaviour_fingerprints.py uses — called "
                "here, not hardcoded). Per-client panic/dividend-leakage/SIP figures are read "
                "as-is from wealth.client_behaviour (already computed against these same "
                "windows)."
            ),
            "assumptions": [
                {
                    "text": "the most recent window may still be open (no recovery back to the "
                    "prior peak yet) — flagged per-window as still_open",
                    "bias": "exact — the window boundary is real, just not yet closed",
                }
            ],
            "steps": [
                {"label": "Clients with a behaviour row", "value": len(rows)},
                {"label": "Sum panic_loss_out_rs", "value": _f(total_panic_loss)},
            ],
            "sample_rows": sample_rows,
            "sample_of": len(rows),
            "honesty": "exact",
        },
    }


def b4_advice_switches(conn) -> dict:
    """Advice switches. Source: wealth.advice_ledger (paired switches) +
    wealth.advice_waves (push-wave detection). The switch-pairing definition
    is quoted faithfully, not paraphrased loosely."""
    names = client_names(conn)
    cur = conn.cursor()
    cur.execute(
        """select client_id, switch_date, amount::float, from_name, to_name,
                  alpha_1y_pp::float, alpha_1y_rs::float, alpha_3y_pp::float, alpha_3y_rs::float
           from wealth.advice_ledger"""
    )
    rows = cur.fetchall()
    a1 = [r[5] for r in rows if r[5] is not None]
    a1rs = [r[6] for r in rows if r[6] is not None]
    beating_1y = sum(1 for v in a1 if v > 0)

    cur.execute(
        """select scheme_name, window_start, window_end, n_clients, inflow_rs::float,
                  fwd1y_scheme::float, fwd1y_bench::float
           from wealth.advice_waves order by inflow_rs desc"""
    )
    wave_rows = cur.fetchall()
    waves = [
        {
            "scheme": name,
            "window_start": str(ws),
            "window_end": str(we),
            "n_clients": n,
            "inflow_rs": _f(inflow),
            "fwd1y_scheme_pct": _f(fs),
            "fwd1y_index_pct": _f(fb),
        }
        for name, ws, we, n, inflow, fs, fb in wave_rows[:20]
    ]

    verdict = (
        f"{len(rows)} paired advised switches; {beating_1y} of {len(a1)} added extra growth over "
        f"1y (median {statistics.median(a1):+.2f}pp, {lcr_py(sum(a1rs))} net); "
        f"{len(wave_rows)} book-wide push-waves detected."
    )

    sample_rows = [
        {
            "client_id": cid,
            "name": names.get(cid),
            "switch_date": str(sd),
            "amount_rs": _f(amt),
            "from_fund": fn,
            "to_fund": tn,
            "extra_growth_1y_pp": _f(a1v),
        }
        for cid, sd, amt, fn, tn, a1v, _a1rs, _a3, _a3rs in rows[:20]
    ]

    return {
        "n_switches": len(rows),
        "n_scored_1y": len(a1),
        "n_beating_1y": beating_1y,
        "median_extra_growth_1y_pp": _f(statistics.median(a1)) if a1 else None,
        "net_extra_growth_1y_rs": _f(sum(a1rs)) if a1rs else None,
        "waves": waves,
        "n_waves": len(wave_rows),
        "verdict": verdict,
        "honesty": "estimate",
        "working": {
            "inputs": [
                {"label": "Paired advised switches", "value": len(rows)},
                {"label": "Beating the source fund over 1y", "value": beating_1y},
                {"label": "Push-waves detected", "value": len(wave_rows)},
            ],
            "rule": (
                "A switch event = a client's switch_out of scheme A paired with a switch_in to "
                "scheme B within ±5 calendar days for a comparable amount (±5% or ±₹500) "
                "(advice_ledger.py, quoted verbatim). Each pair is judged by comparing what the "
                "money did vs what would have happened if left: forward 1y/3y returns of A vs B "
                "from the switch date; extra growth = retB - retA (annualised), rupee impact = "
                "switch amount x that spread. A push-wave = >=5 distinct clients entering the "
                "same scheme (switch_in or purchase >= ₹25,000) inside a rolling 30-day window, "
                "scored on the wave's own median entry date vs the Nifty index fund."
            ),
            "assumptions": [
                {
                    "text": "'extra growth' rests on a "
                    "benchmark-comparison assumption — it compares the destination fund's own "
                    "forward return against the source fund's forward return, both real NAV "
                    "series, but is not a claim about what else the client could have done with "
                    "the money",
                    "bias": "estimate — a real historical replay of the two named funds, but "
                    "the comparison set (fund A vs fund B) is a modelling choice, not the only "
                    "possible one",
                }
            ],
            "steps": [
                {"label": "Switches with a scored 1y outcome", "value": len(a1)},
                {"label": "Net 1y rupee impact", "value": _f(sum(a1rs)) if a1rs else None},
            ],
            "sample_rows": sample_rows,
            "sample_of": len(rows),
            "honesty": "estimate",
        },
    }


def b5_what_if_machine(conn) -> dict:
    """The what-if machine. Source: wealth.counterfactuals (four historical
    replay scenarios, already computed — no recompute here, just a book-level
    sum). Honesty tags follow the brief's explicit assignment, not the
    engine docstring's simpler "upper bound for panic/SIP only" framing:
    cf_no_panic_rs = upper bound (idle-cash assumption, a real ceiling);
    cf_index_rs and cf_sip_alive_rs = estimate (each assumes the client would
    have kept the SAME cash-flow/contribution behaviour under a counterfactual
    fund choice — itself an assumption, not just a NAV replay); cf_no_switch_rs
    carries the same "unchanged behaviour" assumption, tagged estimate for
    consistency. Each what-if's assumption card must render ABOVE its
    headline number, not below — a page-layout requirement for Task 5/6, not
    something this data layer can enforce, so it's called out here too."""
    names = client_names(conn)
    cur = conn.cursor()
    cur.execute(
        """select client_id, cf_index_rs::float, cf_no_panic_rs::float, panic_sells,
                  cf_sip_alive_rs::float, sip_cash::float, sip_streams,
                  cf_no_switch_rs::float, switches
           from wealth.counterfactuals"""
    )
    rows = cur.fetchall()
    n = len(rows)
    index_total_raw = sum(r[1] or 0.0 for r in rows)
    index_total = _f(index_total_raw)
    scenarios = {
        "cf_index_rs": {
            "label": "If every rupee had gone into the index fund instead",
            "total_rs": index_total,
            "n_clients_positive": sum(1 for r in rows if (r[1] or 0) > 0),
            "honesty": "estimate",
            "assumption": "a historical replay of the same external flows into the Nifty-50 "
            "index fund at the same dates — assumes the client would have made the exact same "
            "deposits/withdrawals on the exact same dates regardless of which fund held the "
            "money, which is itself an assumption, not a certainty.",
        },
        "cf_no_panic_rs": {
            "label": "If drawdown-window sells had been held instead",
            "total_rs": _f(sum(r[2] or 0.0 for r in rows)),
            "n_panic_sells": sum(r[3] or 0 for r in rows),
            "honesty": "upper bound",
            "assumption": "we assume panic-sold units are simply held today; proceeds are NOT "
            "reinvested elsewhere — a real ceiling on the foregone gain, not the actual missed "
            "return.",
        },
        "cf_sip_alive_rs": {
            "label": "If stopped SIPs had kept running to today",
            "total_rs": _f(sum(r[4] or 0.0 for r in rows)),
            "sip_cash_rs": _f(sum(r[5] or 0.0 for r in rows)),
            "honesty": "estimate",
            "assumption": "continues the SIP at its own last-6-month median amount into the "
            "same scheme all the way to today — not a guarantee the client would have kept "
            "paying that long.",
        },
        "cf_no_switch_rs": {
            "label": "If every advised switch had stayed in the source fund",
            "total_rs": _f(sum(r[6] or 0.0 for r in rows)),
            "n_switches": sum(r[7] or 0 for r in rows),
            "honesty": "estimate",
            "assumption": "a historical replay of the source fund's own NAV vs the destination "
            "fund's, from the switch date to today — assumes the client would have made no "
            "other move with that money if the switch hadn't happened.",
        },
    }

    beat_note = (
        f"the book as a whole BEAT indexing by {lcr_py(abs(index_total_raw))} (negative = "
        "actual outcome beat the index-everything what-if scenario) — a genuinely good-news "
        "honest result, not buried."
        if index_total_raw < 0
        else f"indexing would have added {lcr_py(index_total_raw)} over what actually happened."
    )
    verdict = (
        f"across {n} clients: {beat_note} no-panic-sells (upper bound) "
        f"{lcr_py(scenarios['cf_no_panic_rs']['total_rs'])}, SIPs-alive (estimate) "
        f"{lcr_py(scenarios['cf_sip_alive_rs']['total_rs'])}, no-switches (estimate) "
        f"{lcr_py(scenarios['cf_no_switch_rs']['total_rs'])}."
    )

    sample_rows = [
        {
            "client_id": cid,
            "name": names.get(cid),
            "cf_index_rs": _f(ci),
            "cf_no_panic_rs": _f(cp),
            "cf_sip_alive_rs": _f(cs),
            "cf_no_switch_rs": _f(cw),
        }
        for cid, ci, cp, _ps, cs, _sc, _ss, cw, _sw in rows[:20]
    ]

    return {
        "n_clients": n,
        "scenarios": scenarios,
        "verdict": verdict,
        "honesty": "estimate",
        "working": {
            "inputs": [
                {"label": "Clients with what-if scenarios", "value": n},
                {"label": "Book cf_index_rs (estimate)", "value": index_total},
                {
                    "label": "Book cf_no_panic_rs (upper bound)",
                    "value": scenarios["cf_no_panic_rs"]["total_rs"],
                },
            ],
            "rule": (
                "the what-if-scenario table stores four historical-replay scenarios per client, "
                "computed once (not recomputed here): index-everything (bench terminal value minus actual "
                "terminal value, from the same exact-replay used in B1); no-panic-sells (value "
                "today of drawdown-window-sold units minus cash received, cash assumed idle); "
                "SIPs-alive (stopped SIP streams continued at their own last-6-month median "
                "amount to the ledger's end, value today minus contributions); no-switches "
                "(paired-switch amount x (source-fund return - destination-fund return) to "
                "today). This function only sums the already-computed per-client columns to "
                "book level — no new math."
            ),
            "assumptions": [
                {
                    "text": "cf_no_panic_rs assumes idle cash (no reinvestment) — a real ceiling "
                    "on the foregone gain, not what the client would actually have done",
                    "bias": "upper bound — real foregone gain would be <= this figure",
                },
                {
                    "text": "cf_index_rs, cf_sip_alive_rs, and cf_no_switch_rs all replay real "
                    "NAV series but each assumes the client's own cash-flow behaviour (deposit "
                    "dates/amounts, SIP continuation, no other move) would have stayed identical "
                    "under the what-if scenario — a modelling assumption, not a certainty",
                    "bias": "estimate — the direction is evidence-based but the magnitude "
                    "depends on an unchanged-behaviour assumption",
                },
            ],
            "steps": [{"label": "Clients summed", "value": n}],
            "sample_rows": sample_rows,
            "sample_of": n,
            "honesty": "estimate",
        },
    }


def annotate_client_index(conn, client_index: dict) -> dict:
    """Second-pass enrichment of Task 1's client_index rows with the
    chronic-laggard and fees-above-median flags deferred until Q4/Q5 landed
    (per data_holdings_overlap.client_index_rows' own docstring note).
    Chronic laggard = client holds >=1 fund whose beat_count < windows/2
    (same cutoff as Q5/weak_funds()). Fees-above-median = client's own
    fee_save_yr_rs exceeds the book median among clients with fee_save_yr_rs
    > 0 (flags the WORSE half of paying clients, not an absolute cutoff)."""
    cur = conn.cursor()
    cur.execute(
        """select distinct h.client_id
           from wealth.holdings h
           join wealth.fund_performance fp using (scheme_id)
           where h.market_value > 0 and fp.beat_count is not null and fp.windows > 0
             and fp.beat_count < fp.windows / 2.0"""
    )
    laggard_clients = {r[0] for r in cur.fetchall()}

    cur.execute("select client_id, fee_save_yr_rs::float from wealth.value_statements")
    fee_by_client = dict(cur.fetchall())
    paying = [v for v in fee_by_client.values() if v and v > 0]
    fee_median = statistics.median(paying) if paying else None

    for row in client_index["rows"]:
        cid = row["client_id"]
        row["chronic_laggard_flag"] = cid in laggard_clients
        fee = fee_by_client.get(cid) or 0.0
        row["fees_above_median_flag"] = bool(fee_median is not None and fee > fee_median)
        row["fee_save_yr_rs"] = _f(fee)
    return client_index


def annotate_behaviour_flags(conn, client_index: dict) -> dict:
    """Third-pass client_index enrichment: Behaviour page's own flags.
    panic_seller_flag reuses b3_panic_pattern's own >25% panic_share cutoff
    verbatim (agrees with its "n_panic_heavy_clients" headline). dead_sip_flag
    = sip_streams > 0 but sip_active == 0 today. chronic_switcher_flag = a
    client's wealth.advice_ledger switch count above the BOOK's own 90th
    percentile (counts range 1-1201, median ~78.5 — a single absolute cutoff
    would be arbitrary; a book-relative percentile flags the top decile)."""
    cur = conn.cursor()
    cur.execute("select client_id from wealth.client_behaviour where panic_share > 0.25")
    panic_clients = {r[0] for r in cur.fetchall()}

    cur.execute(
        "select client_id from wealth.client_behaviour where sip_streams > 0 and sip_active = 0"
    )
    dead_sip_clients = {r[0] for r in cur.fetchall()}

    cur.execute("select client_id, count(*) from wealth.advice_ledger group by client_id")
    switch_counts = cur.fetchall()
    counts = [c for _cid, c in switch_counts]
    p90 = statistics.quantiles(counts, n=10)[8] if len(counts) >= 2 else None
    chronic_clients = {cid for cid, c in switch_counts if p90 is not None and c > p90}

    for row in client_index["rows"]:
        cid = row["client_id"]
        row["panic_seller_flag"] = cid in panic_clients
        row["dead_sip_flag"] = cid in dead_sip_clients
        row["chronic_switcher_flag"] = cid in chronic_clients
    return client_index
