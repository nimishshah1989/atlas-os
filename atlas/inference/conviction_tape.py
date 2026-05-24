"""Daily conviction tape — per-instrument × tenure verdict generator.

For each instrument with a row in ``atlas_scorecard_daily`` on the
snapshot date, walks the four tenures (1m, 3m, 6m, 12m) and:

1. Pulls top-K POSITIVE + top-K NEGATIVE candidates from
   ``atlas_cell_rule_candidates`` for the instrument's ``cap_tier`` and the
   tenure.
2. Evaluates each candidate's predicates against the scorecard row.
3. Picks the verdict using deterministic rules (see :func:`_decide_verdict`).
4. Emits an UPSERT into ``atlas_conviction_daily``.

The CLI writes either to the live DB (when ``.supabase-write-approved``
marker is present at the repo root) OR to a SQL file under
``<output-dir>/conviction_daily_<date>.sql``. The default is SQL-file
mode — live writes require explicit user opt-in via the marker.

Schema reference: migration 092.
"""

# allow-large: end-to-end conviction-tape pipeline. The two helpers
# (_decide_verdict + _evaluate_candidates) plus the SQL emitter live
# together because they share the verdict shape and the candidate row
# semantics — splitting would require duplicating the candidate-row
# typedict across modules.

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.decisions.evaluator import _eval_predicate  # pure, internal reuse
from atlas.decisions.rule_dsl import CellRule, validate_rule_dsl
from atlas.inference.eli5 import eli5 as render_eli5

log = structlog.get_logger()

Tenure = Literal["1m", "3m", "6m", "12m"]
Verdict = Literal["POSITIVE", "NEUTRAL", "NEGATIVE"]
TENURES: tuple[Tenure, ...] = ("1m", "3m", "6m", "12m")


@dataclass(frozen=True)
class ConvictionRow:
    """One row of the daily conviction tape."""

    snapshot_date: date
    instrument_id: str
    tenure: Tenure
    verdict: Verdict
    best_rule_id: str | None
    cell_definition_id: str | None
    ic: Decimal | None
    friction_adjusted_excess: Decimal | None
    fired_predicates: list[dict[str, Any]] | None
    eli5: str
    conflict: bool


@dataclass(frozen=True)
class CandidateRow:
    """A row from ``atlas_cell_rule_candidates`` joined to its cell def."""

    candidate_id: str
    cell_definition_id: str
    cap_tier: str
    action: str  # POSITIVE / NEGATIVE
    tenure: Tenure
    rule: CellRule
    ic: Decimal | None
    friction_adjusted_excess: Decimal | None
    archetype: str


# ---------------------------------------------------------------------------
# Verdict decision logic
# ---------------------------------------------------------------------------


def _decide_verdict(
    positive_hits: list[CandidateRow],
    negative_hits: list[CandidateRow],
) -> tuple[Verdict, CandidateRow | None, bool]:
    """Pick the verdict + best rule given the firing candidate lists.

    Rules:
      * If only POSITIVE hits → verdict=POSITIVE, best=top fric-adj-excess (DESC).
      * If only NEGATIVE hits → verdict=NEGATIVE, best=top fric-adj-excess (ASC).
      * If both → pick by abs(fric-adj-excess); tie → NEUTRAL + conflict=True.
      * If neither → NEUTRAL, best=None.

    Returns ``(verdict, best_candidate_or_None, conflict_flag)``.
    """
    if positive_hits and not negative_hits:
        best = max(
            positive_hits,
            key=lambda c: float(c.friction_adjusted_excess or 0),
        )
        return "POSITIVE", best, False
    if negative_hits and not positive_hits:
        best = min(
            negative_hits,
            key=lambda c: float(c.friction_adjusted_excess or 0),
        )
        return "NEGATIVE", best, False
    if not positive_hits and not negative_hits:
        return "NEUTRAL", None, False

    # Both fire — pick by absolute fric-adj-excess
    best_pos = max(positive_hits, key=lambda c: abs(float(c.friction_adjusted_excess or 0)))
    best_neg = max(negative_hits, key=lambda c: abs(float(c.friction_adjusted_excess or 0)))
    pos_mag = abs(float(best_pos.friction_adjusted_excess or 0))
    neg_mag = abs(float(best_neg.friction_adjusted_excess or 0))
    if pos_mag > neg_mag:
        return "POSITIVE", best_pos, True
    if neg_mag > pos_mag:
        return "NEGATIVE", best_neg, True
    # Exact tie — defer to NEUTRAL with conflict flag.
    return "NEUTRAL", None, True


# ---------------------------------------------------------------------------
# Candidate evaluation
# ---------------------------------------------------------------------------


def _evaluate_candidate(
    candidate: CandidateRow,
    row: Mapping[str, Any],
) -> tuple[bool, list[dict[str, Any]]]:
    """Evaluate one candidate against one scorecard row.

    Returns ``(fired, fired_predicates_summary)`` where the summary lists
    each predicate that contributed to firing (or all the predicates if
    the rule fires — they all passed).
    """
    rule = candidate.rule
    # Evaluate eligibility first — every predicate must pass.
    for pred in rule.eligibility:
        if not _eval_predicate(pred, row):
            return False, []
    # Then entry predicates — every predicate must pass.
    for pred in rule.entry:
        if not _eval_predicate(pred, row):
            return False, []

    # All predicates passed — record the rule signature for the daily row.
    fired = [
        {"feature": p.feature, "cmp": p.cmp, "value": str(p.value)}
        for p in rule.eligibility + rule.entry
    ]
    return True, fired


# ---------------------------------------------------------------------------
# DB queries (sync SQLAlchemy)
# ---------------------------------------------------------------------------


_LOAD_SCORECARD_SQL = text(
    """
    SELECT
        s.instrument_id::text AS instrument_id,
        s.cap_tier::text AS cap_tier,
        s.rs_residual_6m,
        s.log_med_tv_60d,
        s.realized_vol_60d,
        s.formation_max_dd,
        s.listing_age_days,
        s.log_price,
        s.features
    FROM atlas.atlas_scorecard_daily s
    WHERE s.date = :snapshot_date
    """
)


_LOAD_CANDIDATES_SQL = text(
    """
    SELECT
        c.id::text AS candidate_id,
        c.cell_definition_id::text AS cell_definition_id,
        d.cap_tier::text AS cap_tier,
        d.action::text AS action,
        d.tenure::text AS tenure,
        c.rule_dsl,
        c.ic,
        c.friction_adjusted_excess,
        c.archetype
    FROM atlas.atlas_cell_rule_candidates c
    JOIN atlas.atlas_cell_definitions d
      ON d.cell_id = c.cell_definition_id
    WHERE c.validated = TRUE
      AND d.deprecated_at IS NULL
    """
)


def _load_candidates(engine: Engine) -> dict[tuple[str, str, str], list[CandidateRow]]:
    """Load every validated candidate, keyed by ``(cap_tier, action, tenure)``."""
    out: dict[tuple[str, str, str], list[CandidateRow]] = {}
    with engine.connect() as conn:
        result = conn.execute(_LOAD_CANDIDATES_SQL)
        for row in result.mappings():
            rule_dsl = row["rule_dsl"]
            if isinstance(rule_dsl, str):
                rule_dsl = json.loads(rule_dsl)
            rule = validate_rule_dsl(rule_dsl)
            cand = CandidateRow(
                candidate_id=row["candidate_id"],
                cell_definition_id=row["cell_definition_id"],
                cap_tier=row["cap_tier"],
                action=row["action"],
                tenure=row["tenure"],
                rule=rule,
                ic=row["ic"],
                friction_adjusted_excess=row["friction_adjusted_excess"],
                archetype=row["archetype"],
            )
            key = (cand.cap_tier, cand.action, cand.tenure)
            out.setdefault(key, []).append(cand)
    return out


def _load_scorecard_rows(engine: Engine, snapshot_date: date) -> list[Mapping[str, Any]]:
    """Read the entire scorecard table for the snapshot date."""
    with engine.connect() as conn:
        result = conn.execute(_LOAD_SCORECARD_SQL, {"snapshot_date": snapshot_date})
        rows = [dict(r) for r in result.mappings()]
    # Merge the features JSONB into the top-level row dict so predicate
    # lookups see every feature.
    merged: list[Mapping[str, Any]] = []
    for r in rows:
        features = r.pop("features", None) or {}
        if isinstance(features, str):
            features = json.loads(features)
        r.update(features)
        merged.append(r)
    return merged


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def compute_conviction_for_snapshot(
    snapshot_date: date,
    *,
    engine: Engine | None = None,
    scorecard_rows: Sequence[Mapping[str, Any]] | None = None,
    candidates_by_key: dict[tuple[str, str, str], list[CandidateRow]] | None = None,
) -> list[ConvictionRow]:
    """Compute the conviction tape for one snapshot date.

    Either pass a live ``engine`` (production path) OR pre-loaded
    ``scorecard_rows`` + ``candidates_by_key`` for unit-testing.
    """
    if engine is not None:
        scorecard_rows = _load_scorecard_rows(engine, snapshot_date)
        candidates_by_key = _load_candidates(engine)
    assert scorecard_rows is not None and candidates_by_key is not None

    out: list[ConvictionRow] = []
    for row in scorecard_rows:
        cap_tier = row["cap_tier"]
        instrument_id = row["instrument_id"]

        for tenure in TENURES:
            pos_key = (cap_tier, "POSITIVE", tenure)
            neg_key = (cap_tier, "NEGATIVE", tenure)
            positive_cands = candidates_by_key.get(pos_key, [])
            negative_cands = candidates_by_key.get(neg_key, [])

            positive_hits: list[CandidateRow] = []
            negative_hits: list[CandidateRow] = []
            fired_for_hit: dict[str, list[dict[str, Any]]] = {}

            for cand in positive_cands:
                fired, summary = _evaluate_candidate(cand, row)
                if fired:
                    positive_hits.append(cand)
                    fired_for_hit[cand.candidate_id] = summary
            for cand in negative_cands:
                fired, summary = _evaluate_candidate(cand, row)
                if fired:
                    negative_hits.append(cand)
                    fired_for_hit[cand.candidate_id] = summary

            verdict, best, conflict = _decide_verdict(positive_hits, negative_hits)

            if best is not None:
                eli5_text = render_eli5(best.rule, cap_tier, tenure, best.action)
                fired_summary = fired_for_hit.get(best.candidate_id, [])
            else:
                eli5_text = "No active signal at this tenure."
                fired_summary = []

            out.append(
                ConvictionRow(
                    snapshot_date=snapshot_date,
                    instrument_id=instrument_id,
                    tenure=tenure,
                    verdict=verdict,
                    best_rule_id=best.candidate_id if best else None,
                    cell_definition_id=best.cell_definition_id if best else None,
                    ic=best.ic if best else None,
                    friction_adjusted_excess=(best.friction_adjusted_excess if best else None),
                    fired_predicates=fired_summary if fired_summary else None,
                    eli5=eli5_text,
                    conflict=conflict,
                )
            )
    return out


# ---------------------------------------------------------------------------
# SQL emission
# ---------------------------------------------------------------------------


def _sql_quote(s: str | None) -> str:
    if s is None:
        return "NULL"
    return "'" + s.replace("'", "''") + "'"


def _sql_decimal(d: Decimal | None) -> str:
    if d is None:
        return "NULL"
    return f"{float(d):.6f}"


def emit_upsert_sql(rows: list[ConvictionRow]) -> str:
    """Build a multi-row INSERT...ON CONFLICT statement."""
    if not rows:
        return "-- (no rows)\n"
    values_lines: list[str] = []
    for r in rows:
        fired_json = (
            _sql_quote(json.dumps(r.fired_predicates)) if r.fired_predicates is not None else "NULL"
        )
        values_lines.append(
            "  ("
            f"'{r.snapshot_date.isoformat()}', "
            f"'{r.instrument_id}', "
            f"'{r.tenure}', "
            f"'{r.verdict}', "
            f"{_sql_quote(r.best_rule_id)}, "
            f"{_sql_quote(r.cell_definition_id)}, "
            f"{_sql_decimal(r.ic)}, "
            f"{_sql_decimal(r.friction_adjusted_excess)}, "
            f"{fired_json}{'::jsonb' if r.fired_predicates is not None else ''}, "
            f"{_sql_quote(r.eli5)}, "
            f"{'TRUE' if r.conflict else 'FALSE'}"
            ")"
        )
    sql = (
        "INSERT INTO atlas.atlas_conviction_daily "
        "(snapshot_date, instrument_id, tenure, verdict, best_rule_id, "
        "cell_definition_id, ic, friction_adjusted_excess, fired_predicates, "
        "eli5, conflict) VALUES\n" + ",\n".join(values_lines) + "\n"
        "ON CONFLICT (snapshot_date, instrument_id, tenure) DO UPDATE SET\n"
        "  verdict = EXCLUDED.verdict,\n"
        "  best_rule_id = EXCLUDED.best_rule_id,\n"
        "  cell_definition_id = EXCLUDED.cell_definition_id,\n"
        "  ic = EXCLUDED.ic,\n"
        "  friction_adjusted_excess = EXCLUDED.friction_adjusted_excess,\n"
        "  fired_predicates = EXCLUDED.fired_predicates,\n"
        "  eli5 = EXCLUDED.eli5,\n"
        "  conflict = EXCLUDED.conflict;\n"
    )
    return sql


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _has_write_marker(repo_root: Path) -> bool:
    """Check for the .supabase-write-approved marker."""
    return (repo_root / ".supabase-write-approved").exists()


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--date", required=True, help="Snapshot date (YYYY-MM-DD)")
    p.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Currently unused (kept for forward compat)",
    )
    p.add_argument(
        "--backfill",
        action="store_true",
        help="Marker flag — pure documentation; pipeline runs the same regardless",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Where to write the SQL file when live writes are blocked",
    )
    p.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repo root (used to look for .supabase-write-approved marker)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    snapshot_date = date.fromisoformat(args.date)

    # Local import — avoids importing the DB engine when the module is
    # used in pure unit-test mode.
    from atlas.db import get_engine

    engine = get_engine()
    rows = compute_conviction_for_snapshot(snapshot_date, engine=engine)
    log.info("conviction_tape_computed", date=str(snapshot_date), n_rows=len(rows))

    if _has_write_marker(args.repo_root):
        log.info("conviction_tape_live_write", n_rows=len(rows))
        sql = emit_upsert_sql(rows)
        with engine.begin() as conn:
            conn.execute(text(sql))
        print(f"Wrote {len(rows)} rows to atlas_conviction_daily")
        return 0

    # Marker absent — write the SQL to a file instead.
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.output_dir / f"conviction_daily_{snapshot_date.isoformat()}.sql"
    out_path.write_text(emit_upsert_sql(rows))
    print(f"Wrote {len(rows)} rows to {out_path}")
    print("Live DB write skipped — .supabase-write-approved marker not present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
