"""HTML report renderer for :mod:`atlas.discovery.deep_search`.

Renders a self-contained HTML document showing:
* Cell target + run timestamp + methodology gate.
* Headline summary (best IC, validated count, total candidates).
* Top-N candidate drill-down (default top-10 by absolute IC).
* Per-candidate: rule features, IC, TP rate, percentile distribution,
  per-window stability.
* Honest verdict block: "validated" / "no signal found in this space".

Atlas visual language — white background, teal accent (#1D9E75),
information-dense tables. Single file, no JS dependencies.
"""

from __future__ import annotations

from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atlas.decisions.rule_dsl import FeaturePredicate
    from atlas.discovery.deep_search import CandidateResult, DeepSearchSummary


TOP_N_DISPLAYED = 10


def _fmt_float(value: float | None, places: int = 4, default: str = "—") -> str:
    if value is None:
        return default
    try:
        fv = float(value)
    except (TypeError, ValueError):
        return default
    if fv != fv:  # NaN
        return default
    return f"{fv:.{places}f}"


def _fmt_pct(value: float | None, places: int = 2, default: str = "—") -> str:
    if value is None:
        return default
    try:
        fv = float(value)
    except (TypeError, ValueError):
        return default
    if fv != fv:  # NaN
        return default
    return f"{fv * 100:.{places}f}%"


def _fmt_predicate(pred: FeaturePredicate) -> str:
    feat = escape(pred.feature)
    cmp = escape(pred.cmp)
    if pred.cmp == "in_range" and isinstance(pred.value, tuple):
        low, high = pred.value
        return f"{feat} in [{low}, {high}]"
    if pred.cmp == "in_top_quantile":
        return f"{feat} in top-1/{pred.value_quantile_n}"
    return f"{feat} {cmp} {pred.value}"


def _render_predicate_list(features: tuple[FeaturePredicate, ...]) -> str:
    items = "".join(f"<li>{_fmt_predicate(p)}</li>" for p in features)
    return f"<ul class='predicate-list'>{items}</ul>"


def _render_per_window(per_window: tuple[dict, ...]) -> str:
    rows = []
    for w in per_window:
        pos = w["positive"]
        cls = "win-pos" if pos else "win-neg"
        rows.append(
            f"<tr class='{cls}'>"
            f"<td>{escape(w['window'])}</td>"
            f"<td>{w['n_obs']}</td>"
            f"<td>{_fmt_pct(w['median_excess'])}</td>"
            f"<td>{'positive' if pos else 'negative/zero'}</td>"
            f"</tr>"
        )
    return (
        "<table class='per-window'>"
        "<thead><tr><th>Window</th><th>n triggers</th>"
        "<th>median excess</th><th>direction</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _render_candidate(rank: int, cr: CandidateResult) -> str:
    status_class = "candidate-validated" if cr.validated else "candidate-no-conviction"
    status_label = "VALIDATED" if cr.validated else "no_conviction"
    rule = cr.rule
    return f"""
    <article class="candidate {status_class}">
      <header class="candidate-header">
        <span class="rank">#{rank}</span>
        <span class="candidate-name">{escape(rule.name)}</span>
        <span class="archetype">{escape(rule.archetype)}</span>
        <span class="status-badge">{escape(status_label)}</span>
      </header>
      <p class="rationale">{escape(rule.rationale)}</p>
      <div class="metrics-grid">
        <div class="metric"><span class="metric-label">IC</span>
          <span class="metric-value">{_fmt_float(cr.ic)}</span></div>
        <div class="metric"><span class="metric-label">TP rate</span>
          <span class="metric-value">{_fmt_pct(cr.tp_rate)}</span></div>
        <div class="metric"><span class="metric-label">Median excess</span>
          <span class="metric-value">{_fmt_pct(cr.median_excess)}</span></div>
        <div class="metric"><span class="metric-label">Mean excess</span>
          <span class="metric-value">{_fmt_pct(cr.mean_excess)}</span></div>
        <div class="metric"><span class="metric-label">Friction-adj</span>
          <span class="metric-value">{_fmt_pct(cr.friction_adjusted_excess)}</span></div>
        <div class="metric"><span class="metric-label">n triggers</span>
          <span class="metric-value">{cr.n_observations}</span></div>
      </div>
      <div class="percentile-bar">
        <div class="pct-col"><div class="pct-label">p10</div>
          <div class="pct-value">{_fmt_pct(cr.percentile_10)}</div></div>
        <div class="pct-col"><div class="pct-label">p25</div>
          <div class="pct-value">{_fmt_pct(cr.percentile_25)}</div></div>
        <div class="pct-col"><div class="pct-label">p50</div>
          <div class="pct-value">{_fmt_pct(cr.percentile_50)}</div></div>
        <div class="pct-col"><div class="pct-label">p75</div>
          <div class="pct-value">{_fmt_pct(cr.percentile_75)}</div></div>
        <div class="pct-col"><div class="pct-label">p90</div>
          <div class="pct-value">{_fmt_pct(cr.percentile_90)}</div></div>
      </div>
      <details class="features">
        <summary>Features</summary>
        {_render_predicate_list(rule.features)}
      </details>
      <details class="windows" open>
        <summary>Per-window stability</summary>
        {_render_per_window(cr.per_window_results)}
      </details>
    </article>
    """


def _render_summary_header(summary: DeepSearchSummary) -> str:
    cap, tenure, action = summary.cell_target
    duration_s = (summary.run_completed_at - summary.run_started_at).total_seconds()
    verdict_class = "verdict-good" if summary.n_validated > 0 else "verdict-honest"
    verdict_text = (
        f"VALIDATED — {summary.n_validated} candidate(s) cleared the gate"
        if summary.n_validated > 0
        else "NO SIGNAL — no candidate cleared IC>=0.04 + friction-adj>0 in this search space"
    )
    insert_block = ""
    if summary.inserted_cell_id is not None:
        insert_block = (
            f"<div class='insert-block'>INSERTED into atlas_cell_definitions: "
            f"<code>{escape(str(summary.inserted_cell_id))}</code> "
            f"(rule: <code>{escape(summary.best_rule_name or '')}</code>)</div>"
        )

    cell_label = f"{escape(cap)} · {escape(tenure)} · {escape(action)}"
    return f"""
    <section class="summary-section">
      <h2>Search verdict</h2>
      <div class="verdict {verdict_class}">{escape(verdict_text)}</div>
      {insert_block}
      <div class="summary-stats">
        <div class="stat"><div class="stat-value">{cell_label}</div>
          <div class="stat-label">Cell target</div></div>
        <div class="stat"><div class="stat-value">{summary.n_candidates}</div>
          <div class="stat-label">Candidates tried</div></div>
        <div class="stat"><div class="stat-value">{summary.n_validated}</div>
          <div class="stat-label">Validated</div></div>
        <div class="stat"><div class="stat-value">{_fmt_float(summary.best_ic)}</div>
          <div class="stat-label">Best |IC|</div></div>
        <div class="stat"><div class="stat-value">{duration_s:.1f}s</div>
          <div class="stat-label">Duration</div></div>
      </div>
    </section>
    """


def _render_archetype_distribution(summary: DeepSearchSummary) -> str:
    by_arch: dict[str, dict[str, int | float]] = {}
    for r in summary.results:
        arch = r.rule.archetype
        if arch not in by_arch:
            by_arch[arch] = {"count": 0, "validated": 0, "best_ic": 0.0}
        d = by_arch[arch]
        d["count"] = int(d["count"]) + 1
        if r.validated:
            d["validated"] = int(d["validated"]) + 1
        ic_abs = abs(r.ic) if r.ic == r.ic else 0.0  # NaN check
        if ic_abs > float(d["best_ic"]):
            d["best_ic"] = ic_abs

    rows = []
    for arch in sorted(by_arch.keys()):
        d = by_arch[arch]
        rows.append(
            f"<tr><td>{escape(arch)}</td>"
            f"<td>{d['count']}</td>"
            f"<td>{d['validated']}</td>"
            f"<td>{float(d['best_ic']):.4f}</td></tr>"
        )
    return f"""
    <section class="archetype-section">
      <h2>Archetype distribution</h2>
      <table class="archetype-table">
        <thead><tr><th>Archetype</th><th>Candidates</th><th>Validated</th>
        <th>Best |IC|</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>
    """


_CSS = """
  :root {
    --teal: #1D9E75;
    --teal-light: #E8F5EF;
    --red: #C8102E;
    --red-light: #FBEAED;
    --amber: #F5A623;
    --grey-50: #F8F9FA;
    --grey-100: #ECEFF1;
    --grey-200: #CFD8DC;
    --grey-400: #90A4AE;
    --grey-700: #455A64;
    --grey-900: #1A2329;
  }
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI",
      Roboto, "Helvetica Neue", Arial, sans-serif;
    margin: 0; padding: 32px; background: var(--grey-50);
    color: var(--grey-900); line-height: 1.45;
  }
  header.page-header { border-bottom: 1px solid var(--grey-200);
                       padding-bottom: 16px; margin-bottom: 24px; }
  header.page-header h1 { margin: 0; font-size: 24px; }
  header.page-header p { margin: 4px 0 0; color: var(--grey-700); font-size: 13px; }
  section { background: white; border: 1px solid var(--grey-200);
            border-radius: 8px; padding: 20px 24px; margin-bottom: 24px; }
  section h2 { margin: 0 0 12px; font-size: 18px; }
  .summary-stats { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px;
                   margin-top: 12px; }
  .stat { background: var(--grey-50); padding: 12px; border-radius: 6px;
          border: 1px solid var(--grey-100); }
  .stat-value { font-size: 20px; font-weight: 600; }
  .stat-label { font-size: 11px; color: var(--grey-700); text-transform: uppercase;
                letter-spacing: 0.05em; margin-top: 4px; }
  .verdict { padding: 12px 16px; border-radius: 6px; font-weight: 600; font-size: 14px; }
  .verdict-good { background: var(--teal-light); border-left: 4px solid var(--teal);
                  color: var(--grey-900); }
  .verdict-honest { background: var(--grey-100); border-left: 4px solid var(--amber);
                    color: var(--grey-900); }
  .insert-block { margin-top: 12px; padding: 10px 14px; background: var(--teal-light);
                  border-radius: 6px; font-size: 13px; }
  .insert-block code { background: white; padding: 2px 6px; border-radius: 3px;
                       font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
  .archetype-table { border-collapse: collapse; width: 100%; font-size: 13px; }
  .archetype-table th, .archetype-table td { text-align: left; padding: 6px 10px;
                                              border-bottom: 1px solid var(--grey-100); }
  .archetype-table th { font-weight: 600; color: var(--grey-700);
                        text-transform: uppercase; letter-spacing: 0.05em; font-size: 11px; }
  .candidate { background: white; border: 1px solid var(--grey-200);
               border-radius: 8px; padding: 16px 20px; margin-bottom: 16px; }
  .candidate-validated { border-left: 4px solid var(--teal);
                         background: linear-gradient(to right, var(--teal-light), white 40%); }
  .candidate-no-conviction { border-left: 4px solid var(--grey-400); }
  .candidate-header { display: flex; gap: 12px; align-items: center; flex-wrap: wrap;
                      margin-bottom: 6px; }
  .rank { background: var(--grey-100); padding: 4px 10px; border-radius: 12px;
          font-size: 12px; font-weight: 600; color: var(--grey-700); }
  .candidate-name { font-weight: 600; font-size: 14px;
                    font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
  .archetype { font-size: 11px; padding: 2px 8px; background: var(--grey-100);
               border-radius: 12px; color: var(--grey-700); text-transform: uppercase;
               letter-spacing: 0.05em; }
  .status-badge { margin-left: auto; font-size: 11px; padding: 4px 10px; border-radius: 12px;
                  font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase; }
  .candidate-validated .status-badge { background: var(--teal); color: white; }
  .candidate-no-conviction .status-badge { background: var(--grey-100); color: var(--grey-700); }
  .rationale { color: var(--grey-700); font-size: 13px; font-style: italic;
               margin: 4px 0 12px; }
  .metrics-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px;
                  margin-bottom: 12px; }
  .metric { background: var(--grey-50); padding: 8px; border-radius: 4px; }
  .metric-label { font-size: 10px; color: var(--grey-700); text-transform: uppercase;
                  letter-spacing: 0.05em; }
  .metric-value { font-size: 14px; font-weight: 600; margin-top: 2px; }
  .percentile-bar { display: grid; grid-template-columns: repeat(5, 1fr); gap: 4px;
                    margin-bottom: 12px; padding: 8px;
                    background: var(--grey-50); border-radius: 4px; }
  .pct-col { text-align: center; }
  .pct-label { font-size: 10px; color: var(--grey-400); }
  .pct-value { font-size: 12px; font-weight: 600;
               font-feature-settings: "tnum"; }
  details { background: var(--grey-50); border-radius: 4px; padding: 8px 12px;
            margin-bottom: 6px; font-size: 12px; }
  details summary { cursor: pointer; font-weight: 600; color: var(--grey-700);
                    font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; }
  .predicate-list { margin: 8px 0 0; padding-left: 20px; }
  .predicate-list li { font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
                       font-size: 12px; margin-bottom: 4px; }
  .per-window { border-collapse: collapse; width: 100%; font-size: 12px; margin-top: 8px; }
  .per-window th, .per-window td { text-align: left; padding: 4px 8px;
                                    border-bottom: 1px solid var(--grey-100); }
  .per-window th { font-weight: 600; color: var(--grey-700);
                   text-transform: uppercase; letter-spacing: 0.05em; font-size: 10px; }
  .win-pos td:nth-child(3), .win-pos td:nth-child(4) { color: var(--teal); font-weight: 600; }
  .win-neg td:nth-child(3), .win-neg td:nth-child(4) { color: var(--red); }
  .methodology-note { font-size: 11px; color: var(--grey-700);
                      background: var(--grey-50); padding: 12px 16px; border-radius: 6px;
                      margin-top: 24px; }
"""


def generate_deep_search_report(
    summary: DeepSearchSummary,
    *,
    output_path: Path | str,
    top_n: int = TOP_N_DISPLAYED,
) -> Path:
    """Render the deep-search HTML report to ``output_path``.

    Args:
        summary: :class:`DeepSearchSummary` from
            :func:`atlas.discovery.deep_search.run_deep_search`.
        output_path: file path to write the HTML.
        top_n: how many top candidates to render in detail. Default 10.

    Returns:
        The :class:`pathlib.Path` written.
    """
    path = Path(output_path)
    timestamp = datetime.now(UTC).isoformat()
    cap, tenure, action = summary.cell_target

    top_candidates = list(summary.results)[:top_n]
    top_html = "".join(_render_candidate(i + 1, r) for i, r in enumerate(top_candidates))

    cap_e = escape(cap)
    tenure_e = escape(tenure)
    action_e = escape(action)
    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Atlas v6 deep search — {cap_e}/{tenure_e}/{action_e}</title>
<style>{_CSS}</style>
</head>
<body>
<header class="page-header">
  <h1>Atlas v6 · deep search · {cap_e} @ {tenure_e} {action_e}</h1>
  <p>
    Per-cell exhaustive feature search · methodology lock §4 principle 7 ·
    generated <strong>{escape(timestamp)}</strong>
  </p>
</header>

{_render_summary_header(summary)}
{_render_archetype_distribution(summary)}

<section class="top-candidates-section">
  <h2>Top {len(top_candidates)} candidates (ranked by |IC| descending)</h2>
  <p class="methodology-note">
    Validation gate: <strong>|IC| &ge; 0.04</strong> (12m floor) AND
    <strong>friction-adjusted excess &gt; 0</strong> AND
    <strong>at least 2 of 3 walk-forward windows show positive median excess</strong>.
    IC is pooled-Spearman of <code>rs_residual_6m</code> vs forward 252d excess across
    all Large-cap, in-test-window observations. Friction = 26 bps round-trip for Large.
  </p>
  {top_html}
</section>

<footer class="methodology-note">
  Atlas v6 deep search · cache mode · methodology lock methodology-lock-2026-05-23
  · per-cell extension DEEP_SEARCH_2026-05-24 · CONTEXT.md §"24-framework discovery model"
</footer>
</body>
</html>
"""
    path.write_text(document, encoding="utf-8")
    return path
