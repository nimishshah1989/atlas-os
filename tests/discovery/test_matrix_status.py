"""Tests for :mod:`atlas.discovery.matrix_status`."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from atlas.discovery.engine import (
    CellDiscoveryResult,
    CellSpec,
    SweepResult,
    WalkForwardSweep,
)
from atlas.discovery.matrix_status import (
    _cell_status_class,
    _cell_status_label,
    _fmt_decimal,
    _fmt_pct,
    _render_cell,
    generate_matrix_status_html,
)


def _make_synthetic_result() -> SweepResult:
    sweep = WalkForwardSweep(mode="synthetic")
    return sweep.run_full_matrix()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_fmt_decimal_none() -> None:
    assert _fmt_decimal(None) == "—"


def test_fmt_decimal_rounds_to_places() -> None:
    assert _fmt_decimal(Decimal("0.123456"), places=2) == "0.12"


def test_fmt_pct_none() -> None:
    assert _fmt_pct(None) == "—"


def test_fmt_pct_scales_by_100() -> None:
    assert _fmt_pct(Decimal("0.1234"), places=1) == "12.3%"


def _dummy_cell(validated: bool = False, n_obs: int = 100) -> CellDiscoveryResult:
    import uuid

    spec = CellSpec(cap_tier="Mid", tenure="12m", action="POSITIVE", rule_type_hint="pullback")
    return CellDiscoveryResult(
        spec=spec,
        validated=validated,
        ic=Decimal("0.05") if validated else None,
        tp_rate=Decimal("0.7"),
        tn_rate=None,
        median_excess=Decimal("0.03"),
        friction_adjusted_excess=Decimal("0.02"),
        percentile_10=Decimal("-0.05"),
        percentile_25=Decimal("-0.01"),
        percentile_50=Decimal("0.03"),
        percentile_75=Decimal("0.08"),
        percentile_90=Decimal("0.15"),
        n_observations=n_obs,
        stable_features=["rs_residual_6m"] if validated else [],
        rule_dsl={"rule_type": "pullback"} if validated else {},
        walkforward_run_id=uuid.uuid4(),
        notes="test cell",
    )


def test_cell_status_class_validated() -> None:
    cell = _dummy_cell(validated=True)
    assert _cell_status_class(cell) == "cell-validated"


def test_cell_status_class_no_conviction() -> None:
    cell = _dummy_cell(validated=False, n_obs=100)
    assert _cell_status_class(cell) == "cell-no-conviction"


def test_cell_status_class_empty() -> None:
    cell = _dummy_cell(validated=False, n_obs=0)
    assert _cell_status_class(cell) == "cell-empty"


def test_cell_status_label_validated() -> None:
    cell = _dummy_cell(validated=True)
    assert _cell_status_label(cell) == "VALIDATED"


def test_cell_status_label_no_data() -> None:
    cell = _dummy_cell(validated=False, n_obs=0)
    assert _cell_status_label(cell) == "no_data"


def test_cell_status_label_no_conviction() -> None:
    cell = _dummy_cell(validated=False, n_obs=100)
    assert _cell_status_label(cell) == "no_conviction"


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def test_render_cell_contains_spec_identifiers() -> None:
    html = _render_cell(_dummy_cell(validated=True))
    assert "Mid" in html
    assert "12m" in html
    assert "POSITIVE" in html
    assert "pullback" in html


def test_render_cell_contains_metrics() -> None:
    html = _render_cell(_dummy_cell(validated=True))
    assert "IC" in html
    assert "TP rate" in html
    assert "Friction-adj" in html


def test_render_cell_validated_class() -> None:
    html = _render_cell(_dummy_cell(validated=True))
    assert "cell-validated" in html


def test_render_cell_no_conviction_class() -> None:
    html = _render_cell(_dummy_cell(validated=False, n_obs=100))
    assert "cell-no-conviction" in html


def test_render_cell_negative_action_shows_tn_rate() -> None:
    import uuid

    spec = CellSpec(
        cap_tier="Mid", tenure="12m", action="NEGATIVE", rule_type_hint="severely_broken"
    )
    cell = CellDiscoveryResult(
        spec=spec,
        validated=True,
        ic=Decimal("-0.05"),
        tp_rate=None,
        tn_rate=Decimal("0.85"),
        median_excess=Decimal("-0.08"),
        friction_adjusted_excess=Decimal("-0.07"),
        percentile_10=Decimal("-0.20"),
        percentile_25=Decimal("-0.15"),
        percentile_50=Decimal("-0.08"),
        percentile_75=Decimal("-0.02"),
        percentile_90=Decimal("0.03"),
        n_observations=200,
        stable_features=["rs_residual_6m"],
        rule_dsl={"rule_type": "severely_broken"},
        walkforward_run_id=uuid.uuid4(),
        notes="ok",
    )
    html = _render_cell(cell)
    assert "TN rate" in html
    assert "TP rate" not in html


# ---------------------------------------------------------------------------
# Full HTML generation
# ---------------------------------------------------------------------------


def test_generate_matrix_status_html_writes_file(tmp_path: Path) -> None:
    result = _make_synthetic_result()
    out = tmp_path / "matrix.html"
    written = generate_matrix_status_html(result, output_path=out)
    assert written.exists()
    assert written == out
    contents = out.read_text(encoding="utf-8")
    assert contents.startswith("<!doctype html>")


def test_generate_matrix_status_html_contains_all_24_cells(tmp_path: Path) -> None:
    result = _make_synthetic_result()
    out = tmp_path / "matrix.html"
    generate_matrix_status_html(result, output_path=out)
    contents = out.read_text(encoding="utf-8")
    # Every (cap, tenure, action) tuple should appear in the rendered HTML.
    for cap_tier in ("Small", "Mid", "Large"):
        for tenure in ("1m", "3m", "6m", "12m"):
            for action in ("POSITIVE", "NEGATIVE"):
                needle = f"{cap_tier} · {tenure} · {action}"
                assert needle in contents, f"missing cell {needle!r}"


def test_generate_matrix_status_html_summary_section(tmp_path: Path) -> None:
    result = _make_synthetic_result()
    out = tmp_path / "matrix.html"
    generate_matrix_status_html(result, output_path=out)
    contents = out.read_text(encoding="utf-8")
    assert "Sweep summary" in contents
    assert "Per-tenure pass rate" in contents
    assert "24-cell discovery matrix" in contents


def test_generate_matrix_status_html_records_mode(tmp_path: Path) -> None:
    result = _make_synthetic_result()
    out = tmp_path / "matrix.html"
    generate_matrix_status_html(result, output_path=out)
    contents = out.read_text(encoding="utf-8")
    assert "synthetic" in contents


def test_generate_matrix_status_html_accepts_str_path(tmp_path: Path) -> None:
    """output_path can be a string, not just a Path."""
    result = _make_synthetic_result()
    out = tmp_path / "matrix.html"
    generate_matrix_status_html(result, output_path=str(out))
    assert out.exists()
