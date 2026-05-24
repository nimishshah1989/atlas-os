"""Atlas-visual-language HTML renderer for the 24-cell matrix status.

The matrix view (CONTEXT.md §"24-framework discovery model") presents the
full ``(cap_tier × tenure × actionable_state)`` cube. Each cell is colour-
coded by status and carries a drill-down showing:

* IC + per-tenure floor + pass/fail.
* TP/TN rate (per action).
* Friction-adjusted excess (the cost-of-trading-adjusted edge).
* Percentile distribution of trigger-set forward excess.
* n observations + stable features.
* Notes (validation reason for ``no_conviction`` cells).

Aesthetic: white background, subtle borders, teal accent (#1D9E75) per
the global frontend conventions. The output is a single self-contained
HTML file — no external CSS, no JS dependencies. Open in any browser.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atlas.discovery.engine import CellDiscoveryResult, SweepResult


_TENURES = ("1m", "3m", "6m", "12m")
_ACTIONS = ("POSITIVE", "NEGATIVE")
_CAP_TIERS = ("Large", "Mid", "Small")  # render order; matches docs/CONTEXT matrix


def _fmt_decimal(value: Decimal | None, places: int = 4, default: str = "—") -> str:
    if value is None:
        return default
    return f"{float(value):.{places}f}"


def _fmt_pct(value: Decimal | None, places: int = 1, default: str = "—") -> str:
    if value is None:
        return default
    return f"{float(value) * 100:.{places}f}%"


def _cell_status_class(cell: CellDiscoveryResult) -> str:
    if cell.validated:
        return "cell-validated"
    if cell.n_observations == 0:
        return "cell-empty"
    return "cell-no-conviction"


def _cell_status_label(cell: CellDiscoveryResult) -> str:
    if cell.validated:
        return "VALIDATED"
    if cell.n_observations == 0:
        return "no_data"
    return "no_conviction"


def _percentile_row(label: str, value: Decimal | None) -> str:
    fmt = _fmt_pct(value, places=2)
    return (
        f'<div class="pct-row">'
        f'<span class="pct-label">{escape(label)}</span>'
        f'<span class="pct-value">{fmt}</span>'
        f"</div>"
    )


def _render_cell(cell: CellDiscoveryResult) -> str:
    status_class = _cell_status_class(cell)
    status_label = _cell_status_label(cell)
    spec = cell.spec

    confidence = cell.tp_rate if spec.action == "POSITIVE" else cell.tn_rate
    confidence_label = "TP rate" if spec.action == "POSITIVE" else "TN rate"

    cap = escape(spec.cap_tier)
    tenure = escape(spec.tenure)
    action = escape(spec.action)
    rule_hint = escape(spec.rule_type_hint)
    pair_label = f"{cap} · {tenure} · {action}"

    median_pct = _fmt_pct(cell.median_excess, places=2)
    friction_pct = _fmt_pct(cell.friction_adjusted_excess, places=2)

    pct_rows = "".join(
        [
            _percentile_row("p10", cell.percentile_10),
            _percentile_row("p25", cell.percentile_25),
            _percentile_row("p50", cell.percentile_50),
            _percentile_row("p75", cell.percentile_75),
            _percentile_row("p90", cell.percentile_90),
        ]
    )

    return f"""
    <div class="cell {status_class}">
      <div class="cell-header">
        <span class="cell-pair">{pair_label}</span>
        <span class="cell-status">{escape(status_label)}</span>
      </div>
      <div class="cell-metrics">
        <div class="metric">
          <span class="metric-label">IC</span>
          <span class="metric-value">{_fmt_decimal(cell.ic)}</span>
        </div>
        <div class="metric">
          <span class="metric-label">{escape(confidence_label)}</span>
          <span class="metric-value">{_fmt_pct(confidence)}</span>
        </div>
        <div class="metric">
          <span class="metric-label">Median excess</span>
          <span class="metric-value">{median_pct}</span>
        </div>
        <div class="metric">
          <span class="metric-label">Friction-adj</span>
          <span class="metric-value">{friction_pct}</span>
        </div>
        <div class="metric">
          <span class="metric-label">n obs</span>
          <span class="metric-value">{cell.n_observations}</span>
        </div>
        <div class="metric">
          <span class="metric-label">Rule type</span>
          <span class="metric-value">{rule_hint}</span>
        </div>
      </div>
      <div class="cell-percentiles">
        {pct_rows}
      </div>
      <div class="cell-notes">{escape(cell.notes)}</div>
    </div>
    """


def _group_results_by_cell(
    result: SweepResult,
) -> dict[tuple[str, str, str], CellDiscoveryResult]:
    """Index results by (cap_tier, tenure, action) for matrix rendering."""
    return {(r.spec.cap_tier, r.spec.tenure, r.spec.action): r for r in result.results}


def _render_summary(result: SweepResult) -> str:
    total = len(result.results)
    validated = result.validated_count
    no_conv = result.no_conviction_count
    duration_s = (result.run_completed_at - result.run_started_at).total_seconds()

    # Per-tenure pass-rate breakdown.
    per_tenure_rows = []
    for tenure in _TENURES:
        tenure_cells = [r for r in result.results if r.spec.tenure == tenure]
        validated_count = sum(1 for r in tenure_cells if r.validated)
        per_tenure_rows.append(
            f"<tr><td>{tenure}</td><td>{validated_count}</td>"
            f"<td>{len(tenure_cells) - validated_count}</td>"
            f"<td>{len(tenure_cells)}</td></tr>"
        )

    return f"""
    <section class="summary">
      <h2>Sweep summary</h2>
      <div class="summary-grid">
        <div class="summary-stat">
          <div class="stat-value">{total}</div>
          <div class="stat-label">Total cells</div>
        </div>
        <div class="summary-stat summary-stat-pos">
          <div class="stat-value">{validated}</div>
          <div class="stat-label">Validated</div>
        </div>
        <div class="summary-stat summary-stat-neg">
          <div class="stat-value">{no_conv}</div>
          <div class="stat-label">No conviction</div>
        </div>
        <div class="summary-stat">
          <div class="stat-value">{duration_s:.1f}s</div>
          <div class="stat-label">Duration</div>
        </div>
        <div class="summary-stat">
          <div class="stat-value">{escape(result.mode)}</div>
          <div class="stat-label">Mode</div>
        </div>
      </div>
      <h3>Per-tenure pass rate</h3>
      <table class="tenure-table">
        <thead>
          <tr><th>Tenure</th><th>Validated</th><th>No conviction</th><th>Total</th></tr>
        </thead>
        <tbody>
          {"".join(per_tenure_rows)}
        </tbody>
      </table>
    </section>
    """


def _render_matrix_grid(result: SweepResult) -> str:
    indexed = _group_results_by_cell(result)

    rows_html = []
    for cap_tier in _CAP_TIERS:
        row_cells = [f"<div class='row-label'>{escape(cap_tier)}</div>"]
        for tenure in _TENURES:
            for action in _ACTIONS:
                key = (cap_tier, tenure, action)
                if key not in indexed:
                    missing_label = f"{escape(cap_tier)}·{escape(tenure)}·{escape(action)}"
                    row_cells.append(
                        f"<div class='cell cell-empty'>(missing) {missing_label}</div>"
                    )
                else:
                    row_cells.append(_render_cell(indexed[key]))
        rows_html.append(f"<div class='matrix-row'>{''.join(row_cells)}</div>")

    # Header row: tenure × action labels.
    header_cells = ["<div class='row-label header'>cap × tenure</div>"]
    for tenure in _TENURES:
        for action in _ACTIONS:
            action_class = action.lower()
            action_label = escape(action)
            tenure_label = escape(tenure)
            header_cells.append(
                f"<div class='col-header'>{tenure_label}<br/>"
                f"<span class='action-{action_class}'>{action_label}</span></div>"
            )
    header_row = f"<div class='matrix-row matrix-header'>{''.join(header_cells)}</div>"

    return f"""
    <section class="matrix">
      <h2>24-cell discovery matrix</h2>
      <p class="matrix-caption">
        Each cell = (cap_tier × tenure × actionable_state). VALIDATED cells cleared
        the per-tenure IC floor AND have right-signed friction-adjusted excess.
        ``no_conviction`` cells render in the UI as "insufficient validation — no
        recommendation available."
      </p>
      <div class="matrix-grid">
        {header_row}
        {"".join(rows_html)}
      </div>
    </section>
    """


_CSS = """
  :root {
    --teal: #1D9E75;
    --teal-light: #E8F5EF;
    --red: #C8102E;
    --red-light: #FBEAED;
    --grey-50: #F8F9FA;
    --grey-100: #ECEFF1;
    --grey-200: #CFD8DC;
    --grey-400: #90A4AE;
    --grey-700: #455A64;
    --grey-900: #1A2329;
    --amber: #F5A623;
  }
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI",
      Roboto, "Helvetica Neue", Arial, sans-serif;
    margin: 0;
    padding: 32px;
    background: var(--grey-50);
    color: var(--grey-900);
    line-height: 1.45;
  }
  header.page-header {
    border-bottom: 1px solid var(--grey-200);
    padding-bottom: 16px;
    margin-bottom: 24px;
  }
  header.page-header h1 {
    margin: 0;
    font-size: 24px;
    color: var(--grey-900);
  }
  header.page-header p {
    margin: 4px 0 0;
    color: var(--grey-700);
    font-size: 13px;
  }
  section { background: white; border: 1px solid var(--grey-200); border-radius: 8px;
            padding: 20px 24px; margin-bottom: 24px; }
  section h2 { margin: 0 0 12px; font-size: 18px; color: var(--grey-900); }
  section h3 { margin: 16px 0 8px; font-size: 14px; color: var(--grey-700);
               text-transform: uppercase; letter-spacing: 0.05em; }
  .summary-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; }
  .summary-stat { background: var(--grey-50); padding: 12px; border-radius: 6px;
                  border: 1px solid var(--grey-100); }
  .summary-stat-pos { border-left: 4px solid var(--teal); }
  .summary-stat-neg { border-left: 4px solid var(--grey-400); }
  .stat-value { font-size: 24px; font-weight: 600; color: var(--grey-900); }
  .stat-label { font-size: 11px; color: var(--grey-700); text-transform: uppercase;
                letter-spacing: 0.05em; margin-top: 4px; }
  .tenure-table { border-collapse: collapse; width: 100%; font-size: 13px; }
  .tenure-table th, .tenure-table td { text-align: left; padding: 6px 10px;
                                       border-bottom: 1px solid var(--grey-100); }
  .tenure-table th { font-weight: 600; color: var(--grey-700);
                     text-transform: uppercase; letter-spacing: 0.05em; font-size: 11px; }
  .matrix-grid { display: flex; flex-direction: column; gap: 8px; }
  .matrix-row { display: grid; grid-template-columns: 80px repeat(8, 1fr); gap: 8px; }
  .matrix-header .col-header { background: var(--grey-100); border-radius: 4px;
                               padding: 6px; text-align: center; font-size: 11px;
                               font-weight: 600; color: var(--grey-700);
                               text-transform: uppercase; letter-spacing: 0.05em; }
  .action-positive { color: var(--teal); font-weight: 600; }
  .action-negative { color: var(--red); font-weight: 600; }
  .row-label { background: var(--grey-100); border-radius: 4px;
               padding: 6px; text-align: center; font-size: 12px;
               font-weight: 600; color: var(--grey-700);
               display: flex; align-items: center; justify-content: center; }
  .row-label.header { font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em; }
  .cell { background: var(--grey-50); border: 1px solid var(--grey-200);
          border-radius: 6px; padding: 8px; font-size: 11px;
          display: flex; flex-direction: column; gap: 6px; min-height: 220px; }
  .cell-validated { background: var(--teal-light); border-color: var(--teal); }
  .cell-no-conviction { background: var(--grey-50); border-color: var(--grey-200); }
  .cell-empty { background: var(--grey-100); border-color: var(--grey-200);
                color: var(--grey-400); }
  .cell-header { display: flex; flex-direction: column; gap: 2px;
                 padding-bottom: 4px; border-bottom: 1px solid var(--grey-100); }
  .cell-pair { font-weight: 600; color: var(--grey-900); font-size: 11px; }
  .cell-status { font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em;
                 color: var(--grey-700); }
  .cell-validated .cell-status { color: var(--teal); font-weight: 600; }
  .cell-metrics { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 8px; }
  .metric { display: flex; flex-direction: column; }
  .metric-label { font-size: 9px; color: var(--grey-700); text-transform: uppercase;
                  letter-spacing: 0.05em; }
  .metric-value { font-size: 11px; color: var(--grey-900); font-weight: 600; }
  .cell-percentiles { background: white; border-radius: 4px; padding: 4px 6px;
                      border: 1px solid var(--grey-100); }
  .pct-row { display: flex; justify-content: space-between; font-size: 10px;
             color: var(--grey-700); }
  .pct-label { color: var(--grey-400); }
  .pct-value { color: var(--grey-900); font-feature-settings: "tnum"; }
  .cell-notes { font-size: 10px; color: var(--grey-700); font-style: italic;
                line-height: 1.3; }
  .matrix-caption { color: var(--grey-700); font-size: 13px; margin-bottom: 16px; }
"""


def generate_matrix_status_html(result: SweepResult, *, output_path: Path | str) -> Path:
    """Render the 24-cell matrix status as a self-contained HTML document.

    Args:
        result: a completed :class:`SweepResult` from
            :meth:`WalkForwardSweep.run_full_matrix`.
        output_path: file path to write the HTML to. Parent directories
            are NOT created — the caller is responsible.

    Returns:
        The :class:`pathlib.Path` written.
    """
    path = Path(output_path)
    timestamp = datetime.now(UTC).isoformat()

    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Atlas v6 — 24-cell discovery matrix ({result.mode})</title>
<style>{_CSS}</style>
</head>
<body>
<header class="page-header">
  <h1>Atlas v6 · 24-cell discovery matrix</h1>
  <p>
    Phase 0.5g walk-forward sweep · mode=<strong>{escape(result.mode)}</strong>
    · generated <strong>{escape(timestamp)}</strong>
    · windows={len(result.windows)} (train/test {result.windows[0].train_start.isoformat()}
      → {result.windows[-1].test_end.isoformat()})
  </p>
</header>

{_render_summary(result)}
{_render_matrix_grid(result)}

<footer style="text-align: center; color: #90A4AE; font-size: 11px; margin-top: 32px;">
  Atlas v6 Phase 0.5g · methodology lock: methodology-lock-2026-05-23 ·
  cells per CONTEXT.md §"24-framework discovery model"
</footer>
</body>
</html>
"""
    path.write_text(document, encoding="utf-8")
    return path
