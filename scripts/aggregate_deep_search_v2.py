# allow-large: One-shot reporting script. Single-purpose, end-to-end:
# loads 24 per-cell JSONs, computes pooled BH-FDR, emits HTML/SQL/JSON.
# The bulk is inline CSS (~250 LOC) + HTML templates (~600 LOC) which are
# load-bearing UI/visual artifacts; splitting them into separate modules
# would only fragment a linear render pipeline. Reviewers should challenge
# the artifact dimensions (3 disclaimers, 24 cells, sortable tables) — not
# the line count.
"""Aggregate 24-cell deep-search v2 results into:
- master HTML report
- cross-cell BH-FDR
- dry-run persistence SQL
- master_summary.json

Run: python3 scripts/aggregate_deep_search_v2.py
"""

from __future__ import annotations

import glob
import html
import json
import math
import os
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

import numpy as np

# Inputs/outputs intentionally live under /tmp for the agent-run pipeline;
# these are not credentials and the dir is created/owned by the running user.
CELLS_DIR = "/tmp/deep_search_v2/cells"  # noqa: S108
HTML_OUT = "/Users/nimishshah/.gstack/projects/atlas-os/deep-search-all-cells.html"
SQL_OUT = "/tmp/deep_search_v2/persist.sql"  # noqa: S108
SUMMARY_OUT = "/tmp/deep_search_v2/master_summary.json"  # noqa: S108

ENGINE_SHA = "e60f8c8"
BRANCH = "feat/v6-deep-search-all-cells"
METHODOLOGY_REF = "DEEP_SEARCH_V2_2026-05-24"

PER_TENURE_IC_FLOOR = {"1m": 0.02, "3m": 0.04, "6m": 0.05, "12m": 0.04}
TIERS = ["Large", "Mid", "Small"]
TENURES = ["1m", "3m", "6m", "12m"]
DIRECTIONS = ["POSITIVE", "NEGATIVE"]


# --------------------------------------------------------------------------
# Stats helpers (mirror engine's Fisher-z + BH)
# --------------------------------------------------------------------------
def ic_to_p_value(ic: float, n: int) -> float:
    if n is None or n < 4 or ic is None or (isinstance(ic, float) and math.isnan(ic)):
        return 1.0
    r = max(-0.9999, min(0.9999, float(ic)))
    z = math.atanh(r) * math.sqrt(max(n - 3, 1))
    # two-sided normal tail
    p = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(z) / math.sqrt(2.0))))
    return max(min(p, 1.0), 0.0)


def bh_q_values(p_values: list[float]) -> list[float]:
    p_arr = np.asarray(p_values, dtype=float)
    n = len(p_arr)
    if n == 0:
        return []
    order = np.argsort(p_arr)
    ranks = np.empty(n, dtype=float)
    ranks[order] = np.arange(1, n + 1, dtype=float)
    q = p_arr * (n / ranks)
    sorted_q = q[order]
    for i in range(n - 2, -1, -1):
        sorted_q[i] = min(sorted_q[i], sorted_q[i + 1])
    q_out = np.empty(n, dtype=float)
    q_out[order] = np.clip(sorted_q, 0.0, 1.0)
    return q_out.tolist()


# --------------------------------------------------------------------------
# Load + enrich
# --------------------------------------------------------------------------
def load_all_cells() -> list[dict[str, Any]]:
    cells = []
    for path in sorted(glob.glob(f"{CELLS_DIR}/*.json")):
        with open(path) as fh:
            cell = json.load(fh)
        cell["_path"] = path
        cells.append(cell)
    return cells


def annotate_cross_cell_q(cells: list[dict[str, Any]]) -> None:
    """Compute cross-cell BH-FDR over ALL candidates from ALL cells."""
    all_records: list[tuple[int, int, float]] = []  # (cell_idx, cand_idx, p)
    for ci, cell in enumerate(cells):
        for ki, cand in enumerate(cell["candidates"]):
            ic = cand.get("ic")
            n = cand.get("n_observations", 0)
            p = ic_to_p_value(ic if ic is not None else float("nan"), n or 0)
            all_records.append((ci, ki, p))

    p_values = [r[2] for r in all_records]
    q_values = bh_q_values(p_values)
    for (ci, ki, _), q in zip(all_records, q_values, strict=True):
        cells[ci]["candidates"][ki]["bh_q_value_cross_cell"] = float(q)
        cells[ci]["candidates"][ki]["raw_p_value"] = (
            float(p_values[all_records.index((ci, ki, _))]) if False else None
        )
    # Faster: assign p directly during loop
    for (ci, ki, p), q in zip(all_records, q_values, strict=True):
        cells[ci]["candidates"][ki]["raw_p_value"] = float(p)
        cells[ci]["candidates"][ki]["bh_q_value_cross_cell"] = float(q)

    # Mirror onto top_10 entries (match by name).
    for cell in cells:
        by_name = {c["name"]: c for c in cell["candidates"]}
        for entry in cell["top_10"]:
            full = by_name.get(entry["name"])
            if full is not None:
                entry["bh_q_value_cross_cell"] = full["bh_q_value_cross_cell"]
                entry["raw_p_value"] = full["raw_p_value"]


# --------------------------------------------------------------------------
# Rule DSL builder (synthesized — engine doesn't expose a builder)
# --------------------------------------------------------------------------
def build_rule_dsl(cand: dict[str, Any], cell_meta: dict[str, str]) -> dict[str, Any]:
    """Return a JSON-serialisable rule DSL describing the candidate predicate chain."""
    return {
        "version": "atlas.deep_search.v2",
        "tier": cell_meta["tier"],
        "tenure": cell_meta["tenure"],
        "direction": cell_meta["direction"],
        "rule_name": cand["name"],
        "archetype": cand["archetype"],
        "predicates": cand.get("predicates", []),
        "rationale": cand.get("rationale", ""),
        "metrics": {
            "ic": cand.get("ic"),
            "tp_rate": cand.get("tp_rate"),
            "median_excess": cand.get("median_excess"),
            "mean_excess": cand.get("mean_excess"),
            "friction_adjusted_excess": cand.get("friction_adjusted_excess"),
            "n_observations": cand.get("n_observations"),
            "percentile_50": cand.get("percentile_50"),
        },
        "per_window": cand.get("per_window", []),
        "methodology_ref": METHODOLOGY_REF,
    }


# --------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------
def fmt_ic(x: float | None) -> str:
    if x is None:
        return "—"
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "—"
    if math.isnan(v) or math.isinf(v):
        return "—"
    return f"{v:+.4f}"


def fmt_excess(x: float | None) -> str:
    if x is None:
        return "—"
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "—"
    if math.isnan(v) or math.isinf(v):
        return "—"
    return f"{v * 100:+.2f}%"


def fmt_q(x: float | None) -> str:
    if x is None:
        return "—"
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "—"
    if math.isnan(v) or math.isinf(v):
        return "—"
    return f"{v:.4f}"


def fmt_int(x) -> str:
    if x is None:
        return "—"
    return f"{int(x):,}"


def cell_id(tier: str, tenure: str, direction: str) -> str:
    return f"{tier}-{tenure}-{direction}"


# --------------------------------------------------------------------------
# Classification: ship vs park, ship-grade per cell
# --------------------------------------------------------------------------
def classify_cell(cell: dict[str, Any]) -> dict[str, Any]:
    """Pick the best candidate for the cell and classify ship/park."""
    direction = cell["cell"]["direction"]
    tenure = cell["cell"]["tenure"]
    floor = PER_TENURE_IC_FLOOR[tenure]

    cands = cell["candidates"]

    # Filter out NaN ICs from any selection.
    def _ic_ok(c):
        ic = c.get("ic")
        return ic is not None and not (isinstance(ic, float) and math.isnan(ic))

    valid_ic = [c for c in cands if _ic_ok(c)]
    # Pick best within validated (gate-pass), else best signed-IC in direction.
    validated = [c for c in valid_ic if c.get("validated")]
    if validated:
        # Sort by signed IC in the correct direction
        if direction == "POSITIVE":
            validated.sort(key=lambda c: c["ic"], reverse=True)
        else:
            validated.sort(key=lambda c: c["ic"])
        best = validated[0]
    else:
        # No validated — pick the candidate with best signed-IC in the *correct* direction
        # (i.e. largest positive for POSITIVE; most negative for NEGATIVE).
        if not valid_ic:
            best = None
        elif direction == "POSITIVE":
            best = max(valid_ic, key=lambda c: c["ic"])
        else:
            best = min(valid_ic, key=lambda c: c["ic"])

    if best is None:
        return {
            "best": None,
            "ship_or_park": "no_candidate",
            "grade": "red",
            "reason": "No candidates returned for this cell.",
        }

    ic = best.get("ic") or 0
    q_within = best.get("bh_q_value")
    q_cross = best.get("bh_q_value_cross_cell")
    validated_flag = bool(best.get("validated"))
    direction_ok = (direction == "POSITIVE" and ic > floor) or (
        direction == "NEGATIVE" and ic < -floor
    )

    # Grading
    if validated_flag and q_cross is not None and q_cross <= 0.10 and direction_ok:
        grade = "green"
        ship_or_park = "ship"
        reason = (
            f"Validated; IC {ic:+.4f} {'>' if direction == 'POSITIVE' else '<'} "
            f"{'+' if direction == 'POSITIVE' else '-'}{floor}; "
            f"cross-cell q={q_cross:.4f} ≤ 0.10."
        )
    elif validated_flag and q_cross is not None and q_cross <= 0.20:
        grade = "amber"
        ship_or_park = "park_borderline"
        reason = (
            f"Validated within-cell but cross-cell q={q_cross:.4f} "
            f"is borderline (0.10–0.20). Worth a second walk-forward before shipping."
        )
    elif validated_flag:
        grade = "amber"
        ship_or_park = "park_borderline"
        reason = (
            f"Validated within-cell but cross-cell q={fmt_q(q_cross)} > 0.20. "
            "Survives within-cell BH but not the 6,144-test pooled correction."
        )
    else:
        grade = "red"
        ship_or_park = "park_no_signal"
        reason = (
            f"No candidate cleared the gate. Best |IC|={abs(ic):.4f} "
            f"vs floor {floor}; likely needs sector/regime conditioning, "
            "fundamentals, or (for NEGATIVE) survivorship-fixed cache."
        )

    if direction == "NEGATIVE" and ship_or_park == "ship":
        # Survivorship caveat downgrades NEGATIVE ship to park-with-caveat
        ship_or_park = "park_survivorship"
        grade = "amber"
        reason = (
            "Passes BH-FDR cross-cell gate, BUT the OHLCV cache is "
            "survivor-only (727 alive names from 2,275 EC2 universe). "
            "NEGATIVE rules here are 'weak-vs-strong within survivors,' "
            "NOT validated avoid-signals. Park until delisted backfill lands."
        )

    return {
        "best": best,
        "ship_or_park": ship_or_park,
        "grade": grade,
        "reason": reason,
        "validated": validated_flag,
        "direction_ok": direction_ok,
        "ic_floor": floor,
        "q_within": q_within,
        "q_cross": q_cross,
    }


# --------------------------------------------------------------------------
# HTML rendering
# --------------------------------------------------------------------------
CSS = """
:root {
  --teal: #1D9E75;
  --teal-light: #E8F5EF;
  --teal-dark: #157957;
  --red: #C8102E;
  --red-light: #FBEAED;
  --amber: #F5A623;
  --amber-light: #FFF5E1;
  --grey-50: #F8F9FA;
  --grey-100: #ECEFF1;
  --grey-200: #CFD8DC;
  --grey-300: #B0BEC5;
  --grey-400: #90A4AE;
  --grey-600: #607D8B;
  --grey-700: #455A64;
  --grey-900: #1A2329;
}
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI",
    Roboto, "Helvetica Neue", Arial, sans-serif;
  margin: 0; padding: 24px 32px; background: var(--grey-50);
  color: var(--grey-900); line-height: 1.45;
  font-size: 14px;
}
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
header.page-header {
  border-bottom: 2px solid var(--teal); padding-bottom: 16px; margin-bottom: 24px;
}
header.page-header h1 { margin: 0; font-size: 26px; color: var(--grey-900); }
header.page-header .sub { margin: 4px 0 0; color: var(--grey-700); font-size: 13px; }
header.page-header .meta { margin-top: 8px; font-size: 12px; color: var(--grey-600); }
header.page-header .meta code { background: var(--grey-100); padding: 1px 6px;
  border-radius: 3px; font-size: 12px; }

section {
  background: white; border: 1px solid var(--grey-200);
  border-radius: 8px; padding: 20px 24px; margin-bottom: 24px;
}
section h2 { margin: 0 0 16px; font-size: 20px; border-bottom: 1px solid var(--grey-100);
             padding-bottom: 8px; }
section h3 { margin: 20px 0 10px; font-size: 16px; }

.callout {
  padding: 14px 18px; border-radius: 6px; margin-bottom: 14px;
  border-left: 4px solid var(--red); background: var(--red-light);
}
.callout.warn { border-left-color: var(--amber); background: var(--amber-light); }
.callout.info { border-left-color: var(--teal); background: var(--teal-light); }
.callout strong { display: block; margin-bottom: 4px; font-size: 14px; }
.callout small { color: var(--grey-700); }

.stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
             gap: 12px; margin-bottom: 12px; }
.stat { background: var(--grey-50); padding: 12px; border-radius: 6px;
        border: 1px solid var(--grey-100); }
.stat-value { font-size: 22px; font-weight: 600; }
.stat-label { font-size: 11px; color: var(--grey-700); text-transform: uppercase;
              letter-spacing: 0.05em; margin-top: 4px; }

/* Matrix grid */
.matrix-grid { display: grid; grid-template-columns: 110px repeat(4, 1fr); gap: 8px;
               margin-top: 12px; }
.matrix-grid .label-col, .matrix-grid .label-row {
  background: var(--grey-100); padding: 8px; font-weight: 600;
  font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em;
  display: flex; align-items: center; justify-content: center;
  text-align: center;
}
.matrix-cell {
  background: white; border: 1px solid var(--grey-200); border-radius: 6px;
  padding: 10px 12px; font-size: 12px; cursor: pointer;
  transition: transform 0.1s ease, box-shadow 0.1s ease;
}
.matrix-cell:hover { transform: translateY(-1px); box-shadow: 0 2px 6px rgba(0,0,0,0.08); }
.matrix-cell.green { border-left: 4px solid var(--teal); background: var(--teal-light); }
.matrix-cell.amber { border-left: 4px solid var(--amber); background: var(--amber-light); }
.matrix-cell.red   { border-left: 4px solid var(--red); background: var(--red-light); }
.matrix-cell .mc-title { font-weight: 600; font-size: 12px; }
.matrix-cell .mc-rule  { font-family: ui-monospace, Menlo, monospace; font-size: 11px;
                         color: var(--grey-700); margin-top: 3px; word-break: break-all; }
.matrix-cell .mc-stats { margin-top: 6px; display: flex; gap: 8px; flex-wrap: wrap;
                         font-size: 11px; color: var(--grey-700); }
.matrix-cell .mc-stat b { color: var(--grey-900); }
.matrix-cell .surv-badge { display: inline-block; background: #FBEAED; color: #C8102E;
                           font-size: 9px; padding: 1px 5px; border-radius: 8px;
                           font-weight: 600; margin-left: 4px; }
.matrix-cell.muted { opacity: 0.65; }

/* Tier-section header */
.tier-section-head { display: flex; align-items: center; gap: 12px;
                     margin-top: 18px; margin-bottom: 6px; }
.tier-section-head h3 { margin: 0; font-size: 14px; color: var(--grey-700);
                        text-transform: uppercase; letter-spacing: 0.08em; }

/* Tables */
table.data-table { border-collapse: collapse; width: 100%; font-size: 12.5px;
                   margin-top: 8px; }
table.data-table th, table.data-table td {
  text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--grey-100);
  vertical-align: top;
}
table.data-table th { background: var(--grey-50); font-weight: 600;
                      color: var(--grey-700); text-transform: uppercase;
                      letter-spacing: 0.05em; font-size: 11px;
                      cursor: pointer; user-select: none; white-space: nowrap; }
table.data-table th.sort-asc::after  { content: " ▲"; color: var(--teal); }
table.data-table th.sort-desc::after { content: " ▼"; color: var(--teal); }
table.data-table td.num { text-align: right; font-family: ui-monospace, Menlo, monospace;
                          white-space: nowrap; }
table.data-table tr:hover td { background: var(--grey-50); }
table.data-table tr.validated td { background: var(--teal-light); }
table.data-table tr.validated:hover td { background: #d6eee2; }
.archetype-pill { display: inline-block; font-size: 10px; padding: 1px 6px;
                  background: var(--grey-100); border-radius: 8px; color: var(--grey-700);
                  text-transform: uppercase; letter-spacing: 0.03em; }
.win-badge { display: inline-block; font-family: ui-monospace, Menlo, monospace;
             font-size: 11px; padding: 1px 4px; border-radius: 3px;
             background: var(--grey-100); margin-right: 2px; }
.win-badge.pass { background: var(--teal-light); color: var(--teal-dark); }
.win-badge.fail { background: var(--red-light); color: var(--red); }
.q-good { color: var(--teal-dark); font-weight: 600; }
.q-borderline { color: var(--amber); font-weight: 600; }
.q-bad   { color: var(--grey-600); }

/* Per-cell drill-down */
details.cell-detail { margin-bottom: 12px; border: 1px solid var(--grey-200);
                      border-radius: 6px; overflow: hidden; background: white; }
details.cell-detail summary { padding: 10px 14px; cursor: pointer;
                              background: var(--grey-50); font-weight: 600;
                              display: flex; align-items: center; gap: 10px;
                              list-style: none; }
details.cell-detail summary::-webkit-details-marker { display: none; }
details.cell-detail summary::before { content: "▶"; color: var(--grey-400); font-size: 10px; }
details.cell-detail[open] summary::before { content: "▼"; }
details.cell-detail .cell-body { padding: 14px 18px; }
.cell-meta-row { display: flex; gap: 16px; font-size: 12px; color: var(--grey-700);
                 margin-bottom: 8px; flex-wrap: wrap; }
.cell-meta-row b { color: var(--grey-900); }
.cell-verdict { padding: 8px 12px; border-radius: 5px; margin: 6px 0 12px;
                font-size: 13px; }
.cell-verdict.green { background: var(--teal-light); border-left: 3px solid var(--teal); }
.cell-verdict.amber { background: var(--amber-light); border-left: 3px solid var(--amber); }
.cell-verdict.red   { background: var(--red-light);   border-left: 3px solid var(--red); }
.predicates { font-family: ui-monospace, Menlo, monospace; font-size: 11.5px;
              background: var(--grey-50); padding: 6px 10px; border-radius: 4px;
              margin: 6px 0; }

/* Heatmap */
.heatmap { border-collapse: collapse; font-size: 12px; margin-top: 8px; }
.heatmap th, .heatmap td { padding: 8px 10px; text-align: center;
                            border: 1px solid var(--grey-200); min-width: 80px; }
.heatmap th { background: var(--grey-100); font-weight: 600; }
.heatmap td.label { text-align: left; background: var(--grey-50); font-weight: 600; }
.heatmap td.cell { font-family: ui-monospace, Menlo, monospace; font-weight: 600; }

footer { margin-top: 32px; padding-top: 16px; border-top: 1px solid var(--grey-200);
         color: var(--grey-600); font-size: 12px; }
"""

SORT_JS = """
(function(){
  function getCellValue(tr, idx) {
    var c = tr.children[idx];
    var dv = c.getAttribute('data-sort');
    if (dv !== null && dv !== undefined && dv !== '') return parseFloat(dv);
    var txt = c.textContent.trim();
    var num = parseFloat(txt.replace(/[+,%\\s]/g, ''));
    if (!isNaN(num) && /^[-+]?[\\d.]+%?$/.test(txt.replace(/[+,\\s]/g, ''))) return num;
    return txt.toLowerCase();
  }
  document.querySelectorAll('table.data-table').forEach(function(table){
    var ths = table.querySelectorAll('thead th');
    ths.forEach(function(th, idx){
      th.addEventListener('click', function(){
        var tbody = table.querySelector('tbody');
        var rows = Array.from(tbody.querySelectorAll('tr'));
        var asc = !th.classList.contains('sort-asc');
        ths.forEach(function(h){ h.classList.remove('sort-asc','sort-desc'); });
        th.classList.add(asc ? 'sort-asc' : 'sort-desc');
        rows.sort(function(a,b){
          var av = getCellValue(a, idx);
          var bv = getCellValue(b, idx);
          if (av === bv) return 0;
          if (typeof av === 'number' && typeof bv === 'number') {
            return asc ? av - bv : bv - av;
          }
          return asc ? (av < bv ? -1 : 1) : (av > bv ? -1 : 1);
        });
        rows.forEach(function(r){ tbody.appendChild(r); });
      });
    });
  });
})();
"""


def esc(s: Any) -> str:
    return html.escape(str(s)) if s is not None else "—"


def render_header(stats: dict[str, Any]) -> str:
    return f"""
<header class="page-header">
  <h1>Atlas v6 — Deep Search v2 (24-cell sweep)</h1>
  <p class="sub">Tier × tenure × direction matrix · {stats["n_total_cells"]} cells ·
     {stats["n_total_candidates"]:,} candidates tested · pooled BH-FDR</p>
  <p class="meta">
    Engine <code>{ENGINE_SHA}</code> ·
    Branch <code>{BRANCH}</code> ·
    Methodology ref <code>{METHODOLOGY_REF}</code> ·
    Generated {datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")}
  </p>
</header>
"""


def render_disclaimers() -> str:
    return """
<section>
  <h2>⚠ Critical disclaimers — read before interpreting any cell</h2>
  <div class="callout">
    <strong>1. Survivorship bias (HIGH severity)</strong>
    The OHLCV cache contains <b>727 currently-alive instruments</b> (~32% of the
    2,275-name EC2-tracked universe). Zero delisted/suspended names. <b>NEGATIVE</b>
    cells search within a survivor-only population — the fat left tail of names
    that subsequently delisted is <i>entirely absent</i>. NEGATIVE rules from
    this sweep are "weak-relative-to-strong patterns within curated leaders,"
    <b>NOT</b> validated avoid-signals against the full tradable universe.
    Cache rebuild + delisted_on backfill from EC2 <code>de_equity_ohlcv ∩
    de_instrument</code> is required before production-grade NEGATIVE claims.
  </div>
  <div class="callout warn">
    <strong>2. W3 thin coverage (MEDIUM severity)</strong>
    The third walk-forward OOS window (2024-07 → 2024-12) has materially less
    data — monthly mean instrument count drops to ~345/day (from ~600).
    Full-coverage instruments in W3 collapse to <b>Small=30 / Mid=40 / Large=96</b>.
    Per-window stability checks on W3 are noisier than W1/W2; treat W3-only
    conviction with skepticism.
  </div>
  <div class="callout info">
    <strong>3. No fundamentals</strong>
    All ~50 features are derived from close+volume + Nifty benchmark + sector
    mapping. <b>Quality / Value / Earnings-revision factor families</b>
    (QMJ, HML, PEAD, CMA) are entirely unaddressable in this sweep.
    Any "~95% confidence" claim applies to <i>price+volume+sector derivable
    space</i> only, not the full asset-pricing factor universe.
  </div>
  <p style="margin-top: 10px; font-size: 12px; color: var(--grey-700);">
    Source documents:
    <code>/tmp/deep_search_v2/cache_qa_report.md</code> ·
    <code>/tmp/deep_search_v2/factor_coverage_critique.md</code>
  </p>
</section>
"""


def render_summary_stats(cells: list[dict[str, Any]], classifications: dict[str, Any]) -> str:
    n_total_cand = sum(c["n_candidates"] for c in cells)
    n_gate_pass = sum(c["n_gate_pass"] for c in cells)
    grades = [classifications[cell_id(**c["cell"])]["grade"] for c in cells]
    n_green = grades.count("green")
    n_amber = grades.count("amber")
    n_red = grades.count("red")

    # Cross-cell q tallies
    n_q05 = 0
    n_q10 = 0
    n_q20 = 0
    for cell in cells:
        for c in cell["candidates"]:
            q = c.get("bh_q_value_cross_cell", 1.0)
            if q <= 0.05:
                n_q05 += 1
            if q <= 0.10:
                n_q10 += 1
            if q <= 0.20:
                n_q20 += 1

    return f"""
<section>
  <h2>Summary</h2>
  <div class="stat-grid">
    <div class="stat"><div class="stat-value">{len(cells)}</div>
      <div class="stat-label">Cells run</div></div>
    <div class="stat"><div class="stat-value">{n_total_cand:,}</div>
      <div class="stat-label">Candidates tested</div></div>
    <div class="stat"><div class="stat-value">{n_gate_pass:,}</div>
      <div class="stat-label">Within-cell gate-pass</div></div>
    <div class="stat"><div class="stat-value q-good">{n_green}</div>
      <div class="stat-label">Cells: ship-grade (green)</div></div>
    <div class="stat"><div class="stat-value q-borderline">{n_amber}</div>
      <div class="stat-label">Cells: borderline (amber)</div></div>
    <div class="stat"><div class="stat-value q-bad">{n_red}</div>
      <div class="stat-label">Cells: no signal (red)</div></div>
  </div>
  <h3>Cross-cell BH-FDR survivors (pooled across all {n_total_cand:,} tests)</h3>
  <div class="stat-grid">
    <div class="stat"><div class="stat-value q-good">{n_q05:,}</div>
      <div class="stat-label">q ≤ 0.05 (strict)</div></div>
    <div class="stat"><div class="stat-value q-good">{n_q10:,}</div>
      <div class="stat-label">q ≤ 0.10 (ship gate)</div></div>
    <div class="stat"><div class="stat-value q-borderline">{n_q20:,}</div>
      <div class="stat-label">q ≤ 0.20 (borderline)</div></div>
  </div>
</section>
"""


def render_matrix(
    cells_by_id: dict[str, dict[str, Any]], classifications: dict[str, dict[str, Any]]
) -> str:
    out = [
        "<section><h2>24-cell matrix</h2>",
        '<p style="font-size:12px;color:var(--grey-700);margin:0 0 8px;">'
        "Each cell shows best validated candidate (or top |IC| if none validated). "
        'Color: <span style="color:var(--teal-dark);font-weight:600;">green</span> = '
        "ship-grade (validated + cross-cell q≤0.10); "
        '<span style="color:var(--amber);font-weight:600;">amber</span> = borderline; '
        '<span style="color:var(--red);font-weight:600;">red</span> = no gate-passing candidate. '
        'NEGATIVE cells carry a <span class="surv-badge">SURV</span> badge.</p>',
    ]

    for direction in DIRECTIONS:
        out.append(f'<div class="tier-section-head"><h3>{direction}</h3></div>')
        # header row: blank + tenures
        out.append('<div class="matrix-grid">')
        out.append('<div class="label-col"></div>')
        for tenure in TENURES:
            out.append(f'<div class="label-row">{tenure}</div>')

        for tier in TIERS:
            out.append(f'<div class="label-col">{tier}</div>')
            for tenure in TENURES:
                cid = cell_id(tier, tenure, direction)
                cell = cells_by_id[cid]
                cls = classifications[cid]
                best = cls["best"]
                grade = cls["grade"]
                surv = '<span class="surv-badge">SURV</span>' if direction == "NEGATIVE" else ""
                if best is None:
                    out.append(
                        '<div class="matrix-cell red"><div class="mc-title">'
                        "No candidates</div></div>"
                    )
                    continue
                ic = best.get("ic")
                excess = best.get("friction_adjusted_excess")
                q_cross = best.get("bh_q_value_cross_cell")
                trig = best.get("n_observations")
                n_gp = cell["n_gate_pass"]
                rule = esc(best.get("name", "—"))
                out.append(
                    f'<div class="matrix-cell {grade}">'
                    f'<div class="mc-title">{esc(best.get("archetype", ""))} {surv}</div>'
                    f'<div class="mc-rule">{rule}</div>'
                    f'<div class="mc-stats">'
                    f'<span class="mc-stat">IC <b>{fmt_ic(ic)}</b></span>'
                    f'<span class="mc-stat">fric-adj <b>{fmt_excess(excess)}</b></span>'
                    f'<span class="mc-stat">q⊕ <b>{fmt_q(q_cross)}</b></span>'
                    f'<span class="mc-stat">trig <b>{fmt_int(trig)}</b></span>'
                    f'<span class="mc-stat">pass <b>{n_gp}</b></span>'
                    f"</div>"
                    f"</div>"
                )
        out.append("</div>")
    out.append("</section>")
    return "\n".join(out)


def render_cell_detail(cell: dict[str, Any], cls: dict[str, Any]) -> str:
    meta = cell["cell"]
    cid = cell_id(**meta)
    direction = meta["direction"]

    # Top-10 table
    rows = []
    for i, c in enumerate(cell["top_10"], 1):
        pw = c.get("per_window", []) or []
        win_excess = []
        win_trigger = []
        for w in pw:
            ex = w.get("median_excess")
            n = w.get("n_obs", 0)
            mt = w.get("meets_triggers", False)
            consist = w.get("consistent", False)
            cls_win = "pass" if (mt and consist) else "fail"
            ex_text = fmt_excess(ex)
            win_excess.append(f'<span class="win-badge {cls_win}">{ex_text}</span>')
            win_trigger.append(f'<span class="win-badge {cls_win}">{n}</span>')

        q_w = c.get("bh_q_value")
        q_x = c.get("bh_q_value_cross_cell")
        q_w_cls = (
            "q-good"
            if (q_w is not None and q_w <= 0.10)
            else ("q-borderline" if (q_w is not None and q_w <= 0.20) else "q-bad")
        )
        q_x_cls = (
            "q-good"
            if (q_x is not None and q_x <= 0.10)
            else ("q-borderline" if (q_x is not None and q_x <= 0.20) else "q-bad")
        )
        row_cls = "validated" if c.get("validated") else ""
        ic = c.get("ic")
        fa = c.get("friction_adjusted_excess")

        def _ds(v):
            if v is None:
                return ""
            try:
                f = float(v)
            except (TypeError, ValueError):
                return ""
            if math.isnan(f) or math.isinf(f):
                return ""
            return repr(f)

        rows.append(
            f"<tr class='{row_cls}'>"
            f"<td class='num'>{i}</td>"
            f"<td class='mono'>{esc(c.get('name'))}</td>"
            f"<td><span class='archetype-pill'>{esc(c.get('archetype', ''))}</span></td>"
            f"<td class='num' data-sort='{_ds(ic)}'>{fmt_ic(ic)}</td>"
            f"<td class='num' data-sort='{_ds(fa)}'>{fmt_excess(fa)}</td>"
            f"<td class='num {q_w_cls}' data-sort='{_ds(q_w)}'>{fmt_q(q_w)}</td>"
            f"<td class='num {q_x_cls}' data-sort='{_ds(q_x)}'>{fmt_q(q_x)}</td>"
            f"<td>{''.join(win_trigger)}</td>"
            f"<td>{''.join(win_excess)}</td>"
            f"<td>{'✓' if c.get('validated') else '✗'}</td>"
            f"</tr>"
        )

    # Top-1 expanded
    top1 = cell["top_10"][0] if cell["top_10"] else None
    top1_block = ""
    if top1 is not None:
        preds = top1.get("predicates", [])
        pred_text = " AND ".join(f"{p['feature']} {p['cmp']} {p['value']}" for p in preds)
        stab_rows = []
        for w in cell.get("top_1_stability", []):
            ex = w.get("median_excess")
            n = w.get("n_obs", 0)
            mt = w.get("meets_triggers", False)
            consist = w.get("consistent", False)
            cls_win = "validated" if (mt and consist) else ""
            stab_rows.append(
                f"<tr class='{cls_win}'>"
                f"<td class='mono'>{esc(w.get('window'))}</td>"
                f"<td class='num'>{fmt_int(n)}</td>"
                f"<td class='num'>{fmt_excess(ex)}</td>"
                f"<td>{'✓' if consist else '✗'}</td>"
                f"<td>{'✓' if mt else '✗'}</td>"
                f"</tr>"
            )
        top1_block = f"""
<h3>Top-1 candidate — per-window breakdown</h3>
<div class='cell-meta-row'><b>{esc(top1.get("name"))}</b> ·
  <span class='archetype-pill'>{esc(top1.get("archetype", ""))}</span> ·
  <span>{esc(top1.get("rationale", ""))}</span></div>
<div class='predicates'>{esc(pred_text)}</div>
<table class='data-table'>
<thead><tr><th>Window</th><th>n_obs</th><th>Median excess</th>
<th>Consistent</th><th>Triggers ≥ 30</th></tr></thead>
<tbody>{"".join(stab_rows)}</tbody></table>
"""

    verdict_class = cls["grade"]
    surv_caveat = ""
    if direction == "NEGATIVE":
        surv_caveat = (
            "<div class='callout' style='margin-top:10px;'>"
            "<strong>NEGATIVE cell — survivorship caveat applies</strong>"
            "<small>This cell evaluates ~727 alive instruments. "
            "Treat all rules as 'weakest-of-the-strong' patterns, "
            "NOT validated avoid-signals against the full universe.</small></div>"
        )

    summary_line = (
        f"<b>{cid}</b> · "
        f"{cell['n_candidates']} candidates · "
        f"{cell['n_gate_pass']} gate-pass · "
        f"grade <span class='q-{('good' if verdict_class == 'green' else 'borderline' if verdict_class == 'amber' else 'bad')}'>"
        f"{verdict_class.upper()}</span>"
    )

    return f"""
<details class="cell-detail" id="cell-{cid}">
  <summary>{summary_line}</summary>
  <div class="cell-body">
    <div class="cell-meta-row">
      <span><b>Tier:</b> {meta["tier"]}</span>
      <span><b>Tenure:</b> {meta["tenure"]}</span>
      <span><b>Direction:</b> {direction}</span>
      <span><b>IC floor:</b> {("+" if direction == "POSITIVE" else "-")}{PER_TENURE_IC_FLOOR[meta["tenure"]]}</span>
    </div>
    <div class="cell-verdict {verdict_class}">
      <b>Disposition: {cls["ship_or_park"].upper()}</b> — {esc(cls["reason"])}
    </div>
    {surv_caveat}
    <h3>Top-10 candidates</h3>
    <table class='data-table'>
      <thead><tr>
        <th>#</th><th>Name</th><th>Archetype</th>
        <th>IC</th><th>Fric-adj excess</th>
        <th>q within-cell</th><th>q cross-cell</th>
        <th>Triggers W1/W2/W3</th><th>Excess W1/W2/W3</th>
        <th>Validated</th>
      </tr></thead>
      <tbody>
{"".join(rows)}
      </tbody>
    </table>
    {top1_block}
  </div>
</details>
"""


def render_archetype_heatmap(cells_by_id: dict[str, dict[str, Any]]) -> str:
    """Best-archetype IC per (tier × tenure × direction)."""
    out = [
        "<section><h2>Cross-cell archetype heatmap</h2>",
        '<p style="font-size:12px;color:var(--grey-700);">'
        "For each cell: archetype with the highest signed IC (in the cell's direction). "
        "Colored by absolute IC magnitude.</p>",
    ]

    for direction in DIRECTIONS:
        out.append(f"<h3>{direction}</h3>")
        out.append('<table class="heatmap"><thead><tr><th></th>')
        for ten in TENURES:
            out.append(f"<th>{ten}</th>")
        out.append("</tr></thead><tbody>")
        for tier in TIERS:
            out.append(f'<tr><td class="label">{tier}</td>')
            for ten in TENURES:
                cid = cell_id(tier, ten, direction)
                cell = cells_by_id[cid]
                # Best by signed IC in direction
                cands = cell["candidates"]
                if direction == "POSITIVE":
                    cands = sorted(cands, key=lambda c: c.get("ic") or -1, reverse=True)
                else:
                    cands = sorted(cands, key=lambda c: c.get("ic") or 1)
                top = cands[0] if cands else None
                if top is None:
                    out.append('<td class="cell">—</td>')
                    continue
                ic_raw = top.get("ic")
                if ic_raw is None or (isinstance(ic_raw, float) and math.isnan(ic_raw)):
                    ic = 0.0
                else:
                    ic = float(ic_raw)
                arc = top.get("archetype", "—")
                mag = min(abs(ic), 0.15) / 0.15
                if direction == "POSITIVE":
                    bg = f"rgba(29,158,117,{0.10 + 0.60 * mag:.2f})"
                else:
                    bg = f"rgba(200,16,46,{0.10 + 0.60 * mag:.2f})"
                out.append(
                    f'<td class="cell" style="background:{bg};">'
                    f'{esc(arc)}<br><span style="font-size:11px;color:var(--grey-700);">'
                    f"IC {fmt_ic(ic)}</span></td>"
                )
            out.append("</tr>")
        out.append("</tbody></table>")
    out.append("</section>")
    return "\n".join(out)


def render_cross_tier_analysis(cells: list[dict[str, Any]]) -> str:
    """Best archetype per tier, best tenure per tier, sector-RS contribution."""
    # Best archetype per (tier, direction) by mean of best-ic-per-tenure
    by_tier_dir: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for cell in cells:
        m = cell["cell"]
        for c in cell["candidates"]:
            by_tier_dir[(m["tier"], m["direction"])].append({**c, "_tenure": m["tenure"]})

    archetype_rows = []
    for (tier, direction), lst in sorted(by_tier_dir.items()):
        # group by archetype, take median signed IC in direction
        by_arc: dict[str, list[float]] = defaultdict(list)
        for c in lst:
            ic = c.get("ic")
            if ic is None:
                continue
            by_arc[c.get("archetype", "—")].append(float(ic))
        if direction == "POSITIVE":
            best_arc = (
                max(by_arc.items(), key=lambda kv: np.median(kv[1])) if by_arc else (None, [0])
            )
        else:
            best_arc = (
                min(by_arc.items(), key=lambda kv: np.median(kv[1])) if by_arc else (None, [0])
            )
        if best_arc[0] is not None:
            archetype_rows.append(
                f"<tr><td>{tier}</td><td>{direction}</td>"
                f"<td>{esc(best_arc[0])}</td>"
                f"<td class='num'>{fmt_ic(float(np.median(best_arc[1])))}</td>"
                f"<td class='num'>{len(best_arc[1])}</td></tr>"
            )

    # Best tenure per (tier, direction) by best validated candidate's IC
    by_meta: dict[tuple[str, str, str], dict[str, Any]] = {
        (c["cell"]["tier"], c["cell"]["tenure"], c["cell"]["direction"]): c for c in cells
    }
    tenure_rows = []
    for tier in TIERS:
        for direction in DIRECTIONS:
            best = None
            best_tenure = None
            for ten in TENURES:
                lookup = by_meta.get((tier, ten, direction))
                if lookup is None:
                    continue
                cands = [c for c in lookup["candidates"] if c.get("validated")]
                if not cands:
                    continue
                if direction == "POSITIVE":
                    top = max(cands, key=lambda c: c.get("ic") or -1)
                    if best is None or (top.get("ic") or -1) > (best.get("ic") or -1):
                        best, best_tenure = top, ten
                else:
                    top = min(cands, key=lambda c: c.get("ic") or 1)
                    if best is None or (top.get("ic") or 1) < (best.get("ic") or 1):
                        best, best_tenure = top, ten
            if best is None:
                tenure_rows.append(
                    f"<tr><td>{tier}</td><td>{direction}</td>"
                    f"<td>—</td><td class='num'>—</td><td>—</td></tr>"
                )
            else:
                tenure_rows.append(
                    f"<tr><td>{tier}</td><td>{direction}</td>"
                    f"<td>{best_tenure}</td>"
                    f"<td class='num'>{fmt_ic(best.get('ic'))}</td>"
                    f"<td class='mono'>{esc(best.get('name'))}</td></tr>"
                )

    # Sector-RS contribution: count archetypes containing 'sector' that validated
    sector_archetypes = (
        "sector_relative_leadership",
        "sector_drag",
        "sector_breakdown",
        "sector_relative_strength",
    )
    sector_rows = []
    for cell in cells:
        m = cell["cell"]
        n_sector = 0
        best_sector = None
        for c in cell["candidates"]:
            if c.get("archetype") in sector_archetypes and c.get("validated"):
                n_sector += 1
                if best_sector is None or abs(c.get("ic") or 0) > abs(best_sector.get("ic") or 0):
                    best_sector = c
        if n_sector > 0:
            sector_rows.append(
                f"<tr><td>{m['tier']}</td><td>{m['tenure']}</td><td>{m['direction']}</td>"
                f"<td class='num'>{n_sector}</td>"
                f"<td class='mono'>{esc(best_sector.get('name') if best_sector else '—')}</td>"
                f"<td class='num'>{fmt_ic(best_sector.get('ic') if best_sector else None)}</td></tr>"
            )

    return f"""
<section>
  <h2>Cross-tier pattern analysis</h2>

  <h3>Best archetype per tier × direction (by median IC across candidates)</h3>
  <table class='data-table'>
    <thead><tr><th>Tier</th><th>Direction</th><th>Archetype</th>
      <th>Median IC</th><th>n candidates</th></tr></thead>
    <tbody>{"".join(archetype_rows)}</tbody>
  </table>

  <h3>Best tenure per tier × direction (by best validated candidate)</h3>
  <table class='data-table'>
    <thead><tr><th>Tier</th><th>Direction</th><th>Best tenure</th>
      <th>IC</th><th>Rule</th></tr></thead>
    <tbody>{"".join(tenure_rows)}</tbody>
  </table>

  <h3>Sector-RS contribution — cells where sector-aware archetypes validated</h3>
  <table class='data-table'>
    <thead><tr><th>Tier</th><th>Tenure</th><th>Direction</th>
      <th># sector-validated</th><th>Best sector rule</th><th>IC</th></tr></thead>
    <tbody>{"".join(sector_rows) if sector_rows else "<tr><td colspan='6' style='text-align:center;color:var(--grey-600);'>No sector-archetype rules validated in any cell.</td></tr>"}</tbody>
  </table>
</section>
"""


def render_ship_park_table(
    cells: list[dict[str, Any]], classifications: dict[str, dict[str, Any]]
) -> str:
    rows = []
    for cell in cells:
        cid = cell_id(**cell["cell"])
        cls = classifications[cid]
        best = cls["best"]
        ic = best.get("ic") if best else None
        q_x = best.get("bh_q_value_cross_cell") if best else None
        rule = best.get("name") if best else "—"
        sp = cls["ship_or_park"]
        sp_cls = {
            "ship": "q-good",
            "park_borderline": "q-borderline",
            "park_no_signal": "q-bad",
            "park_survivorship": "q-borderline",
            "no_candidate": "q-bad",
        }.get(sp, "q-bad")
        rows.append(
            f"<tr>"
            f"<td>{cid}</td>"
            f"<td class='mono'>{esc(rule)}</td>"
            f"<td class='num'>{fmt_ic(ic)}</td>"
            f"<td class='num'>{fmt_q(q_x)}</td>"
            f"<td class='{sp_cls}'><b>{sp.replace('_', ' ').upper()}</b></td>"
            f"<td>{esc(cls['reason'])}</td>"
            f"</tr>"
        )
    return f"""
<section>
  <h2>What we'd ship vs what's parked</h2>
  <table class='data-table'>
    <thead><tr><th>Cell</th><th>Best rule</th><th>IC</th>
      <th>Cross-cell q</th><th>Disposition</th><th>Reason</th></tr></thead>
    <tbody>{"".join(rows)}</tbody>
  </table>
</section>
"""


def render_methodology() -> str:
    return f"""
<section>
  <h2>Methodology & provenance</h2>
  <ul>
    <li><b>Engine SHA:</b> <code>{ENGINE_SHA}</code> (branch <code>{BRANCH}</code>)</li>
    <li><b>Walk-forward windows (W1/W2/W3):</b>
      2022-05-01 → 2023-04-30 · 2023-05-01 → 2024-04-30 · 2024-05-01 → 2025-04-30</li>
    <li><b>Per-tenure IC floor:</b> 1m=0.02 · 3m=0.04 · 6m=0.05 · 12m=0.04
      (literature-backed; null-distribution sweep pending per Phase 0.5g-pre)</li>
    <li><b>Gate (per candidate):</b> sign-correct IC vs floor · ≥30 triggers per window ·
      consistent excess sign in correct direction across all 3 windows.</li>
    <li><b>Friction model:</b> friction_adjusted_excess = mean_excess − 23 bps (4 bps spread + 19 bps
      slippage at the median trigger).</li>
    <li><b>Sector LOO fix:</b> the v1 leakage bug (a stock's own return inside its sector
      benchmark) is corrected — sector benchmarks are now leave-one-out per name.</li>
    <li><b>BH-FDR procedure:</b> two-sided Fisher-z p-values from IC + n_obs. Within-cell BH-FDR
      applied per cell (n=191 NEGATIVE / 321 POSITIVE). <b>Cross-cell BH-FDR</b> applied across
      the pooled 6,144-test space; this is the more conservative gate we use for ship decisions.</li>
    <li><b>Cache:</b> 727 alive instruments. Delisted/suspended names absent (see disclaimer 1).</li>
    <li><b>Red-team critique:</b> <code>/tmp/deep_search_v2/factor_coverage_critique.md</code></li>
    <li><b>Cache QA:</b> <code>/tmp/deep_search_v2/cache_qa_report.md</code></li>
  </ul>
</section>
"""


def render_top5_friction(cells: list[dict[str, Any]]) -> str:
    """Top-5 cells by friction-adjusted excess of the best validated candidate."""
    rows = []
    for cell in cells:
        cands = [c for c in cell["candidates"] if c.get("validated")]
        if not cands:
            continue
        best = max(cands, key=lambda c: c.get("friction_adjusted_excess") or -1)
        rows.append((cell, best))
    rows.sort(key=lambda r: r[1].get("friction_adjusted_excess") or 0, reverse=True)
    out = []
    for cell, best in rows[:5]:
        m = cell["cell"]
        out.append(
            f"<tr>"
            f"<td>{cell_id(**m)}</td>"
            f"<td class='mono'>{esc(best.get('name'))}</td>"
            f"<td><span class='archetype-pill'>{esc(best.get('archetype', ''))}</span></td>"
            f"<td class='num'>{fmt_ic(best.get('ic'))}</td>"
            f"<td class='num'>{fmt_excess(best.get('friction_adjusted_excess'))}</td>"
            f"<td class='num'>{fmt_q(best.get('bh_q_value_cross_cell'))}</td>"
            f"</tr>"
        )
    return f"""
<section>
  <h2>Top 5 by friction-adjusted excess (across all 24 cells)</h2>
  <table class='data-table'>
    <thead><tr><th>Cell</th><th>Rule</th><th>Archetype</th>
      <th>IC</th><th>Fric-adj excess</th><th>Cross-cell q</th></tr></thead>
    <tbody>{"".join(out)}</tbody>
  </table>
</section>
"""


# --------------------------------------------------------------------------
# Build HTML
# --------------------------------------------------------------------------
def build_html(cells: list[dict[str, Any]], classifications: dict[str, dict[str, Any]]) -> str:
    cells_by_id = {cell_id(**c["cell"]): c for c in cells}
    stats = {
        "n_total_cells": len(cells),
        "n_total_candidates": sum(c["n_candidates"] for c in cells),
    }

    body_parts = [
        render_header(stats),
        render_disclaimers(),
        render_summary_stats(cells, classifications),
        render_matrix(cells_by_id, classifications),
        render_top5_friction(cells),
        render_archetype_heatmap(cells_by_id),
        render_cross_tier_analysis(cells),
        render_ship_park_table(cells, classifications),
        "<section><h2>Per-cell drill-downs</h2>",
    ]
    # Drill-downs grouped by direction then tier-tenure
    for direction in DIRECTIONS:
        body_parts.append(
            f"<h3>{direction} ({'survivorship-caveated' if direction == 'NEGATIVE' else 'no survivorship caveat'})</h3>"
        )
        for tier in TIERS:
            for tenure in TENURES:
                cid = cell_id(tier, tenure, direction)
                body_parts.append(render_cell_detail(cells_by_id[cid], classifications[cid]))
    body_parts.append("</section>")

    body_parts.append(render_methodology())
    body_parts.append(
        "<footer>Atlas v6 deep-search v2 aggregator · "
        f"{datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}</footer>"
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Atlas v6 — Deep Search v2 (24 cells)</title>
<style>{CSS}</style>
</head>
<body>
{"".join(body_parts)}
<script>{SORT_JS}</script>
</body>
</html>
"""


# --------------------------------------------------------------------------
# Persist SQL
# --------------------------------------------------------------------------
def build_persist_sql(
    cells: list[dict[str, Any]], classifications: dict[str, dict[str, Any]]
) -> str:
    """One INSERT per cell whose best candidate passes gate AND cross-cell q ≤ 0.10."""
    lines = [
        "-- =========================================================",
        "-- Atlas v6 Deep Search v2 — dry-run persistence",
        f"-- Generated: {datetime.now(UTC).isoformat()}",
        f"-- Engine SHA: {ENGINE_SHA}",
        f"-- Branch:     {BRANCH}",
        f"-- Methodology: {METHODOLOGY_REF}",
        "-- ",
        "-- DO NOT EXECUTE blind. Review each row, then run with explicit",
        "-- DBA approval. NEGATIVE rows carry [SURVIVORSHIP-BIASED] prefix",
        "-- because the OHLCV cache is survivor-only (727/2275 names).",
        "-- =========================================================",
        "",
        "BEGIN;",
        "",
    ]
    n_emitted = 0
    n_skipped = 0
    for cell in cells:
        cid = cell_id(**cell["cell"])
        cls = classifications[cid]
        best = cls["best"]
        if best is None:
            n_skipped += 1
            lines.append(f"-- SKIP {cid}: no candidates returned")
            continue
        q_cross = best.get("bh_q_value_cross_cell")
        if not cls["validated"] or q_cross is None or q_cross > 0.10:
            n_skipped += 1
            lines.append(
                f"-- SKIP {cid}: best={best.get('name')} "
                f"validated={cls['validated']} cross-cell-q={fmt_q(q_cross)} — "
                f"does not pass ship gate (q≤0.10)"
            )
            continue
        dsl = build_rule_dsl(best, cell["cell"])
        dsl_json = json.dumps(dsl, separators=(",", ":"))
        # SQL-escape single quotes by doubling.
        dsl_sql = dsl_json.replace("'", "''")
        prefix = "[SURVIVORSHIP-BIASED] " if cell["cell"]["direction"] == "NEGATIVE" else ""
        notes = (
            f"{prefix}{best.get('name')} | "
            f"IC={best.get('ic'):.4f} | "
            f"fric-adj={best.get('friction_adjusted_excess'):.4f} | "
            f"within-cell-q={fmt_q(best.get('bh_q_value'))} | "
            f"cross-cell-q={fmt_q(q_cross)}"
        ).replace("'", "''")
        lines.append(f"-- {cid}: ship-grade (cross-cell q={q_cross:.4f})")
        # Dry-run SQL file — never executed by this script. Values come from
        # signed-off candidate JSONs with quote-escaping above.
        # ruff S608 flags any "INSERT INTO ... f-string" — suppressed because
        # we emit text to disk for human review, not execute it.
        insert_stmt = (
            "INSERT INTO atlas_cell_definitions ("  # noqa: S608
            "cell_id, tier, tenure, direction, rule_dsl, methodology_ref, notes, created_at"
            ") VALUES ("
            "gen_random_uuid(), "
            f"'{cell['cell']['tier']}', "
            f"'{cell['cell']['tenure']}', "
            f"'{cell['cell']['direction']}', "
            f"'{dsl_sql}'::jsonb, "
            f"'{METHODOLOGY_REF}', "
            f"'{notes}', "
            "NOW()"
            ");"
        )
        lines.append(insert_stmt)
        lines.append("")
        n_emitted += 1
    lines.append("")
    lines.append(f"-- Summary: {n_emitted} rows to INSERT, {n_skipped} skipped.")
    lines.append("COMMIT;")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Master summary JSON
# --------------------------------------------------------------------------
def build_master_summary(
    cells: list[dict[str, Any]], classifications: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    out = []
    for cell in cells:
        cid = cell_id(**cell["cell"])
        cls = classifications[cid]
        best = cls["best"]
        rec = {
            "cell_id": cid,
            "tier": cell["cell"]["tier"],
            "tenure": cell["cell"]["tenure"],
            "direction": cell["cell"]["direction"],
            "n_candidates": cell["n_candidates"],
            "n_gate_pass": cell["n_gate_pass"],
            "best_rule": best.get("name") if best else None,
            "best_archetype": best.get("archetype") if best else None,
            "best_ic": best.get("ic") if best else None,
            "best_fric_adj_excess": best.get("friction_adjusted_excess") if best else None,
            "best_q_value_within_cell": best.get("bh_q_value") if best else None,
            "best_q_value_cross_cell": best.get("bh_q_value_cross_cell") if best else None,
            "best_validated": cls["validated"],
            "grade": cls["grade"],
            "ship_or_park": cls["ship_or_park"],
            "reason": cls["reason"],
            "disclaimers_applicable": (
                ["survivorship_bias", "w3_thin_coverage", "no_fundamentals"]
                if cell["cell"]["direction"] == "NEGATIVE"
                else ["w3_thin_coverage", "no_fundamentals"]
            ),
        }
        out.append(rec)
    return out


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main() -> None:
    print("Loading cells...")
    cells = load_all_cells()
    print(f"  {len(cells)} cells loaded")

    print("Computing cross-cell BH-FDR over pooled candidate space...")
    annotate_cross_cell_q(cells)

    print("Classifying cells (ship/park)...")
    classifications = {cell_id(**c["cell"]): classify_cell(c) for c in cells}

    print(f"Building HTML → {HTML_OUT}")
    html_out = build_html(cells, classifications)
    os.makedirs(os.path.dirname(HTML_OUT), exist_ok=True)
    with open(HTML_OUT, "w") as fh:
        fh.write(html_out)
    print(f"  wrote {len(html_out):,} bytes")

    print(f"Building persist SQL → {SQL_OUT}")
    sql = build_persist_sql(cells, classifications)
    with open(SQL_OUT, "w") as fh:
        fh.write(sql)
    print(f"  wrote {len(sql):,} bytes")

    print(f"Building master_summary.json → {SUMMARY_OUT}")
    summary = build_master_summary(cells, classifications)
    with open(SUMMARY_OUT, "w") as fh:
        json.dump(summary, fh, indent=2)
    print(f"  {len(summary)} records")

    # Quick exit-report stats
    n_green = sum(1 for v in classifications.values() if v["grade"] == "green")
    n_amber = sum(1 for v in classifications.values() if v["grade"] == "amber")
    n_red = sum(1 for v in classifications.values() if v["grade"] == "red")
    print()
    print(f"GREEN (ship-grade): {n_green}")
    print(f"AMBER (borderline): {n_amber}")
    print(f"RED   (no signal):  {n_red}")
    print()
    print("Cells green-graded:")
    for cid, v in classifications.items():
        if v["grade"] == "green":
            b = v["best"]
            print(
                f"  {cid}: {b.get('name')} IC={b.get('ic'):+.4f} "
                f"fric-adj={b.get('friction_adjusted_excess'):+.4f} "
                f"cross-q={v['q_cross']:.4f}"
            )
    print()
    print("Top 5 by fric-adj excess (validated only):")
    validated_rows = []
    for cell in cells:
        m = cell["cell"]
        cands = [c for c in cell["candidates"] if c.get("validated")]
        for c in cands:
            validated_rows.append((cell_id(**m), c))
    validated_rows.sort(key=lambda r: r[1].get("friction_adjusted_excess") or 0, reverse=True)
    for cid, c in validated_rows[:5]:
        print(f"  {cid}: {c.get('name')} fric-adj={c.get('friction_adjusted_excess'):+.4f}")


if __name__ == "__main__":
    main()
