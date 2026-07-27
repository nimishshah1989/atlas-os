"""Behaviour page: B1-B5 + client index. Every chart below reads a field
that already exists in the bN dict, or a trivial build-time reshape of one
(date-string -> year-fraction for the crisis-window shading, dict -> rows
for the what-if cards) to match a chart form's contract — no re-derivation,
no new data.py functions. Mirrors page_holdings.py's structure exactly.
"""

from __future__ import annotations

from datetime import date

from .data import lcr_py
from .render import (
    COL_MONEY,
    COL_NUMERIC,
    assumption_cards,
    chart_spec,
    client_index_table,
    data_table,
    exhibit,
    method_note,
    paragraph,
    sticky_subnav,
)
from .render import (
    cols as _cols,
)

FRAMING = {
    "b1": "Did the advice this book received actually beat just buying the index? "
    "Every rupee, every client, replayed against the Nifty-50 on the same dates.",
    "b2": "How investors cost themselves: the gap between what a fund earned and what "
    "the investor actually earned on their own money, timing included.",
    "b3": "The panic pattern: what clients sold, and when, during every real market "
    "drawdown — not a story about one crash, every crash in the data.",
    "b4": "Advice switches: every scheme-to-scheme move this book made, and whether "
    "the destination actually beat the source afterward.",
    "b5": "The what-if machine: four honest replays of the same real cash flows under "
    "a different choice — index instead, no panic-sells, SIPs never stopped, no switches.",
}

MINI_INDEX = [
    ("b1", "B1 · Advice vs index"),
    ("b2", "B2 · Behaviour gap"),
    ("b3", "B3 · Panic pattern"),
    ("b4", "B4 · Switches"),
    ("b5", "B5 · What-if"),
    ("client-index-behaviour", "Clients"),
]

_C, _F = COL_NUMERIC, COL_MONEY
_LINK = {"link": "name"}


COLS_B1 = _cols(
    ("client_id", "Client", _LINK),
    ("client_growth_pct", "Client %/yr", _C),
    ("index_growth_pct", "Index %/yr", _C),
    ("extra_growth_pp", "Extra growth (pp)", _C),
    ("approx", "Approx.", {}),
)
COLS_B2 = _cols(
    ("client_id", "Client", _LINK),
    ("scheme_id", "Scheme", {}),
    ("mwr_pct", "Investor %/yr", _C),
    ("twr_pct", "Fund %/yr", _C),
    ("gap_pp", "Gap (pp)", _C),
    ("gap_rs", "Gap", _F),
)
COLS_B3 = _cols(
    ("client_id", "Client", _LINK),
    ("panic_out_rs", "Sold in drawdown", _F),
    ("panic_loss_out_rs", "Sold below cost", _F),
    ("panic_share", "Panic share", _C),
    ("div_leak_rs", "Dividend leak", _F),
)
COLS_B4 = _cols(
    ("client_id", "Client", _LINK),
    ("switch_date", "Date", {}),
    ("from_fund", "From", {}),
    ("to_fund", "To", {}),
    ("amount_rs", "Amount", _F),
    ("extra_growth_1y_pp", "Extra growth 1y (pp)", _C),
)
COLS_B5 = _cols(
    ("client_id", "Client", _LINK),
    ("cf_index_rs", "If indexed", _F),
    ("cf_no_panic_rs", "If held", _F),
    ("cf_sip_alive_rs", "If SIP alive", _F),
    ("cf_no_switch_rs", "If no switch", _F),
)


def _b1(book: dict) -> str:
    q = book["b1"]
    kpis = [
        {"label": "Flow-complete clients", "value": f"{q['n_clean']} of {q['n_clients']}"},
        {"label": "Beating the index", "value": str(q["n_beating_clean"])},
        {
            "label": "Median extra growth",
            "value": f"{q['median_extra_growth_pp']:+.2f}pp/yr"
            if q["median_extra_growth_pp"] is not None
            else "—",
        },
    ]
    charts = [
        chart_spec(
            "histogram",
            "Extra growth vs index, per client (pp/yr)",
            "b1-hist",
            "DATA.b1.extra_growth_hist",
            {"unit": "pp"},
        ),
    ]
    return exhibit(
        "b1",
        "B1 · Did advice beat index?",
        FRAMING["b1"],
        q["verdict"],
        q["honesty"],
        kpis,
        charts,
        q["working"],
        COLS_B1,
    )


def _b2(book: dict) -> str:
    q = book["b2"]
    kpis = [
        {"label": "Client x scheme rows", "value": str(q["n_rows"])},
        {
            "label": "Median gap",
            "value": f"{q['median_gap_pp']:+.2f}pp/yr" if q["median_gap_pp"] is not None else "—",
        },
        {
            "label": "Invested-weighted gap",
            "value": f"{q['invested_weighted_gap_pp']:+.2f}pp/yr"
            if q["invested_weighted_gap_pp"] is not None
            else "—",
        },
        {"label": "Total gap", "value": lcr_py(q["total_gap_rs"])},
    ]
    charts = [
        chart_spec(
            "histogram",
            "Investor-vs-fund gap, per client x scheme (pp/yr)",
            "b2-hist",
            "DATA.b2.gap_hist",
            {"unit": "pp"},
        ),
    ]
    body_extra = method_note(
        "Part of any MWR-TWR gap is mechanical (Hayley, 2014) — a falling NAV right after "
        "an inflow drags the investor's own return below the fund's, regardless of skill."
    )
    return exhibit(
        "b2",
        "B2 · How investors cost themselves",
        FRAMING["b2"],
        q["verdict"],
        q["honesty"],
        kpis,
        charts,
        q["working"],
        COLS_B2,
        body_extra=body_extra,
    )


def _b3(book: dict) -> str:
    q = book["b3"]
    kpis = [
        {"label": "Drawdown windows", "value": str(q["n_windows"])},
        {"label": "Sold below cost", "value": lcr_py(q["total_panic_loss_rs"])},
        {"label": "Panic-heavy clients (>25%)", "value": str(q["n_panic_heavy_clients"])},
        {"label": "SIPs stopped mid-drawdown", "value": str(q["n_sip_stops_in_drawdown"])},
    ]

    # build-time reshape of crisis_windows' date strings into the year-fraction
    # x-coordinates bench_monthly already uses — a presentation transform for
    # the chart's shading, not new data (mirrors _q2's dumbbell_rows reshape).
    def _yfrac(s: str) -> float:
        d = date.fromisoformat(s)
        return round(d.year + (d.timetuple().tm_yday - 1) / 365.0, 4)

    shaded = [
        {"x0": _yfrac(w["start"]), "x1": _yfrac(w["trough_or_end"])} for w in q["crisis_windows"]
    ]
    charts = [
        chart_spec(
            "lineArea",
            "Nifty-50 index-fund NAV, with drawdown windows shaded",
            "b3-crisis",
            [{"label": "Index fund NAV", "points": q["bench_monthly"], "emphasis": True}],
            {"xLabel": "year", "yLabel": "NAV", "shadedWindows": shaded},
        ),
    ]
    return exhibit(
        "b3",
        "B3 · The panic pattern",
        FRAMING["b3"],
        q["verdict"],
        q["honesty"],
        kpis,
        charts,
        q["working"],
        COLS_B3,
    )


def _b4(book: dict) -> str:
    q = book["b4"]
    kpis = [
        {"label": "Paired switches", "value": str(q["n_switches"])},
        {
            "label": "Beating source fund (1y)",
            "value": f"{q['n_beating_1y']} of {q['n_scored_1y']}",
        },
        {
            "label": "Median extra growth (1y)",
            "value": f"{q['median_extra_growth_1y_pp']:+.2f}pp"
            if q["median_extra_growth_1y_pp"] is not None
            else "—",
        },
        {"label": "Push-waves detected", "value": str(q["n_waves"])},
    ]
    dumbbell_rows = [
        {"label": w["scheme"], "a": w["fwd1y_scheme_pct"], "b": w["fwd1y_index_pct"]}
        for w in q["waves"]
        if w["fwd1y_scheme_pct"] is not None and w["fwd1y_index_pct"] is not None
    ]
    charts = [
        chart_spec(
            "dumbbell",
            "Push-waves: scheme vs index forward 1y return (%)",
            "b4-waves",
            dumbbell_rows,
            {"aLabel": "Scheme fwd 1y %", "bLabel": "Index fwd 1y %"},
        ),
    ]
    body_extra = data_table(
        q["waves"],
        [
            {"key": "scheme", "label": "Scheme"},
            {"key": "window_start", "label": "Window start"},
            {"key": "window_end", "label": "Window end"},
            {"key": "n_clients", "label": "# clients", "numeric": True},
            {"key": "inflow_rs", "label": "Inflow", "numeric": True, "fmt": lcr_py},
        ],
    )
    return exhibit(
        "b4",
        "B4 · Advice switches",
        FRAMING["b4"],
        q["verdict"],
        q["honesty"],
        kpis,
        charts,
        q["working"],
        COLS_B4,
        body_extra=body_extra,
    )


def _b5(book: dict) -> str:
    q = book["b5"]
    kpis = [{"label": "Clients scored", "value": str(q["n_clients"])}]
    # Layout requirement (task-5 brief): each sub-exhibit's assumption card
    # renders ABOVE its headline number — see assumption_cards()'s docstring
    # for why this must be body_extra, not the generic `kpis` param.
    order = ["cf_index_rs", "cf_no_panic_rs", "cf_sip_alive_rs", "cf_no_switch_rs"]
    body_extra = assumption_cards([q["scenarios"][key] for key in order])
    return exhibit(
        "b5",
        "B5 · The what-if machine",
        FRAMING["b5"],
        q["verdict"],
        q["honesty"],
        kpis,
        [],
        q["working"],
        COLS_B5,
        body_extra=body_extra,
    )


def render_behaviour_page(book: dict) -> str:
    n_txns = book["n_transactions"]
    years = book["txn_years"]
    frame = paragraph(
        f"{n_txns:,} transactions across {years} years. What they reveal about investors — "
        "and about the advice they were given."
    )
    body = frame + sticky_subnav(MINI_INDEX)
    body += "".join(fn(book) for fn in (_b1, _b2, _b3, _b4, _b5))
    body += client_index_table(
        book["client_index"],
        flags=[
            ("panic_seller_flag", "panic seller"),
            ("dead_sip_flag", "dead SIP"),
            ("chronic_switcher_flag", "chronic switcher"),
        ],
        section_id="client-index-behaviour",
    )
    return body
