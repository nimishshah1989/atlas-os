# allow-large: plan-mandated single-file app template (HTML/CSS/JS inline string)
"""Build the Jhaveri capability app — ONE self-contained, CSP-safe HTML file.

Reads the live wealth.* tables at build time and embeds EVERYTHING as a single
<script id="data" type="application/json"> block. The app is hash-routed vanilla
JS with inline CSS; zero external requests (no CDN, no fonts fetch, no images —
inline SVG only). Rule #0: every number on screen is computed here from the DB,
nothing invented.

Routes: #book (6 scroll-snap chapters) · #calls (three PREDICT lists) ·
#client/<id> (the 8-section Audit Pack).

Output: /home/ubuntu/jhaveri_data/reports/jhaveri-capability-app.html (~2-4 MB).
Not committed — lives outside the repo. Gate it with validate_wealth_app.py.

Usage: set -a; source .env; set +a; .venv/bin/python scripts/wealth/build_capability_app.py
"""
from __future__ import annotations

import json
import math
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

from build_audit_packs import SECTION_NAMES
from build_segments import SEGMENTS
from engine_common import connect

# segment-based proxy for the armed pool; not a 1:1 map of build_call_lists'
# candidate rows (that engine pools from client_behaviour/sip_streams/client_churn_risk).
ARMED_SEGMENTS = tuple(s for s in SEGMENTS if s not in ("Too New to Tell", "Steady Compounders"))

_XIRR_RE = re.compile(r"(?i)\bXIRR\b")

OUT = Path("/home/ubuntu/jhaveri_data/reports/jhaveri-capability-app.html")


def _f(x):
    """-> float rounded, or None (never NaN/Inf — strict-JSON safe)."""
    if x is None:
        return None
    v = float(x)
    if not math.isfinite(v):
        return None
    return round(v, 4)


def lcr_py(n: float) -> str:
    """₹ in L/cr, en-IN style (mirror of the JS lcr for build-time story text)."""
    a = abs(n)
    if a >= 1e7:
        return f"₹{n/1e7:.2f} cr"
    if a >= 1e5:
        return f"₹{n/1e5:.2f} L"
    return f"₹{round(n):,}"


# ----------------------------------------------------------------- fetch --

def _degarble(s):
    """Same XIRR->plain-language swap build_audit_packs applies to flags/
    evidence text — client_flags.evidence and client_scorecard.attention_reasons
    contain literal 'XIRR' that would trip the banned-word gate otherwise."""
    return None if s is None else _XIRR_RE.sub("yearly growth", s)


def _hist(values, n_bins=10):
    """Equal-width histogram over the REAL observed min/max + median. Honest
    binning: no fabricated category thresholds, stdlib only."""
    vals = sorted(float(v) for v in values if v is not None and math.isfinite(float(v)))
    if not vals:
        return {"edges": [], "counts": [], "median": None, "n": 0}
    lo, hi = vals[0], vals[-1]
    if lo == hi:
        return {"edges": [lo, hi], "counts": [len(vals)], "median": lo, "n": len(vals)}
    width = (hi - lo) / n_bins
    counts = [0] * n_bins
    for v in vals:
        counts[min(int((v - lo) / width), n_bins - 1)] += 1
    edges = [round(lo + i * width, 2) for i in range(n_bins + 1)]
    return {"edges": edges, "counts": counts, "median": round(statistics.median(vals), 2), "n": len(vals)}


def _widen_clients(conn, clients: dict) -> None:
    """Mutate `clients` in place: add the v2 per-client keys (holdings,
    scorecard, flags, churn, stock_exposure, segment, curve, fund_performance,
    cut_list). A client missing a source row gets None/[] — never a fabricated
    stand-in (Rule #0)."""

    def q(sql, params=None):
        return pd.read_sql(sql, conn, params=params)

    # A client can have >1 wealth.client_reports snapshot (e.g. client 198 has 2) —
    # restrict to each client's LATEST snapshot so holdings aren't double-counted.
    hold = q("""
        select h.client_id, s.scheme_id, s.display_name as fund, s.asset_class,
               h.market_value, flc.verdict, fr.composite
        from wealth.holdings h
        join (select distinct on (client_id) report_id from wealth.client_reports
              order by client_id, as_on_date desc) latest on latest.report_id = h.report_id
        join wealth.schemes s using (scheme_id)
        left join wealth.fund_label_check flc on flc.scheme_id = h.scheme_id
        left join atlas_foundation.fund_rank_daily fr
               on fr.mstar_id = s.mstar_id
              and fr.date = (select max(date) from atlas_foundation.fund_rank_daily)
    """)
    hold_by: dict[int, list] = defaultdict(list)
    for r in hold.itertuples():
        hold_by[r.client_id].append({
            "scheme_id": int(r.scheme_id), "fund": r.fund, "asset_class": r.asset_class,
            "mv": _f(r.market_value), "verdict": r.verdict, "quality": _f(r.composite),
        })

    fp = q("""select scheme_id, roll_3y_pct, roll_5y_pct, dn_capture_pct,
                     best_year_stripped_pct, full_period_pct, beat_count, windows,
                     benchmark_note, verdict from wealth.fund_performance""")
    fp_by = {int(r.scheme_id): r for r in fp.itertuples()}

    def fp_row(h):
        r = fp_by.get(h["scheme_id"])
        if r is None:
            return None
        return {
            "scheme_id": h["scheme_id"], "fund": h["fund"],
            "roll_3y_pct": _f(r.roll_3y_pct), "roll_5y_pct": _f(r.roll_5y_pct),
            "dn_capture_pct": _f(r.dn_capture_pct), "best_year_stripped_pct": _f(r.best_year_stripped_pct),
            "full_period_pct": _f(r.full_period_pct),
            "beat_count": None if pd.isna(r.beat_count) else int(r.beat_count),
            "windows": None if pd.isna(r.windows) else int(r.windows),
            "benchmark_note": r.benchmark_note, "verdict": r.verdict,
        }

    # ponytail: client_scorecard fans out to 2 rows for the one client with a
    # duplicate wealth.client_reports snapshot (build_scorecard.py joins the
    # raw table, no dedup) — pick the latest (highest mv_total) deterministically
    # instead of letting a dict comprehension silently pick an arbitrary one.
    sc = q("""select distinct on (client_id) client_id, outcome_grade, needs_attention,
                     attention_reasons, laggard_pct, wcomp, mv_total, equity_pct,
                     top10_stock_pct, financials_pct, dup_cats, side_pockets, dust_lines, n_lines
              from wealth.client_scorecard order by client_id, mv_total desc nulls last""")
    sc_by = {int(r.client_id): r for r in sc.itertuples()}

    fl = q("""select client_id, rule, evidence, action, est_value, basis
              from wealth.client_flags order by client_id, est_value desc nulls last""")
    fl_by: dict[int, list] = defaultdict(list)
    for r in fl.itertuples():
        fl_by[r.client_id].append({
            "rule": _degarble(r.rule), "evidence": _degarble(r.evidence),
            "action": _degarble(r.action), "est_value": _f(r.est_value), "basis": r.basis,
        })

    ch = q("""select client_id, mv, months_since_inflow, sip_stop_share, out12_share,
                     disengagement_score, clv_aum_l_years, computed_asof
              from wealth.client_churn_risk""")
    ch_by = {int(r.client_id): r for r in ch.itertuples()}

    se = q("""
        select client_id, holding_name, isin, exposure, bucket from (
          select client_id, holding_name, isin, exposure, bucket,
                 row_number() over (partition by client_id order by exposure desc) rn
          from wealth.client_stock_exposure) t
        where rn <= 10
    """)
    se_by: dict[int, list] = defaultdict(list)
    for r in se.itertuples():
        se_by[r.client_id].append({
            "name": r.holding_name, "isin": r.isin, "exposure": _f(r.exposure), "bucket": r.bucket,
        })

    sg = q("select client_id, segment, reason, whatif_rs, traits from wealth.client_segments")
    sg_by = {int(r.client_id): r for r in sg.itertuples()}

    # curve + events: compact PARALLEL-ARRAY encoding (byte-gate lever 1) —
    # array-of-dicts would repeat every JSON key name once per row/event.
    # byte-gate lever 2: net_flow_rs dropped from the embed (still <6MB target
    # needed it) — coverage_pct + events carry the story, net_flow_rs stays a
    # DB-only field for now.
    cv = q("select client_id, month, value_rs, coverage_pct "
           "from wealth.client_curves order by client_id, month")
    curve_by: dict[int, dict] = {}
    for cid, g in cv.groupby("client_id"):
        curve_by[int(cid)] = {
            "months": [d.strftime("%Y-%m") for d in g.month],
            "values": [int(v) for v in g.value_rs],
            "coverage_pct": _f(g.coverage_pct.iloc[0]),
        }
    # byte-gate lever 3: the free-text `note` (avg ~50 chars x 24270 events =
    # 1.28MB, the single largest field measured) is dropped from the embed —
    # kind + amount + date already carry every story marker the client-360
    # curve needs (panic dot / SIP-stop marker / big-flow tick); the sentence
    # is reconstructable client-side from `kind`, no DB prose required.
    ev = q("select client_id, event_date, kind, amount_rs "
           "from wealth.client_curve_events order by client_id, event_date")
    for cid, g in ev.groupby("client_id"):
        if int(cid) in curve_by:
            curve_by[int(cid)]["events"] = {
                "dates": [d.isoformat() for d in g.event_date],
                "kinds": list(g.kind),
                "amounts": [int(v) for v in g.amount_rs],
            }

    cl = q("select client_id, keep, cut, min_fund_count, note from wealth.cut_list")
    cl_by = {int(r.client_id): r for r in cl.itertuples()}

    for cid_str, c in clients.items():
        cid = int(cid_str)
        c["holdings"] = hold_by.get(cid, [])
        c["fund_performance"] = [fp_row(h) for h in c["holdings"] if fp_row(h) is not None]
        r = sc_by.get(cid)
        c["scorecard"] = None if r is None else {
            "grade": r.outcome_grade, "needs_attention": bool(r.needs_attention),
            "reasons": _degarble(r.attention_reasons), "laggard_pct": _f(r.laggard_pct),
            "wcomp": _f(r.wcomp), "mv_total": _f(r.mv_total), "equity_pct": _f(r.equity_pct),
            "top10_stock_pct": _f(r.top10_stock_pct), "financials_pct": _f(r.financials_pct),
            "dup_cats": None if pd.isna(r.dup_cats) else int(r.dup_cats),
            "side_pockets": None if pd.isna(r.side_pockets) else int(r.side_pockets),
            "dust_lines": None if pd.isna(r.dust_lines) else int(r.dust_lines),
            "n_lines": None if pd.isna(r.n_lines) else int(r.n_lines),
        }
        c["flags"] = fl_by.get(cid, [])
        r = ch_by.get(cid)
        c["churn"] = None if r is None else {
            "mv": _f(r.mv), "months_since_inflow": _f(r.months_since_inflow),
            "sip_stop_share": _f(r.sip_stop_share), "out12_share": _f(r.out12_share),
            "score": _f(r.disengagement_score), "clv_l_years": _f(r.clv_aum_l_years),
            "asof": r.computed_asof.isoformat(),
        }
        c["stock_exposure"] = se_by.get(cid, [])
        r = sg_by.get(cid)
        c["segment"] = None if r is None else {
            "segment": r.segment, "reason": r.reason, "whatif_rs": _f(r.whatif_rs), "traits": r.traits,
        }
        c["curve"] = curve_by.get(cid)
        r = cl_by.get(cid)
        c["cut_list"] = None if r is None else {
            "keep": r.keep, "cut": r.cut,
            "min_fund_count": None if pd.isna(r.min_fund_count) else int(r.min_fund_count),
            "note": r.note,
        }


def _build_cohort(conn, book: dict) -> dict:
    """Management-dashboard binning, done in Python at build time (spec §3):
    headline / segment bar / 6 histograms / behaviour-cost waterfall /
    churn x book scatter / call-list funnel. Every number sourced straight
    from the same tables the v1 chapters use — bin honestly, no fabrication."""

    def q(sql, params=None):
        return pd.read_sql(sql, conn, params=params)

    # ---- headline: realized value delivered + coaching opportunity (exact
    # mirror of build_audit_packs.sec_value's per-client definition, summed) ----
    vs = q("""select sum(sip_discipline_rs + staying_power_rs + advice_outcome_rs
                          + fee_save_yr_rs + tax_headroom_rs) realized,
                     sum(coaching_opportunity_rs) coaching
              from wealth.value_statements""").iloc[0]
    headline = {
        "book_cr": book["mv_cr"], "clients": book["clients"], "families": book["families"],
        "realized_cr": _f(float(vs.realized) / 1e7) if vs.realized is not None else None,
        "coaching_cr": _f(float(vs.coaching) / 1e7) if vs.coaching is not None else None,
    }

    # ---- segment bar: counts sum to book['clients'], ₹ what-if per segment ----
    seg = q("select segment, count(*) n, sum(whatif_rs) whatif from wealth.client_segments group by 1")
    seg_by = {r.segment: r for r in seg.itertuples()}
    segment_bar = [
        {"segment": s, "count": int(seg_by[s].n) if s in seg_by else 0,
         "whatif_cr": _f(float(seg_by[s].whatif or 0) / 1e7) if s in seg_by else 0.0}
        for s in SEGMENTS
    ]

    # ---- 6 histograms (book size / tenure / growth-gap / freak-out / effective
    # bets / SIP health), driven from client_scorecard (dedup'd, see _widen_clients) ----
    hdf = q("""
        with sc as (
          select distinct on (client_id) client_id, mv_total
          from wealth.client_scorecard order by client_id, mv_total desc nulls last)
        select sc.client_id, sc.mv_total,
               cb.alpha as growth_gap_pp, be.panic_share, ov.eff_bets,
               be.sip_active, be.sip_streams, t.inv_since, r.as_on_date
        from sc
        left join wealth.client_benchmark cb on cb.client_id = sc.client_id
        left join wealth.client_behaviour be on be.client_id = sc.client_id
        left join wealth.client_overlap ov on ov.client_id = sc.client_id
        left join (select client_id, min(inv_since) inv_since from wealth.holdings group by 1) t
               on t.client_id = sc.client_id
        left join (select distinct on (client_id) client_id, as_on_date from wealth.client_reports
                   order by client_id, as_on_date desc) r on r.client_id = sc.client_id
    """)
    book_l, tenure_y, growth_gap, freak_out, eff_bets, sip_health = [], [], [], [], [], []
    for row in hdf.itertuples():
        if row.mv_total is not None:
            book_l.append(float(row.mv_total) / 1e5)
        if row.inv_since is not None and row.as_on_date is not None:
            tenure_y.append((row.as_on_date - row.inv_since).days / 365.25)
        if row.growth_gap_pp is not None:
            growth_gap.append(float(row.growth_gap_pp))
        if row.panic_share is not None:
            freak_out.append(float(row.panic_share) * 100)
        if row.eff_bets is not None:
            eff_bets.append(float(row.eff_bets))
        if row.sip_streams and row.sip_active is not None:
            sip_health.append(100.0 * float(row.sip_active) / float(row.sip_streams))

    histograms = {
        "book_size_l": _hist(book_l),
        "tenure_years": _hist(tenure_y),
        "growth_gap_pp": _hist(growth_gap),
        "freak_out_pct": _hist(freak_out),
        "effective_bets": _hist(eff_bets),
        "sip_health_pct": _hist(sip_health),
    }

    # ---- behaviour-cost waterfall: panic + dividend leak + dead SIPs -> total
    # (same >=0-only convention as build_segments.whatif_rs) ----
    beh = q("select sum(greatest(panic_loss_out_rs,0)) panic, "
            "sum(greatest(div_leak_rs,0)) div_leak from wealth.client_behaviour").iloc[0]
    sipv = q("select sum(greatest(cf_sip_alive_rs,0)) sip from wealth.counterfactuals").iloc[0]
    panic_cr = float(beh.panic or 0) / 1e7
    div_cr = float(beh.div_leak or 0) / 1e7
    sip_cr = float(sipv.sip or 0) / 1e7
    waterfall = [
        {"label": "Panic selling", "value_cr": _f(panic_cr)},
        {"label": "Dividend payouts taken as cash", "value_cr": _f(div_cr)},
        {"label": "SIPs stopped", "value_cr": _f(sip_cr)},
        {"label": "Total behaviour cost", "value_cr": _f(panic_cr + div_cr + sip_cr)},
    ]

    # ---- churn x book scatter (top-right = valuable AND at risk) ----
    cr = q("select client_id, disengagement_score, mv from wealth.client_churn_risk")
    seg_of = {int(r.client_id): r.segment for r in
              q("select client_id, segment from wealth.client_segments").itertuples()}
    # medians must be computed over the SAME both-non-null population as `points`,
    # not two independently-dropna'd full columns, else the quadrant split is off.
    both = [r for r in cr.itertuples() if r.disengagement_score is not None and r.mv is not None]
    scores = [float(r.disengagement_score) for r in both]
    mvs = [float(r.mv) for r in both]
    points = [
        {"client_id": int(r.client_id), "churn_score": _f(r.disengagement_score),
         "book_cr": _f(float(r.mv) / 1e7), "segment": seg_of.get(int(r.client_id))}
        for r in both
    ]
    scatter = {
        "points": points,
        "churn_threshold": _f(statistics.median(scores)) if scores else None,
        "book_threshold_cr": _f(statistics.median(mvs) / 1e7) if mvs else None,
    }

    # ---- call-list funnel: segments -> armed -> on a list -> tonight's 20 ----
    armed_n = int(q("select count(*) n from wealth.client_segments where segment = any(%(segs)s)",
                     params={"segs": list(ARMED_SEGMENTS)}).n.iloc[0])
    on_list_n = int(q("select count(distinct client_id) n from wealth.call_lists").n.iloc[0])
    tonight_n = len(q("select client_id, max(score) mx from wealth.call_lists "
                       "group by 1 order by mx desc nulls last limit 20"))
    funnel = [
        {"stage": "All clients", "n": book["clients"]},
        {"stage": "In an armed segment", "n": armed_n},
        {"stage": "On a call list", "n": on_list_n},
        {"stage": "Tonight's call sheet", "n": tonight_n},
    ]

    return {
        "headline": headline, "segment_bar": segment_bar, "histograms": histograms,
        "waterfall": waterfall, "scatter": scatter, "funnel": funnel,
    }


def fetch(conn) -> dict:
    def q(sql):
        return pd.read_sql(sql, conn)

    asof = q("select max(as_on_date) d from wealth.client_reports").d.iloc[0]
    asof = asof.isoformat()

    book_row = q("""
        select (select count(distinct household_name) from wealth.households) families,
               (select count(*) from wealth.clients) clients,
               (select extract(year from min(txn_date))::int from wealth.transactions) since
    """).iloc[0]
    mv_cr = _f(q("""select round(sum(mv_total)/1e7,1) v from (
        select distinct on (client_id) mv_total from wealth.client_reports
        order by client_id, as_on_date desc) t""").v.iloc[0])
    book = {"families": int(book_row.families), "clients": int(book_row.clients),
            "mv_cr": mv_cr, "since": int(book_row.since)}

    # ch2 — typical yearly growth + a ₹10L growth strip
    growth = _f(q("""select percentile_cont(0.5) within group (order by xirr_client) m
                     from wealth.client_benchmark where xirr_client is not null""").m.iloc[0])
    r = (growth or 0) / 100.0
    strip = [{"year": y, "value": round(1_000_000 * (1 + r) ** y)} for y in range(0, 11)]

    # ch3 — share of clients ahead of the index fund (never say "alpha")
    pct_ahead = int(round(_f(q("""select 100.0*sum(case when alpha>0 then 1 else 0 end)/count(*) p
        from wealth.client_benchmark where alpha is not null""").p.iloc[0])))

    # ch4 — what habits cost / protected, each card opens a real call list
    stay = _f(q("select round(sum(staying_power_rs)/1e7,1) v from wealth.value_statements").v.iloc[0])
    sip_cost = _f(q("select round(sum(cf_sip_alive_rs)/1e7,1) v from wealth.counterfactuals").v.iloc[0])
    div_cost = _f(q("select round(sum(div_leak_rs)/1e7,1) v from wealth.client_behaviour").v.iloc[0])

    def top_call(list_type):
        rows = q(f"""select client_id, reason from wealth.call_lists
                     where list_type='{list_type}' order by rank limit 1""")
        if rows.empty:
            return None, None
        return int(rows.client_id.iloc[0]), rows.reason.iloc[0]

    # cards 1 & 2 open their matching call list; card 3 (dividends) has no call
    # list, so it opens a real high-dividend-leakage client's own page — headline,
    # number, story and click-through all agree.
    ch4 = []
    for key, title, amt, verb in [
        ("crash_sellers", "Held through the crashes", stay,
         "protected by clients who stayed invested through every major fall"),
        ("sip_fragile", "Stopped SIPs", sip_cost,
         "the running total left behind when steady monthly investing was switched off"),
    ]:
        cid, reason = top_call(key)
        ch4.append({"href": f"calls:{key}", "title": title, "amount_cr": amt,
                    "subtitle": verb, "story": reason, "sample_ids": [cid] if cid else []})

    dl = q("""select b.client_id, b.div_leak_rs, c.full_name
              from wealth.client_behaviour b join wealth.clients c on c.client_id = b.client_id
              where b.div_leak_rs > 0 order by b.div_leak_rs desc limit 1""")
    dl_id = int(dl.client_id.iloc[0]) if not dl.empty else None
    dl_story = (f"One client alone has taken about {lcr_py(float(dl.div_leak_rs.iloc[0]))} of "
                f"dividends as cash instead of letting it compound — open their page to see it."
                if not dl.empty else None)
    ch4.append({"href": f"client:{dl_id}" if dl_id else "calls:disengaged",
                "title": "Dividends taken as cash", "amount_cr": div_cost,
                "subtitle": "paid out and spent instead of being reinvested to compound",
                "story": dl_story, "sample_ids": [dl_id] if dl_id else []})

    # ch5 — our advice, marked honestly
    ledg = q("""select count(*) n, sum(case when alpha_1y_pp>0 then 1 else 0 end) ahead
                from wealth.advice_ledger where alpha_1y_pp is not null""").iloc[0]
    waves = q("select count(*) n, sum(n_clients) fam, round(sum(inflow_rs)/1e7,1) cr from wealth.advice_waves").iloc[0]
    wave_list = q("""select scheme_name, window_start, window_end, n_clients,
                            fwd1y_scheme, fwd1y_bench from wealth.advice_waves
                     where fwd1y_scheme is not null order by inflow_rs desc limit 12""")
    ch5 = {
        "switch_ahead": int(ledg.ahead), "switch_total": int(ledg.n),
        "waves": int(waves.n), "families_nudged": int(waves.fam),
        "wave_rows": [
            {"fund": w.scheme_name, "from": str(w.window_start), "to": str(w.window_end),
             "n": int(w.n_clients), "scheme": _f(w.fwd1y_scheme), "bench": _f(w.fwd1y_bench)}
            for w in wave_list.itertuples()],
    }

    chapters = {
        "ch2": {"growth_pct": growth, "strip": strip},
        "ch3": {"pct_ahead": pct_ahead, "dots_filled": max(0, min(10, round(pct_ahead / 10)))},
        "ch4": ch4,
        "ch5": ch5,
    }

    # ---- call lists (name + book MV per row) ----
    calls_df = q("""
        select cl.client_id, cl.list_type, cl.rank, cl.reason, cl.script,
               c.full_name, r.mv_total
        from wealth.call_lists cl
        join wealth.clients c on c.client_id = cl.client_id
        left join lateral (select mv_total from wealth.client_reports cr
                           where cr.client_id = cl.client_id
                           order by as_on_date desc limit 1) r on true
        order by cl.list_type, cl.rank""")
    call_lists = {}
    for lt, g in calls_df.groupby("list_type"):
        call_lists[lt] = [
            {"id": str(row.client_id), "name": row.full_name, "book_rs": _f(row.mv_total),
             "reason": row.reason, "script": row.script}
            for row in g.itertuples()]

    # ---- per-client packs + prose + chips ----
    names = q("select client_id, full_name from wealth.clients")
    name_by = dict(zip(names.client_id, names.full_name))
    hh = q("select client_id, household_name, members, household_mv, succession_flag from wealth.households")
    hh_by = {r.client_id: {"name": r.household_name, "members": int(r.members),
                            "mv": _f(r.household_mv), "succession": r.succession_flag}
             for r in hh.itertuples()}
    beh = q("""select client_id, panic_share, sip_streams, sip_active, div_leak_rs,
                      chase_hot_share from wealth.client_behaviour""")
    beh_by = {r.client_id: r for r in beh.itertuples()}
    packs = q("select client_id, payload, prose from wealth.audit_packs")

    def chips(cid):
        b = beh_by.get(cid)
        if b is None:
            return ["Not enough history yet"]
        out = []
        ps = float(b.panic_share or 0)
        out.append("Sells in market falls" if ps >= 0.25
                   else "Sometimes sells in falls" if ps > 0 else "Holds through falls")
        streams, active = int(b.sip_streams or 0), int(b.sip_active or 0)
        out.append("No active SIPs" if streams == 0
                   else "Keeps every SIP running" if active >= streams
                   else "Some SIPs stopped" if active > 0 else "All SIPs stopped")
        out.append("Takes dividends as cash" if float(b.div_leak_rs or 0) > 0
                   else "Reinvests dividends")
        return out

    clients = {}
    for row in packs.itertuples():
        cid = row.client_id
        pack = row.payload
        # value.summary is engine-provenance text (never rendered) — don't embed it
        if isinstance(pack.get("value"), dict):
            pack["value"].pop("summary", None)
        clients[str(cid)] = {
            "name": name_by.get(cid),
            "household": hh_by.get(cid),
            "chips": chips(cid),
            "pack": pack,             # already strict-JSON clean (build_audit_packs)
            "prose": row.prose or {},  # NULL for most; JS falls back to a template line
        }

    _widen_clients(conn, clients)
    cohort = _build_cohort(conn, book)

    return {"asof": asof, "book": book, "chapters": chapters,
            "sections": SECTION_NAMES, "call_lists": call_lists, "clients": clients,
            "cohort": cohort}


# --------------------------------------------------------------- render --

def render(data: dict) -> str:
    blob = json.dumps(data, allow_nan=False, ensure_ascii=False, separators=(",", ":"))
    blob = blob.replace("</", "<\\/")  # never break out of the <script> block
    return HTML.replace("__DATA__", blob)


def main() -> int:
    conn = connect()
    data = fetch(conn)
    conn.close()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    html = render(data)
    OUT.write_text(html, encoding="utf-8")
    size = len(html.encode("utf-8"))
    print(f"wrote {OUT} ({size/1e6:.2f} MB, {len(data['clients'])} clients, "
          f"{sum(len(v) for v in data['call_lists'].values())} call rows)")
    return 0


# ------------------------------------------------------------- template --
# One string: inline CSS (design tokens verbatim from the locked plan) + the
# JSON data block + vanilla-JS hash router. No external requests anywhere.
HTML = r"""<style>
:root{
  --paper:#FAF7F1; --card:#FFFFFF; --ink:#232019; --muted:#6B6357; --line:#E7E0D4;
  --accent:#0E5A6D; --good:#256C3C; --warn:#9A6A0A; --crit:#A63A32; --soft:#0E5A6D12;
  --serif:Georgia,'Times New Roman',serif;
  --sans:-apple-system,'Segoe UI',Roboto,sans-serif;
}
:root[data-theme=dark]{
  --paper:#14120E; --card:#1C1915; --ink:#EDE7DC; --muted:#9A917F; --line:#2E2A22;
  --accent:#4FB3C9; --good:#57BE7C; --warn:#DFA83D; --crit:#E06B5F; --soft:#4FB3C91F;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{background:var(--paper);color:var(--ink);font-family:var(--sans);
  font-size:16px;line-height:1.55;-webkit-font-smoothing:antialiased}
.num,.big{font-variant-numeric:tabular-nums}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.eyebrow{font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;
  color:var(--muted);font-weight:600}
.big{font-family:var(--serif);font-size:clamp(40px,7vw,72px);line-height:1.02;
  letter-spacing:-.02em;font-weight:600}
h1,h2,h3{font-family:var(--serif);font-weight:600;letter-spacing:-.01em;margin:0}
.wrap{max-width:920px;margin:0 auto;padding:0 20px}
details{margin-top:18px;border-top:1px solid var(--line);padding-top:12px}
details summary{cursor:pointer;color:var(--accent);font-size:.9rem;font-weight:600;
  list-style:none}
details summary::-webkit-details-marker{display:none}
details summary::before{content:"▸ ";}
details[open] summary::before{content:"▾ ";}
table{width:100%;border-collapse:collapse;margin-top:10px;font-size:.9rem}
th,td{text-align:left;padding:6px 10px;border-bottom:1px solid var(--line)}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
.method{color:var(--muted);font-size:.85rem;margin-top:8px}

/* top bar */
.bar{position:sticky;top:0;z-index:20;display:flex;gap:6px;align-items:center;
  background:var(--paper);border-bottom:1px solid var(--line);padding:10px 18px}
.bar .brand{font-family:var(--serif);font-weight:600;font-size:1.05rem;margin-right:auto}
.bar a,.bar button{font-family:var(--sans);font-size:.85rem;font-weight:600;
  padding:6px 12px;border-radius:999px;border:1px solid var(--line);background:var(--card);
  color:var(--ink);cursor:pointer}
.bar a.on{background:var(--accent);color:#fff;border-color:var(--accent)}

/* book */
.book{scroll-snap-type:y mandatory;height:calc(100vh - 45px);overflow-y:scroll}
.chapter{scroll-snap-align:start;min-height:calc(100vh - 45px);display:flex;
  align-items:center;padding:40px 20px}
.chapter .inner{max-width:820px;margin:0 auto;width:100%}
.chapter h2{font-size:clamp(24px,3.4vw,34px);margin:14px 0 22px;max-width:20ch}
.visual{margin:8px 0 4px}
.cards{display:flex;flex-wrap:wrap;gap:16px;margin-top:8px}
.card{flex:1 1 240px;background:var(--card);border:1px solid var(--line);
  border-radius:14px;padding:18px}
.card .big{font-size:clamp(30px,4.4vw,44px)}
.card h3{font-size:1.05rem;margin-bottom:6px}
.card p{color:var(--muted);font-size:.9rem;margin:6px 0 0}
.dots{display:flex;gap:10px;flex-wrap:wrap;max-width:420px}

/* calls */
.chips{display:flex;flex-wrap:wrap;gap:10px;margin:18px 0 22px}
.chip{font-size:.85rem;font-weight:600;padding:8px 14px;border-radius:999px;
  border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer}
.chip.on{background:var(--accent);color:#fff;border-color:var(--accent)}
.row{display:block;background:var(--card);border:1px solid var(--line);border-radius:12px;
  padding:14px 16px;margin-bottom:10px;color:var(--ink)}
.row:hover{border-color:var(--accent);text-decoration:none}
.row .rline{display:flex;justify-content:space-between;gap:14px;align-items:baseline}
.row .rname{font-weight:700}
.row .rbook{color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap}
.row .reason{color:var(--ink);font-size:.92rem;margin-top:4px}
.row .script{color:var(--muted);font-size:.88rem;margin-top:4px;font-style:italic}

/* client */
.searchbox{margin:16px 0}
.searchbox input{width:100%;max-width:420px;padding:10px 14px;border-radius:10px;
  border:1px solid var(--line);background:var(--card);color:var(--ink);font-size:1rem}
.profile{background:var(--soft);border:1px solid var(--line);border-radius:14px;
  padding:18px 20px;margin-bottom:8px}
.profile h1{font-size:clamp(22px,3vw,30px)}
.hchip{display:inline-block;font-size:.8rem;font-weight:600;padding:4px 10px;border-radius:999px;
  background:var(--card);border:1px solid var(--line);margin:8px 8px 0 0;color:var(--muted)}
.section{padding:26px 0;border-top:1px solid var(--line)}
.section h3{font-size:1.15rem;margin:6px 0 10px}
.section .prose{max-width:60ch}
.section .big{margin:14px 0 4px}
.insuf{color:var(--muted);font-style:italic;max-width:60ch}
.act{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--accent);
  border-radius:10px;padding:14px 16px;margin-bottom:10px}
.act .verb{font-weight:700}
.act .tax{color:var(--muted);font-size:.88rem;margin-top:4px}
.win{flex:1 1 200px;background:var(--card);border:1px solid var(--line);border-left:3px solid var(--good);
  border-radius:10px;padding:14px 16px;margin-bottom:10px}
.win .verb{font-weight:700}
.fdrow{margin-top:0;border-top:none;padding-top:0}
.fdrow summary{font-size:.88rem;font-weight:600}
.foot{color:var(--muted);font-size:.8rem;padding:30px 20px;text-align:center}
</style>

<script id="data" type="application/json">__DATA__</script>

<div class="bar" role="navigation" aria-label="Primary">
  <span class="brand">The Book</span>
  <a href="#book" data-nav>Book</a>
  <a href="#calls" data-nav>Who to call</a>
  <a href="#cohort" data-nav>Cohort</a>
  <a href="#client/" data-nav>A client</a>
  <button id="theme" aria-label="Toggle light or dark theme">◑ Theme</button>
</div>
<main id="app" role="main"></main>

<script>
"use strict";
const DATA = JSON.parse(document.getElementById("data").textContent);
const app = document.getElementById("app");
const esc = s => String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const enIN = n => Math.round(n).toLocaleString("en-IN");
function lcr(n){ if(n==null) return "—"; const a=Math.abs(n);
  if(a>=1e7) return "₹"+(n/1e7).toFixed(2)+" cr";
  if(a>=1e5) return "₹"+(n/1e5).toFixed(2)+" L";
  return "₹"+enIN(n); }
function pct(n){ return n==null?"—":(n>=0?"":"")+n.toFixed(1)+"%"; }

/* ---- theme ---- */
document.getElementById("theme").onclick = () => {
  const r=document.documentElement;
  r.setAttribute("data-theme", r.getAttribute("data-theme")==="dark"?"light":"dark");
};

/* ---- inline SVG helpers ---- */
function svgBars(strip){
  const W=560,H=150,pad=24, max=Math.max(...strip.map(d=>d.value));
  const bw=(W-pad)/strip.length;
  const bars=strip.map((d,i)=>{
    const h=(d.value/max)*(H-30), x=pad+i*bw, y=H-h-16;
    return `<rect x="${x+3}" y="${y}" width="${bw-6}" height="${h}" rx="2" fill="var(--accent)"></rect>`+
           (i===0||i===strip.length-1?`<text x="${x+bw/2}" y="${H-3}" font-size="10" fill="var(--muted)" text-anchor="middle">Yr ${d.year}</text>`:"");
  }).join("");
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Ten lakh rupees growing year by year">${bars}</svg>`;
}
function svgDots(filled){
  let out="";
  for(let i=0;i<10;i++){ const on=i<filled;
    out+=`<circle cx="${20+i*38}" cy="24" r="13" fill="${on?"var(--accent)":"none"}" stroke="var(--accent)" stroke-width="2"></circle>`;
  }
  return `<svg viewBox="0 0 400 48" width="100%" style="max-width:420px" role="img" aria-label="${filled} of 10 ahead of the index fund">${out}</svg>`;
}
function svgDial(eff, stocks){
  // arc: eff genuinely-different bets out of the underlying stocks actually held
  const frac=(stocks&&eff!=null)?Math.max(0.02,Math.min(1,eff/stocks)):0.02, R=54, C=Math.PI*R;
  const off=C*(1-frac);
  const lab=eff==null?"unknown":eff.toFixed(1);
  return `<svg viewBox="0 0 140 90" width="160" role="img" aria-label="About ${lab} genuinely different bets out of ${stocks==null?"the":stocks} underlying stocks held">
    <path d="M16 78 A62 62 0 0 1 124 78" fill="none" stroke="var(--line)" stroke-width="12" stroke-linecap="round"/>
    <path d="M16 78 A62 62 0 0 1 124 78" fill="none" stroke="var(--accent)" stroke-width="12" stroke-linecap="round"
      stroke-dasharray="${C}" stroke-dashoffset="${off}"/>
    <text x="70" y="72" text-anchor="middle" font-family="var(--serif)" font-size="26" fill="var(--ink)">${lab}</text>
  </svg>`;
}
function svgTwoLine(rClient, rBench){
  // two growth curves from yearly-growth rates over 8 years
  const yrs=8,W=340,H=120;
  const pts=r=>{let s="";for(let y=0;y<=yrs;y++){const v=Math.pow(1+(r||0)/100,y);
    const x=20+(y/yrs)*(W-30), max=Math.pow(1+Math.max(rClient,rBench,1)/100,yrs);
    const yy=H-14-(v/max)*(H-30); s+=(y?"L":"M")+x.toFixed(0)+" "+yy.toFixed(0)+" ";}return s;};
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" style="max-width:360px" role="img" aria-label="Your growth versus the index fund">
    <path d="${pts(rBench)}" fill="none" stroke="var(--muted)" stroke-width="2" stroke-dasharray="4 3"/>
    <path d="${pts(rClient)}" fill="none" stroke="var(--accent)" stroke-width="2.5"/>
    <text x="${W-4}" y="14" text-anchor="end" font-size="10" fill="var(--accent)">you</text>
    <text x="${W-4}" y="28" text-anchor="end" font-size="10" fill="var(--muted)">index fund</text>
  </svg>`;
}

/* ---- routing ---- */
function nav(){
  const h=location.hash.replace(/^#/,"")||"book";
  document.querySelectorAll(".bar a[data-nav]").forEach(a=>{
    const t=a.getAttribute("href").replace(/^#/,"");
    a.classList.toggle("on", h===t || (t==="book"&&h==="book") ||
      (t==="calls"&&h==="calls") || (t==="client/"&&h.startsWith("client/")) ||
      (t==="cohort"&&(h==="cohort"||h.startsWith("segment/"))));
  });
  if(h==="book") return renderBook();
  if(h==="calls") return renderCalls();
  if(h==="cohort") return renderCohort();
  if(h.startsWith("segment/")) return renderSegment(h.slice(8));
  if(h.startsWith("client/")) return renderClient(h.slice(7));
  renderBook();
}
window.addEventListener("hashchange", ()=>{app.scrollTop=0;nav();});

/* ---- screen 1: the book ---- */
function chapter(n, eyebrow, headline, big, visualHTML, howHTML){
  return `<section class="chapter"><div class="inner">
    <div class="eyebrow">Chapter ${n} · ${esc(eyebrow)}</div>
    <h2>${headline}</h2>
    <div class="big">${big}</div>
    <div class="visual">${visualHTML||""}</div>
    <details><summary>How we know this</summary>${howHTML}</details>
  </div></section>`;
}
function renderBook(){
  const b=DATA.book, c=DATA.chapters;
  const chaps=[];
  chaps.push(chapter(1,"The book",
    `${b.families} families and ${b.clients} accounts, with records going back to ${b.since}.`,
    "₹"+b.mv_cr+" cr",
    "",
    `<div class="method">Family count = distinct households (surname + joint-holder roll-up). Book value = the header total on each client's latest valuation report, added up. Oldest transaction on file is dated ${b.since}.</div>`));

  chaps.push(chapter(2,"Did clients make money?",
    `A typical client's money has grown about ${c.ch2.growth_pct}% every year.`,
    c.ch2.growth_pct+"%/yr",
    svgBars(c.ch2.strip),
    `<div class="method">Growth here is the median yearly growth across all clients, measured on their real money-in and money-out dates. The bars show ₹10 lakh growing at that rate — ₹10 L becomes about ${lcr(c.ch2.strip[10].value)} over ten years.</div>`));

  chaps.push(chapter(3,"An honest comparison",
    `We replayed every client's exact investments into a plain Nifty-50 index fund. ${c.ch3.dots_filled} in 10 came out ahead.`,
    c.ch3.pct_ahead+"%",
    svgDots(c.ch3.dots_filled),
    `<div class="method">For each client we took their real money-in and money-out dates and put the same amounts into an ICICI Pru Nifty-50 index fund on the same days, then compared. ${c.ch3.pct_ahead}% of clients ended ahead of the index. Note: this is our current book — clients who left over the years are not in it.</div>`));

  const cardHref=card=>{
    const [kind,arg]=card.href.split(":");
    if(kind==="client") return {href:`#client/${arg}`,click:""};
    return {href:"#calls",click:`sessionStorage.setItem('callfilter','${arg}')`};
  };
  const cards=c.ch4.map(card=>{const h=cardHref(card);return `
    <a class="card" href="${h.href}" onclick="${h.click}">
      <h3>${esc(card.title)}</h3>
      <div class="big">₹${card.amount_cr==null?"—":card.amount_cr} cr</div>
      <p>${esc(card.subtitle)}.</p>
      <p style="margin-top:8px;color:var(--ink)">${esc(card.story||"")}</p>
    </a>`;}).join("");
  chaps.push(chapter(4,"What habits cost, and saved",
    "The same three habits, measured across the whole book. Each card opens the clients it affects.",
    "",
    `<div class="cards">${cards}</div>`,
    `<div class="method">"Held through the crashes" = the realised value protected for clients who stayed invested through major falls. The other two are upper-bound estimates of value left behind when SIPs were stopped or dividends taken as cash instead of reinvested — labelled as estimates, not booked losses.</div>`));

  const c5=c.ch5;
  const waveRows=c5.wave_rows.map(w=>`<tr><td>${esc(w.fund)}</td><td class="n">${w.n}</td>
    <td class="n">${pct(w.scheme)}</td><td class="n">${pct(w.bench)}</td></tr>`).join("");
  chaps.push(chapter(5,"Our advice, marked honestly",
    "We keep score of our own calls — the switches we suggested and the funds we pushed clients into.",
    c5.switch_ahead+" of "+c5.switch_total,
    `<div class="cards">
       <div class="card"><h3>Switches that worked</h3><div class="big">${c5.switch_ahead}/${c5.switch_total}</div><p>fund switches we advised were ahead of the old fund a year later.</p></div>
       <div class="card"><h3>Funds we pushed</h3><div class="big">${c5.waves}</div><p>buying waves across ${enIN(c5.families_nudged)} client positions — the year-after record is below.</p></div>
     </div>`,
    `<div class="method">Every advised switch is replayed one year forward: old fund vs new fund. Every buying wave is checked against a Nifty-50 index fund a year later. We show wins and misses both.</div>
     <details style="margin-top:14px"><summary>The push-wave scorecard</summary>
       <table><thead><tr><th>Fund</th><th class="n">Clients</th><th class="n">Fund +1yr</th><th class="n">Index +1yr</th></tr></thead><tbody>${waveRows}</tbody></table>
       <div class="method">Percent = one-year growth after the wave. Where the fund column beats the index column, the push added value.</div>
     </details>`));

  const sample=Object.keys(DATA.clients).sort((a,b)=>a-b)[0];
  chaps.push(chapter(6,"What this makes possible",
    "Three capabilities, running on our own book today — not a pitch, a demonstration.",
    "",
    `<div class="cards">
      <div class="card"><h3>Profile</h3><p style="color:var(--ink)">We can tell a client how they behave — whether they sell in every crash, keep their SIPs alive, or take dividends as cash — from what they actually did.</p></div>
      <div class="card"><h3>Predict &amp; prevent</h3><p style="color:var(--ink)">We know who to call this week and what to say, before they act. <a href="#calls">See the call lists →</a></p></div>
      <div class="card"><h3>Prescribe</h3><p style="color:var(--ink)">Every client gets a plain-language audit of what they own, what they pay, and what to do. <a href="#client/${sample}">Open a client audit →</a></p></div>
    </div>`,
    `<div class="method">Profile is computed from each client's transaction history. Predict lists are regenerated every run. Prescribe assembles seven checks per client, every number traced to a source table.</div>`));

  app.innerHTML = `<div class="book" id="book">${chaps.join("")}</div>`;
  // arrow-key chapter nav
  const bookEl=document.getElementById("book");
  bookEl.tabIndex=0;
  bookEl.onkeydown=e=>{
    const secs=[...bookEl.querySelectorAll(".chapter")];
    const cur=secs.findIndex(s=>s.getBoundingClientRect().top>=-5);
    if(e.key==="ArrowDown"&&cur<secs.length-1){e.preventDefault();secs[cur+1].scrollIntoView({behavior:"smooth"});}
    if(e.key==="ArrowUp"&&cur>0){e.preventDefault();secs[cur-1].scrollIntoView({behavior:"smooth"});}
  };
}

/* ---- screen 2: who to call ---- */
const CALL_META={crash_sellers:"Crash sellers",sip_fragile:"Fragile SIPs",disengaged:"Drifting away"};
function renderCalls(){
  const lists=DATA.call_lists;
  const keys=Object.keys(CALL_META).filter(k=>lists[k]);
  let active=sessionStorage.getItem("callfilter");
  if(!keys.includes(active)) active=keys[0];
  const chips=keys.map(k=>`<button class="chip${k===active?" on":""}" data-list="${k}">${esc(CALL_META[k])}</button>`).join("");
  app.innerHTML=`<div class="wrap" style="padding-top:26px">
    <div class="eyebrow">Predict &amp; prevent</div>
    <h1 style="font-size:clamp(24px,3.4vw,32px);margin-top:8px">Who to call this week</h1>
    <div class="chips" role="tablist">${chips}</div>
    <div id="rows"></div>
    <div class="foot">Each name is a client on our book. The line under is what to say. Click a row to open their full audit.</div>
  </div>`;
  const paint=k=>{
    document.querySelectorAll(".chip").forEach(c=>c.classList.toggle("on",c.dataset.list===k));
    document.getElementById("rows").innerHTML=(lists[k]||[]).map(r=>`
      <a class="row" href="#client/${r.id}">
        <div class="rline"><span class="rname">${esc(r.name)}</span><span class="rbook">${lcr(r.book_rs)} on our book</span></div>
        <div class="reason">${esc(r.reason)}</div>
        <div class="script">Script: ${esc(r.script)}</div>
      </a>`).join("");
  };
  document.querySelectorAll(".chip").forEach(c=>c.onclick=()=>{sessionStorage.setItem("callfilter",c.dataset.list);paint(c.dataset.list);});
  paint(active);
}

/* ---- screen: cohort dashboard + segment drill (Task 7) ---- */
const SEGMENT_COLOR={
  "Too New to Tell":"var(--muted)", "Crash Sellers":"var(--crit)",
  "Dividend Spenders":"var(--warn)", "SIP Quitters":"var(--accent)",
  "Drifted Away":"var(--crit)", "Steady Compounders":"var(--good)",
};
function segColor(name){ return SEGMENT_COLOR[name]||"var(--accent)"; }

function svgSegBar(bar){
  const max=Math.max(...bar.map(s=>s.count),1);
  return bar.map(s=>{
    const w=Math.max(2,(s.count/max)*100);
    return `<a href="#segment/${slug(s.segment)}" style="display:block;margin-bottom:12px;color:inherit;text-decoration:none">
      <div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:6px;font-size:.9rem;margin-bottom:3px">
        <span style="font-weight:600">${esc(s.segment)}</span>
        <span class="num" style="color:var(--muted)">${s.count} clients &middot; ${lcr((s.whatif_cr||0)*1e7)} what-if</span>
      </div>
      <div style="background:var(--line);border-radius:6px;height:16px;overflow:hidden">
        <div style="width:${w}%;height:100%;background:${segColor(s.segment)};border-radius:6px"></div>
      </div>
    </a>`;
  }).join("");
}

function svgHist(h,fmt){
  if(!h||!h.n) return '<p class="insuf">Not enough data.</p>';
  const W=280,H=104,pad=4,padB=18,padT=6;
  const max=Math.max(...h.counts,1);
  const bw=(W-2*pad)/h.counts.length;
  const bars=h.counts.map((c,i)=>{
    const bh=(c/max)*(H-padB-padT), x=pad+i*bw, y=H-padB-bh;
    return `<rect x="${(x+0.5).toFixed(1)}" y="${y.toFixed(1)}" width="${Math.max(bw-1,1).toFixed(1)}" height="${bh.toFixed(1)}" fill="var(--accent)" opacity=".78"><title>${fmt(h.edges[i])}–${fmt(h.edges[i+1])}: ${c} client${c===1?"":"s"}</title></rect>`;
  }).join("");
  const lo=h.edges[0], hi=h.edges[h.edges.length-1], span=(hi-lo)||1;
  const medX=h.median==null?null:pad+((h.median-lo)/span)*(W-2*pad);
  const medLine=medX==null?"":`<line x1="${medX.toFixed(1)}" y1="0" x2="${medX.toFixed(1)}" y2="${H-padB}" stroke="var(--ink)" stroke-width="1.5" stroke-dasharray="3 2"><title>Median ${fmt(h.median)}</title></line>`;
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" style="max-width:280px;display:block" role="img" aria-label="Distribution, median ${h.median==null?"unknown":fmt(h.median)} across ${h.n} clients">
    ${bars}${medLine}
    <text x="${pad}" y="${H-4}" font-size="9" fill="var(--muted)">${fmt(lo)}</text>
    <text x="${W-pad}" y="${H-4}" font-size="9" fill="var(--muted)" text-anchor="end">${fmt(hi)}</text>
  </svg>
  <div class="method">Median ${fmt(h.median)} &middot; ${h.n} clients.</div>`;
}

function svgBarList(rows,barColor){
  const max=Math.max(...rows.map(r=>r.n),1);
  return rows.map(r=>{
    const w=Math.max(2,(r.n/max)*100);
    const weight=r.bold?700:600;
    const color=r.bold?"var(--ink)":(barColor||"var(--accent)");
    const inner=`<div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:6px;font-size:.88rem;margin-bottom:3px">
        <span style="font-weight:${weight}">${esc(r.label)}</span>
        <span class="num" style="font-weight:${weight}">${r.valueLabel}</span></div>
      <div style="background:var(--line);border-radius:6px;height:${r.bold?16:12}px;overflow:hidden">
        <div style="width:${w}%;height:100%;background:${color}"></div></div>`;
    return r.href
      ? `<a href="${r.href}" style="display:block;margin-bottom:10px;color:inherit;text-decoration:none">${inner}</a>`
      : `<div style="margin-bottom:10px">${inner}</div>`;
  }).join("");
}

function svgScatter(points,cfg){
  if(!points.length) return '<p class="insuf">Not enough data.</p>';
  const W=360,H=240,pad=8;
  const xs=v=>pad+((v-cfg.xMin)/((cfg.xMax-cfg.xMin)||1))*(W-2*pad);
  const ys=v=>H-pad-((v-cfg.yMin)/((cfg.yMax-cfg.yMin)||1))*(H-2*pad);
  const quad=(cfg.thrX!=null&&cfg.thrY!=null)?
    `<rect x="${xs(cfg.thrX).toFixed(1)}" y="${pad}" width="${Math.max(0,W-pad-xs(cfg.thrX)).toFixed(1)}" height="${Math.max(0,ys(cfg.thrY)-pad).toFixed(1)}" fill="var(--crit)" opacity=".08"></rect>`:"";
  const lines=(cfg.thrX!=null?`<line x1="${xs(cfg.thrX).toFixed(1)}" y1="${pad}" x2="${xs(cfg.thrX).toFixed(1)}" y2="${H-pad}" stroke="var(--ink)" stroke-width="1" stroke-dasharray="3 3"></line>`:"")+
    (cfg.thrY!=null?`<line x1="${pad}" y1="${ys(cfg.thrY).toFixed(1)}" x2="${W-pad}" y2="${ys(cfg.thrY).toFixed(1)}" stroke="var(--ink)" stroke-width="1" stroke-dasharray="3 3"></line>`:"");
  const dots=points.map(p=>{
    const cx=xs(Math.max(cfg.xMin,Math.min(cfg.xMax,p.x))).toFixed(1);
    const cy=ys(Math.max(cfg.yMin,Math.min(cfg.yMax,p.y))).toFixed(1);
    return `<circle cx="${cx}" cy="${cy}" r="3.2" fill="${p.color||"var(--accent)"}" opacity=".55" style="cursor:pointer" onclick="location.hash='client/${p.id}'"><title>${esc(p.label)}</title></circle>`;
  }).join("");
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" style="max-width:380px;display:block;border:1px solid var(--line);border-radius:10px" role="img" aria-label="${esc(cfg.xLabel)} versus ${esc(cfg.yLabel)}, ${points.length} clients, click a dot to open that client">
    ${quad}${lines}${dots}
  </svg>
  <div class="method">x axis: ${esc(cfg.xLabel)} &middot; y axis: ${esc(cfg.yLabel)}${cfg.note?" &middot; "+esc(cfg.note):""}${cfg.quadrantLabel?" &middot; shaded corner = "+esc(cfg.quadrantLabel):""}</div>`;
}

function svgCompareBars(rows,color){
  return rows.map(r=>{
    const sv=r.segVal, av=r.allVal;
    const max=Math.max(sv||0,av||0,0.0001);
    const segW=sv==null?0:Math.max(2,(sv/max)*100);
    const allW=av==null?0:Math.max(2,(av/max)*100);
    return `<div style="margin-bottom:14px">
      <div style="font-weight:600;font-size:.9rem;margin-bottom:4px">${esc(r.label)}</div>
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:3px">
        <span style="width:92px;font-size:.78rem;color:var(--muted)">This segment</span>
        <div style="flex:1;background:var(--line);border-radius:6px;height:12px"><div style="width:${segW}%;height:100%;background:${color};border-radius:6px"></div></div>
        <span class="num" style="width:44px;text-align:right;font-size:.85rem">${sv==null?"—":r.fmt(sv)}</span>
      </div>
      <div style="display:flex;align-items:center;gap:8px">
        <span style="width:92px;font-size:.78rem;color:var(--muted)">Whole cohort</span>
        <div style="flex:1;background:var(--line);border-radius:6px;height:12px"><div style="width:${allW}%;height:100%;background:var(--muted);border-radius:6px"></div></div>
        <span class="num" style="width:44px;text-align:right;font-size:.85rem">${av==null?"—":r.fmt(av)}</span>
      </div>
    </div>`;
  }).join("");
}

function renderCohort(){
  const co=DATA.cohort, hl=co.headline, H=co.histograms;
  const totalSeg=co.segment_bar.reduce((s,x)=>s+x.count,0);

  const fmtL=v=>v==null?"—":lcr(v*1e5);
  const fmtYr=v=>v==null?"—":v.toFixed(1)+"y";
  const fmtGap=v=>v==null?"—":pct(v)+"/yr";
  const fmtPct=v=>v==null?"—":Math.round(v)+"%";
  const fmtBets=v=>v==null?"—":v.toFixed(1);
  const histCard=(h,title,fmt)=>`<div class="card"><h3>${esc(title)}</h3>${svgHist(h,fmt)}</div>`;

  const wf=co.waterfall.map((w,i)=>({label:w.label,n:Math.max(w.value_cr||0,0),
    valueLabel:lcr((w.value_cr||0)*1e7), bold:i===co.waterfall.length-1}));
  const fn=co.funnel.map((f,i)=>({label:f.stage,n:f.n,valueLabel:String(f.n),
    bold:i===co.funnel.length-1, href:i===co.funnel.length-1?"#calls":null}));

  const sc=co.scatter;
  const scatterPoints=(sc.points||[]).map(p=>{
    const cl=DATA.clients[String(p.client_id)]||{};
    return {x:p.churn_score, y:p.book_cr, id:p.client_id, color:segColor(p.segment),
      label:`${cl.name||("Client "+p.client_id)} &middot; ${esc(p.segment||"")} &middot; churn ${p.churn_score} &middot; ${lcr((p.book_cr||0)*1e7)} book`};
  }).filter(p=>p.x!=null&&p.y!=null);
  const xVals=scatterPoints.map(p=>p.x), yVals=scatterPoints.map(p=>p.y);
  const scatterHTML=svgScatter(scatterPoints,{
    xMin:0, xMax:Math.max(100,...xVals), yMin:0, yMax:Math.max(1,...yVals),
    thrX:sc.churn_threshold, thrY:sc.book_threshold_cr,
    xLabel:"Churn risk score", yLabel:"Book value",
    quadrantLabel:"valuable and at risk",
  });

  app.innerHTML=`<div class="wrap" style="padding-top:22px">
    <div class="eyebrow">Management dashboard</div>
    <h1 style="font-size:clamp(24px,3.4vw,32px);margin-top:8px">The cohort</h1>
    <p class="method">Every client on the book, binned honestly. Click a segment or a dot to open the client behind it.</p>

    <div class="section" style="border-top:none;padding-top:8px">
      <div class="cards">
        <div class="card"><h3>Book</h3><div class="big" style="font-size:clamp(26px,4vw,38px)">${lcr(hl.book_cr*1e7)}</div></div>
        <div class="card"><h3>Clients</h3><div class="big" style="font-size:clamp(26px,4vw,38px)">${hl.clients}</div></div>
        <div class="card"><h3>Families</h3><div class="big" style="font-size:clamp(26px,4vw,38px)">${hl.families}</div></div>
        <div class="card"><h3>Realized value delivered</h3><div class="big" style="font-size:clamp(26px,4vw,38px)">${hl.realized_cr==null?"—":lcr(hl.realized_cr*1e7)}</div><p>SIP discipline, staying invested, switch outcomes, fee and tax savings — booked and added up.</p></div>
        <div class="card"><h3>Coaching opportunity</h3><div class="big" style="font-size:clamp(26px,4vw,38px)">${hl.coaching_cr==null?"—":lcr(hl.coaching_cr*1e7)}</div><p>A labelled what-if upper bound, not booked.</p></div>
      </div>
    </div>

    <div class="section">
      <h3>Segments</h3>
      <p class="method">${totalSeg} clients across ${co.segment_bar.length} segments.</p>
      ${svgSegBar(co.segment_bar)}
    </div>

    <div class="section">
      <h3>Six distributions</h3>
      <div class="cards">
        ${histCard(H.book_size_l,"Book size",fmtL)}
        ${histCard(H.tenure_years,"Tenure",fmtYr)}
        ${histCard(H.growth_gap_pp,"Growth vs index fund",fmtGap)}
        ${histCard(H.freak_out_pct,"Freak-out score",fmtPct)}
        ${histCard(H.effective_bets,"Effective bets",fmtBets)}
        ${histCard(H.sip_health_pct,"SIP health",fmtPct)}
      </div>
    </div>

    <div class="section">
      <h3>What behaviour has cost the book</h3>
      ${svgBarList(wf,"var(--crit)")}
    </div>

    <div class="section">
      <h3>Churn risk vs. book value</h3>
      ${scatterHTML}
    </div>

    <div class="section">
      <h3>Tonight's call list, from the top</h3>
      ${svgBarList(fn,"var(--accent)")}
    </div>

    <div class="foot">Every figure above is computed from the book's own transaction, holdings and behaviour history, as on ${esc(DATA.asof)}.</div>
  </div>`;
}

function segAvg(list,f){ const v=list.map(f).filter(x=>x!=null&&isFinite(x)); return v.length?v.reduce((a,b)=>a+b,0)/v.length:null; }
function clientBookRs(c){ return (c.pack&&c.pack.map&&!c.pack.map.insufficient)?c.pack.map.total_mv:(c.churn?c.churn.mv:null); }
function clientPanic(c){ return (c.pack&&c.pack.habits&&!c.pack.habits.insufficient)?c.pack.habits.panic_share:null; }
function clientChase(c){ return (c.pack&&c.pack.habits&&!c.pack.habits.insufficient)?c.pack.habits.chase_hot_share:null; }
function clientSipStopPct(c){ const h=(c.pack&&c.pack.habits&&!c.pack.habits.insufficient)?c.pack.habits:null; return (h&&h.sip_active_share!=null)?100*(1-h.sip_active_share):null; }
function clientAlpha(c){ return (c.pack&&c.pack.benchmark&&!c.pack.benchmark.insufficient)?c.pack.benchmark.alpha:null; }

function renderSegment(key){
  const bar=(DATA.cohort.segment_bar||[]).find(s=>slug(s.segment)===key);
  if(!bar){
    app.innerHTML=`<div class="wrap" style="padding-top:26px"><div class="eyebrow">Cohort</div>
      <h1 style="font-size:clamp(24px,3.4vw,32px)">Segment not found</h1>
      <p><a href="#cohort">&larr; Back to the cohort</a></p></div>`;
    return;
  }
  const name=bar.segment, color=segColor(name);
  const entries=Object.entries(DATA.clients).filter(([id,c])=>c.segment&&c.segment.segment===name);
  const allClients=Object.values(DATA.clients);
  const segClients=entries.map(([id,c])=>c);

  const rows=[
    {label:"Sells in market falls",fmt:v=>Math.round(v)+"%",
     segVal:segAvg(segClients,c=>{const p=clientPanic(c);return p==null?null:p*100;}),
     allVal:segAvg(allClients,c=>{const p=clientPanic(c);return p==null?null:p*100;})},
    {label:"Chases recently-hot funds",fmt:v=>Math.round(v)+"%",
     segVal:segAvg(segClients,c=>{const p=clientChase(c);return p==null?null:p*100;}),
     allVal:segAvg(allClients,c=>{const p=clientChase(c);return p==null?null:p*100;})},
    {label:"SIPs stopped",fmt:v=>Math.round(v)+"%",
     segVal:segAvg(segClients,clientSipStopPct),
     allVal:segAvg(allClients,clientSipStopPct)},
  ];
  const behaviourHTML=svgCompareBars(rows,color);

  const rrPoints=entries.map(([id,c])=>{
    const a=clientAlpha(c), p=clientPanic(c);
    return {x:a, y:p==null?null:p*100, id, color,
      label:`${esc(c.name)} &middot; ${pct(a)}/yr vs index fund &middot; ${p==null?"—":Math.round(p*100)}% sold in falls`};
  }).filter(p=>p.x!=null&&p.y!=null);
  let rrHTML;
  if(rrPoints.length){
    const xs=rrPoints.map(p=>p.x), ys=rrPoints.map(p=>p.y);
    rrHTML=svgScatter(rrPoints,{
      xMin:Math.min(0,...xs), xMax:Math.max(0,...xs), yMin:0, yMax:Math.max(10,...ys),
      thrX:0, thrY:null, xLabel:"Growth vs index fund (%/yr)", yLabel:"Sold in market falls (%)",
      note:"dashed line = even with the index fund",
    });
  } else {
    rrHTML='<p class="insuf">Not enough index-fund or behaviour history in this segment yet.</p>';
  }

  const bookShareRs=segClients.reduce((s,c)=>s+(clientBookRs(c)||0),0);
  const bookSharePct=DATA.book.mv_cr?100*bookShareRs/(DATA.book.mv_cr*1e7):null;
  const clientSharePct=100*bar.count/DATA.book.clients;

  const rowsHTML=entries
    .slice().sort((a,b)=>(b[1].segment.whatif_rs||0)-(a[1].segment.whatif_rs||0))
    .map(([id,c])=>{
      const mv=clientBookRs(c), churnScore=(c.churn&&c.churn.score!=null)?Math.round(c.churn.score):null;
      return `<a class="row" href="#client/${id}">
        <div class="rline"><span class="rname">${esc(c.name)}</span><span class="rbook">${lcr(mv)} book</span></div>
        <div class="reason">${esc(c.segment.reason)}</div>
        <div class="script">What-if ${lcr(c.segment.whatif_rs)}${churnScore!=null?" &middot; churn score "+churnScore:""}</div>
      </a>`;
    }).join("");

  app.innerHTML=`<div class="wrap" style="padding-top:22px">
    <div class="eyebrow"><a href="#cohort">&larr; The cohort</a></div>
    <div class="profile" style="border-left:4px solid ${color}">
      <h1>${esc(name)}</h1>
      <p class="method" style="margin-top:6px">${esc((segClients[0]&&segClients[0].segment.reason)||"")}</p>
      <div style="display:flex;flex-wrap:wrap;gap:26px;margin-top:14px;align-items:center">
        <div><div class="eyebrow">Clients</div><div class="big" style="font-size:clamp(24px,3.6vw,36px)">${bar.count}</div><p style="color:var(--muted);font-size:.85rem;margin:2px 0 0">${clientSharePct.toFixed(0)}% of the book</p></div>
        <div><div class="eyebrow">Book share</div><div class="big" style="font-size:clamp(24px,3.6vw,36px)">${lcr(bookShareRs)}</div><p style="color:var(--muted);font-size:.85rem;margin:2px 0 0">${bookSharePct==null?"—":bookSharePct.toFixed(0)+"% of the book"}</p></div>
        <div><div class="eyebrow">&#8377; what-if</div><div class="big" style="font-size:clamp(24px,3.6vw,36px)">${lcr((bar.whatif_cr||0)*1e7)}</div><p style="color:var(--muted);font-size:.85rem;margin:2px 0 0">Labelled upper bound, not booked.</p></div>
      </div>
    </div>

    <div class="section"><h3>How this segment behaves</h3>
      <p class="method">This segment versus the whole cohort.</p>
      ${behaviourHTML}
    </div>

    <div class="section"><h3>Growth vs. behaviour</h3>
      ${rrHTML}
    </div>

    <div class="section"><h3>Every client in this segment</h3>
      ${rowsHTML || '<p class="insuf">No clients resolved to this segment.</p>'}
    </div>

    <div class="foot">${esc(name)} &middot; ${bar.count} clients &middot; as on ${esc(DATA.asof)}.</div>
  </div>`;
}

/* ---- screen 3: client audit pack ---- */
const SEC_META={
  map:["The map","What you own, in one clean picture"],
  label_check:["The label check","Does each fund do what its name says?"],
  overlap:["The overlap trap","How many genuinely different bets you own"],
  fees:["What you actually pay","The fees, in rupees a year"],
  benchmark:["Did you beat the market?","Your money vs a plain index fund"],
  habits:["Your habits","How you behave — and what it costs"],
  value:["What our advice was worth","The value we've added, added up"],
  actions:["The action list","What to do next"],
};
function bigFor(key,p){
  if(p.insufficient) return null;
  if(key==="map") return lcr(p.headline_value);
  if(key==="label_check") return p.n_mismatch+(p.n_mismatch===1?" fund off-label":" funds off-label");
  if(key==="overlap") return (p.eff_bets==null?"—":p.eff_bets.toFixed(1))+" real bets";
  if(key==="fees") return lcr(p.fee_save_yr_rs)+"/yr";
  if(key==="benchmark"){const a=p.alpha; return a==null?"—":(a>=0?"+":"")+a.toFixed(1)+"%/yr "+(a>=0?"ahead":"behind");}
  if(key==="habits") return Math.round((p.panic_share||0)*100)+"% sold in falls";
  if(key==="value") return lcr(p.realized_total_rs);
  if(key==="actions") return p.n_actions+(p.n_actions===1?" thing to do":" things to do");
  return lcr(p.headline_value);
}
function fallbackProse(key,p,name){
  const n=esc(name||"This client");
  if(p.insufficient) return "";
  if(key==="map") return `${n}'s money with us is ${lcr(p.total_mv)}, spread across ${p.n_funds||"several"} funds holding ${p.n_stocks||"many"} different stocks underneath.`;
  if(key==="label_check") return p.n_mismatch>0?`${p.n_mismatch} of ${p.n_funds_checked} funds don't invest the way their name suggests — worth a closer look.`:`All ${p.n_funds_checked} checked funds invest broadly the way their names suggest.`;
  if(key==="overlap") return `Across all the funds, there are really about ${p.eff_bets==null?"a handful of":p.eff_bets.toFixed(1)} genuinely different bets — the rest is the same stocks showing up again and again.`;
  if(key==="fees") return p.fee_save_yr_rs>0?`We estimate about ${lcr(p.fee_save_yr_rs)} a year could be saved on fees without changing what you're really invested in.`:`No obvious fee savings flagged — the funds held aren't the closet-index kind.`;
  if(key==="benchmark"){const a=p.alpha; return a==null?"":`Put the exact same money on the exact same dates into a plain index fund, and you'd be ${a>=0?"ahead":"behind"} by about ${Math.abs(a).toFixed(1)}% a year.`;}
  if(key==="habits") return `In past market falls, ${Math.round((p.panic_share||0)*100)}% of everything ever withdrawn was pulled out during the drop.`;
  if(key==="value") return `Adding up SIP discipline, staying invested, switches, fees and tax, the value we've helped with comes to about ${lcr(p.realized_total_rs)}.`;
  if(key==="actions") return p.n_actions>0?`There ${p.n_actions===1?"is":"are"} ${p.n_actions} thing${p.n_actions===1?"":"s"} worth doing on this account.`:`Nothing pressing — a genuinely clean account right now.`;
  return "";
}
function visualFor(key,p){
  if(p.insufficient) return "";
  if(key==="overlap") return svgDial(p.eff_bets, p.n_stocks);
  if(key==="benchmark" && p.xirr_client!=null) return svgTwoLine(p.xirr_client, p.xirr_bench);
  return "";
}
function tableFor(key,p){
  const rows=[];
  const R=(k,v)=>rows.push(`<tr><td>${k}</td><td class="n">${v}</td></tr>`);
  if(key==="map"){R("Book value",lcr(p.total_mv));R("Funds",p.n_funds);R("Stocks underneath",p.n_stocks);R("Years with us",p.tenure_years);}
  else if(key==="label_check"){(p.funds||[]).slice(0,12).forEach(f=>rows.push(
    `<tr><td>${esc(f.fund)}${f.coverage_note?`<div class="method" style="margin-top:2px">${esc(f.coverage_note)}</div>`:""}</td><td class="n">${esc(f.verdict)}</td></tr>`));}
  else if(key==="overlap"){R("Genuinely different bets",p.eff_bets==null?"—":p.eff_bets.toFixed(1));R("Biggest single stock",esc(p.top_stock_name)+" · "+lcr(p.top_stock_rs));R("Top-10 stocks share",p.top10_share==null?"—":(p.top10_share*100).toFixed(0)+"%");if(p.worst_fund_pair)R("Most-overlapping pair",esc(p.worst_fund_pair.fund_a)+" / "+esc(p.worst_fund_pair.fund_b)+" ("+(p.worst_fund_pair.overlap_pct).toFixed(0)+"%)");}
  else if(key==="fees"){R("Estimated saving / year",lcr(p.fee_save_yr_rs));(p.flags||[]).forEach(f=>rows.push(`<tr><td>${esc(f.rule||f.evidence)}</td><td class="n">${lcr(f.est_value)}</td></tr>`));}
  else if(key==="benchmark"){R("Your yearly growth",pct(p.xirr_client));R("Index-fund yearly growth",pct(p.xirr_bench));R("Ahead / behind",p.alpha==null?"—":(p.alpha>=0?"+":"")+p.alpha.toFixed(1)+"%/yr");R("Money-in / money-out events",p.n_flows);}
  else if(key==="habits"){R("Withdrawn during falls",Math.round((p.panic_share||0)*100)+"%");if(p.sip_active_share!=null)R("SIPs still running",Math.round(p.sip_active_share*100)+"%");R("Dividends taken as cash",lcr(p.div_leak_rs));if(p.cf_no_panic_rs!=null)R("Est. value if never sold in falls",lcr(p.cf_no_panic_rs));}
  else if(key==="value"){const r=p.realized||{};R("SIP discipline",lcr(r.sip_discipline_rs));R("Staying invested",lcr(r.staying_power_rs));R("Switch outcomes",lcr(r.advice_outcome_rs));R("Fee savings",lcr(r.fee_save_yr_rs));R("Tax headroom",lcr(r.tax_headroom_rs));R("Total realised",lcr(p.realized_total_rs));}
  return rows.length?`<table><tbody>${rows.join("")}</tbody></table>`:"";
}
function actionsHTML(p){
  const cards=[];
  (p.calls||[]).forEach(c=>cards.push(`<div class="act"><div class="verb">Call this client</div><div>${esc(c.reason)}</div><div class="tax">${esc(c.script)}</div></div>`));
  (p.flags||[]).forEach(f=>cards.push(`<div class="act"><div class="verb">${esc(f.action||"Review")}</div><div>${esc(f.evidence)}</div>${f.est_value?`<div class="tax">Worth about ${lcr(f.est_value)}</div>`:""}</div>`));
  if(p.tax && p.tax.n_gain_candidates>0)cards.push(`<div class="act"><div class="verb">Harvest gains this year (${esc(p.tax.fy)})</div><div>${p.tax.n_gain_candidates} lot(s) with tax-free headroom of ${lcr(p.tax.headroom)}.</div><div class="tax">Est. tax saved: ${lcr(p.tax.tax_saved_if_harvested)}${p.tax.loss_note?" · "+esc(p.tax.loss_note):""}</div></div>`);
  return cards.length?cards.join(""):`<div class="insuf">Nothing pressing on this account right now.</div>`;
}
/* ---- client 360 ("the Kundli") ---- */
function slug(s){ return String(s||"").toLowerCase().replace(/[^a-z0-9]+/g,"_").replace(/^_+|_+$/g,""); }

// Part 2: story curve — monthly value line, drawdown-to-peak shaded, event markers.
function svgStoryCurve(curve){
  if(!curve || !curve.months || !curve.months.length){
    return '<p class="insuf">Not enough NAV history in mapped funds to trace this client’s value over time.</p>';
  }
  const months=curve.months, vals=curve.values, n=vals.length, cov=curve.coverage_pct;
  const W=680,H=220,padL=6,padR=6,padT=10,padB=24;
  const lo=Math.min(...vals), hi=Math.max(...vals), span=(hi-lo)||1;
  const x=i=>padL+i*(W-padL-padR)/(n-1||1);
  const y=v=>H-padB-(v-lo)/span*(H-padT-padB);
  let peak=-Infinity; const peaks=vals.map(v=>{peak=Math.max(peak,v);return peak;});
  const line=vals.map((v,i)=>(i?"L":"M")+x(i).toFixed(1)+" "+y(v).toFixed(1)).join(" ");
  const underPeak=peaks.map((v,i)=>"L"+x(n-1-i).toFixed(1)+" "+y(peaks[n-1-i]).toFixed(1)).join(" ");
  const area=line+" "+underPeak+" Z";
  const partial=cov!=null && cov<70;   // build_equity_curves.py: <70% is the app's own insufficient flag
  const monthIdx={}; months.forEach((m,i)=>monthIdx[m]=i);
  let markers="";
  const ev=curve.events, tickTop=H-padB+4, tickBot=H-padB+16;
  if(ev){
    for(let k=0;k<ev.dates.length;k++){
      const i=monthIdx[String(ev.dates[k]).slice(0,7)];
      if(i==null) continue;
      const cx=x(i).toFixed(1), kind=ev.kinds[k], amt=lcr(Math.abs(ev.amounts[k])), d=esc(ev.dates[k]);
      if(kind==="panic_sell") markers+=`<circle cx="${cx}" cy="${y(vals[i]).toFixed(1)}" r="4.5" fill="var(--crit)"><title>Sold in a market fall — ${amt} on ${d}</title></circle>`;
      else if(kind==="sip_stop") markers+=`<rect x="${cx-3}" y="${tickTop}" width="6" height="${tickBot-tickTop}" fill="var(--warn)"><title>SIP stopped — ${amt} on ${d}</title></rect>`;
      else if(kind==="big_inflow") markers+=`<line x1="${cx}" y1="${tickTop}" x2="${cx}" y2="${tickBot}" stroke="var(--good)" stroke-width="2.5"><title>Large inflow — ${amt} on ${d}</title></line>`;
      else if(kind==="big_outflow") markers+=`<line x1="${cx}" y1="${tickTop}" x2="${cx}" y2="${tickBot}" stroke="var(--muted)" stroke-width="2.5"><title>Large withdrawal — ${amt} on ${d}</title></line>`;
    }
  }
  const banner=partial?`<p class="insuf">We can only trace ${cov.toFixed(0)}% of this client’s current book back through mapped-fund NAV history — the line below covers just that share, marked partial.</p>`:"";
  const caption=(cov!=null&&cov<100)?`reconstructed from mapped funds, ${cov.toFixed(0)}% of book covered`:"";
  return `<div class="curvewrap">${banner}
    <svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Value over time, ${lcr(vals[n-1])} today">
      <path d="${area}" fill="var(--crit)" opacity="0.10"></path>
      <path d="${line}" fill="none" stroke="${partial?"var(--muted)":"var(--accent)"}" stroke-width="2.4" ${partial?'stroke-dasharray="5 4"':""}></path>
      ${markers}
    </svg>
    <div class="method">${esc(months[0])} → ${esc(months[n-1])}${caption?" · "+caption:""} ·
      <span style="color:var(--crit)">●</span> sold in a fall &nbsp;
      <span style="color:var(--warn)">▮</span> SIP stopped &nbsp;
      <span style="color:var(--good)">│</span> large inflow &nbsp;
      <span style="color:var(--muted)">│</span> large withdrawal</div>
  </div>`;
}

// Allocation donut (Part 3) + a generic 0-100 gauge (Part 1, churn risk).
function svgDonut(segs){
  const total=segs.reduce((s,d)=>s+d.v,0)||1;
  const R=44,C=2*Math.PI*R; let off=0;
  const COLORS=["var(--accent)","var(--good)","var(--warn)","var(--crit)","var(--muted)"];
  const arcs=segs.map((s,i)=>{
    const len=C*s.v/total, rot=(off/C*360-90).toFixed(1); off+=len;
    return `<circle cx="60" cy="60" r="${R}" fill="none" stroke="${COLORS[i%COLORS.length]}" stroke-width="16" stroke-dasharray="${len.toFixed(1)} ${(C-len).toFixed(1)}" transform="rotate(${rot} 60 60)"><title>${esc(s.k)} · ${pct(s.v/total*100)}</title></circle>`;
  }).join("");
  const legend=segs.map((s,i)=>`<div style="display:flex;align-items:center;gap:6px;font-size:.85rem"><span style="width:10px;height:10px;border-radius:50%;background:${COLORS[i%COLORS.length]};display:inline-block"></span>${esc(s.k)} · ${lcr(s.v)}</div>`).join("");
  return `<div style="display:flex;gap:20px;align-items:center;flex-wrap:wrap">
    <svg viewBox="0 0 120 120" width="130" role="img" aria-label="Allocation by asset class">${arcs}</svg>
    <div style="display:flex;flex-direction:column;gap:4px">${legend}</div>
  </div>`;
}
function svgGauge(value,color,label){
  const v=Math.max(0,Math.min(100,value)), R=40,C=Math.PI*R, off=C*(1-v/100);
  return `<svg viewBox="0 0 120 70" width="104" role="img" aria-label="${esc(label)}: ${Math.round(value)} of 100">
    <path d="M14 62 A46 46 0 0 1 106 62" fill="none" stroke="var(--line)" stroke-width="10" stroke-linecap="round"/>
    <path d="M14 62 A46 46 0 0 1 106 62" fill="none" stroke="${color}" stroke-width="10" stroke-linecap="round" stroke-dasharray="${C.toFixed(1)}" stroke-dashoffset="${off.toFixed(1)}"/>
    <text x="60" y="52" text-anchor="middle" font-family="var(--serif)" font-size="22" fill="var(--ink)">${Math.round(value)}</text>
  </svg>`;
}

// Part 4 (wins) + Part 5 (behaviour costs) — gated on real segment traits, never invented.
function clientWins(c){
  const v=(c.pack&&c.pack.value)||{}, r=v.realized||{};
  const bench=(c.pack&&c.pack.benchmark&&!c.pack.benchmark.insufficient)?c.pack.benchmark:{};
  // GOOD maps a chip to its own description + the win title it duplicates
  // when a ₹ figure already covers the same fact (skip the bare chip then).
  const GOOD={"Holds through falls":["Never sold out during a market downturn.","Held through market falls"],
    "Keeps every SIP running":["Every SIP has stayed active without a gap.","Kept SIPs running"],
    "Reinvests dividends":["Dividend payouts are reinvested instead of taken as cash.",null]};
  const out=[]; const titles=new Set();
  if(r.staying_power_rs>0){ out.push({t:"Held through market falls",v:r.staying_power_rs,d:"Stayed invested through drops instead of selling at a loss."}); titles.add("Held through market falls"); }
  if(r.sip_discipline_rs>0){ out.push({t:"Kept SIPs running",v:r.sip_discipline_rs,d:"Stuck to monthly investing instead of timing the market."}); titles.add("Kept SIPs running"); }
  if(r.advice_outcome_rs>0) out.push({t:"Our switches paid off",v:r.advice_outcome_rs,d:"Fund switches we recommended came out ahead of the old fund."});
  if(bench.alpha!=null && bench.alpha>0) out.push({t:"Ahead of the index fund",d:`Real money, real dates, replayed into a Nifty-50 index fund — came out ${pct(bench.alpha)}/yr ahead.`});
  (c.chips||[]).forEach(ch=>{ const g=GOOD[ch]; if(g && !titles.has(g[1])) out.push({t:ch,d:g[0]}); });
  if(!out.length){
    const m=(c.pack&&c.pack.map)||{};
    if(!m.insufficient && m.tenure_years!=null && m.total_mv!=null)
      out.push({t:"Building a track record",d:`${m.tenure_years} years invested with us, a book now worth ${lcr(m.total_mv)}.`});
    else
      out.push({t:"Still early days",d:"Not enough history yet to call out a specific win — the relationship is still new."});
  }
  return out;
}
function clientCosts(c){
  const seg=c.segment||{}, tr=seg.traits||{};
  if(seg.segment==="Too New to Tell") return [];
  const hb=(c.pack&&c.pack.habits&&!c.pack.habits.insufficient)?c.pack.habits:{};
  const out=[];
  if(tr.crash_seller) out.push({t:"Sells in market falls",v:hb.cf_no_panic_rs,d:`About ${Math.round((hb.panic_share||0)*100)}% of past withdrawals were sold during a market fall.`});
  if(tr.div_spender) out.push({t:"Takes dividends as cash",v:hb.div_leak_rs,d:"Dividend payouts taken as cash instead of reinvested."});
  if(tr.sip_quitter) out.push({t:"Stopped a SIP",v:hb.cf_sip_alive_rs,d:"A running SIP was stopped instead of continued."});
  if(tr.chaser) out.push({t:"Chases recently hot funds",v:null,d:`${Math.round((hb.chase_hot_share||0)*100)}% of switches followed a fund that had just outperformed.`});
  return out;
}

// Part 3 (the floor) — holdings grouped by asset class, deduped by scheme_id
// (a client can carry the same scheme_id twice across folios); per-fund
// expander doubles as Part 7's per-fund prompt 2 (label) + prompt 5 (performance).
function fmtVerdict(v){ return v==null?"—":v==="mismatch"?"Off-label":v==="ok"?"On-label":esc(v); }
function qualityDot(q){
  if(q==null) return '<span style="color:var(--muted)">—</span>';
  const c=q>=65?"var(--good)":q>=40?"var(--warn)":"var(--crit)";
  return `<span style="color:${c};font-weight:700">${q.toFixed(0)}</span>`;
}
function fundPerfText(fp){
  if(!fp) return "Not equity, or no rolling-performance signal computed for this fund.";
  if(fp.verdict==="insufficient_history") return "Not enough NAV history yet to score rolling returns.";
  const parts=[`3-yr yearly growth ${pct(fp.roll_3y_pct)}`];
  if(fp.roll_5y_pct!=null) parts.push(`5-yr ${pct(fp.roll_5y_pct)}`);
  if(fp.dn_capture_pct!=null) parts.push(`fell ${fp.dn_capture_pct.toFixed(0)}% as much as the market in its worst falls`);
  if(fp.beat_count!=null && fp.windows) parts.push(`beat its benchmark in ${fp.beat_count} of ${fp.windows} rolling 1-year windows`);
  if(fp.best_year_stripped_pct!=null && fp.full_period_pct!=null) parts.push(`full-period growth ${pct(fp.full_period_pct)}, ${pct(fp.best_year_stripped_pct)} with its single best year stripped out`);
  let s=parts.join("; ")+".";
  if(fp.benchmark_note) s+=" "+esc(fp.benchmark_note);
  return s;
}
function renderFloor(c){
  const raw=c.holdings||[];
  if(!raw.length) return {donut:"",table:'<p class="insuf">No held-fund detail on file for this client.</p>'};
  const bySid=new Map();
  raw.forEach(h=>{
    const cur=bySid.get(h.scheme_id);
    if(cur) cur.mv=(cur.mv||0)+(h.mv||0); else bySid.set(h.scheme_id,Object.assign({},h,{mv:h.mv||0}));
  });
  const holds=[...bySid.values()];
  const byClass={};
  holds.forEach(h=>{ const k=h.asset_class||"Other"; (byClass[k]=byClass[k]||[]).push(h); });
  const fpBySid={}; (c.fund_performance||[]).forEach(f=>fpBySid[f.scheme_id]=f);
  const lc=(c.pack&&c.pack.label_check&&!c.pack.label_check.insufficient)?c.pack.label_check:{};
  const labelByName={}; (lc.funds||[]).forEach(f=>labelByName[f.fund]=f);
  const classEntries=Object.entries(byClass).sort((a,b)=>b[1].reduce((s,h)=>s+h.mv,0)-a[1].reduce((s,h)=>s+h.mv,0));
  const donut=svgDonut(classEntries.map(([k,hs])=>({k,v:hs.reduce((s,h)=>s+h.mv,0)})));
  const table=classEntries.map(([cls,hs])=>{
    const rows=hs.sort((a,b)=>b.mv-a.mv).map(h=>{
      const lbl=labelByName[h.fund], fp=fpBySid[h.scheme_id];
      return `<tr><td>
          <details class="fdrow"><summary>${esc(h.fund)}</summary>
            <div class="method">Label check — does it do what its name promises? ${fmtVerdict(h.verdict)}${lbl&&lbl.detail?": "+esc(lbl.detail):""}${lbl&&lbl.coverage_note?` <em>(${esc(lbl.coverage_note)})</em>`:""}</div>
            <div class="method">Rolling performance: ${fundPerfText(fp)}</div>
          </details>
        </td><td class="n">${lcr(h.mv)}</td><td class="n">${qualityDot(h.quality)}</td></tr>`;
    }).join("");
    return `<h4 style="margin:16px 0 2px">${esc(cls)} · ${lcr(hs.reduce((s,h)=>s+h.mv,0))}</h4>
      <table><thead><tr><th>Fund (tap to expand)</th><th class="n">Value</th><th class="n">Quality</th></tr></thead><tbody>${rows}</tbody></table>`;
  }).join("");
  return {donut,table};
}
function renderOverlap(c){
  const p=(c.pack&&c.pack.overlap)||{};
  if(p.insufficient) return '<p class="insuf">Not enough mapped fund holdings to compute overlap.</p>';
  const wp=p.worst_fund_pair;
  return `<div style="display:flex;gap:20px;align-items:center;flex-wrap:wrap">
    ${svgDial(p.eff_bets,p.n_stocks)}
    <div style="max-width:34ch;font-size:.92rem">
      Biggest single stock: <b>${esc(p.top_stock_name)}</b> (${lcr(p.top_stock_rs)}, ${p.top10_share==null?"—":(p.top10_share*100).toFixed(0)+"%"} of the top 10)<br>
      ${wp?`Most-overlapping pair: <b>${esc(wp.fund_a)}</b> / <b>${esc(wp.fund_b)}</b> (${wp.overlap_pct.toFixed(0)}% overlap)`:"No fund pair overlaps meaningfully."}
    </div>
  </div>`;
}

// Part 7 (portfolio half): prompt 7's cut list, evidence-gated.
function cutListHTML(c){
  const cl=c.cut_list;
  if(!cl) return '<p class="insuf">Not enough mapped-fund holdings to compute a cut list.</p>';
  const cuts=cl.cut||[], keep=cl.keep||[];
  if(!cuts.length) return `<p class="prose">${esc(cl.note)}</p>`;
  const rows=cuts.map(f=>`<tr><td>${esc(f.fund)}</td><td>${esc(f.reason)}</td><td class="n">${lcr(f.exit_tax_rs)}</td><td class="n">${f.unwind_order}</td></tr>`).join("");
  return `<p class="prose">${esc(cl.note)}</p>
    <details><summary>See the ${cuts.length} fund${cuts.length===1?"":"s"} to cut, in order</summary>
      <table><thead><tr><th>Fund</th><th>Why</th><th class="n">Tax if sold now</th><th class="n">Order</th></tr></thead><tbody>${rows}</tbody></table>
      <div class="method">Keeping just ${cl.min_fund_count} fund${cl.min_fund_count===1?"":"s"} — ${keep.map(k=>esc(k.fund)).join(", ")} — covers essentially the same look-through exposure.</div>
    </details>`;
}
// Part 7 (fund-audit half): prompts 1/3/4 restated + the new prompt 7 cut list.
function sevenPromptHTML(c){
  const m=(c.pack&&c.pack.map)||{}, ov=(c.pack&&c.pack.overlap)||{}, fees=(c.pack&&c.pack.fees)||{};
  const wp=ov.worst_fund_pair, nClosets=(fees.flags||[]).length;
  return `<ul style="padding-left:18px;margin:6px 0 16px">
    <li><b>The map:</b> ${m.n_funds==null?"—":m.n_funds} funds across ${m.n_stocks==null?"—":m.n_stocks} underlying stocks, worth ${lcr(m.total_mv)}.</li>
    <li><b>The overlap trap:</b> about ${ov.eff_bets==null?"—":ov.eff_bets.toFixed(1)} genuinely different bets${wp?`; the most overlap is ${esc(wp.fund_a)} / ${esc(wp.fund_b)} (${wp.overlap_pct.toFixed(0)}%)`:""}.</li>
    <li><b>What you actually pay:</b> ${nClosets} closet-index fund${nClosets===1?"":"s"} flagged, ${lcr(fees.fee_save_yr_rs)}/yr potential saving.</li>
  </ul>
  <h4 style="margin:0 0 6px">What to cut</h4>
  ${cutListHTML(c)}
  <div class="method" style="margin-top:10px">Fund labels and rolling performance for each holding are in the expander next to its name in the holdings table above. A sixth check (fund-manager tenure / AUM bloat) needs factsheet data we don’t have yet, so it’s left out rather than guessed.</div>`;
}

// Part 6 — scorecard grade + gate verdict, then ranked client_flags actions + one FY tax note.
function recommendHTML(c){
  const sc=c.scorecard;
  if(!sc) return '<p class="insuf">Not enough on record yet to grade this account or recommend changes.</p>';
  const gateLine=sc.needs_attention?esc(sc.reasons||"Some attention areas flagged."):"Compounding well — no changes forced.";
  const flags=c.flags||[];
  const tax=(c.pack&&c.pack.actions&&c.pack.actions.tax)||null;
  const body=flags.length
    ? flags.map(f=>`<div class="act"><div class="verb">${esc(f.action||"Review")}</div><div>${esc(f.evidence)}${f.est_value?" — "+lcr(f.est_value):""}</div></div>`).join("")
    : (sc.needs_attention?'<p class="prose">No single action flagged, but the scorecard above still calls for a closer look.</p>':'<p class="prose">No changes forced — compounding well.</p>');
  const taxNote=(tax&&tax.n_gain_candidates>0)?`<div class="method">Tax picture this FY (${esc(tax.fy)}): ${tax.n_gain_candidates} gain-lot(s) worth ${lcr(tax.gain_value)}, ${lcr(tax.headroom)} exemption headroom, up to ${lcr(tax.tax_saved_if_harvested)} saved if harvested.${tax.loss_note?" "+esc(tax.loss_note):""}</div>`:"";
  return `<div class="eyebrow">Grade ${esc(sc.grade||"—")}</div><p class="prose">${gateLine}</p>${body}${taxNote}`;
}

// Part 8 — the 8 v1 audit sections, reusing SEC_META/bigFor/fallbackProse/visualFor/
// tableFor/actionsHTML AS-IS, now collapsed as a "how we know this" proof layer.
function auditExpanders(c){
  return DATA.sections.map(key=>{
    const p=(c.pack||{})[key]||{}; const meta=SEC_META[key];
    if(p.insufficient){
      return `<details><summary>${esc(meta[0])}</summary><p class="insuf">We can’t say this honestly for you yet — ${esc(p.reason)}.</p></details>`;
    }
    const prose=(c.prose&&c.prose[key])||fallbackProse(key,p,c.name);
    const vis=visualFor(key,p);
    const body = key==="actions"
      ? actionsHTML(p)
      : `<p class="prose">${esc(prose)}</p>
         ${bigFor(key,p)?`<div class="big" style="font-size:clamp(26px,4vw,40px)">${bigFor(key,p)}</div>`:""}
         ${vis?`<div class="visual">${vis}</div>`:""}
         <details><summary>How we know this</summary>
           ${tableFor(key,p)}
           <div class="method">${esc(p.method||"")}</div>
         </details>`;
    return `<details><summary>${esc(meta[0])}</summary><div class="eyebrow">${esc(meta[1])}</div>${body}</details>`;
  }).join("");
}

function renderClient(id){
  const opts=Object.entries(DATA.clients).map(([cid,c])=>`<option value="${esc(c.name)}" data-id="${cid}">`).join("");
  const search=`<div class="searchbox">
    <label class="eyebrow" for="csearch">Find a client</label><br>
    <input id="csearch" list="clist" placeholder="Type a client name…" autocomplete="off" aria-label="Find a client">
    <datalist id="clist">${opts}</datalist></div>`;
  const c=DATA.clients[id];
  if(!c){
    app.innerHTML=`<div class="wrap" style="padding-top:26px"><div class="eyebrow">Prescribe</div>
      <h1 style="font-size:clamp(24px,3.4vw,32px);margin-top:8px">The client 360</h1>${search}
      <p class="insuf">Pick a client above to open their 360.</p></div>`;
    wireSearch(); return;
  }
  const hh=c.household||{}, seg=c.segment||{}, ch=c.churn||{}, pack=c.pack||{};
  const segChip=seg.segment?`<button class="chip on" onclick="location.hash='segment/${slug(seg.segment)}'">${esc(seg.segment)}</button>`:"";
  const hchips=[hh.name?`<span class="hchip">🏠 ${esc(hh.name)} · ${hh.members} member${hh.members===1?"":"s"}</span>`:"",
    ...(c.chips||[]).map(ch2=>`<span class="hchip">${esc(ch2)}</span>`)].join("");
  const mv=(pack.map && !pack.map.insufficient)?pack.map.total_mv:ch.mv;
  const tenure=(pack.map && !pack.map.insufficient)?pack.map.tenure_years:null;
  const habitsOK=pack.habits && !pack.habits.insufficient;

  const wins=clientWins(c), costs=clientCosts(c);
  const winsHTML=wins.map(w=>`<div class="win"><div class="verb">${esc(w.t)}</div>${w.v?`<div class="big" style="font-size:clamp(24px,3.6vw,34px)">${lcr(w.v)}</div>`:""}<p style="color:var(--muted);font-size:.9rem;margin:4px 0 0">${esc(w.d)}</p></div>`).join("");
  const costsHTML=costs.length
    ? costs.map(w=>`<div class="act" style="border-left-color:var(--warn)"><div class="verb">${esc(w.t)}</div>${w.v?`<div class="big" style="font-size:clamp(22px,3.2vw,30px)">${lcr(w.v)}</div>`:""}<p style="color:var(--muted);font-size:.9rem;margin:4px 0 0">${esc(w.d)}</p></div>`).join("")
    : `<p class="insuf">${seg.segment==="Too New to Tell"?"Not enough history yet to assess behaviour costs.":"No costly habits worth flagging — clean behaviour record."}</p>`;

  const floor=renderFloor(c);

  app.innerHTML=`<div class="wrap" style="padding-top:22px">
    <div class="eyebrow">Prescribe · client 360</div>${search}

    <div class="profile">
      <h1>${esc(c.name)}</h1>
      <div>${hchips}${segChip?" "+segChip:""}</div>
      <div style="display:flex;flex-wrap:wrap;gap:26px;margin-top:14px;align-items:center">
        <div><div class="eyebrow">Book value</div><div class="big" style="font-size:clamp(24px,3.6vw,36px)">${lcr(mv)}</div></div>
        ${tenure!=null?`<div><div class="eyebrow">Years with us</div><div class="big" style="font-size:clamp(24px,3.6vw,36px)">${tenure}</div></div>`:""}
        ${ch.score!=null?`<div><div class="eyebrow">Churn risk</div>${svgGauge(ch.score,ch.score>=66?"var(--crit)":ch.score>=33?"var(--warn)":"var(--good)","Churn risk score")}</div>`:""}
        ${habitsOK&&pack.habits.panic_share!=null?`<div><div class="eyebrow">Freak-out score</div><div class="big" style="font-size:clamp(24px,3.6vw,36px)">${Math.round(pack.habits.panic_share*100)}%</div></div>`:""}
      </div>
    </div>

    <div class="section"><div class="eyebrow">The story</div><h3>Value over time</h3>
      ${svgStoryCurve(c.curve)}
    </div>

    <div class="section"><div class="eyebrow">The floor</div><h3>What they hold</h3>
      ${floor.donut}
      <div style="margin-top:16px">${renderOverlap(c)}</div>
      <details><summary>Holdings, by asset class</summary>${floor.table}</details>
    </div>

    <div class="section"><div class="eyebrow">What they did right</div><h3>Wins, in rupees</h3>
      <div style="display:flex;flex-wrap:wrap;gap:14px">${winsHTML}</div>
    </div>

    <div class="section"><div class="eyebrow">Areas of improvement</div><h3>What their habits cost</h3>
      ${costsHTML}
    </div>

    <div class="section"><div class="eyebrow">Changes we recommend</div><h3>What to do next, and why</h3>
      ${recommendHTML(c)}
    </div>

    <div class="section"><div class="eyebrow">Seven-prompt MF audit</div><h3>Every fund, under one lens</h3>
      ${sevenPromptHTML(c)}
    </div>

    <div class="section"><div class="eyebrow">Audit trail</div><h3>How we know all of this</h3>
      ${auditExpanders(c)}
    </div>

    <div class="foot">Every number above is computed from ${esc(c.name)}'s own transaction and holdings history, as on ${esc(DATA.asof)}.</div>
  </div>`;
  wireSearch();
}
function wireSearch(){
  const inp=document.getElementById("csearch"); if(!inp) return;
  inp.onchange=()=>{
    const opt=[...document.querySelectorAll("#clist option")].find(o=>o.value===inp.value);
    if(opt) location.hash="client/"+opt.dataset.id;
  };
}

nav();
</script>
"""


if __name__ == "__main__":
    sys.exit(main())
