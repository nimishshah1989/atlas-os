"""v6 — mark v5 atlas_* tables deprecated + seed v6 placeholder defaults.

Final Phase 2 schema migration (per CEO plan §"Migration cutover (v5 → v6)"
+ /grill Q10 Path A). Two scoped changes:

1. Stamp every v5 atlas_* table created in migrations 060–079 with a
   ``deprecated_at`` TIMESTAMPTZ column (nullable, default NULL) and a
   table COMMENT noting the v5 status. The column is the marker the
   read-only / DROP enforcement layer will key off later (Phase 6 public
   launch + 6mo post-launch per /grill Q10 Path A — NOT this migration).

2. Seed 12 PLACEHOLDER rows into ``atlas.atlas_cell_definitions`` so the
   v6 schema is exercised end-to-end. Real cell definitions ship when
   Phase 0.5g 24-framework discovery (issue #25) completes. Every
   placeholder row carries ``methodology_lock_ref = 'PLACEHOLDER_2026-05-24'``
   so downgrade can target them exactly.

v5 atlas_* tables marked deprecated
-----------------------------------
From migrations 060–079 (v5/Phase-1 era):

- ``atlas_signal_alerts`` (064)
- ``atlas_fund_holdings_changes`` (065)
- ``atlas_fund_decision_scores`` (065)
- ``atlas_strategy_genomes`` (067)
- ``atlas_strategy_performance_daily`` (067)
- ``atlas_strategy_positions_daily`` (067)
- ``atlas_strategy_leaderboard`` (067)
- ``atlas_strategy_insights`` (067)
- ``atlas_universe_membership_daily`` (067)
- ``atlas_strategy_evolution_log`` (067)
- ``atlas_portfolio_config`` (067)
- ``atlas_strategy_recommendations_daily`` (069)
- ``atlas_strategy_validation`` (070)
- ``atlas_stock_state_daily`` (072)
- ``atlas_state_dwell_statistics`` (073)
- ``atlas_state_thresholds`` (074)
- ``atlas_state_action_log`` (075)
- ``atlas_component_validation`` (079)

Per the issue brief: mark ALL of them deprecated. If v6 ends up depending
on one long-term (e.g. universe definition rows used as a stepping stone),
that's a separate decision tracked elsewhere — the deprecated_at flag
does NOT enforce read-only. It's a marker.

Placeholder cell_definitions seed
---------------------------------
12 rows covering every (cap_tier × action × tenure) combination where
action ∈ {POSITIVE, NEGATIVE} and tenure ∈ {6m, 12m}:

    3 cap_tier (Small, Mid, Large)
  × 2 action (POSITIVE, NEGATIVE)
  × 2 tenure (6m, 12m)
  = 12 placeholder cells

Every row is tagged ``methodology_lock_ref = 'PLACEHOLDER_2026-05-24'``
and ``rule_dsl.rule_type = 'placeholder'`` so downgrade + the real
Phase 0.5g discovery output can both find / replace them deterministically.

The partial unique index ``uq_atlas_cell_definitions_active`` (created
in 080) requires (cap_tier, action, tenure) be unique while
``deprecated_at IS NULL`` — so each (cap_tier, action, tenure) tuple
gets exactly one placeholder row, which satisfies the constraint.

atlas_thresholds regime placeholder rows — SKIPPED
--------------------------------------------------
``atlas.atlas_thresholds`` exists (created in migration 007) but its
``threshold_value`` column is ``NUMERIC(18,6) NOT NULL`` with a
``CHECK (threshold_value >= min_allowed AND threshold_value <= max_allowed)``
constraint. A string sentinel like ``'PLACEHOLDER'`` cannot be stored
there.

Per the issue brief's escape clause ("If atlas_thresholds table doesn't
exist yet, SKIP this section and document"): regime classifier threshold
rows are deferred to the Phase 0.5h-prime sweep migration which will
ship real numeric values + a non-null methodology_section + valid
min_allowed/max_allowed bounds.

Migration chain
---------------
    080 (foundation) -> 082 (brief_cache)
                     -> 083 (ledger)
                     -> 084 (paper_portfolio + user_lots)
                     -> 085 (ETF + MF)
                     -> 086 (macro overlay)
                     -> 087 (provenance log)
                     -> 088 (drift event log)
                     -> 089 (v5 deprecation + v6 placeholder seed — this migration)

Revision ID: 089
Revises: 088
Create Date: 2026-05-24
"""

from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "089"
down_revision = "088"
branch_labels = None
depends_on = None

_SCHEMA = "atlas"

# ---------------------------------------------------------------------------
# v5 atlas_* tables to mark deprecated. Sourced from migrations 060–079.
# ---------------------------------------------------------------------------

V5_DEPRECATED_TABLES: tuple[str, ...] = (
    "atlas_signal_alerts",                # 064
    "atlas_fund_holdings_changes",        # 065
    "atlas_fund_decision_scores",         # 065
    "atlas_strategy_genomes",             # 067
    "atlas_strategy_performance_daily",   # 067
    "atlas_strategy_positions_daily",     # 067
    "atlas_strategy_leaderboard",         # 067
    "atlas_strategy_insights",            # 067
    "atlas_universe_membership_daily",    # 067
    "atlas_strategy_evolution_log",       # 067
    "atlas_portfolio_config",             # 067
    "atlas_strategy_recommendations_daily",  # 069
    "atlas_strategy_validation",          # 070
    "atlas_stock_state_daily",            # 072
    "atlas_state_dwell_statistics",       # 073
    "atlas_state_thresholds",             # 074
    "atlas_state_action_log",             # 075
    "atlas_component_validation",         # 079
)

_DEPRECATED_COMMENT = (
    "v5 — read-only for backfill comparison. "
    "v6 trunk uses atlas_signal_calls / atlas_scorecard_daily instead."
)

# ---------------------------------------------------------------------------
# Placeholder cell_definitions seed config.
# ---------------------------------------------------------------------------

PLACEHOLDER_METHODOLOGY_LOCK_REF = "PLACEHOLDER_2026-05-24"
PLACEHOLDER_CAP_TIERS: tuple[str, ...] = ("Small", "Mid", "Large")
PLACEHOLDER_ACTIONS: tuple[str, ...] = ("POSITIVE", "NEGATIVE")
PLACEHOLDER_TENURES: tuple[str, ...] = ("6m", "12m")


def _build_placeholder_cells() -> list[dict[str, object]]:
    """Build the 12 placeholder cell_definitions rows.

    Every row:

    - has a fresh UUID for ``cell_id``
    - has ``rule_dsl`` as a JSON-serialised dict tagging ``rule_type``
      ``'placeholder'`` so downstream consumers can filter cleanly
    - shares ``methodology_lock_ref = PLACEHOLDER_2026-05-24`` so
      downgrade can target placeholders precisely
    - leaves the metric columns NULL (real values come from Phase 0.5g
      walk-forward)
    """
    cells: list[dict[str, object]] = []
    for cap_tier in PLACEHOLDER_CAP_TIERS:
        for action in PLACEHOLDER_ACTIONS:
            for tenure in PLACEHOLDER_TENURES:
                rule_dsl = {
                    "rule_type": "placeholder",
                    "eligibility": [],
                    "entry": [],
                    "tier": cap_tier,
                    "action": action,
                    "tenure": tenure,
                    "rule_version": 0,
                    "methodology_lock_ref": PLACEHOLDER_METHODOLOGY_LOCK_REF,
                    "notes": (
                        "placeholder — real rule_dsl shipped by "
                        "Phase 0.5g 24-framework discovery"
                    ),
                }
                cells.append(
                    {
                        "cell_id": str(uuid.uuid4()),
                        "cap_tier": cap_tier,
                        "action": action,
                        "tenure": tenure,
                        "rule_dsl": json.dumps(rule_dsl),
                        "confidence_unconditional": None,
                        "friction_adjusted_excess": None,
                        "confidence_by_regime": None,
                        "stable_features": None,
                        "methodology_lock_ref": PLACEHOLDER_METHODOLOGY_LOCK_REF,
                        "rule_version": 0,
                        "drift_status": "healthy",
                        "validated_at": None,
                        "deprecated_at": None,
                    }
                )
    return cells


def upgrade() -> None:
    # -----------------------------------------------------------------
    # 1. Stamp every v5 atlas_* table with deprecated_at + table COMMENT.
    # -----------------------------------------------------------------
    for table in V5_DEPRECATED_TABLES:
        op.add_column(
            table,
            sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
            schema=_SCHEMA,
        )
        op.execute(
            sa.text(
                f"COMMENT ON TABLE {_SCHEMA}.{table} IS :comment"
            ).bindparams(comment=_DEPRECATED_COMMENT)
        )

    # -----------------------------------------------------------------
    # 2. Seed 12 placeholder rows into atlas_cell_definitions.
    #
    # Use SQLAlchemy table reflection via a lightweight Table object so
    # op.bulk_insert can run regardless of metadata being loaded. The
    # placeholder rule_dsl is JSON-encoded; the JSONB column on the
    # target table will cast on insert.
    # -----------------------------------------------------------------
    cell_definitions = sa.table(
        "atlas_cell_definitions",
        sa.column("cell_id", postgresql.UUID(as_uuid=False)),
        sa.column("cap_tier", sa.String()),
        sa.column("action", sa.String()),
        sa.column("tenure", sa.String()),
        sa.column("rule_dsl", postgresql.JSONB()),
        sa.column("confidence_unconditional", sa.Numeric(5, 4)),
        sa.column("friction_adjusted_excess", sa.Numeric(10, 6)),
        sa.column("confidence_by_regime", postgresql.JSONB()),
        sa.column("stable_features", postgresql.JSONB()),
        sa.column("methodology_lock_ref", sa.String(length=64)),
        sa.column("rule_version", sa.Integer()),
        sa.column("drift_status", sa.String()),
        sa.column("validated_at", sa.DateTime(timezone=True)),
        sa.column("deprecated_at", sa.DateTime(timezone=True)),
        schema=_SCHEMA,
    )
    op.bulk_insert(cell_definitions, _build_placeholder_cells())


def downgrade() -> None:
    """Reverse upgrade. Strict ordering:

    1. DELETE placeholder rows from atlas_cell_definitions
       (must happen BEFORE dropping deprecated_at column because the
       order is independent — but conceptually data first, then schema).
    2. DROP the deprecated_at column from every v5 atlas_* table.

    Step 1 keys off ``methodology_lock_ref = 'PLACEHOLDER_2026-05-24'``
    so it only removes the rows this migration inserted — never any
    real cell definitions that may have been added between upgrade
    and downgrade.
    """
    # 1. Delete placeholder cell_definitions rows.
    op.execute(
        sa.text(
            f"DELETE FROM {_SCHEMA}.atlas_cell_definitions "
            f"WHERE methodology_lock_ref = :ref"
        ).bindparams(ref=PLACEHOLDER_METHODOLOGY_LOCK_REF)
    )

    # 2. Drop deprecated_at column from every v5 atlas_* table.
    #    Reverse order keeps the audit trail readable (mirrors upgrade
    #    list) but ordering is not load-bearing — each column is
    #    independent of every other.
    for table in reversed(V5_DEPRECATED_TABLES):
        op.drop_column(table, "deprecated_at", schema=_SCHEMA)
