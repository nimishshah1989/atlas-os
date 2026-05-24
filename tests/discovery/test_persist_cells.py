"""Tests for atlas.discovery.persist_cells.

Verifies:
* shape / count of emitted INSERTs
* CellRule validation roundtrip (predicates split into eligibility vs entry)
* sort order (POSITIVE = DESC, NEGATIVE = ASC by fric-adj excess)
* q-gate filter
* SQL safety: single quotes are escape-doubled
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from atlas.decisions.rule_dsl import validate_rule_dsl
from atlas.discovery import persist_cells


def _make_candidate(
    name: str,
    archetype: str,
    fric_adj: float,
    ic: float = 0.1,
    validated: bool = True,
    bh_q: float = 0.05,
    predicates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "archetype": archetype,
        "rationale": f"test {name}",
        "ic": ic,
        "tp_rate": 0.55,
        "median_excess": fric_adj + 0.01,
        "mean_excess": fric_adj + 0.005,
        "friction_adjusted_excess": fric_adj,
        "n_observations": 100,
        "per_window": [],
        "validated": validated,
        "bh_q_value": bh_q,
        "predicates": predicates
        or [
            {"feature": "log_med_tv_60d", "cmp": ">=", "value": "16.5"},
            {"feature": "rs_residual_6m", "cmp": ">", "value": "0"},
        ],
    }


def _make_payload(
    tier: str,
    tenure: str,
    direction: str,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "methodology_lock_ref": "TEST_LOCK_2026",
        "cell": {"tier": tier, "tenure": tenure, "direction": direction},
        "n_candidates": len(candidates),
        "n_gate_pass": sum(1 for c in candidates if c.get("validated")),
        "candidates": candidates,
    }


@pytest.fixture
def cells_dir(tmp_path: Path) -> Path:
    """Write a 2-cell fixture: 1 POSITIVE + 1 NEGATIVE."""
    d = tmp_path / "cells"
    d.mkdir()

    pos = _make_payload(
        "Large",
        "12m",
        "POSITIVE",
        [
            _make_candidate("A_strong", "sector_relative_leadership", 0.30),
            _make_candidate("B_mid", "quality_momentum", 0.20),
            _make_candidate("C_weak", "deep_value", 0.05),
            _make_candidate(
                "D_failed_q",
                "inflection",
                0.50,
                bh_q=0.5,  # q-fail: should be filtered
            ),
            _make_candidate(
                "E_not_validated",
                "structural",
                0.40,
                validated=False,  # validation fail
            ),
        ],
    )
    neg = _make_payload(
        "Mid",
        "6m",
        "NEGATIVE",
        [
            _make_candidate("N_most_neg", "sector_drag", -0.30),
            _make_candidate("N_mid", "weak_quality", -0.20),
            _make_candidate("N_least_neg", "volatility_spike", -0.05),
        ],
    )

    (d / "Large-12m-POSITIVE.json").write_text(json.dumps(pos))
    (d / "Mid-6m-NEGATIVE.json").write_text(json.dumps(neg))
    return d


def test_build_sql_files_creates_two_files(cells_dir: Path, tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    defs_path, cands_path, stats = persist_cells.build_sql_files(
        cells_dir=cells_dir, output_dir=output_dir
    )
    assert defs_path.exists()
    assert cands_path.exists()
    assert stats["n_cells"] == 2
    assert stats["n_definitions_emitted"] == 2


def test_top_k_filters_validated_and_qgate(cells_dir: Path, tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    _, _, stats = persist_cells.build_sql_files(cells_dir=cells_dir, output_dir=output_dir, top_k=5)
    # POSITIVE has 3 valid (A_strong, B_mid, C_weak) — D_failed_q filtered by
    # q-gate, E_not_validated filtered by validated flag.
    # NEGATIVE has 3.
    # Total: 6 candidate INSERTs.
    assert stats["n_candidates_emitted"] == 6


def test_positive_sort_descending(cells_dir: Path, tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    persist_cells.build_sql_files(cells_dir=cells_dir, output_dir=output_dir)
    cands_text = (output_dir / "atlas_cell_rule_candidates_insert.sql").read_text()
    # A_strong (0.30) should appear before B_mid (0.20) before C_weak (0.05)
    a_pos = cands_text.find("A_strong")
    b_pos = cands_text.find("B_mid")
    c_pos = cands_text.find("C_weak")
    assert 0 < a_pos < b_pos < c_pos


def test_negative_sort_ascending(cells_dir: Path, tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    persist_cells.build_sql_files(cells_dir=cells_dir, output_dir=output_dir)
    cands_text = (output_dir / "atlas_cell_rule_candidates_insert.sql").read_text()
    # N_most_neg (-0.30) should appear before N_mid (-0.20) before N_least_neg (-0.05)
    most = cands_text.find("N_most_neg")
    mid = cands_text.find("N_mid")
    least = cands_text.find("N_least_neg")
    assert 0 < most < mid < least


def test_cell_rule_validates_predicates_split(cells_dir: Path, tmp_path: Path) -> None:
    """The translator must put log_med_tv_60d in eligibility, not entry."""
    output_dir = tmp_path / "out"
    persist_cells.build_sql_files(cells_dir=cells_dir, output_dir=output_dir)

    defs_text = (output_dir / "atlas_cell_definitions_insert.sql").read_text()
    # Extract the first jsonb blob
    start = defs_text.find("'{")
    end = defs_text.find("}'::jsonb")
    rule_json = defs_text[start + 1 : end + 1]
    # Un-escape doubled single quotes for parsing
    parsed = json.loads(rule_json.replace("''", "'"))
    rule = validate_rule_dsl(parsed)
    eligibility_features = {p.feature for p in rule.eligibility}
    entry_features = {p.feature for p in rule.entry}
    assert "log_med_tv_60d" in eligibility_features
    assert "log_med_tv_60d" not in entry_features
    assert "rs_residual_6m" in entry_features


def test_negative_notes_carries_survivorship_prefix(cells_dir: Path, tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    persist_cells.build_sql_files(cells_dir=cells_dir, output_dir=output_dir)
    cands_text = (output_dir / "atlas_cell_rule_candidates_insert.sql").read_text()
    # The NEGATIVE cell should have [SURVIVORSHIP-BIASED] in its notes
    assert "[SURVIVORSHIP-BIASED]" in cands_text


def test_cell_skipped_when_no_validated_candidate(tmp_path: Path) -> None:
    cells_dir = tmp_path / "cells"
    cells_dir.mkdir()
    payload = _make_payload(
        "Small",
        "1m",
        "POSITIVE",
        [
            _make_candidate("fail", "structural", 0.1, validated=False, bh_q=0.99),
        ],
    )
    (cells_dir / "Small-1m-POSITIVE.json").write_text(json.dumps(payload))
    _, _, stats = persist_cells.build_sql_files(cells_dir=cells_dir, output_dir=tmp_path / "out")
    assert stats["n_cells_skipped_no_validated"] == 1
    assert stats["n_definitions_emitted"] == 0


def test_sql_quote_escaping() -> None:
    """A predicate value containing a single quote must be escape-doubled."""
    out = persist_cells._sql_quote_json({"k": "O'Reilly"})
    assert "O''Reilly" in out
    assert "O'Reilly" not in out.replace("''", "")


def test_emit_definition_sql_has_required_columns(cells_dir: Path, tmp_path: Path) -> None:
    """Ensure the emitted DDL references the correct migration-080 columns."""
    output_dir = tmp_path / "out"
    persist_cells.build_sql_files(cells_dir=cells_dir, output_dir=output_dir)
    defs_text = (output_dir / "atlas_cell_definitions_insert.sql").read_text()
    # Must use cap_tier, action, methodology_lock_ref — NOT tier, direction, methodology_ref
    assert "cap_tier" in defs_text
    assert "methodology_lock_ref" in defs_text
    assert "INSERT INTO atlas.atlas_cell_definitions" in defs_text
    # Must NOT use the old (incorrect) column names
    assert "methodology_ref'" not in defs_text  # old name had quote after it
