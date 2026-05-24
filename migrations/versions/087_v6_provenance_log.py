"""v6 — atlas_provenance_log + retroactive FKs (R9 data lineage).

Adds the write-once data-lineage log per CONTEXT.md "Data lineage +
provenance" section (post-adversarial review G1 + P3). One row per
walk-forward run, cell validation, drift event, feature compute,
inference, or brief generation — records the exact inputs (dataset
SHA256 + universe SHA256), the code commit, the friction parameter
row ids, and the output row range. This makes every produced row
traceable back to the exact code + data + universe that produced it.

Tables
------
- ``atlas_provenance_log`` — write-once lineage log. UPDATE and
  DELETE are denied by a plpgsql trigger; the only valid mutation is
  INSERT. Indexed by (ts DESC), (output_table, ts DESC) and
  (run_type, ts DESC) for the common audit queries.

Retroactive FK additions
------------------------
Earlier migrations declared ``provenance_log_id`` as a plain nullable
UUID column with no FK target, because the target table did not yet
exist. This migration adds the FK constraint NOW that the target
exists. Tables FK'd in this migration:

- ``atlas_ledger`` (column added by 083) — FK target
  ``atlas_provenance_log.run_id`` ON DELETE SET NULL.
- ``atlas_macro_features_daily`` (column added by 086) — FK target
  ``atlas_provenance_log.run_id`` ON DELETE SET NULL.

Tables that do NOT yet have ``provenance_log_id`` (verified by
reading 080, 082, 084, 085 — column not present):

- ``atlas_scorecard_daily``         (080) — no column; needs a follow-up
- ``atlas_signal_calls``            (080) — no column; needs a follow-up
- ``atlas_brief_cache``             (082) — provenance lives in row-level
                                            attribution; deferred
- ``atlas_paper_portfolio``         (084) — no column; needs a follow-up
- ``atlas_user_lots``               (084) — no column; needs a follow-up
- ``atlas_etf_*``                   (085) — no column; needs a follow-up
- ``atlas_mf_*``                    (085) — no column; needs a follow-up
- ``atlas_macro_recommendation_daily`` (086) — no column; needs a follow-up

Each of these can be wired in a later migration by ALTER TABLE ADD
COLUMN + ADD CONSTRAINT once the writer code that populates the column
ships.

Write-once enforcement
----------------------
A plpgsql trigger function ``atlas.deny_update_delete_provenance()``
raises an exception on any UPDATE or DELETE. The trigger fires BEFORE
UPDATE OR DELETE on each row, so the operation is rejected before any
write side-effect. INSERTs are the only valid mutation. This protects
the audit trail against accidental or malicious tampering at the SQL
layer — separate ROLE-level grants (handled outside this migration)
provide the second line of defense.

CHECK constraints
-----------------
- ``input_dataset_sha256`` and ``universe_definition_sha256`` are
  enforced as 64-character lowercase-hex strings (CHAR(64)) via a
  regex CHECK. Catches bad upstream hashing at write time.
- ``code_commit_sha`` is required to be non-empty.

Friction params reference
-------------------------
``friction_params_row_ids`` is JSONB and intentionally NOT FK'd at the
column level — the friction_params table lives in migration 081 which
is reserved for a parallel workstream and has not yet shipped. The
JSONB is shaped as ``[<uuid>, <uuid>, ...]``. When 081 lands the
writer code is expected to validate each id exists.

Migration chain
---------------
    080 (foundation) -> 082 (brief_cache)
                     -> 083 (ledger)
                     -> 084 (paper_portfolio + user_lots)
                     -> 085 (ETF + MF)
                     -> 086 (macro overlay)
                     -> 087 (provenance log — this migration)

081 (friction params / cell walkforward runs) is tracked separately
and may land out of order. 087 does NOT depend on 081.

Revision ID: 087
Revises: 086
Create Date: 2026-05-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "087"
down_revision = "086"
branch_labels = None
depends_on = None

_SCHEMA = "atlas"

# Tables retroactively FK'd to atlas_provenance_log.run_id in this
# migration. Each tuple is (table_name, column_name). Keep this list
# narrow and explicit — only tables whose provenance_log_id column was
# already created by a prior migration belong here.
_RETRO_FK_TABLES: tuple[tuple[str, str], ...] = (
    ("atlas_ledger", "provenance_log_id"),
    ("atlas_macro_features_daily", "provenance_log_id"),
)


def _fk_name(table: str, column: str) -> str:
    return f"fk_{table}_{column}"


def upgrade() -> None:
    # -----------------------------------------------------------------
    # atlas_provenance_log — write-once lineage log.
    # -----------------------------------------------------------------
    op.create_table(
        "atlas_provenance_log",
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        # 64-char lowercase hex (SHA-256). Enforced as CHAR(64) + regex
        # CHECK below — catches malformed hashes at write time.
        sa.Column("input_dataset_sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("universe_definition_sha256", sa.CHAR(length=64), nullable=False),
        # Git commit SHA at execution time. Length 40 to fit a full SHA-1;
        # short SHAs are tolerated but discouraged.
        sa.Column("code_commit_sha", sa.String(length=40), nullable=False),
        # JSONB array of friction_params row UUIDs. No FK at the column
        # level because the target table lives in migration 081 which
        # has not yet shipped. Writers should validate ids out-of-band
        # until 081 lands and a follow-up migration tightens this.
        sa.Column("friction_params_row_ids", postgresql.JSONB(), nullable=True),
        # Name of the table this run wrote to. e.g. 'atlas_signal_calls'.
        sa.Column("output_table", sa.String(length=64), nullable=False),
        # Shape: {"min_id": "<uuid>", "max_id": "<uuid>", "count": N,
        #          "date_range": [...]}. Stored as JSONB so the shape
        # can evolve without a schema change.
        sa.Column("output_row_range", postgresql.JSONB(), nullable=False),
        # One of: 'walk_forward', 'cell_validation', 'drift_event',
        # 'feature_compute', 'inference', 'brief_generation'. Kept as
        # a free-form string to avoid a schema change every time the
        # set of run types grows.
        sa.Column("run_type", sa.String(length=32), nullable=False),
        sa.Column(
            "actor",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("'system'"),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        # CHECKs — catch malformed hashes + empty commit SHA at write time.
        sa.CheckConstraint(
            "input_dataset_sha256 ~ '^[a-f0-9]{64}$'",
            name="ck_atlas_provenance_log_input_dataset_sha256_hex",
        ),
        sa.CheckConstraint(
            "universe_definition_sha256 ~ '^[a-f0-9]{64}$'",
            name="ck_atlas_provenance_log_universe_definition_sha256_hex",
        ),
        sa.CheckConstraint(
            "length(code_commit_sha) > 0",
            name="ck_atlas_provenance_log_code_commit_sha_non_empty",
        ),
        schema=_SCHEMA,
    )

    # Indexes — chronological + per-table + per-run-type queries.
    op.create_index(
        "ix_atlas_provenance_log_ts_desc",
        "atlas_provenance_log",
        [sa.text("ts DESC")],
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_atlas_provenance_log_output_table_ts_desc",
        "atlas_provenance_log",
        ["output_table", sa.text("ts DESC")],
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_atlas_provenance_log_run_type_ts_desc",
        "atlas_provenance_log",
        ["run_type", sa.text("ts DESC")],
        schema=_SCHEMA,
    )

    # -----------------------------------------------------------------
    # Write-once enforcement — plpgsql trigger denying UPDATE + DELETE.
    # -----------------------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION atlas.deny_update_delete_provenance()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION
                'atlas_provenance_log is write-once; UPDATE/DELETE not permitted (tg_op=%)',
                TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER deny_update_delete_atlas_provenance_log
        BEFORE UPDATE OR DELETE ON atlas.atlas_provenance_log
        FOR EACH ROW EXECUTE FUNCTION atlas.deny_update_delete_provenance();
        """
    )

    # -----------------------------------------------------------------
    # Retroactive FK constraints — only on tables whose
    # provenance_log_id column was created by a prior migration.
    # ondelete='SET NULL' so a provenance row can be purged
    # (separately, by superuser) without cascading delete of the
    # downstream data rows it produced.
    # -----------------------------------------------------------------
    for table_name, column_name in _RETRO_FK_TABLES:
        op.create_foreign_key(
            _fk_name(table_name, column_name),
            table_name,
            "atlas_provenance_log",
            [column_name],
            ["run_id"],
            source_schema=_SCHEMA,
            referent_schema=_SCHEMA,
            ondelete="SET NULL",
        )


def downgrade() -> None:
    """Reverse upgrade. Drop order:

    1. Retroactive FK constraints first — they reference the target
       table, so they must go before the trigger / function / table.
    2. Trigger on the target table.
    3. plpgsql function backing the trigger.
    4. Named indexes.
    5. The atlas_provenance_log table itself.
    """
    # 1. Drop retroactive FKs first.
    for table_name, column_name in _RETRO_FK_TABLES:
        op.drop_constraint(
            _fk_name(table_name, column_name),
            table_name,
            type_="foreignkey",
            schema=_SCHEMA,
        )

    # 2. Drop trigger on atlas_provenance_log.
    op.execute(
        "DROP TRIGGER IF EXISTS deny_update_delete_atlas_provenance_log "
        "ON atlas.atlas_provenance_log;"
    )

    # 3. Drop plpgsql function.
    op.execute("DROP FUNCTION IF EXISTS atlas.deny_update_delete_provenance();")

    # 4. Drop indexes.
    op.drop_index(
        "ix_atlas_provenance_log_run_type_ts_desc",
        "atlas_provenance_log",
        schema=_SCHEMA,
    )
    op.drop_index(
        "ix_atlas_provenance_log_output_table_ts_desc",
        "atlas_provenance_log",
        schema=_SCHEMA,
    )
    op.drop_index(
        "ix_atlas_provenance_log_ts_desc",
        "atlas_provenance_log",
        schema=_SCHEMA,
    )

    # 5. Drop the table.
    op.drop_table("atlas_provenance_log", schema=_SCHEMA)
