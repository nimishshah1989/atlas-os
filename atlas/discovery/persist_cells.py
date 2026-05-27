"""Deep-search v2 → atlas_cell_definitions + atlas_cell_rule_candidates SQL.

Reads 24 cell JSON files from the deep-search v2 output directory and emits
two INSERT SQL files:

* ``atlas_cell_definitions_insert.sql`` — top-1 sign-correct validated rule
  per cell (up to 24 rows; cells with no validated candidate are skipped
  with a SKIP comment).
* ``atlas_cell_rule_candidates_insert.sql`` — top-5 validated candidates per
  cell, ranked 1..5, gated by ``validated=True`` AND ``bh_q_value <= 0.10``.

Sort order:

* POSITIVE direction → ``friction_adjusted_excess DESC`` (largest positive
  excess is rank 1).
* NEGATIVE direction → ``friction_adjusted_excess ASC`` (most-negative
  excess is rank 1).

Each candidate's predicate list is translated to the existing
:class:`atlas.decisions.rule_dsl.CellRule` shape with a manual
``eligibility`` vs ``entry`` split:

* ``log_med_tv_60d`` (the tier liquidity floor) → ``eligibility``
* everything else → ``entry``

The translator validates each rule via
:func:`atlas.decisions.rule_dsl.validate_rule_dsl` BEFORE emitting SQL — a
typo in a predicate's feature surfaces here, not at inference time.

Live DB writes are NOT performed by this module. The CLI writes the two SQL
files to ``--output-dir``; applying them is the user's manual step (the
``.supabase-write-approved`` marker is the gate, NOT this script).

Schema notes
------------
Migration 080 names the columns ``cap_tier`` (NOT ``tier``), ``action``
(NOT ``direction``), ``methodology_lock_ref`` (NOT ``methodology_ref``),
and folds free-text notes into ``rule_dsl.notes`` rather than a separate
column. This module respects the migration-080 schema verbatim.

Usage
-----
::

    python -m atlas.discovery.persist_cells \\
        --cells-dir /tmp/deep_search_v2/cells \\
        --output-dir /tmp/deep_search_v2
"""

# allow-large: cohesive single-responsibility surface — read JSONs, translate
# predicates, emit two SQL files. Splitting would scatter the schema-mapping
# logic across modules and obscure the migration-080 column-name corrections
# documented in the module docstring.

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from atlas.decisions.rule_dsl import CellRule, FeaturePredicate, validate_rule_dsl

# Archetype → CellRule.rule_type mapping. CellRule defines a fixed Literal
# vocabulary {pullback, severely_broken, emerging, topping, accumulate, trim,
# watch, hold, placeholder}; deep-search archetypes are richer (25 names), so
# we project them onto the closest rule_type slot. The semantic identity is
# preserved by carrying ``archetype`` as a top-level column in
# ``atlas_cell_rule_candidates`` AND inside ``rule_dsl.notes``.
ARCHETYPE_TO_RULE_TYPE: dict[str, str] = {
    # POSITIVE
    "mean_reversion": "pullback",
    "deep_value": "severely_broken",
    "quality_momentum": "hold",
    "inflection": "emerging",
    "consolidation_breakout": "emerging",
    "liquidity_expansion": "accumulate",
    "structural": "hold",
    "low_vol_carry": "hold",
    "breakout_with_pullback": "pullback",
    "sector_relative_leadership": "accumulate",
    "bab_low_beta": "hold",
    "liquidity_thrust_mfi": "accumulate",
    "obv_thrust": "accumulate",
    # NEGATIVE
    "mean_reversion_overbought": "trim",
    "distribution": "topping",
    "volatility_spike": "topping",
    "breakdown": "severely_broken",
    "deep_value_avoid": "watch",
    "weak_quality": "trim",
    "overextension": "topping",
    "sector_drag": "watch",
    "sector_breakdown": "severely_broken",
    "bab_high_beta_short": "trim",
    "mfi_overbought_distrib": "topping",
    "obv_divergence_neg": "trim",
}

# Predicates whose feature name implies an eligibility filter (universe
# selection / liquidity floor), NOT an entry trigger. Everything else is
# treated as an entry predicate.
_ELIGIBILITY_FEATURES = frozenset(
    {
        "log_med_tv_60d",
        "listing_age_days",
        "log_price",
    }
)

Direction = Literal["POSITIVE", "NEUTRAL", "NEGATIVE"]


@dataclass(frozen=True)
class CellMetadata:
    cap_tier: Literal["Large", "Mid", "Small"]
    tenure: Literal["1m", "3m", "6m", "12m"]
    action: Direction
    methodology_lock_ref: str


def _parse_value(raw: Any) -> Decimal | tuple[Decimal, Decimal]:
    """Convert the JSON value field into Decimal or (low, high) tuple."""
    if isinstance(raw, list):
        if len(raw) != 2:
            raise ValueError(f"in_range value must be 2-element list, got {raw!r}")
        return (Decimal(str(raw[0])), Decimal(str(raw[1])))
    return Decimal(str(raw))


def _predicate_from_json(p: dict[str, Any]) -> FeaturePredicate:
    """Convert a single predicate JSON object to a FeaturePredicate."""
    cmp_ = p["cmp"]
    feature = p["feature"]
    if cmp_ == "in_top_quantile":
        # in_top_quantile carries value_quantile_n; value is the sentinel
        return FeaturePredicate(
            feature=feature,
            cmp="in_top_quantile",
            value=Decimal("1"),
            value_quantile_n=int(p.get("value_quantile_n") or 0),
        )
    return FeaturePredicate(
        feature=feature,
        cmp=cmp_,
        value=_parse_value(p["value"]),
    )


def _split_predicates(
    predicates: list[FeaturePredicate],
) -> tuple[list[FeaturePredicate], list[FeaturePredicate]]:
    """Split predicates into (eligibility, entry) lists.

    eligibility: universe / liquidity gates (log_med_tv_60d et al).
    entry:       everything else (the actual signal triggers).
    """
    eligibility: list[FeaturePredicate] = []
    entry: list[FeaturePredicate] = []
    for p in predicates:
        if p.feature in _ELIGIBILITY_FEATURES:
            eligibility.append(p)
        else:
            entry.append(p)
    return eligibility, entry


def _build_cell_rule(
    candidate: dict[str, Any],
    meta: CellMetadata,
    rank: int,
) -> CellRule:
    """Translate a deep-search candidate into a validated CellRule."""
    predicates = [_predicate_from_json(p) for p in candidate["predicates"]]
    eligibility, entry = _split_predicates(predicates)

    archetype = candidate["archetype"]
    rule_type = ARCHETYPE_TO_RULE_TYPE.get(archetype, "placeholder")

    # Compose the notes blob — survives in rule_dsl as a JSON-serializable
    # string so callers can render the lineage without a JOIN.
    is_negative = meta.action == "NEGATIVE"
    bias_prefix = "[SURVIVORSHIP-BIASED] " if is_negative else ""
    notes = (
        f"{bias_prefix}{candidate['name']} | archetype={archetype} | "
        f"rank={rank} | IC={candidate.get('ic', 0):.4f} | "
        f"fric-adj={candidate.get('friction_adjusted_excess', 0):.4f} | "
        f"bh_q={candidate.get('bh_q_value', 'n/a')}"
    )

    rule = CellRule(
        rule_type=rule_type,  # type: ignore[arg-type]
        eligibility=eligibility,
        entry=entry,
        tier=meta.cap_tier,
        action=meta.action,
        tenure=meta.tenure,
        rule_version=1,
        methodology_lock_ref=meta.methodology_lock_ref,
        notes=notes,
    )
    # Validate roundtrip via the canonical helper — catches feature-allowlist
    # mismatches early.
    validate_rule_dsl(rule.model_dump(mode="json"))
    return rule


def _select_top_k(
    candidates: list[dict[str, Any]],
    action: Direction,
    k: int,
    require_validated: bool = True,
    q_threshold: float = 0.10,
) -> list[dict[str, Any]]:
    """Sort + filter candidates, return top-k.

    POSITIVE: friction_adjusted_excess DESC.
    NEGATIVE: friction_adjusted_excess ASC (most-negative ranks first).

    Gate:
      * ``validated == True`` (unless ``require_validated=False``)
      * ``bh_q_value <= q_threshold`` when bh_q_value is present.
    """
    filtered: list[dict[str, Any]] = []
    for c in candidates:
        if require_validated and not c.get("validated", False):
            continue
        bh_q = c.get("bh_q_value")
        if bh_q is not None and float(bh_q) > q_threshold:
            continue
        filtered.append(c)

    reverse = action == "POSITIVE"

    def _key(c: dict[str, Any]) -> float:
        v = c.get("friction_adjusted_excess")
        return float(v) if v is not None else 0.0

    filtered.sort(key=_key, reverse=reverse)
    return filtered[:k]


def _cell_meta_from_payload(payload: dict[str, Any]) -> CellMetadata:
    cell = payload["cell"]
    action_raw = cell["direction"]
    if action_raw not in {"POSITIVE", "NEUTRAL", "NEGATIVE"}:
        raise ValueError(f"Unexpected cell direction: {action_raw!r}")
    return CellMetadata(
        cap_tier=cell["tier"],
        tenure=cell["tenure"],
        action=action_raw,  # type: ignore[arg-type]
        methodology_lock_ref=payload["methodology_lock_ref"],
    )


def _sql_quote_json(d: dict[str, Any] | list[Any]) -> str:
    """Quote a JSON blob for inline INSERT — single-quote-escape doubled."""
    return json.dumps(d, default=str).replace("'", "''")


def _format_decimal(v: Any) -> str:
    if v is None:
        return "NULL"
    try:
        return f"{float(v):.6f}"
    except (TypeError, ValueError):
        return "NULL"


def emit_definition_sql(
    rule: CellRule,
    candidate: dict[str, Any],
    meta: CellMetadata,
) -> str:
    """Emit a single INSERT for ``atlas_cell_definitions``."""
    rule_json = _sql_quote_json(rule.model_dump(mode="json"))
    confidence_unconditional = candidate.get("tp_rate")
    fric_adj = candidate.get("friction_adjusted_excess")
    stable_features = {
        "ic": candidate.get("ic"),
        "median_excess": candidate.get("median_excess"),
        "n_observations": candidate.get("n_observations"),
        "per_window": candidate.get("per_window", []),
        "archetype": candidate["archetype"],
        "rule_name": candidate["name"],
    }
    stable_json = _sql_quote_json(stable_features)

    # Emits SQL files for human review; not executed.
    sql = (
        "INSERT INTO atlas.atlas_cell_definitions "  # noqa: S608
        "(cap_tier, action, tenure, rule_dsl, "
        "confidence_unconditional, friction_adjusted_excess, "
        "stable_features, methodology_lock_ref, rule_version, "
        "validated_at) VALUES ("
        f"'{meta.cap_tier}', '{meta.action}', '{meta.tenure}', "
        f"'{rule_json}'::jsonb, "
        f"{_format_decimal(confidence_unconditional)}, "
        f"{_format_decimal(fric_adj)}, "
        f"'{stable_json}'::jsonb, "
        f"'{meta.methodology_lock_ref}', 1, NOW());"
    )
    return sql


def emit_candidate_sql(
    rule: CellRule,
    candidate: dict[str, Any],
    meta: CellMetadata,
    rank: int,
    eli5: str,
) -> str:
    """Emit a single INSERT for ``atlas_cell_rule_candidates``.

    The ``cell_definition_id`` is bound by a CTE-style lookup against the
    just-inserted ``atlas_cell_definitions`` row on natural key
    ``(cap_tier, action, tenure)`` filtered to the active partial unique
    index (``deprecated_at IS NULL``).
    """
    rule_json = _sql_quote_json(rule.model_dump(mode="json"))
    archetype = candidate["archetype"]
    ic = candidate.get("ic")
    fric_adj = candidate.get("friction_adjusted_excess")
    bh_q = candidate.get("bh_q_value")
    eli5_sql = eli5.replace("'", "''")
    notes_sql = rule.notes.replace("'", "''")

    sql = (
        "INSERT INTO atlas.atlas_cell_rule_candidates "  # noqa: S608
        "(cell_definition_id, rank, rule_dsl, archetype, ic, "
        "friction_adjusted_excess, bh_q_value, eli5, validated, notes) "
        "SELECT cell_id, "
        f"{rank}, '{rule_json}'::jsonb, '{archetype}', "
        f"{_format_decimal(ic)}, "
        f"{_format_decimal(fric_adj)}, "
        f"{_format_decimal(bh_q)}, "
        f"'{eli5_sql}', TRUE, '{notes_sql}' "
        "FROM atlas.atlas_cell_definitions "
        f"WHERE cap_tier = '{meta.cap_tier}' "
        f"AND action = '{meta.action}' "
        f"AND tenure = '{meta.tenure}' "
        "AND deprecated_at IS NULL;"
    )
    return sql


def load_cell_payloads(cells_dir: Path) -> list[dict[str, Any]]:
    """Read every ``*.json`` (excluding ``*.out``) in the directory.

    The deep-search v2 engine writes one JSON per cell file named
    ``<Tier>-<tenure>-<DIRECTION>.json``.
    """
    payloads: list[dict[str, Any]] = []
    for path in sorted(cells_dir.glob("*.json")):
        with path.open() as fp:
            payloads.append(json.load(fp))
    return payloads


def build_sql_files(
    cells_dir: Path,
    output_dir: Path,
    top_k: int = 5,
    q_threshold: float = 0.10,
) -> tuple[Path, Path, dict[str, int]]:
    """Build the two SQL files. Returns (definitions_path, candidates_path, stats)."""
    payloads = load_cell_payloads(cells_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    defs_path = output_dir / "atlas_cell_definitions_insert.sql"
    cands_path = output_dir / "atlas_cell_rule_candidates_insert.sql"

    # Local import to avoid a circular dep at module import time.
    from atlas.inference.eli5 import eli5 as _eli5

    stats = {
        "n_cells": 0,
        "n_definitions_emitted": 0,
        "n_candidates_emitted": 0,
        "n_cells_skipped_no_validated": 0,
    }

    defs_sql_lines: list[str] = [
        "-- atlas_cell_definitions inserts — top-1 per cell",
        "-- Source: deep-search v2 cell JSONs",
        "-- Generated by atlas.discovery.persist_cells",
        "",
    ]
    cands_sql_lines: list[str] = [
        "-- atlas_cell_rule_candidates inserts — top-5 per cell",
        "-- Source: deep-search v2 cell JSONs",
        "-- Generated by atlas.discovery.persist_cells",
        "",
    ]

    for payload in payloads:
        stats["n_cells"] += 1
        meta = _cell_meta_from_payload(payload)
        candidates = payload.get("candidates", [])

        top_k_candidates = _select_top_k(candidates, meta.action, k=top_k, q_threshold=q_threshold)
        if not top_k_candidates:
            stats["n_cells_skipped_no_validated"] += 1
            defs_sql_lines.append(
                f"-- SKIP {meta.cap_tier}-{meta.tenure}-{meta.action}: "
                "no validated candidate passes q-gate."
            )
            cands_sql_lines.append(
                f"-- SKIP {meta.cap_tier}-{meta.tenure}-{meta.action}: "
                "no validated candidate passes q-gate."
            )
            continue

        # Top-1 → atlas_cell_definitions
        top1 = top_k_candidates[0]
        top1_rule = _build_cell_rule(top1, meta, rank=1)
        defs_sql_lines.append(
            f"-- {meta.cap_tier}-{meta.tenure}-{meta.action}: "
            f"{top1['name']} ({top1['archetype']})"
        )
        defs_sql_lines.append(emit_definition_sql(top1_rule, top1, meta))
        stats["n_definitions_emitted"] += 1

        # Top-1..K → atlas_cell_rule_candidates
        cands_sql_lines.append(
            f"-- {meta.cap_tier}-{meta.tenure}-{meta.action}: "
            f"{len(top_k_candidates)} candidate(s)"
        )
        for rank, cand in enumerate(top_k_candidates, start=1):
            rule = _build_cell_rule(cand, meta, rank=rank)
            eli5_text = _eli5(rule, meta.cap_tier, meta.tenure, meta.action)
            cands_sql_lines.append(emit_candidate_sql(rule, cand, meta, rank, eli5_text))
            stats["n_candidates_emitted"] += 1

    defs_path.write_text("\n".join(defs_sql_lines) + "\n")
    cands_path.write_text("\n".join(cands_sql_lines) + "\n")
    return defs_path, cands_path, stats


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--cells-dir",
        type=Path,
        required=True,
        help="Directory of deep-search v2 cell JSON files (e.g. ./deep_search_v2/cells)",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Where to write the two INSERT SQL files",
    )
    p.add_argument("--top-k", type=int, default=5, help="Top-K candidates per cell")
    p.add_argument(
        "--q-threshold",
        type=float,
        default=0.10,
        help="BH-FDR q-value gate (skip candidates with q > threshold)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    if not args.cells_dir.exists():
        print(f"ERROR: cells-dir does not exist: {args.cells_dir}", file=sys.stderr)
        return 2

    defs_path, cands_path, stats = build_sql_files(
        cells_dir=args.cells_dir,
        output_dir=args.output_dir,
        top_k=args.top_k,
        q_threshold=args.q_threshold,
    )

    print(f"Wrote {defs_path} ({stats['n_definitions_emitted']} INSERTs)")
    print(f"Wrote {cands_path} ({stats['n_candidates_emitted']} INSERTs)")
    print(
        f"Cells processed: {stats['n_cells']} | "
        f"definitions emitted: {stats['n_definitions_emitted']} | "
        f"candidates emitted: {stats['n_candidates_emitted']} | "
        f"skipped (no validated): {stats['n_cells_skipped_no_validated']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
