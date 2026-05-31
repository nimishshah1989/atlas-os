"""Compare v2 (alive-only) vs v3 (full-universe) deep-search outputs.

Reads two parallel directories of per-cell JSONs:

* ``--v2-cells-dir`` — existing 24 cells from the survivorship-biased
  v2 cache (default ``/tmp/deep_search_v2/cells``).
* ``--v3-cells-dir`` — new 24 cells from the full-universe v3 cache
  (default ``/tmp/deep_search_v3/cells``).

For each cell, computes:

* Did the top-1 rule change? If so, both names + ICs + fric-adj excess.
* Universe size delta (alive-only n vs full n at the trigger set).
* NEGATIVE direction: how many MORE rules pass the gate now?
* POSITIVE direction: did adding delisted instruments change which rules
  survive cross-cell BH-FDR?

Emits:

* ``<output-dir>/v2_vs_v3_comparison.md`` — markdown report.
* ``<output-dir>/v2_vs_v3_comparison.html`` — Atlas-styled HTML.
* ``<output-dir>/atlas_cell_definitions_v3.sql`` — persist SQL that
  DEPRECATES the v2 rows (``deprecated_at = NOW()``) and INSERTS new
  top-1 rules with ``methodology_lock_ref = 'DEEP_SEARCH_V3_2026-05-25'``.
* ``<output-dir>/atlas_cell_rule_candidates_v3.sql`` — top-5 candidate
  INSERTs FK-referencing the new cell_definitions rows.

The SQL files are **dry-run artifacts** — the user reviews them, then
runs them inside a Supabase transaction after `touch .supabase-write-approved`.

CLI
---
    python scripts/compare_v2_v3.py \\
        --v2-cells-dir /tmp/deep_search_v2/cells \\
        --v3-cells-dir /tmp/deep_search_v3/cells \\
        --output-dir   /Users/nimishshah/.gstack/projects/atlas-os/v3-cache
"""

# allow-large: one-shot reporting + persist-SQL emitter. Splitting
# would force shared CLI plumbing across modules. The bulk is HTML
# rendering (visual artifact) — exempt under the same rationale as
# scripts/aggregate_deep_search_v2.py.

from __future__ import annotations

import argparse
import glob
import html
import json
import math
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TIERS = ("Large", "Mid", "Small")
TENURES = ("1m", "3m", "6m", "12m")
DIRECTIONS = ("POSITIVE", "NEGATIVE")

V2_METHODOLOGY = "DEEP_SEARCH_V2_2026-05-24"
V3_METHODOLOGY = "DEEP_SEARCH_V3_2026-05-25"

# Ship gate (matches aggregate_deep_search_v2.py).
SHIP_Q_THRESHOLD = 0.10
PER_TENURE_IC_FLOOR = {"1m": 0.02, "3m": 0.04, "6m": 0.05, "12m": 0.04}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class CellComparison:
    """Per-cell v2 ↔ v3 delta record."""

    cell_id: str
    tier: str
    tenure: str
    direction: str
    v2_n_candidates: int
    v3_n_candidates: int
    v2_n_gate_pass: int
    v3_n_gate_pass: int
    v2_top_name: str | None
    v3_top_name: str | None
    v2_top_ic: float | None
    v3_top_ic: float | None
    v2_top_fric_adj: float | None
    v3_top_fric_adj: float | None
    v2_top_n_obs: int | None
    v3_top_n_obs: int | None
    rule_changed: bool
    universe_delta: int | None  # v3_top_n_obs - v2_top_n_obs
    v2_top: dict[str, Any] | None
    v3_top: dict[str, Any] | None


# ---------------------------------------------------------------------------
# IO
# ---------------------------------------------------------------------------


def _cell_id(tier: str, tenure: str, direction: str) -> str:
    return f"{tier}-{tenure}-{direction}"


def _load_cells(cells_dir: Path) -> dict[str, dict[str, Any]]:
    """Load per-cell JSON files keyed by ``cell_id``.

    Missing cells (e.g. a partial v3 run) are tolerated — we record the
    absence in the comparison and skip persist-SQL emission for them.
    """
    out: dict[str, dict[str, Any]] = {}
    for path in sorted(glob.glob(str(cells_dir / "*.json"))):
        with open(path) as fh:
            cell = json.load(fh)
        meta = cell.get("cell", {})
        cid = _cell_id(meta.get("tier", "?"), meta.get("tenure", "?"), meta.get("direction", "?"))
        out[cid] = cell
    return out


def _top_candidate(cell: dict[str, Any]) -> dict[str, Any] | None:
    """Return the cell's top candidate (best validated, else best signed IC)."""
    cands = cell.get("candidates", []) or []
    direction = cell.get("cell", {}).get("direction", "POSITIVE")
    validated = [c for c in cands if c.get("validated")]

    def _ic_ok(c: dict[str, Any]) -> bool:
        ic = c.get("ic")
        return ic is not None and not (isinstance(ic, float) and math.isnan(ic))

    valid_ic = [c for c in cands if _ic_ok(c)]
    if validated:
        if direction == "POSITIVE":
            validated.sort(key=lambda c: c["ic"], reverse=True)
        else:
            validated.sort(key=lambda c: c["ic"])
        return validated[0]
    if not valid_ic:
        return None
    if direction == "POSITIVE":
        return max(valid_ic, key=lambda c: c["ic"])
    return min(valid_ic, key=lambda c: c["ic"])


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def build_comparisons(
    v2_cells: dict[str, dict[str, Any]],
    v3_cells: dict[str, dict[str, Any]],
) -> list[CellComparison]:
    """Walk all 24 cells and produce per-cell deltas."""
    comparisons: list[CellComparison] = []
    for tier in TIERS:
        for tenure in TENURES:
            for direction in DIRECTIONS:
                cid = _cell_id(tier, tenure, direction)
                v2 = v2_cells.get(cid)
                v3 = v3_cells.get(cid)
                v2_top = _top_candidate(v2) if v2 else None
                v3_top = _top_candidate(v3) if v3 else None
                v2_name = v2_top.get("name") if v2_top else None
                v3_name = v3_top.get("name") if v3_top else None
                v2_n_obs = v2_top.get("n_observations") if v2_top else None
                v3_n_obs = v3_top.get("n_observations") if v3_top else None
                universe_delta: int | None
                if v2_n_obs is not None and v3_n_obs is not None:
                    universe_delta = int(v3_n_obs) - int(v2_n_obs)
                else:
                    universe_delta = None
                comparisons.append(
                    CellComparison(
                        cell_id=cid,
                        tier=tier,
                        tenure=tenure,
                        direction=direction,
                        v2_n_candidates=v2.get("n_candidates", 0) if v2 else 0,
                        v3_n_candidates=v3.get("n_candidates", 0) if v3 else 0,
                        v2_n_gate_pass=v2.get("n_gate_pass", 0) if v2 else 0,
                        v3_n_gate_pass=v3.get("n_gate_pass", 0) if v3 else 0,
                        v2_top_name=v2_name,
                        v3_top_name=v3_name,
                        v2_top_ic=v2_top.get("ic") if v2_top else None,
                        v3_top_ic=v3_top.get("ic") if v3_top else None,
                        v2_top_fric_adj=(
                            v2_top.get("friction_adjusted_excess") if v2_top else None
                        ),
                        v3_top_fric_adj=(
                            v3_top.get("friction_adjusted_excess") if v3_top else None
                        ),
                        v2_top_n_obs=v2_n_obs,
                        v3_top_n_obs=v3_n_obs,
                        rule_changed=bool(v2_name != v3_name and v3_name is not None),
                        universe_delta=universe_delta,
                        v2_top=v2_top,
                        v3_top=v3_top,
                    )
                )
    return comparisons


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _fmt(v: float | int | None, kind: str = "ic") -> str:
    if v is None:
        return "—"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "—"
    if math.isnan(f) or math.isinf(f):
        return "—"
    if kind == "ic":
        return f"{f:+.4f}"
    if kind == "pct":
        return f"{f * 100:+.2f}%"
    if kind == "int":
        return f"{int(f):,}"
    return str(f)


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------


def render_markdown(comparisons: list[CellComparison]) -> str:
    rule_changed = [c for c in comparisons if c.rule_changed]
    n_neg_more_pass = sum(
        1 for c in comparisons if c.direction == "NEGATIVE" and c.v3_n_gate_pass > c.v2_n_gate_pass
    )
    n_pos_more_pass = sum(
        1 for c in comparisons if c.direction == "POSITIVE" and c.v3_n_gate_pass > c.v2_n_gate_pass
    )
    n_v3_missing = sum(1 for c in comparisons if c.v3_top is None)

    lines = [
        "# v2 vs v3 deep-search comparison",
        "",
        f"Generated: {datetime.now(UTC).isoformat()}",
        "",
        "## Headline numbers",
        "",
        f"- **Cells with rule change**: {len(rule_changed)} / {len(comparisons)}",
        f"- **NEGATIVE cells where v3 has more gate-passers**: {n_neg_more_pass} / 12",
        f"- **POSITIVE cells where v3 has more gate-passers**: {n_pos_more_pass} / 12",
    ]
    if n_v3_missing:
        lines.append(f"- **Cells missing in v3 output**: {n_v3_missing} (partial run?)")
    lines.append("")
    lines.append("## Per-cell summary")
    lines.append("")
    lines.append(
        "| Cell | v2 gate-pass | v3 gate-pass | v2 top rule | v3 top rule | Δ rule | v2 IC | v3 IC | v2 n_obs | v3 n_obs | Δ n_obs |"
    )
    lines.append("|---|---:|---:|---|---|:---:|---:|---:|---:|---:|---:|")
    for c in comparisons:
        lines.append(
            f"| {c.cell_id} "
            f"| {c.v2_n_gate_pass} "
            f"| {c.v3_n_gate_pass} "
            f"| {c.v2_top_name or '—'} "
            f"| {c.v3_top_name or '—'} "
            f"| {'YES' if c.rule_changed else ''} "
            f"| {_fmt(c.v2_top_ic, 'ic')} "
            f"| {_fmt(c.v3_top_ic, 'ic')} "
            f"| {_fmt(c.v2_top_n_obs, 'int')} "
            f"| {_fmt(c.v3_top_n_obs, 'int')} "
            f"| {_fmt(c.universe_delta, 'int')} |"
        )
    lines.append("")

    if rule_changed:
        lines.append("## Cells where the top rule changed")
        lines.append("")
        for c in rule_changed:
            lines.append(f"### {c.cell_id}")
            lines.append("")
            lines.append(
                f"- v2: `{c.v2_top_name}` "
                f"(IC {_fmt(c.v2_top_ic, 'ic')}, "
                f"fric-adj {_fmt(c.v2_top_fric_adj, 'pct')}, "
                f"n_obs {_fmt(c.v2_top_n_obs, 'int')})"
            )
            lines.append(
                f"- v3: `{c.v3_top_name}` "
                f"(IC {_fmt(c.v3_top_ic, 'ic')}, "
                f"fric-adj {_fmt(c.v3_top_fric_adj, 'pct')}, "
                f"n_obs {_fmt(c.v3_top_n_obs, 'int')})"
            )
            lines.append("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# HTML report (Atlas visual language; teal/grey/red)
# ---------------------------------------------------------------------------


def _esc(v: Any) -> str:
    return html.escape(str(v)) if v is not None else "—"


HTML_CSS = """
:root {
  --teal: #1D9E75;
  --teal-light: #E8F5EF;
  --red: #C8102E;
  --red-light: #FBEAED;
  --amber: #F5A623;
  --amber-light: #FFF5E1;
  --grey-50: #F8F9FA;
  --grey-100: #ECEFF1;
  --grey-200: #CFD8DC;
  --grey-700: #455A64;
  --grey-900: #1A2329;
}
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI",
    Roboto, "Helvetica Neue", Arial, sans-serif;
  margin: 0; padding: 24px 32px; background: var(--grey-50);
  color: var(--grey-900); line-height: 1.45; font-size: 14px;
}
header.page-header { border-bottom: 2px solid var(--teal); padding-bottom: 16px;
                     margin-bottom: 24px; }
header.page-header h1 { margin: 0; font-size: 24px; }
header.page-header .sub { margin-top: 4px; color: var(--grey-700); font-size: 13px; }
section { background: white; border: 1px solid var(--grey-200); border-radius: 8px;
          padding: 20px 24px; margin-bottom: 20px; }
section h2 { margin-top: 0; font-size: 18px; border-bottom: 1px solid var(--grey-100);
             padding-bottom: 8px; }
.stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
             gap: 12px; }
.stat { background: var(--grey-50); padding: 12px; border-radius: 6px;
        border: 1px solid var(--grey-100); }
.stat-value { font-size: 22px; font-weight: 600; }
.stat-label { font-size: 11px; color: var(--grey-700); text-transform: uppercase;
              letter-spacing: 0.05em; margin-top: 4px; }
table.data { border-collapse: collapse; width: 100%; font-size: 12.5px; }
table.data th, table.data td { padding: 6px 10px; border-bottom: 1px solid var(--grey-100);
                               text-align: left; vertical-align: top; }
table.data th { background: var(--grey-50); text-transform: uppercase; font-size: 11px;
                color: var(--grey-700); letter-spacing: 0.05em; }
table.data td.num { text-align: right; font-family: ui-monospace, Menlo, monospace;
                    white-space: nowrap; }
tr.changed { background: var(--amber-light); }
.pos { color: var(--teal); font-weight: 600; }
.neg { color: var(--red);  font-weight: 600; }
"""


def render_html(comparisons: list[CellComparison]) -> str:
    rule_changed_count = sum(1 for c in comparisons if c.rule_changed)
    neg_more = sum(
        1 for c in comparisons if c.direction == "NEGATIVE" and c.v3_n_gate_pass > c.v2_n_gate_pass
    )
    pos_more = sum(
        1 for c in comparisons if c.direction == "POSITIVE" and c.v3_n_gate_pass > c.v2_n_gate_pass
    )

    rows = []
    for c in comparisons:
        delta_class = "pos" if (c.universe_delta or 0) > 0 else "neg"
        rows.append(
            f"<tr class='{'changed' if c.rule_changed else ''}'>"
            f"<td>{_esc(c.cell_id)}</td>"
            f"<td class='num'>{c.v2_n_gate_pass}</td>"
            f"<td class='num'>{c.v3_n_gate_pass}</td>"
            f"<td><code>{_esc(c.v2_top_name or '—')}</code></td>"
            f"<td><code>{_esc(c.v3_top_name or '—')}</code></td>"
            f"<td class='num'>{_fmt(c.v2_top_ic, 'ic')}</td>"
            f"<td class='num'>{_fmt(c.v3_top_ic, 'ic')}</td>"
            f"<td class='num'>{_fmt(c.v2_top_n_obs, 'int')}</td>"
            f"<td class='num'>{_fmt(c.v3_top_n_obs, 'int')}</td>"
            f"<td class='num {delta_class}'>{_fmt(c.universe_delta, 'int')}</td>"
            f"</tr>"
        )
    return f"""<!doctype html>
<html lang='en'>
<head>
<meta charset='utf-8' />
<title>v2 vs v3 deep-search comparison</title>
<style>{HTML_CSS}</style>
</head>
<body>
<header class='page-header'>
  <h1>v2 vs v3 deep-search — comparison report</h1>
  <p class='sub'>v2 (alive-only, 727 iids) vs v3 (full universe, ~2,294 iids) ·
    Generated {datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")}</p>
</header>

<section>
  <h2>Headline</h2>
  <div class='stat-grid'>
    <div class='stat'><div class='stat-value'>{rule_changed_count}/{len(comparisons)}</div>
      <div class='stat-label'>Cells with rule change</div></div>
    <div class='stat'><div class='stat-value'>{neg_more}/12</div>
      <div class='stat-label'>NEGATIVE cells with more gate-passers</div></div>
    <div class='stat'><div class='stat-value'>{pos_more}/12</div>
      <div class='stat-label'>POSITIVE cells with more gate-passers</div></div>
  </div>
</section>

<section>
  <h2>Per-cell summary</h2>
  <table class='data'>
    <thead><tr>
      <th>Cell</th><th>v2 gate-pass</th><th>v3 gate-pass</th>
      <th>v2 top rule</th><th>v3 top rule</th>
      <th>v2 IC</th><th>v3 IC</th>
      <th>v2 n_obs</th><th>v3 n_obs</th><th>Δ n_obs</th>
    </tr></thead>
    <tbody>{"".join(rows)}</tbody>
  </table>
</section>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Persist SQL — atlas_cell_definitions_v3.sql + atlas_cell_rule_candidates_v3.sql
# ---------------------------------------------------------------------------


def _rule_dsl_for_candidate(cand: dict[str, Any], meta: dict[str, str]) -> dict[str, Any]:
    """JSONB rule_dsl payload (mirrors aggregate_deep_search_v2.build_rule_dsl)."""
    return {
        "version": "atlas.deep_search.v3",
        "tier": meta["tier"],
        "tenure": meta["tenure"],
        "direction": meta["direction"],
        "rule_name": cand.get("name"),
        "archetype": cand.get("archetype"),
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
        "methodology_ref": V3_METHODOLOGY,
    }


def _sql_quote_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":")).replace("'", "''")


def _fmt_decimal(v: Any) -> str:
    """Format a number for SQL VALUES; ``NULL`` when None/NaN/Inf."""
    if v is None:
        return "NULL"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "NULL"
    if math.isnan(f) or math.isinf(f):
        return "NULL"
    return f"{f:.6f}"


def build_persist_sql(
    comparisons: list[CellComparison],
    v3_cells: dict[str, dict[str, Any]],
) -> tuple[str, str]:
    """Build two SQL files: definitions (top-1) + candidates (top-5).

    Both files are wrapped in a single transaction. Definitions starts with
    a DEPRECATE step for any active v2 rows; the partial unique index
    ``uq_atlas_cell_definitions_active`` is satisfied because the v2 rows
    will have ``deprecated_at`` set BEFORE the v3 rows are inserted.
    """
    timestamp = datetime.now(UTC).isoformat()
    defs_lines: list[str] = [
        "-- =========================================================",
        "-- atlas_cell_definitions — v3 swap",
        f"-- Generated: {timestamp}",
        "-- Source: scripts/compare_v2_v3.py",
        "-- Methodology ref: " + V3_METHODOLOGY,
        "-- ",
        "-- This deprecates ALL active v2 cells, then inserts new",
        "-- top-1 rules per cell. The unique partial index",
        "-- uq_atlas_cell_definitions_active enforces one active row",
        "-- per (cap_tier, action, tenure) — the DEPRECATE step",
        "-- vacates the slot before the INSERT.",
        "-- ",
        "-- DO NOT EXECUTE without `touch .supabase-write-approved`",
        "-- =========================================================",
        "",
        "BEGIN;",
        "",
        "-- Step 1: deprecate v2 cells",
        "UPDATE atlas.atlas_cell_definitions",
        "   SET deprecated_at = NOW()",
        f" WHERE methodology_lock_ref LIKE '{V2_METHODOLOGY[:14]}%'",
        "   AND deprecated_at IS NULL;",
        "",
        "-- Step 2: insert v3 top-1 cells",
    ]
    cands_lines: list[str] = [
        "-- =========================================================",
        "-- atlas_cell_rule_candidates — v3 top-5 per cell",
        f"-- Generated: {timestamp}",
        "-- Source: scripts/compare_v2_v3.py",
        "-- Methodology ref: " + V3_METHODOLOGY,
        "-- ",
        "-- Run AFTER atlas_cell_definitions_v3.sql. The INSERT below",
        "-- looks up the newly-inserted cell_id via the partial unique",
        "-- index (deprecated_at IS NULL).",
        "-- =========================================================",
        "",
        "BEGIN;",
        "",
    ]

    n_defs = 0
    n_cands = 0
    n_skipped = 0

    for c in comparisons:
        cid = c.cell_id
        v3 = v3_cells.get(cid)
        if v3 is None or c.v3_top is None:
            defs_lines.append(f"-- SKIP {cid}: no v3 data or no top candidate")
            cands_lines.append(f"-- SKIP {cid}: no v3 data or no top candidate")
            n_skipped += 1
            continue
        meta = {"tier": c.tier, "tenure": c.tenure, "direction": c.direction}
        action = "POSITIVE" if c.direction == "POSITIVE" else "NEGATIVE"
        # Definition (top-1)
        top = c.v3_top
        dsl = _rule_dsl_for_candidate(top, meta)
        dsl_sql = _sql_quote_json(dsl)
        confidence = top.get("tp_rate")
        fric_adj = top.get("friction_adjusted_excess")
        notes = (
            f"v3 top-1 | {top.get('name')} | "
            f"IC={top.get('ic')} | "
            f"fric-adj={top.get('friction_adjusted_excess')} | "
            f"n_obs={top.get('n_observations')}"
        )
        notes_sql = notes.replace("'", "''")
        defs_lines.append(f"-- {cid}: top={top.get('name')}")
        # S608: dry-run SQL file written for human review, never executed by
        # this script. All injected values are signed-off cell JSONs with
        # quote-escaping above. Mirrors aggregate_deep_search_v2.py.
        defs_lines.append(
            "INSERT INTO atlas.atlas_cell_definitions ("
            "cap_tier, action, tenure, rule_dsl, "
            "confidence_unconditional, friction_adjusted_excess, "
            "stable_features, methodology_lock_ref, "
            "rule_version, drift_status, validated_at, created_at"
            ") VALUES ("
            f"'{c.tier}', '{action}', '{c.tenure}', "
            f"'{dsl_sql}'::jsonb, "
            f"{_fmt_decimal(confidence)}, {_fmt_decimal(fric_adj)}, "
            "NULL, "
            f"'{V3_METHODOLOGY}', 1, 'healthy', NOW(), NOW()"
            ");"
        )
        # Notes annotation as a separate comment line for human reviewers
        defs_lines.append(f"-- notes: {notes_sql}")
        defs_lines.append("")
        n_defs += 1

        # Candidates top-5
        cands = v3.get("top_10", []) or []
        for rank, cand in enumerate(cands[:5], start=1):
            cdsl = _rule_dsl_for_candidate(cand, meta)
            cdsl_sql = _sql_quote_json(cdsl)
            archetype = cand.get("archetype", "")
            ic = cand.get("ic")
            cand_fric = cand.get("friction_adjusted_excess")
            bh_q = cand.get("bh_q_value")
            cands_lines.append(f"-- {cid} rank {rank}: {cand.get('name')}")
            # S608: same rationale as the definitions INSERT above — text
            # emission for human review, never executed by this script.
            cands_lines.append(
                "INSERT INTO atlas.atlas_cell_rule_candidates "
                "(cell_definition_id, rank, rule_dsl, archetype, ic, "
                "friction_adjusted_excess, bh_q_value, eli5, validated, notes) "
                "SELECT cell_id, "
                f"{rank}, '{cdsl_sql}'::jsonb, '{archetype}', "
                f"{_fmt_decimal(ic)}, {_fmt_decimal(cand_fric)}, "
                f"{_fmt_decimal(bh_q)}, "
                f"'v3 top-{rank} candidate', "
                f"{'TRUE' if cand.get('validated') else 'FALSE'}, "
                f"'v3 rank {rank}' "
                "FROM atlas.atlas_cell_definitions "
                f"WHERE cap_tier = '{c.tier}' "
                f"AND action = '{action}' "
                f"AND tenure = '{c.tenure}' "
                f"AND methodology_lock_ref = '{V3_METHODOLOGY}' "
                "AND deprecated_at IS NULL;"
            )
            n_cands += 1
        cands_lines.append("")

    defs_lines.extend(
        ["", f"-- summary: {n_defs} cell definitions, {n_skipped} skipped.", "COMMIT;", ""]
    )
    cands_lines.extend(["", f"-- summary: {n_cands} candidate rows.", "COMMIT;", ""])
    return "\n".join(defs_lines), "\n".join(cands_lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_cli_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="compare_v2_v3", description=__doc__)
    p.add_argument(
        "--v2-cells-dir",
        type=Path,
        default=Path("/tmp/deep_search_v2/cells"),  # noqa: S108
    )
    p.add_argument(
        "--v3-cells-dir",
        type=Path,
        default=Path("/tmp/deep_search_v3/cells"),  # noqa: S108
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/Users/nimishshah/.gstack/projects/atlas-os/v3-cache"),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_cli_parser().parse_args(argv)
    if not args.v2_cells_dir.exists():
        print(f"ERROR: --v2-cells-dir not found: {args.v2_cells_dir}", file=sys.stderr)
        return 2
    if not args.v3_cells_dir.exists():
        print(f"ERROR: --v3-cells-dir not found: {args.v3_cells_dir}", file=sys.stderr)
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)

    v2_cells = _load_cells(args.v2_cells_dir)
    v3_cells = _load_cells(args.v3_cells_dir)
    print(f"Loaded {len(v2_cells)} v2 cells, {len(v3_cells)} v3 cells")

    comparisons = build_comparisons(v2_cells, v3_cells)

    md = render_markdown(comparisons)
    md_path = args.output_dir / "v2_vs_v3_comparison.md"
    md_path.write_text(md)
    print(f"  wrote {md_path}")

    html_doc = render_html(comparisons)
    html_path = args.output_dir / "v2_vs_v3_comparison.html"
    html_path.write_text(html_doc)
    print(f"  wrote {html_path}")

    defs_sql, cands_sql = build_persist_sql(comparisons, v3_cells)
    defs_path = args.output_dir / "atlas_cell_definitions_v3.sql"
    cands_path = args.output_dir / "atlas_cell_rule_candidates_v3.sql"
    defs_path.write_text(defs_sql)
    cands_path.write_text(cands_sql)
    print(f"  wrote {defs_path}")
    print(f"  wrote {cands_path}")

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
