"""Client 360 page: the `#client/<id>` route, six sections per spec §8, for
a handful of real embedded clients (Task 6 embeds 3; Task 7 wires the rest of
the book through the same render layer unchanged). Every section below is
built from the SAME shared primitives page_holdings.py/page_behaviour.py use
— exhibit()/drawer()/data_table()/chart_spec() — no bespoke Client-360-only
rendering pattern. Each client's own dict already exists in full at
book["client360"][client_id] (data_client360.py + data_client360_behaviour.py,
Task 2); this module only reshapes it for the chart/table contracts already
established by those two sibling pages, exactly like _q2's dumbbell_rows or
_b3's crisis-window year-fraction reshape — no re-derivation, no new math.

render_client_page() wraps each client's whole block in one
id="client/<client_id>" container (literally containing the slash) — the
only thing client_link() ever points at, per render.py's own docstring.
Every exhibit id inside is namespaced client-{id}-* so multiple clients can
render side by side in one document without id collisions (mirrors
client_index_table()'s own section_id parametrization for the same reason).
"""

from __future__ import annotations

from datetime import date

from .data import lcr_py
from .data_client360 import CURVE_EVENT_KINDS
from .render import (
    chart_spec,
    chip,
    data_table,
    esc,
    exhibit,
    method_note,
    paragraph,
    sticky_subnav,
)

FRAMING = {
    "header": "Who this client is, how long they've been with the firm, and what their "
    "money actually did — put in, taken out, worth today.",
    "timeline": "This client's value over time against what they actually put in, with "
    "the moments (panics, big flows, stopped SIPs) marked on it.",
    "funds": "What does this one client actually own — every fund, its category, its "
    "value, and whether it beat its benchmark.",
    "label": "Do this client's fund labels match their actual contents?",
    "sector": "Look through every fund this client holds to the stocks and sectors "
    "underneath.",
    "overlap": "Do this client's own funds duplicate each other's holdings?",
    "fees": "What is this client actually paying, in rupees, for the funds they hold?",
    "cutlist": "What would we cut for this client, and why — same evidence used book-wide.",
    "behaviour": "This client's own crisis flows, advised switches, SIP streak, and "
    "dividend leakage.",
    "whatifs": "Four honest replays of this client's own real cash flows under a "
    "different choice.",
}

# Display labels for the 4 confirmed-distinct event kinds (data_client360.py's
# CURVE_EVENT_KINDS) — duplicated as render-layer text, not re-derived.
CURVE_EVENT_LABELS = {
    "panic_sell": "Panic sell",
    "big_inflow": "Big inflow",
    "big_outflow": "Big outflow",
    "sip_stop": "SIP stop",
}

# Same B5 what-if scenario labels/assumptions (data_behaviour.b5_what_if_machine's
# own text, verbatim) — the per-client replay is the identical formula, just not
# summed across clients, so the same real wording applies.
SCENARIO_META = {
    "cf_index_rs": {
        "label": "If every rupee had gone into the index fund instead",
        "assumption": "a historical replay of the same external flows into the Nifty-50 "
        "index fund at the same dates — assumes the client would have made the exact same "
        "deposits/withdrawals on the exact same dates regardless of which fund held the "
        "money, which is itself an assumption, not a certainty.",
    },
    "cf_no_panic_rs": {
        "label": "If drawdown-window sells had been held instead",
        "assumption": "we assume panic-sold units are simply held today; proceeds are NOT "
        "reinvested elsewhere — a real ceiling on the foregone gain, not the actual missed "
        "return.",
    },
    "cf_sip_alive_rs": {
        "label": "If this client's stopped SIPs had kept running to today",
        "assumption": "continues the SIP at its own last-6-month median amount into the "
        "same scheme all the way to today — not a guarantee the client would have kept "
        "paying that long.",
    },
    "cf_no_switch_rs": {
        "label": "If every advised switch had stayed in the source fund",
        "assumption": "a historical replay of the source fund's own NAV vs the destination "
        "fund's, from the switch date to today — assumes the client would have made no "
        "other change.",
    },
}

_C, _F = {"numeric": True}, {"numeric": True, "fmt": lcr_py}


def _cols(*specs: tuple[str, str, dict]) -> list[dict]:
    return [{"key": k, "label": lb, **extra} for k, lb, extra in specs]


COLS_HEADER = _cols(
    ("client_id", "Client", {}), ("grew_pct_per_year", "Grew %/yr", _C), ("worth_now_rs", "Worth now", _F)
)
COLS_TIMELINE = _cols(("month", "Month", {}), ("value_rs", "Value", _F))
COLS_FUNDS = _cols(
    ("fund", "Fund", {}), ("category", "Category", {}), ("value_rs", "Value", _F), ("verdict", "Verdict", {})
)
COLS_LABEL = _cols(
    ("fund", "Fund", {}), ("category", "Category", {}), ("verdict", "Verdict", {}), ("value_rs", "Value", _F)
)
COLS_SECTOR = _cols(("bucket", "Bucket", {}), ("sector", "Sector", {}), ("exposure_rs", "Exposure", _F))
COLS_BUCKET = _cols(("bucket", "Bucket", {}), ("pct", "% of exposure", _C))
COLS_OVERLAP = _cols(("fund_a", "Fund A", {}), ("fund_b", "Fund B", {}), ("overlap_pct", "Overlap %", _C))
COLS_FEES_SAMPLE = _cols(("fund", "Fund", {}), ("expense_ratio_pct", "Expense ratio %", _C))
COLS_FEES_FULL = _cols(
    ("fund", "Fund", {}), ("expense_ratio_pct", "Expense ratio %", _C), ("value_rs", "Value", _F)
)
COLS_CUTLIST = _cols(
    ("fund", "Fund", {}),
    ("reason", "Reason", {}),
    ("chips", "Chips", {}),
    ("exit_tax_rs", "Exit tax", _F),
    ("unwind_order", "Order", {}),
)
COLS_SWITCHES_SAMPLE = _cols(("switch_date", "Date", {}), ("extra_growth_1y_pp", "Extra growth 1y (pp)", _C))
COLS_SWITCHES_FULL = _cols(
    ("switch_date", "Date", {}),
    ("from_fund", "From", {}),
    ("to_fund", "To", {}),
    ("extra_growth_1y_pp", "Extra growth 1y (pp)", _C),
    ("extra_growth_1y_rs", "Extra growth 1y", _F),
)
COLS_WHATIFS = _cols(
    ("client_id", "Client", {}),
    ("cf_index_rs", "If indexed", _F),
    ("cf_no_panic_rs", "If held", _F),
    ("cf_sip_alive_rs", "If SIP alive", _F),
    ("cf_no_switch_rs", "If no switch", _F),
)


def _insufficient(section_id: str, eyebrow: str, framing: str, d: dict) -> str:
    return exhibit(section_id, eyebrow, framing, d["message"], None, [], [], d["working"], [])


def _yfrac(iso_date: str) -> float:
    d = date.fromisoformat(iso_date)
    return round(d.year + (d.timetuple().tm_yday - 1) / 365.0, 4)


def _header(book: dict, cid: int) -> str:
    d = book["client360"][cid]["header"]
    sid = f"client-{cid}-header"
    if d.get("insufficient"):
        return _insufficient(sid, "Client 360 · Header", FRAMING["header"], d)
    kpis = [
        {"label": "With firm since", "value": str(d["since_year"]) if d["since_year"] else "—"},
        {"label": "Put in", "value": lcr_py(d["gross_in_rs"])},
        {"label": "Took out", "value": lcr_py(d["gross_out_rs"])},
        {"label": "Worth now", "value": lcr_py(d["worth_now_rs"])},
        {"label": "Grew at", "value": f"{d['grew_pct_per_year']:+.2f}%/yr"},
    ]
    body_extra = paragraph(
        f"Family group: {d['family_group'] or '—'} · Segment: {d.get('segment') or '—'}.",
        cls="method",
    )
    return exhibit(
        sid,
        f"Client 360 · {d['name'] or f'Client {cid}'}",
        FRAMING["header"],
        d["verdict"],
        d["honesty"],
        kpis,
        [],
        d["working"],
        COLS_HEADER,
        body_extra=body_extra,
    )


def _timeline(book: dict, cid: int) -> str:
    d = book["client360"][cid]["timeline"]
    sid = f"client-{cid}-timeline"
    # ponytail: timeline's own "insufficient" key double-books as the real
    # <70%-coverage flag on a POPULATED row (not just the true empty state) —
    # "message" only exists on the true no-rows empty state, so it (not
    # "insufficient") is the correct empty-state discriminator here.
    if d.get("message"):
        return _insufficient(sid, "Timeline", FRAMING["timeline"], d)
    value_points = [{"x": _yfrac(f"{m}-01"), "y": v} for m, v in zip(d["months"], d["values_rs"])]
    flow_points = [
        {"x": _yfrac(f"{m}-01"), "y": v} for m, v in zip(d["months"], d["cumulative_net_flow_rs"])
    ]
    events = [
        {"x": _yfrac(e["date"]), "label": CURVE_EVENT_LABELS.get(e["kind"], e["kind"]), "kind": e["kind"]}
        for e in d["events"]
    ]
    shaded = [{"x0": _yfrac(w["start"]), "x1": _yfrac(w["end"])} for w in d["crisis_windows"]]
    charts = [
        chart_spec(
            "lineArea",
            "Value vs cumulative net-invested (₹)",
            f"{sid}-chart",
            [
                {"label": "Value", "points": value_points, "emphasis": True},
                {"label": "Cumulative net invested", "points": flow_points},
            ],
            {"xLabel": "year", "yLabel": "₹", "shadedWindows": shaded, "events": events},
        )
    ]
    kpis = [
        {"label": "Months tracked", "value": str(len(d["months"]))},
        {
            "label": "Coverage",
            "value": f"{d['coverage_pct']:.0f}%" if d["coverage_pct"] is not None else "—",
        },
        {"label": "Flagged events", "value": str(len(d["events"]))},
    ]
    legend = "Event markers: " + ", ".join(CURVE_EVENT_LABELS[k] for k in CURVE_EVENT_KINDS) + "."
    return exhibit(
        sid,
        "Timeline",
        FRAMING["timeline"],
        d["verdict"],
        d["honesty"],
        kpis,
        charts,
        d["working"],
        COLS_TIMELINE,
        body_extra=method_note(legend),
    )


def _funds(book: dict, cid: int) -> str:
    d = book["client360"][cid]["funds_table"]
    sid = f"client-{cid}-funds"
    if d.get("insufficient"):
        return _insufficient(sid, "Q1 · What does this client own?", FRAMING["funds"], d)
    kpis = [
        {"label": "Held funds", "value": str(d["n_funds"])},
        {"label": "Total value", "value": lcr_py(d["total_value_rs"])},
        {"label": "Scored for fund performance", "value": f"{d['n_scored']} of {d['n_funds']}"},
    ]
    charts = [
        chart_spec(
            "horizontalBar",
            "Held funds by value (₹cr)",
            f"{sid}-bar",
            [{"label": f["fund"], "value": (f["value_rs"] or 0.0) / 1e7} for f in d["funds"][:15]],
            {},
        )
    ]
    return exhibit(
        sid,
        "Q1 · What does this client own?",
        FRAMING["funds"],
        d["verdict"],
        d["honesty"],
        kpis,
        charts,
        d["working"],
        COLS_FUNDS,
        body_extra=data_table(d["funds"], COLS_FUNDS),
    )


def _label(book: dict, cid: int) -> str:
    d = book["client360"][cid]["label_check"]
    sid = f"client-{cid}-label"
    if d.get("insufficient"):
        return _insufficient(sid, "Q2 · Does the label match?", FRAMING["label"], d)
    kpis = [
        {"label": "Label-checked funds", "value": str(d["n_funds"])},
        {"label": "Mismatch funds", "value": str(d["n_mismatch"])},
        {"label": "₹ off-label", "value": lcr_py(d["mismatch_value_rs"])},
    ]
    return exhibit(
        sid,
        "Q2 · Does the label match?",
        FRAMING["label"],
        d["verdict"],
        d["honesty"],
        kpis,
        [],
        d["working"],
        COLS_LABEL,
        body_extra=data_table(d["funds"], COLS_LABEL),
    )


def _sector(book: dict, cid: int) -> str:
    d = book["client360"][cid]["sector_lookthrough"]
    sid = f"client-{cid}-sector"
    if d.get("insufficient"):
        return _insufficient(sid, "Q3 · Sector look-through", FRAMING["sector"], d)
    kpis = [
        {"label": "Total look-through exposure", "value": lcr_py(d["total_exposure_rs"])},
        {
            "label": "Sector-identified coverage",
            "value": f"{d['identified_pct']:.1f}%" if d["identified_pct"] is not None else "—",
        },
    ]
    top_sectors = sorted(d["sector_pct"].items(), key=lambda kv: -kv[1])[:10]
    charts = [
        chart_spec(
            "horizontalBar",
            "Sector exposure (% of look-through value)",
            f"{sid}-bar",
            [{"label": s, "value": pct} for s, pct in top_sectors],
            {},
        )
    ]
    bucket_rows = [{"bucket": b, "pct": pct} for b, pct in d["bucket_pct"].items()]
    return exhibit(
        sid,
        "Q3 · Sector look-through",
        FRAMING["sector"],
        d["verdict"],
        d["honesty"],
        kpis,
        charts,
        d["working"],
        COLS_SECTOR,
        body_extra=data_table(bucket_rows, COLS_BUCKET),
    )


def _overlap(book: dict, cid: int) -> str:
    d = book["client360"][cid]["overlap"]
    sid = f"client-{cid}-overlap"
    kpis = [
        {"label": f"Pairs > {int(d['threshold_pct'])}%", "value": str(d["n_pairs_above_threshold"])},
        {"label": "Fund pairs held", "value": str(d["n_pairs"])},
    ]
    charts = []
    if d["pairs"]:
        labels = sorted({p["fund_a"] for p in d["pairs"]} | {p["fund_b"] for p in d["pairs"]})
        cells = []
        for p in d["pairs"]:
            cells.append({"row": p["fund_a"], "col": p["fund_b"], "value": p["overlap_pct"]})
            cells.append({"row": p["fund_b"], "col": p["fund_a"], "value": p["overlap_pct"]})
        charts = [
            chart_spec(
                "heatmap",
                "Fund overlap (% common holdings)",
                f"{sid}-heatmap",
                {"rowLabels": labels, "colLabels": labels, "cells": cells},
                {"max": 100},
            )
        ]
    return exhibit(
        sid,
        "Q3 · Fund-pair overlap",
        FRAMING["overlap"],
        d["verdict"],
        d["honesty"],
        kpis,
        charts,
        d["working"],
        COLS_OVERLAP,
    )


def _fees(book: dict, cid: int) -> str:
    d = book["client360"][cid]["fees_and_cuts"]
    sid = f"client-{cid}-fees"
    kpis = [
        {"label": "Avoidable fees / yr", "value": lcr_py(d["fee_save_yr_rs"])},
        {"label": "Index ER assumed", "value": f"{d['index_er_assumed_pct']:.2f}%"},
        {"label": "Held funds with a real ER", "value": str(len(d["held_fund_ers"]))},
    ]
    charts = []
    if d["held_fund_ers"]:
        charts = [
            chart_spec(
                "horizontalBar",
                "Expense ratio by held fund (%)",
                f"{sid}-bar",
                [{"label": f["fund"], "value": f["expense_ratio_pct"]} for f in d["held_fund_ers"]],
                {},
            )
        ]
    return exhibit(
        sid,
        "Q4 · What this client actually pays",
        FRAMING["fees"],
        d["verdict"],
        d["honesty"],
        kpis,
        charts,
        d["working"],
        COLS_FEES_SAMPLE,
        body_extra=data_table(d["held_fund_ers"], COLS_FEES_FULL),
    )


def _cutlist(book: dict, cid: int) -> str:
    d = book["client360"][cid]["fees_and_cuts"]
    sid = f"client-{cid}-cutlist"
    evidence = d["cut_evidence"]
    kpis = [
        {"label": "Funds to cut", "value": str(len(evidence))},
        {"label": "Funds to keep", "value": str(len(d["keep"] or []))},
        {
            "label": "Est. exit tax",
            "value": lcr_py(sum(e["exit_tax_rs"] or 0.0 for e in evidence)),
        },
    ]
    chip_counts: dict[str, int] = {}
    for e in evidence:
        for c in e["chips"]:
            chip_counts[c] = chip_counts.get(c, 0) + 1
    chips_html = "".join(
        f'<span class="chip chip--evidence">{esc(k)} ({v})</span> ' for k, v in chip_counts.items()
    )
    verdict = (
        f"{len(evidence)} fund(s) we'd cut for this client, {len(d['keep'] or [])} to keep."
        if evidence
        else "no funds flagged to cut for this client."
    )
    return exhibit(
        sid,
        "Q7 · The cut list, for this client",
        FRAMING["cutlist"],
        verdict,
        d["honesty"],
        kpis,
        [],
        d["working"],
        COLS_FEES_SAMPLE,
        body_extra=f"<div>{chips_html}</div>" + data_table(evidence, COLS_CUTLIST),
    )


def _behaviour(book: dict, cid: int) -> str:
    d = book["client360"][cid]["behaviour"]
    sid = f"client-{cid}-behaviour"
    if d.get("insufficient"):
        return _insufficient(sid, "Behaviour", FRAMING["behaviour"], d)
    kpis = [
        {"label": "Sold below cost", "value": lcr_py(d["panic_loss_out_rs"])},
        {
            "label": "Panic share of lifetime outflows",
            "value": f"{d['panic_share'] * 100:.0f}%" if d["panic_share"] is not None else "—",
        },
        {"label": "Dividend leakage", "value": lcr_py(d["div_leak_rs"])},
        {"label": "SIP streams", "value": f"{d['sip_active']} active / {d['sip_stopped']} stopped"},
        {"label": "SIP stops mid-drawdown", "value": str(d["sip_stops_in_drawdown"])},
    ]
    return exhibit(
        sid,
        "Behaviour: crisis flows, switches, SIP streams",
        FRAMING["behaviour"],
        d["verdict"],
        d["honesty"],
        kpis,
        [],
        d["working"],
        COLS_SWITCHES_SAMPLE,
        body_extra=data_table(d["switches"], COLS_SWITCHES_FULL),
    )


def _whatifs(book: dict, cid: int) -> str:
    d = book["client360"][cid]["what_ifs"]
    sid = f"client-{cid}-whatifs"
    if d.get("insufficient"):
        return _insufficient(sid, "What-ifs", FRAMING["whatifs"], d)
    # Same B5 layout rule: each scenario's assumption card renders ABOVE its
    # headline number (body_extra, since kpis always render before body_extra
    # in exhibit()'s fixed order).
    order = ["cf_index_rs", "cf_no_panic_rs", "cf_sip_alive_rs", "cf_no_switch_rs"]
    cards = []
    for key in order:
        s = d["scenarios"][key]
        meta = SCENARIO_META[key]
        cards.append(
            '<div class="chart-card">'
            + method_note(meta["assumption"])
            + chip(s["honesty"])
            + '<div class="kpi-tile"><div class="kpi-label">'
            + esc(meta["label"])
            + '</div><div class="kpi-value">'
            + esc(lcr_py(s["total_rs"]))
            + "</div></div></div>"
        )
    return exhibit(
        sid,
        "What-if machine, for this client",
        FRAMING["whatifs"],
        d["verdict"],
        d["honesty"],
        [],
        [],
        d["working"],
        COLS_WHATIFS,
        body_extra=f'<div class="chart-row">{"".join(cards)}</div>',
    )


CLIENT_SECTIONS = (
    _header,
    _timeline,
    _funds,
    _label,
    _sector,
    _overlap,
    _fees,
    _cutlist,
    _behaviour,
    _whatifs,
)

MINI_INDEX_LABELS = (
    ("header", "Header"),
    ("timeline", "Timeline"),
    ("funds", "Funds"),
    ("label", "Label"),
    ("sector", "Sector"),
    ("overlap", "Overlap"),
    ("fees", "Fees"),
    ("cutlist", "Cut list"),
    ("behaviour", "Behaviour"),
    ("whatifs", "What-if"),
)


def render_client_page(book: dict, client_ids: list[int]) -> str:
    """Renders every client in `client_ids` as one id="client/<id>" block,
    literal DOM siblings (render.py has no client-side router — see its
    render_document() docstring). client_link() already emits #client/<id>
    everywhere a client_id is shown book-wide; this is the element the
    browser scrolls to."""
    parts = []
    for cid in client_ids:
        c = book["client360"][cid]
        name = c["header"].get("name") or f"Client {cid}"
        mini = [(f"client-{cid}-{slug}", label) for slug, label in MINI_INDEX_LABELS]
        body = paragraph(f"Client 360 · {name} (client_id {cid}).") + sticky_subnav(mini)
        body += "".join(fn(book, cid) for fn in CLIENT_SECTIONS)
        parts.append(f'<div id="client/{cid}">{body}</div>')
    return "".join(parts)
