"""Tests for ``scripts/compare_v2_v3.py``.

Validates:

* per-cell comparison identifies rule changes,
* persist SQL is well-formed (parses via ``sqlparse``),
* SQL deprecates v2 cells BEFORE inserting v3 (the partial unique index
  ``uq_atlas_cell_definitions_active`` would otherwise fail).
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

sqlparse = pytest.importorskip("sqlparse")


def _load_module():
    repo_root = Path(__file__).resolve().parents[2]
    scripts_dir = repo_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    if "compare_v2_v3" in sys.modules:
        return importlib.reload(sys.modules["compare_v2_v3"])
    return importlib.import_module("compare_v2_v3")


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _build_cell_payload(
    tier: str,
    tenure: str,
    direction: str,
    *,
    top_name: str,
    top_ic: float,
    top_n_obs: int,
    n_candidates: int = 10,
    n_gate_pass: int = 1,
) -> dict[str, Any]:
    """Build a synthetic per-cell JSON payload."""
    top_cand = {
        "name": top_name,
        "archetype": "mean_reversion",
        "rationale": "test",
        "ic": top_ic,
        "tp_rate": 0.6,
        "median_excess": 0.02,
        "mean_excess": 0.018,
        "friction_adjusted_excess": 0.015,
        "percentile_50": 0.02,
        "n_observations": top_n_obs,
        "per_window": [],
        "validated": True,
        "bh_q_value": 0.05,
        "predicates": [
            {"feature": "log_med_tv_60d", "cmp": ">=", "value": "14.5"},
            {"feature": "rs_residual_6m", "cmp": ">", "value": "0.05"},
        ],
    }
    return {
        "methodology_lock_ref": "TEST",
        "cell": {"tier": tier, "tenure": tenure, "direction": direction},
        "run_started_at": "2026-05-25T00:00:00Z",
        "run_completed_at": "2026-05-25T00:00:01Z",
        "n_candidates": n_candidates,
        "n_gate_pass": n_gate_pass,
        "candidates": [top_cand],
        "top_10": [top_cand],
    }


def _write_cells(directory: Path, payloads: dict[str, dict[str, Any]]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for cid, payload in payloads.items():
        (directory / f"{cid}.json").write_text(json.dumps(payload))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_comparison_identifies_cell_rule_changes(tmp_path: Path) -> None:
    """When v3's top rule differs from v2's, ``rule_changed`` is True."""
    mod = _load_module()
    v2_dir = tmp_path / "v2_cells"
    v3_dir = tmp_path / "v3_cells"

    _write_cells(
        v2_dir,
        {
            "Large-12m-POSITIVE": _build_cell_payload(
                "Large",
                "12m",
                "POSITIVE",
                top_name="rule_v2",
                top_ic=0.06,
                top_n_obs=300,
            ),
        },
    )
    _write_cells(
        v3_dir,
        {
            "Large-12m-POSITIVE": _build_cell_payload(
                "Large",
                "12m",
                "POSITIVE",
                top_name="rule_v3_better",
                top_ic=0.08,
                top_n_obs=800,
            ),
        },
    )
    v2_cells = mod._load_cells(v2_dir)
    v3_cells = mod._load_cells(v3_dir)
    comparisons = mod.build_comparisons(v2_cells, v3_cells)
    target = next(c for c in comparisons if c.cell_id == "Large-12m-POSITIVE")
    assert target.rule_changed is True
    assert target.v2_top_name == "rule_v2"
    assert target.v3_top_name == "rule_v3_better"
    assert target.universe_delta == 500


def test_comparison_marks_unchanged_when_v3_top_same_name(tmp_path: Path) -> None:
    mod = _load_module()
    v2_dir = tmp_path / "v2_cells"
    v3_dir = tmp_path / "v3_cells"
    payload_v2 = _build_cell_payload(
        "Mid", "6m", "NEGATIVE", top_name="same_rule", top_ic=-0.08, top_n_obs=200
    )
    payload_v3 = _build_cell_payload(
        "Mid", "6m", "NEGATIVE", top_name="same_rule", top_ic=-0.09, top_n_obs=900
    )
    _write_cells(v2_dir, {"Mid-6m-NEGATIVE": payload_v2})
    _write_cells(v3_dir, {"Mid-6m-NEGATIVE": payload_v3})
    v2_cells = mod._load_cells(v2_dir)
    v3_cells = mod._load_cells(v3_dir)
    comparisons = mod.build_comparisons(v2_cells, v3_cells)
    target = next(c for c in comparisons if c.cell_id == "Mid-6m-NEGATIVE")
    assert target.rule_changed is False


def test_persist_sql_is_parseable(tmp_path: Path) -> None:
    """The two emitted SQL files must parse via sqlparse."""
    mod = _load_module()
    v2_dir = tmp_path / "v2_cells"
    v3_dir = tmp_path / "v3_cells"
    _write_cells(
        v2_dir,
        {
            "Large-12m-POSITIVE": _build_cell_payload(
                "Large", "12m", "POSITIVE", top_name="rule_v2", top_ic=0.06, top_n_obs=300
            )
        },
    )
    _write_cells(
        v3_dir,
        {
            "Large-12m-POSITIVE": _build_cell_payload(
                "Large", "12m", "POSITIVE", top_name="rule_v3", top_ic=0.08, top_n_obs=800
            )
        },
    )
    v2 = mod._load_cells(v2_dir)
    v3 = mod._load_cells(v3_dir)
    comparisons = mod.build_comparisons(v2, v3)
    defs_sql, cands_sql = mod.build_persist_sql(comparisons, v3)
    parsed_defs = sqlparse.parse(defs_sql)
    parsed_cands = sqlparse.parse(cands_sql)
    assert parsed_defs, "definitions SQL did not parse"
    assert parsed_cands, "candidates SQL did not parse"


def test_persist_sql_deprecates_v2_before_inserting_v3(tmp_path: Path) -> None:
    """The DEPRECATE step must precede the INSERT — otherwise the partial
    unique index ``uq_atlas_cell_definitions_active`` blocks the v3 insert.
    """
    mod = _load_module()
    v2_dir = tmp_path / "v2_cells"
    v3_dir = tmp_path / "v3_cells"
    _write_cells(
        v2_dir,
        {
            "Large-12m-POSITIVE": _build_cell_payload(
                "Large", "12m", "POSITIVE", top_name="rule_v2", top_ic=0.06, top_n_obs=300
            )
        },
    )
    _write_cells(
        v3_dir,
        {
            "Large-12m-POSITIVE": _build_cell_payload(
                "Large", "12m", "POSITIVE", top_name="rule_v3", top_ic=0.08, top_n_obs=800
            )
        },
    )
    v2 = mod._load_cells(v2_dir)
    v3 = mod._load_cells(v3_dir)
    comparisons = mod.build_comparisons(v2, v3)
    defs_sql, _ = mod.build_persist_sql(comparisons, v3)
    update_pos = defs_sql.find("UPDATE atlas.atlas_cell_definitions")
    insert_pos = defs_sql.find("INSERT INTO atlas.atlas_cell_definitions")
    assert update_pos != -1, "missing DEPRECATE step"
    assert insert_pos != -1, "missing INSERT step"
    assert (
        update_pos < insert_pos
    ), "DEPRECATE must precede INSERT (partial unique index requires v2 slot vacated)"


def test_persist_sql_uses_v3_methodology_lock(tmp_path: Path) -> None:
    mod = _load_module()
    v3_dir = tmp_path / "v3_cells"
    _write_cells(
        v3_dir,
        {
            "Small-1m-NEGATIVE": _build_cell_payload(
                "Small",
                "1m",
                "NEGATIVE",
                top_name="rule_v3_neg",
                top_ic=-0.05,
                top_n_obs=200,
            ),
        },
    )
    v3 = mod._load_cells(v3_dir)
    comparisons = mod.build_comparisons({}, v3)
    defs_sql, cands_sql = mod.build_persist_sql(comparisons, v3)
    assert mod.V3_METHODOLOGY in defs_sql
    assert mod.V3_METHODOLOGY in cands_sql


def test_persist_sql_skips_cells_without_v3_data(tmp_path: Path) -> None:
    """A cell present in v2 but missing from v3 is recorded as SKIP, not crashed."""
    mod = _load_module()
    v2_dir = tmp_path / "v2_cells"
    v3_dir = tmp_path / "v3_cells"
    _write_cells(
        v2_dir,
        {
            "Large-12m-POSITIVE": _build_cell_payload(
                "Large", "12m", "POSITIVE", top_name="rule_v2", top_ic=0.06, top_n_obs=300
            )
        },
    )
    v3_dir.mkdir()  # empty
    v2 = mod._load_cells(v2_dir)
    v3 = mod._load_cells(v3_dir)
    comparisons = mod.build_comparisons(v2, v3)
    defs_sql, cands_sql = mod.build_persist_sql(comparisons, v3)
    assert "SKIP Large-12m-POSITIVE" in defs_sql
    assert "SKIP Large-12m-POSITIVE" in cands_sql
