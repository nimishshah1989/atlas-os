"""The ONE universal exhibit renderer + page shell (constraint 14's anatomy).

Every page (Holdings today; Behaviour/Client360 in Task 5/6) is built from
the same primitives: `exhibit()` for a Q-numbered card (verdict + KPI tiles
+ 2-3 charts + a five-part "How is this calculated?" drawer), `topbar()` for
the two-link nav, and `client_index_table()` for the searchable client list
shared across pages. `render_document()` inlines app.css/charts*.js and the
single JSON data embed and wraps it all in one self-contained HTML file.

Chart wiring: each chart-card gets a static `<h4>title</h4><div id=...>`
followed by a small inline `<script>Charts.<kind>(el, data, opts)</script>`.
Charts/DATA globals are loaded once at the top of <body>, before any page
content, so every later inline script sees them already defined — no
DOMContentLoaded wrapper needed, no single end-of-body script collector.
"""

from __future__ import annotations

import json
from pathlib import Path

from .data import lcr_py

ASSETS = Path(__file__).parent / "assets"

HONESTY_LABEL = {
    "exact": "exact",
    "estimate": "estimate",
    "upper bound": "upper bound",
    "floor": "floor",
}
HONESTY_CLASS = {
    "exact": "chip--exact",
    "estimate": "chip--estimate",
    "upper bound": "chip--upper-bound",
    "floor": "chip--floor",
}

NAV_LINKS = [("holdings", "Holdings"), ("behaviour", "Behaviour")]


def esc(s: object) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def chip(honesty: str | None) -> str:
    if not honesty:
        return ""
    cls = HONESTY_CLASS.get(honesty, "chip--estimate")
    return f'<span class="chip {cls}">{esc(HONESTY_LABEL.get(honesty, honesty))}</span>'


def client_link(client_id: object, name: str) -> str:
    """Client-name link — used everywhere a client ID appears (constraint:
    no separate client detail nav, just contextual links)."""
    return f'<a href="#client/{esc(client_id)}">{esc(name)}</a>'


def paragraph(text: str, cls: str = "exhibit__verdict") -> str:
    return f'<p class="{cls}">{esc(text)}</p>'


def method_note(text: str) -> str:
    return f'<p class="method">{esc(text)}</p>'


def topbar(active: str, asof: str | None) -> str:
    links = "".join(
        f'<a href="#{slug}"{' class="on"' if slug == active else ""}>{esc(label)}</a>'
        for slug, label in NAV_LINKS
    )
    asof_html = (
        f'<span class="method" style="margin-left:auto">as of {esc(asof)}</span>' if asof else ""
    )
    return (
        '<div class="topbar"><div class="brand">Jhaveri Capability Book</div>'
        f"<nav>{links}</nav>{asof_html}</div>"
    )


def sticky_subnav(items: list[tuple[str, str]]) -> str:
    links = "".join(f'<a href="#{esc(i)}">{esc(label)}</a>' for i, label in items)
    return f'<div class="subnav">{links}</div>'


def kpi_strip(kpis: list[dict]) -> str:
    tiles = []
    for k in kpis:
        delta = ""
        if k.get("delta"):
            cls = "up" if k.get("delta_good", True) else "down"
            delta = f'<div class="kpi-delta {cls}">{esc(k["delta"])}</div>'
        tiles.append(
            '<div class="kpi-tile"><div class="kpi-label">'
            f'{esc(k["label"])}</div><div class="kpi-value">{esc(k["value"])}</div>{delta}</div>'
        )
    return f'<div class="kpi-strip">{"".join(tiles)}</div>' if tiles else ""


def chart_spec(kind: str, title: str, el_id: str, data: object, opts: dict | None = None) -> dict:
    """Build one chart-card's wiring. `data` is either a JS expression
    string referencing the embedded DATA global verbatim (e.g.
    "DATA.q1.treemap", used when the qN dict's own shape already matches
    the chart form's contract) or any JSON-serializable Python value (a
    page module's build-time reshape of real qN fields — still real
    numbers, computed in Python, inlined directly; JS never re-derives
    math, it only draws what Python handed it)."""
    data_expr = (
        data
        if isinstance(data, str) and data.startswith("DATA.")
        else json.dumps(data, ensure_ascii=False, allow_nan=False)
    )
    opts_json = json.dumps(opts or {}, ensure_ascii=False, allow_nan=False)
    return {
        "title": title,
        "el_id": el_id,
        "script": f'Charts.{kind}(document.getElementById("{el_id}"), {data_expr}, {opts_json});',
    }


def connected_components_by_threshold(
    pairs: list[dict], a_key: str, b_key: str, value_key: str, names: dict, threshold: float
) -> list[list[str]]:
    """Group entities into clusters via pairwise values above `threshold`
    (simple adjacency + DFS) — real derived grouping from real pairwise
    data, no new math. Shared by any exhibit needing "who clusters with
    whom" evidence (e.g. Q3's fund-overlap clusters)."""
    adj: dict[str, set[str]] = {}
    for p in pairs:
        if p[value_key] is not None and p[value_key] > threshold:
            a, b = names[p[a_key]], names[p[b_key]]
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
    seen: set[str] = set()
    out = []
    for node in adj:
        if node in seen:
            continue
        stack, comp = [node], set()
        while stack:
            n = stack.pop()
            if n in comp:
                continue
            comp.add(n)
            stack.extend(adj.get(n, ()) - comp)
        seen |= comp
        out.append(sorted(comp))
    return out


def chart_row(charts: list[dict]) -> str:
    if not charts:
        return ""
    cards = "".join(
        f'<div class="chart-card"><h4>{esc(c["title"])}</h4>'
        f'<div id="{esc(c["el_id"])}"></div><script>{c["script"]}</script></div>'
        for c in charts
    )
    return f'<div class="chart-row">{cards}</div>'


def data_table(rows: list[dict], columns: list[dict]) -> str:
    """Generic HTML table for a list of dict rows. `columns`: [{key, label,
    numeric?, fmt?, link?}]. `link`: the row key holding the display name —
    renders this column as client_link(v, row[link]) instead of raw text
    (used for every client_id column, per "client-name links everywhere
    client IDs appear"). Used both for exhibit drawer sample rows and for
    page-level evidence tables (e.g. Q2 offenders, Q3 stock overlap)."""
    if not rows:
        return ""
    head = "".join(
        f"<th{' class="n"' if c.get('numeric') else ''}>{esc(c['label'])}</th>" for c in columns
    )
    body_rows = []
    for r in rows:
        cells = []
        for c in columns:
            v = r.get(c["key"])
            if v is None:
                html_ = "—"
            elif c.get("link"):
                html_ = client_link(v, r.get(c["link"]) or v)
            elif c.get("fmt"):
                html_ = esc(c["fmt"](v))
            elif isinstance(v, list):
                html_ = esc(", ".join(str(x) for x in v) if v else "—")
            else:
                html_ = esc(str(v))
            cells.append(f"<td{' class="n"' if c.get('numeric') else ''}>{html_}</td>")
        body_rows.append(f"<tr>{''.join(cells)}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"


def _kv_table(rows: list[dict]) -> str:
    body = "".join(
        f'<tr><td>{esc(r["label"])}</td><td class="n">{esc(_fmt_working_value(r["value"]))}</td></tr>'
        for r in rows
    )
    return f"<table><tbody>{body}</tbody></table>"


def _fmt_working_value(v: object) -> str:
    if isinstance(v, float):
        return f"{v:,.2f}" if v != int(v) else f"{int(v):,}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


def drawer(working: dict, sample_columns: list[dict]) -> str:
    """The five fixed parts, in order: What we counted / The rule / The
    assumptions / The arithmetic / See rows."""
    parts = []
    if working.get("inputs"):
        parts.append(f"<h5>What we counted</h5>{_kv_table(working['inputs'])}")
    if working.get("rule"):
        parts.append(f"<h5>The rule</h5>{paragraph(working['rule'], cls='method')}")
    if working.get("assumptions"):
        rows = "".join(
            f'<p class="assumption">{esc(a["text"])} <span class="bias">({esc(a["bias"])})</span></p>'
            for a in working["assumptions"]
        )
        parts.append(f"<h5>The assumptions</h5>{rows}")
    if working.get("steps"):
        parts.append(f"<h5>The arithmetic</h5>{_kv_table(working['steps'])}")
    if working.get("sample_rows"):
        n_shown = len(working["sample_rows"])
        sample_of = working.get("sample_of", n_shown)
        parts.append(
            f"<h5>See rows ({n_shown} of {sample_of})</h5>"
            f"{data_table(working['sample_rows'], sample_columns)}"
        )
    if not parts:
        return ""
    return (
        '<details class="drawer"><summary>How is this calculated?</summary>'
        f'<div class="drawer__body">{"".join(parts)}</div></details>'
    )


def exhibit(
    id: str,
    eyebrow: str,
    framing: str,
    verdict: str,
    honesty: str | None,
    kpis: list[dict],
    charts: list[dict],
    working: dict,
    sample_columns: list[dict],
    body_extra: str = "",
) -> str:
    head = (
        f'<div class="exhibit__head"><span class="exhibit__id">{esc(eyebrow)}</span>'
        f"{chip(honesty)}</div>"
    )
    framing_html = method_note(f"“{framing}”")
    return (
        f'<section class="exhibit" id="{esc(id)}">{head}{framing_html}'
        f"{paragraph(verdict)}{kpi_strip(kpis)}{chart_row(charts)}{body_extra}"
        f"{drawer(working, sample_columns)}</section>"
    )


def client_index_table(client_index: dict) -> str:
    rows = client_index.get("rows", [])
    body = []
    for r in rows:
        flags = []
        if r.get("off_label_flag"):
            flags.append('<span class="chip chip--estimate">off-label</span>')
        if r.get("overlap_flag"):
            flags.append('<span class="chip chip--estimate">overlap</span>')
        if r.get("chronic_laggard_flag"):
            flags.append('<span class="chip chip--estimate">laggard</span>')
        if r.get("fees_above_median_flag"):
            flags.append('<span class="chip chip--estimate">fees</span>')
        body.append(
            "<tr>"
            f"<td>{client_link(r['client_id'], r['name'])}</td>"
            f'<td class="n">{esc(lcr_py(r.get("value_rs")))}</td>'
            f'<td class="n">{esc(r.get("fund_count", "—"))}</td>'
            f"<td>{esc(r.get('segment', '—'))}</td>"
            f"<td>{''.join(flags)}</td>"
            "</tr>"
        )
    table = (
        '<table><thead><tr><th>Client</th><th class="n">Value</th>'
        '<th class="n">Funds</th><th>Segment</th><th>Flags</th></tr></thead>'
        f"<tbody>{''.join(body)}</tbody></table>"
    )
    n_clients = client_index.get("n_clients", len(rows))
    return (
        f'<section class="exhibit" id="client-index">'
        f'<div class="exhibit__head"><span class="exhibit__id">Clients</span></div>'
        f"{paragraph(f'{n_clients} clients.')}"
        f'<input type="search" placeholder="Search clients…" '
        f"oninput=\"var q=this.value.toLowerCase();document.querySelectorAll('#client-index tbody tr')"
        f".forEach(function(tr){{tr.style.display=tr.textContent.toLowerCase().indexOf(q)>-1?'':'none';}});\">"
        f"{table}</section>"
    )


def render_document(data: dict, pages: dict[str, str], active: str) -> str:
    css = (ASSETS / "app.css").read_text(encoding="utf-8")
    charts_js = (ASSETS / "charts.js").read_text(encoding="utf-8")
    charts_composite_js = (ASSETS / "charts-composite.js").read_text(encoding="utf-8")
    blob = json.dumps(data, allow_nan=False, ensure_ascii=False, separators=(",", ":")).replace(
        "</", "<\\/"
    )
    body_pages = "".join(f'<div id="{esc(k)}">{html_}</div>' for k, html_ in pages.items())
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Jhaveri Capability Book</title>"
        f"<style>{css}</style></head><body>"
        f'<script id="data" type="application/json">{blob}</script>'
        f"<script>{charts_js}\n{charts_composite_js}</script>"
        f"{topbar(active, data.get('asof'))}"
        f'<div class="shell"><div class="grid-12">{body_pages}</div></div>'
        "</body></html>"
    )
