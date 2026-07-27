"""Holdings page: Q1-Q7 + client index. Verbatim seven-prompt framing from
docs/wealth-seven-prompts-framework.md (quote intent faithfully, no
paraphrase). Every chart below reads a field that already exists in the qN
dict, or a trivial build-time reshape of one (renaming keys / mapping IDs to
names) to match a chart form's contract — no re-derivation, no new data.py
functions.
"""

from __future__ import annotations

from .data import lcr_py
from .render import (
    chart_spec,
    client_index_table,
    connected_components_by_threshold,
    data_table,
    esc,
    exhibit,
    method_note,
    paragraph,
    sticky_subnav,
)

FRAMING = {
    "q1": "pull out, as one clean table, every scheme with SEBI category and AMC, "
    "invested/current/gain, direct-vs-regular, weight %, total schemes and AMCs.",
    "q2": "check actual large/mid/small split vs the SEBI minimum for its category... "
    "if the fund doesn't match its label, say so plainly.",
    "q3": "Owning eight funds isn't diversification if they hold the same thirty stocks.",
    "q4": "act like a cost auditor, not a salesman... every figure in rupees.",
    "q5": "A single great year can carry a ten-year number. Strip that year out and "
    "tell me what's left.",
    "q6": "honest empty-state per Task 1: we don't have a factsheet/SID feed to answer this.",
    "q7": "Do not suggest new funds. Judge only what I already own. If the data doesn't "
    "support a cut, say so plainly.",
}

MINI_INDEX = [
    ("q1", "Q1 · Own"),
    ("q2", "Q2 · Label"),
    ("q3", "Q3 · Overlap"),
    ("q4", "Q4 · Pay"),
    ("q5", "Q5 · Benchmark"),
    ("q6", "Q6 · Bloat"),
    ("q7", "Q7 · Cut list"),
    ("client-index", "Clients"),
]

_C, _F = {"numeric": True}, {"numeric": True, "fmt": lcr_py}
_LINK = {"link": "name"}  # client_id column -> client_link(id, name)


def _cols(*specs: tuple[str, str, dict]) -> list[dict]:
    return [{"key": k, "label": lb, **extra} for k, lb, extra in specs]


COLS_Q1 = _cols(
    ("client_id", "Client", _LINK),
    ("fund", "Fund", {}),
    ("category", "Category", {}),
    ("amc", "AMC", {}),
    ("value_rs", "Value", _F),
)
COLS_Q2 = _cols(
    ("client_id", "Client", _LINK),
    ("fund", "Fund", {}),
    ("category", "Category", {}),
    ("verdict", "Verdict", {}),
    ("value_rs", "Value", _F),
)
COLS_Q3 = _cols(
    ("client_id", "Client", _LINK),
    ("scheme_a", "Fund A", {}),
    ("scheme_b", "Fund B", {}),
    ("overlap_pct", "Overlap %", _C),
)
COLS_Q4 = _cols(
    ("client_id", "Client", _LINK),
    ("evidence", "Evidence", {}),
    ("est_value_rs", "Est. value", _F),
)
COLS_Q5 = _cols(("scheme_id", "Scheme ID", {}), ("fund", "Fund", {}), ("verdict", "Verdict", {}))
COLS_Q7 = _cols(
    ("client_id", "Client", _LINK),
    ("fund", "Fund", {}),
    ("reason", "Reason", {}),
    ("chips", "Chips", {}),
    ("exit_tax_rs", "Exit tax", _F),
    ("fee_save_yr_rs", "Fee save/yr", _F),
)


def _q1(book: dict) -> str:
    q = book["q1"]
    median = q["funds_per_client_hist"].get("median")
    kpis = [
        {"label": "Total value", "value": lcr_py(q["total_value_rs"])},
        {"label": "Funds held", "value": str(q["n_funds"])},
        {"label": "Fund houses", "value": str(q["n_amcs"])},
        {"label": "Median funds/client", "value": str(int(median)) if median is not None else "—"},
    ]
    charts = [
        chart_spec(
            "treemap",
            "Value by category → AMC → fund",
            "q1-treemap",
            "DATA.q1.treemap",
            {"levels": ["category", "amc", "fund"], "valueKey": "value_cr"},
        ),
        chart_spec(
            "histogram",
            "Funds held per client",
            "q1-hist",
            "DATA.q1.funds_per_client_hist",
            {"unit": " funds"},
        ),
        chart_spec(
            "horizontalBar",
            "Top 10 funds by value (₹cr)",
            "q1-top10",
            [{"label": r["fund"], "value": r["value_cr"]} for r in q["top10_funds"]],
            {},
        ),
    ]
    return exhibit(
        "q1",
        "Q1 · What do you actually own?",
        FRAMING["q1"],
        q["verdict"],
        q["honesty"],
        kpis,
        charts,
        q["working"],
        COLS_Q1,
    )


def _q2(book: dict) -> str:
    q = book["q2"]
    kpis = [
        {"label": "₹ off-label", "value": lcr_py(q["mismatch_value_rs"])},
        {"label": "Mismatch funds", "value": str(q["n_mismatch_funds"])},
        {"label": "Disclosure month", "value": q["as_of_month"]},
    ]
    dumbbell_rows = [
        {
            "label": f"{b['category']} · {leg['metric']}",
            "a": leg["actual_pct"],
            "b": leg["mandate_pct"],
        }
        for b in q["category_bars"]
        for leg in b["legs"]
    ]
    offenders_bar = [{"label": o["fund"], "value": o["shortfall_pct"]} for o in q["offenders"][:10]]
    charts = [
        chart_spec(
            "dumbbell",
            "Actual mix vs SEBI mandate (%)",
            "q2-mandate",
            dumbbell_rows,
            {"aLabel": "Actual %", "bLabel": "Mandate %"},
        ),
        chart_spec(
            "horizontalBar", "Worst offenders by shortfall (pp)", "q2-offenders", offenders_bar, {}
        ),
    ]
    body_extra = data_table(
        q["offenders"],
        [
            {"key": "fund", "label": "Fund"},
            {"key": "category", "label": "Category"},
            {"key": "shortfall_pct", "label": "Shortfall (pp)", "numeric": True},
            {"key": "value_rs", "label": "Value", "numeric": True, "fmt": lcr_py},
        ],
    )
    return exhibit(
        "q2",
        "Q2 · The Label Lie",
        FRAMING["q2"],
        q["verdict"],
        q["honesty"],
        kpis,
        charts,
        q["working"],
        COLS_Q2,
        body_extra=body_extra,
    )


def _q3(book: dict) -> str:
    q = book["q3"]
    median = q["median_overlap_pct"]
    kpis = [
        {
            "label": "Median overlap (held pairs)",
            "value": f"{median:.0f}%" if median is not None else "—",
        },
        {"label": f"Pairs > {int(q['threshold_pct'])}%", "value": str(q["pairs_above_threshold"])},
        {"label": "₹ duplicated", "value": lcr_py(q["rupee_duplicated_rs"])},
    ]
    fund_names = {f["scheme_id"]: f["fund"] for f in q["top15_funds"]}
    labels = [f["fund"] for f in q["top15_funds"]]
    cells = []
    for p in q["top15_pairwise"]:
        a, b = fund_names[p["scheme_a"]], fund_names[p["scheme_b"]]
        cells.append({"row": a, "col": b, "value": p["overlap_pct"]})
        cells.append({"row": b, "col": a, "value": p["overlap_pct"]})
    charts = [
        chart_spec(
            "heatmap",
            "Top-15 fund overlap (% common holdings)",
            "q3-heatmap",
            {"rowLabels": labels, "colLabels": labels, "cells": cells},
            {"max": 100},
        ),
    ]
    clusters = connected_components_by_threshold(
        q["top15_pairwise"], "scheme_a", "scheme_b", "overlap_pct", fund_names, q["threshold_pct"]
    )
    cluster_html = "".join(
        method_note(f"These {len(c)} funds effectively overlap: {', '.join(c)}.")
        for c in clusters
        if len(c) > 1
    )
    evidence_table = data_table(
        q["top15_stock_matrix"],
        [
            {"key": "name", "label": "Stock"},
            {"key": "n_funds_holding", "label": "# funds", "numeric": True},
            {"key": "total_weight_pct", "label": "Combined weight %", "numeric": True},
        ],
    )
    return exhibit(
        "q3",
        "Q3 · The Overlap Trap",
        FRAMING["q3"],
        q["verdict"],
        q["honesty"],
        kpis,
        charts,
        q["working"],
        COLS_Q3,
        body_extra=cluster_html + evidence_table,
    )


def _q4(book: dict) -> str:
    q = book["q4"]
    kpis = [
        {"label": "Avoidable fees / yr", "value": lcr_py(q["total_fee_save_yr_rs"])},
        {"label": "Clients paying it", "value": str(q["n_clients_paying"])},
    ]
    dumbbell_rows = [
        {"label": d["category"], "a": d["regular_actual_pct"], "b": d["direct_estimate_pct"]}
        for d in q["dumbbell"]
        if d["direct_estimate_pct"] is not None
    ]
    save_cr = (q["total_fee_save_yr_rs"] or 0) / 1e7
    projection = [{"x": yr, "y": round(save_cr * yr, 2)} for yr in range(11)]
    charts = [
        chart_spec(
            "dumbbell",
            "Regular vs direct-plan expense ratio by category (%)",
            "q4-dumbbell",
            dumbbell_rows,
            {"aLabel": "Regular (actual)", "bLabel": "Direct (category est.)"},
        ),
        chart_spec(
            "lineArea",
            "Cumulative avoidable cost if nothing changes (₹cr)",
            "q4-projection",
            [{"label": "Cumulative avoidable cost", "points": projection, "emphasis": True}],
            {"xLabel": "years"},
        ),
    ]
    body_extra = method_note(
        "Projection assumes today's expense ratios held flat for 10 years — no "
        "compounding, no redemptions modeled."
    )
    return exhibit(
        "q4",
        "Q4 · What You Actually Pay",
        FRAMING["q4"],
        q["verdict"],
        q["honesty"],
        kpis,
        charts,
        q["working"],
        COLS_Q4,
        body_extra=body_extra,
    )


def _q5(book: dict) -> str:
    q = book["q5"]
    kpis = [
        {"label": "Funds beating benchmark", "value": f"{q['n_beating_funds']} of {q['n_funds']}"},
        {"label": "₹ in chronic laggards", "value": lcr_py(q["laggard_value_rs"])},
    ]
    excess_rows = [
        {
            "label": f"{f['fund']} (vs {f['benchmark_note']})"
            if f.get("benchmark_note")
            else f["fund"],
            "value": f["excess_return_pct"],
        }
        for f in q["funds"]
        if f["excess_return_pct"] is not None
    ]
    beat_ratio_rows = [
        {"label": f["fund"], "value": round(f["beat_ratio"] * 100, 1)}
        for f in q["funds"]
        if f["beat_ratio"] is not None
    ]
    charts = [
        chart_spec(
            "divergingBarStrip",
            "Excess return vs own benchmark (pp, full period)",
            "q5-excess",
            excess_rows,
            {},
        ),
        chart_spec(
            "horizontalBar",
            "Beat ratio — % of rolling windows beating benchmark",
            "q5-beatratio",
            beat_ratio_rows,
            {},
        ),
    ]
    return exhibit(
        "q5",
        "Q5 · Beat the Benchmark?",
        FRAMING["q5"],
        q["verdict"],
        q["honesty"],
        kpis,
        charts,
        q["working"],
        COLS_Q5,
    )


def _q6(book: dict) -> str:
    q = book["q6"]
    # ponytail/constraint-3: honest empty-state — no kpis/charts to invent,
    # working stays [] for inputs/assumptions/steps/sample_rows (rule is the
    # only non-empty part); validator exempts q6 from the "5 parts non-empty"
    # check for exactly this reason.
    return exhibit(
        "q6",
        "Q6 · The Bloat Check",
        FRAMING["q6"],
        q["question"],
        None,
        [],
        [],
        q["working"],
        [],
        body_extra=method_note(q["message"]),
    )


def _q7(book: dict) -> str:
    q = book["q7"]
    kpis = [
        {"label": "Clients affected", "value": f"{q['n_with_cut']} of {q['n_clients']}"},
        {"label": "Fee save / yr", "value": lcr_py(q["total_cut_fee_rs"])},
        {"label": "Duplication removed", "value": f"{q['duplication_removed_pct']:.0f}%"},
        {"label": "Est. exit tax", "value": lcr_py(q["total_exit_tax_rs"])},
    ]
    chip_rows = [{"label": k, "value": v} for k, v in q["chip_counts"].items()]
    charts = [
        chart_spec("horizontalBar", "Cut reasons (evidence chips)", "q7-chips", chip_rows, {})
    ]
    if q["sankey"]:
        sankey_rows = [
            {"from": e["from"], "to": e["to"], "value": e["n_clients"]} for e in q["sankey"]
        ]
        charts.append(
            chart_spec(
                "sankey",
                "Cut fund → kept fund (consolidation)",
                "q7-sankey",
                sankey_rows,
                {"valueLabel": "clients"},
            )
        )
    chip_links = {"off-label": "#q2", "duplicate": "#q3", "laggard": "#q5"}
    chips_html = "".join(
        f'<a class="chip chip--evidence" href="{chip_links.get(k, "#q7")}">{esc(k)} ({v})</a> '
        for k, v in q["chip_counts"].items()
    )
    return exhibit(
        "q7",
        "Q7 · The Cut List",
        FRAMING["q7"],
        q["verdict"],
        q["honesty"],
        kpis,
        charts,
        q["working"],
        COLS_Q7,
        body_extra=f"<div>{chips_html}</div>",
    )


def render_holdings_page(book: dict) -> str:
    n_clients = book["client_index"]["n_clients"]
    total_cr = (book["q1"]["total_value_rs"] or 0) / 1e7
    n_funds = book["q1"]["n_funds"]
    frame = paragraph(
        f"{n_clients} investors. ₹{total_cr:.0f}cr across {n_funds} funds. "
        "Seven questions any fee-only adviser would ask."
    )
    body = frame + sticky_subnav(MINI_INDEX)
    body += "".join(fn(book) for fn in (_q1, _q2, _q3, _q4, _q5, _q6, _q7))
    body += client_index_table(book["client_index"])
    return body
