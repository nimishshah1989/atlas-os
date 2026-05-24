"""v6 — atlas_cell_walkforward_runs + atlas_friction_params + regime threshold seeds.

Implements the long-reserved Phase 0.5d/0.5h-prime support tables. Unblocks
``atlas/discovery/`` (Phase 0.5g 24-framework discovery sweep) — the matrix
generator writes its per-sweep audit rows to ``atlas_cell_walkforward_runs``
and reads tiered friction coefficients from ``atlas_friction_params``.

Chain note
----------
The ``081`` slot was reserved when 082–089 shipped (because the original
Phase 0.5d/0.5h-prime workstream was sequenced separately). This migration
lands as ``081_z`` with ``down_revision = '089'`` (chronological order).
The filename uses the ``081z_`` prefix to signal "intended for slot 081 but
landed after 089 due to chain history." Future migrations should set
``down_revision = '081_z'``.

Tables
------
- ``atlas_cell_walkforward_runs`` — write-once audit row per walk-forward
  sweep. UPDATE allowed ONLY for the ``running → completed/failed/aborted``
  status transition; all other mutations rejected by a plpgsql trigger.
  Indexed by (tenure, cell_id, run_started_at DESC), (cell_id, status),
  and (provenance_log_id).

- ``atlas_friction_params`` — per-cap_tier × per-component friction
  coefficient table. Append-only: UPDATE rejected by a trigger except for
  setting ``effective_until`` on a still-open row. Indexed for current-value
  lookup.

New enums
---------
- ``atlas_walkforward_status`` ('running', 'completed', 'failed', 'aborted')
- ``atlas_friction_component`` ('bid_ask', 'impact', 'brokerage', 'slippage')

Reused enums (create_type=False, NOT dropped on downgrade)
----------------------------------------------------------
- ``atlas_tenure`` from 080 (1m / 3m / 6m / 12m)
- ``atlas_cap_tier`` from 080 (Small / Mid / Large)

FK relationships
----------------
- ``atlas_cell_walkforward_runs.provenance_log_id``
    → ``atlas.atlas_provenance_log(run_id)`` ON DELETE SET NULL.
- ``atlas_cell_definitions.walkforward_run_id`` (retroactive FK)
    → ``atlas.atlas_cell_walkforward_runs(run_id)`` ON DELETE SET NULL.
  The column was declared by migration 080 as a plain nullable UUID with
  no FK target; this migration adds the constraint NOW.

Seeds
-----
- 12 friction rows (3 cap_tiers × 4 components) with reasonable Indian
  retail brokerage placeholders. Replace via Phase 0.5d real research by
  inserting new rows with later ``effective_from`` (append-only). Setting
  ``effective_until`` on the placeholder row at the same time is the only
  mutation permitted.
- 7 atlas_thresholds rows with regime classifier placeholders. Replace
  via Phase 0.5h-prime sweep (#16). atlas_thresholds rows are UPDATE-able
  via the existing audit trigger; this migration only seeds initial values
  when keys do not already exist (ON CONFLICT DO NOTHING).

Revision ID: 081_z
Revises: 089
Create Date: 2026-05-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "081_z"
down_revision = "089"
branch_labels = None
depends_on = None

_SCHEMA = "atlas"

# ---------------------------------------------------------------------------
# NEW enums owned by this migration (081_z creates + drops).
# ---------------------------------------------------------------------------

WALKFORWARD_STATUS = ("running", "completed", "failed", "aborted")
FRICTION_COMPONENT = ("bid_ask", "impact", "brokerage", "slippage")


# ---------------------------------------------------------------------------
# Seed data — friction params (12 rows: 3 tiers × 4 components).
# Decimal-style strings; the column type is Numeric(8,6).
# Replace via Phase 0.5d real research.
# ---------------------------------------------------------------------------

FRICTION_SEEDS: tuple[tuple[str, str, str], ...] = (
    # (cap_tier, component, value)
    ("Small", "bid_ask", "0.003000"),
    ("Small", "impact", "0.002000"),
    ("Small", "brokerage", "0.000300"),
    ("Small", "slippage", "0.001000"),
    ("Mid", "bid_ask", "0.001500"),
    ("Mid", "impact", "0.001000"),
    ("Mid", "brokerage", "0.000300"),
    ("Mid", "slippage", "0.000500"),
    ("Large", "bid_ask", "0.000500"),
    ("Large", "impact", "0.000300"),
    ("Large", "brokerage", "0.000300"),
    ("Large", "slippage", "0.000200"),
)

FRICTION_SEED_EFFECTIVE_FROM = "2026-05-24"
FRICTION_SEED_NOTES = "placeholder; replace via Phase 0.5d friction model"

# ---------------------------------------------------------------------------
# Seed data — atlas_thresholds regime classifier rows.
# atlas_thresholds columns: threshold_key, threshold_value, category,
# description, methodology_section, units, min_allowed, max_allowed,
# default_value, last_modified_by, is_active.
# Values are placeholders; replaced by Phase 0.5h-prime sweep (#16).
# ---------------------------------------------------------------------------

# Tuple shape: (key, value, category, description, section, units, min, max, default)
REGIME_THRESHOLD_SEEDS: tuple[tuple[str, str, str, str, str, str, str, str, str], ...] = (
    (
        "regime.smallcap_rs_z.below_trend_threshold",
        "-1.000000",
        "regime",
        "Smallcap RS z-score below which regime moves to Below-Trend "
        "(placeholder; Phase 0.5h-prime sweep replaces this).",
        "regime",
        "z",
        "-5.000000",
        "0.000000",
        "-1.000000",
    ),
    (
        "regime.smallcap_rs_z.risk_off_threshold",
        "-2.000000",
        "regime",
        "Smallcap RS z-score below which regime moves to Risk-Off "
        "(placeholder; Phase 0.5h-prime sweep replaces this).",
        "regime",
        "z",
        "-5.000000",
        "0.000000",
        "-2.000000",
    ),
    (
        "regime.breadth.below_trend_threshold",
        "0.400000",
        "regime",
        "Breadth (% of stocks above 200dma) below which regime moves to "
        "Below-Trend (placeholder).",
        "regime",
        "pct",
        "0.000000",
        "1.000000",
        "0.400000",
    ),
    (
        "regime.breadth.risk_off_threshold",
        "0.200000",
        "regime",
        "Breadth (% of stocks above 200dma) below which regime moves to "
        "Risk-Off (placeholder).",
        "regime",
        "pct",
        "0.000000",
        "1.000000",
        "0.200000",
    ),
    (
        "regime.vix_pct.elevated_threshold",
        "0.700000",
        "regime",
        "VIX percentile above which regime moves to Elevated (placeholder).",
        "regime",
        "pct",
        "0.000000",
        "1.000000",
        "0.700000",
    ),
    (
        "regime.vix_pct.risk_off_threshold",
        "0.900000",
        "regime",
        "VIX percentile above which regime moves to Risk-Off (placeholder).",
        "regime",
        "pct",
        "0.000000",
        "1.000000",
        "0.900000",
    ),
    (
        "regime.dispersion.elevated_threshold",
        "0.020000",
        "regime",
        "Cross-sectional dispersion above which regime moves to Elevated "
        "(placeholder).",
        "regime",
        "ratio",
        "0.000000",
        "1.000000",
        "0.020000",
    ),
)


def upgrade() -> None:
    bind = op.get_bind()

    # -----------------------------------------------------------------
    # NEW enums — atlas_walkforward_status + atlas_friction_component.
    # -----------------------------------------------------------------
    postgresql.ENUM(
        *WALKFORWARD_STATUS, name="atlas_walkforward_status", schema=_SCHEMA
    ).create(bind, checkfirst=True)
    postgresql.ENUM(
        *FRICTION_COMPONENT, name="atlas_friction_component", schema=_SCHEMA
    ).create(bind, checkfirst=True)

    # Reused enums from 080 — create_type=False, do NOT re-create.
    tenure_enum = postgresql.ENUM(
        name="atlas_tenure", schema=_SCHEMA, create_type=False
    )
    cap_tier_enum = postgresql.ENUM(
        name="atlas_cap_tier", schema=_SCHEMA, create_type=False
    )

    # References to the NEW enums just created above.
    walkforward_status_enum = postgresql.ENUM(
        name="atlas_walkforward_status", schema=_SCHEMA, create_type=False
    )
    friction_component_enum = postgresql.ENUM(
        name="atlas_friction_component", schema=_SCHEMA, create_type=False
    )

    # -----------------------------------------------------------------
    # atlas_cell_walkforward_runs — write-once audit row per sweep.
    # -----------------------------------------------------------------
    op.create_table(
        "atlas_cell_walkforward_runs",
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "run_started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "run_completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        # Plain UUID for now — future atlas_universe_snapshot table will
        # be FK'd retroactively by a Phase 0.5a migration.
        sa.Column(
            "universe_snapshot_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("tenure", tenure_enum, nullable=False),
        # Nullable: a run may DISCOVER a new cell (and only insert into
        # atlas_cell_definitions afterwards). Re-validation of a known cell
        # populates this.
        sa.Column(
            "cell_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("window_train_start", sa.Date(), nullable=False),
        sa.Column("window_train_end", sa.Date(), nullable=False),
        sa.Column("window_test_start", sa.Date(), nullable=False),
        sa.Column("window_test_end", sa.Date(), nullable=False),
        # Confusion-matrix proportions (POSITIVE cells emit tp_rate;
        # NEGATIVE cells emit tn_rate). Both nullable while run is in
        # progress.
        sa.Column("tp_rate", sa.Numeric(5, 4), nullable=True),
        sa.Column("tn_rate", sa.Numeric(5, 4), nullable=True),
        sa.Column("median_excess", sa.Numeric(10, 6), nullable=True),
        sa.Column("mean_excess", sa.Numeric(10, 6), nullable=True),
        sa.Column("friction_adjusted_excess", sa.Numeric(10, 6), nullable=True),
        sa.Column("percentile_10", sa.Numeric(10, 6), nullable=True),
        sa.Column("percentile_25", sa.Numeric(10, 6), nullable=True),
        sa.Column("percentile_50", sa.Numeric(10, 6), nullable=True),
        sa.Column("percentile_75", sa.Numeric(10, 6), nullable=True),
        sa.Column("percentile_90", sa.Numeric(10, 6), nullable=True),
        sa.Column("n_observations", sa.Integer(), nullable=False),
        sa.Column("stable_features", postgresql.JSONB(), nullable=True),
        sa.Column(
            "methodology_lock_ref",
            sa.String(length=64),
            nullable=False,
            comment="SHA or date stamp of locking experiment",
        ),
        sa.Column(
            "provenance_log_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{_SCHEMA}.atlas_provenance_log.run_id",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column("status", walkforward_status_enum, nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        # CHECKs — catch malformed inputs at write time.
        sa.CheckConstraint(
            "window_train_end <= window_test_start",
            name="ck_atlas_cell_walkforward_runs_window_order",
        ),
        sa.CheckConstraint(
            "n_observations >= 0",
            name="ck_atlas_cell_walkforward_runs_n_observations_non_negative",
        ),
        sa.CheckConstraint(
            "tp_rate IS NULL OR (tp_rate >= 0 AND tp_rate <= 1)",
            name="ck_atlas_cell_walkforward_runs_tp_rate_range",
        ),
        sa.CheckConstraint(
            "tn_rate IS NULL OR (tn_rate >= 0 AND tn_rate <= 1)",
            name="ck_atlas_cell_walkforward_runs_tn_rate_range",
        ),
        schema=_SCHEMA,
    )

    # Indexes — per-cell history + recent-by-status + provenance lookup.
    op.create_index(
        "ix_atlas_cell_walkforward_runs_tenure_cell_started_desc",
        "atlas_cell_walkforward_runs",
        ["tenure", "cell_id", sa.text("run_started_at DESC")],
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_atlas_cell_walkforward_runs_cell_status",
        "atlas_cell_walkforward_runs",
        ["cell_id", "status"],
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_atlas_cell_walkforward_runs_provenance",
        "atlas_cell_walkforward_runs",
        ["provenance_log_id"],
        schema=_SCHEMA,
    )

    # -----------------------------------------------------------------
    # atlas_friction_params — per-tier × per-component append-only table.
    # -----------------------------------------------------------------
    op.create_table(
        "atlas_friction_params",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("cap_tier", cap_tier_enum, nullable=False),
        sa.Column("component", friction_component_enum, nullable=False),
        # Coefficient stored as Decimal — e.g., 0.001234 = 12.34 bps.
        sa.Column("value", sa.Numeric(8, 6), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_until", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "cap_tier",
            "component",
            "effective_from",
            name="uq_atlas_friction_params_tier_component_from",
        ),
        sa.CheckConstraint(
            "value >= 0",
            name="ck_atlas_friction_params_value_non_negative",
        ),
        sa.CheckConstraint(
            "effective_until IS NULL OR effective_until >= effective_from",
            name="ck_atlas_friction_params_effective_range",
        ),
        schema=_SCHEMA,
    )

    # Partial index — fast lookup of currently-effective rows.
    op.execute(
        f"""
        CREATE INDEX ix_atlas_friction_params_current
        ON {_SCHEMA}.atlas_friction_params (cap_tier, component)
        WHERE effective_until IS NULL
        """
    )

    # -----------------------------------------------------------------
    # Write-once-with-status-transition trigger on
    # atlas_cell_walkforward_runs.
    #
    # Allowed mutations:
    #   - INSERT (always).
    #   - UPDATE that:
    #       * transitions status from 'running' to one of
    #         'completed' / 'failed' / 'aborted', AND
    #       * sets run_completed_at from NULL to non-NULL when going
    #         to 'completed' (other terminal states may also stamp it),
    #       * may also populate the result columns (tp/tn rates,
    #         percentiles, etc.) in the same UPDATE.
    # Denied:
    #   - DELETE (audit immutability).
    #   - UPDATE that changes status away from a terminal state, or
    #     unsets run_completed_at, or mutates any window / metadata
    #     column after the row has been finalized.
    # -----------------------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION atlas.guard_walkforward_run_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION
                    'atlas_cell_walkforward_runs is write-once; DELETE not permitted';
            END IF;

            -- Reject un-setting run_completed_at (terminal -> running).
            IF OLD.run_completed_at IS NOT NULL
               AND NEW.run_completed_at IS NULL THEN
                RAISE EXCEPTION
                    'atlas_cell_walkforward_runs.run_completed_at is write-once; '
                    'cannot un-set after completion';
            END IF;

            -- Reject moves out of a terminal status back to running.
            IF OLD.status IN ('completed', 'failed', 'aborted')
               AND NEW.status = 'running' THEN
                RAISE EXCEPTION
                    'atlas_cell_walkforward_runs.status cannot transition '
                    'from terminal back to running (was=%, new=%)',
                    OLD.status, NEW.status;
            END IF;

            -- Once in a terminal state, immutable columns must not change.
            IF OLD.status IN ('completed', 'failed', 'aborted') THEN
                IF NEW.run_started_at      IS DISTINCT FROM OLD.run_started_at
                OR NEW.universe_snapshot_id IS DISTINCT FROM OLD.universe_snapshot_id
                OR NEW.tenure              IS DISTINCT FROM OLD.tenure
                OR NEW.window_train_start  IS DISTINCT FROM OLD.window_train_start
                OR NEW.window_train_end    IS DISTINCT FROM OLD.window_train_end
                OR NEW.window_test_start   IS DISTINCT FROM OLD.window_test_start
                OR NEW.window_test_end     IS DISTINCT FROM OLD.window_test_end
                OR NEW.methodology_lock_ref IS DISTINCT FROM OLD.methodology_lock_ref THEN
                    RAISE EXCEPTION
                        'atlas_cell_walkforward_runs is write-once after terminal '
                        'status; immutable column changed';
                END IF;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER guard_atlas_cell_walkforward_runs_mutation
        BEFORE UPDATE OR DELETE ON atlas.atlas_cell_walkforward_runs
        FOR EACH ROW EXECUTE FUNCTION atlas.guard_walkforward_run_mutation();
        """
    )

    # -----------------------------------------------------------------
    # Append-only trigger on atlas_friction_params.
    #
    # Allowed mutations:
    #   - INSERT (always).
    #   - UPDATE that only changes effective_until (from NULL to a
    #     concrete date) and optionally notes.
    # Denied:
    #   - DELETE.
    #   - UPDATE that changes cap_tier / component / value /
    #     effective_from / created_at — the row's identity is fixed at
    #     insert time.
    #   - UPDATE that un-sets effective_until back to NULL.
    # -----------------------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION atlas.guard_friction_params_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION
                    'atlas_friction_params is append-only; DELETE not permitted';
            END IF;

            IF NEW.cap_tier        IS DISTINCT FROM OLD.cap_tier
            OR NEW.component       IS DISTINCT FROM OLD.component
            OR NEW.value           IS DISTINCT FROM OLD.value
            OR NEW.effective_from  IS DISTINCT FROM OLD.effective_from
            OR NEW.created_at      IS DISTINCT FROM OLD.created_at THEN
                RAISE EXCEPTION
                    'atlas_friction_params is append-only; only effective_until '
                    '/ notes are mutable (column changed: cap_tier / component '
                    '/ value / effective_from / created_at)';
            END IF;

            IF OLD.effective_until IS NOT NULL
               AND NEW.effective_until IS NULL THEN
                RAISE EXCEPTION
                    'atlas_friction_params.effective_until cannot be un-set';
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER guard_atlas_friction_params_mutation
        BEFORE UPDATE OR DELETE ON atlas.atlas_friction_params
        FOR EACH ROW EXECUTE FUNCTION atlas.guard_friction_params_mutation();
        """
    )

    # -----------------------------------------------------------------
    # Retroactive FK — atlas_cell_definitions.walkforward_run_id.
    # Declared by 080 as a plain nullable UUID; FK added now that the
    # target exists. ondelete='SET NULL' so a walk-forward run can be
    # purged (separately) without cascading delete of the cell row.
    # -----------------------------------------------------------------
    op.create_foreign_key(
        "fk_atlas_cell_definitions_walkforward_run_id",
        "atlas_cell_definitions",
        "atlas_cell_walkforward_runs",
        ["walkforward_run_id"],
        ["run_id"],
        source_schema=_SCHEMA,
        referent_schema=_SCHEMA,
        ondelete="SET NULL",
    )

    # -----------------------------------------------------------------
    # Friction seed rows — 12 (3 tiers × 4 components).
    # Idempotent: UNIQUE (cap_tier, component, effective_from) drops
    # duplicate inserts on re-apply via ON CONFLICT DO NOTHING.
    # -----------------------------------------------------------------
    conn = op.get_bind()
    for cap_tier, component, value in FRICTION_SEEDS:
        conn.execute(
            sa.text(
                f"""
                INSERT INTO {_SCHEMA}.atlas_friction_params
                    (cap_tier, component, value, effective_from, effective_until, notes)
                VALUES
                    (:cap_tier, :component, :value, :effective_from, NULL, :notes)
                ON CONFLICT ON CONSTRAINT uq_atlas_friction_params_tier_component_from
                DO NOTHING
                """
            ),
            {
                "cap_tier": cap_tier,
                "component": component,
                "value": value,
                "effective_from": FRICTION_SEED_EFFECTIVE_FROM,
                "notes": FRICTION_SEED_NOTES,
            },
        )

    # -----------------------------------------------------------------
    # Regime threshold seed rows — 7 atlas_thresholds entries.
    # atlas_thresholds is pre-existing (migration 007); we INSERT ...
    # ON CONFLICT (threshold_key) DO NOTHING so re-applying is safe.
    # -----------------------------------------------------------------
    for (
        key,
        value,
        category,
        description,
        section,
        units,
        min_allowed,
        max_allowed,
        default_value,
    ) in REGIME_THRESHOLD_SEEDS:
        conn.execute(
            sa.text(
                f"""
                INSERT INTO {_SCHEMA}.atlas_thresholds (
                    threshold_key, threshold_value, category, description,
                    methodology_section, units, min_allowed, max_allowed,
                    default_value, last_modified_by, is_active
                ) VALUES (
                    :key, :value, :category, :description,
                    :section, :units, :min_allowed, :max_allowed,
                    :default_value, 'migration_081_z', TRUE
                )
                ON CONFLICT (threshold_key) DO NOTHING
                """
            ),
            {
                "key": key,
                "value": value,
                "category": category,
                "description": description,
                "section": section,
                "units": units,
                "min_allowed": min_allowed,
                "max_allowed": max_allowed,
                "default_value": default_value,
            },
        )


def downgrade() -> None:
    """Reverse upgrade. Drop order:

    1. Retroactive FK from atlas_cell_definitions (references the
       walkforward_runs table).
    2. Regime threshold seed rows.
    3. Triggers + plpgsql functions for both tables.
    4. Indexes on both tables.
    5. The two tables themselves (drops embedded FKs / CHECKs with them).
    6. The NEW enums owned by this migration.

    Reused enums (atlas_tenure, atlas_cap_tier) are owned by 080 and are
    NOT dropped here.
    """
    conn = op.get_bind()

    # 1. Drop retroactive FK first — it references atlas_cell_walkforward_runs.
    op.drop_constraint(
        "fk_atlas_cell_definitions_walkforward_run_id",
        "atlas_cell_definitions",
        type_="foreignkey",
        schema=_SCHEMA,
    )

    # 2. Drop regime threshold seeds (idempotent — only deletes our keys).
    seeded_keys = tuple(seed[0] for seed in REGIME_THRESHOLD_SEEDS)
    conn.execute(
        sa.text(
            f"DELETE FROM {_SCHEMA}.atlas_thresholds WHERE threshold_key = ANY(:keys)"
        ),
        {"keys": list(seeded_keys)},
    )

    # 3a. Drop triggers (must precede DROP FUNCTION).
    op.execute(
        "DROP TRIGGER IF EXISTS guard_atlas_cell_walkforward_runs_mutation "
        "ON atlas.atlas_cell_walkforward_runs;"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS guard_atlas_friction_params_mutation "
        "ON atlas.atlas_friction_params;"
    )

    # 3b. Drop plpgsql functions.
    op.execute(
        "DROP FUNCTION IF EXISTS atlas.guard_walkforward_run_mutation();"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS atlas.guard_friction_params_mutation();"
    )

    # 4. Drop indexes.
    op.execute(
        f"DROP INDEX IF EXISTS {_SCHEMA}.ix_atlas_friction_params_current"
    )
    op.drop_index(
        "ix_atlas_cell_walkforward_runs_provenance",
        "atlas_cell_walkforward_runs",
        schema=_SCHEMA,
    )
    op.drop_index(
        "ix_atlas_cell_walkforward_runs_cell_status",
        "atlas_cell_walkforward_runs",
        schema=_SCHEMA,
    )
    op.drop_index(
        "ix_atlas_cell_walkforward_runs_tenure_cell_started_desc",
        "atlas_cell_walkforward_runs",
        schema=_SCHEMA,
    )

    # 5. Drop tables.
    op.drop_table("atlas_friction_params", schema=_SCHEMA)
    op.drop_table("atlas_cell_walkforward_runs", schema=_SCHEMA)

    # 6. Drop NEW enums owned by this migration. Do NOT drop atlas_tenure
    # or atlas_cap_tier — owned by 080.
    bind = op.get_bind()
    postgresql.ENUM(name="atlas_friction_component", schema=_SCHEMA).drop(
        bind, checkfirst=True
    )
    postgresql.ENUM(name="atlas_walkforward_status", schema=_SCHEMA).drop(
        bind, checkfirst=True
    )
