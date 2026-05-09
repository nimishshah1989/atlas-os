"""M15 — strategy_configs audit trigger (is_fm_authored column + history table).

Revision ID: 025
Revises: 024
Create Date: 2026-05-10 06:00:00.000000

Changes:
  - ADD COLUMN atlas.strategy_configs.is_fm_authored BOOLEAN NOT NULL DEFAULT FALSE
  - ADD COLUMN atlas.strategy_configs.created_by VARCHAR(64)
  - CREATE INDEX idx_strategy_configs_fm_authored (partial, FM rows only)
  - CREATE TABLE atlas.atlas_strategy_history — per-update audit log
  - CREATE FUNCTION atlas.fn_strategy_audit — fires when config OR is_active changes
  - CREATE TRIGGER trg_strategy_audit AFTER UPDATE ON atlas.strategy_configs

Audit pattern parallel to migration 024 (atlas_decision_policy_history).
The trigger reads the optional change reason from the session GUC
``atlas.change_reason`` via ``current_setting('atlas.change_reason', true)``
— the ``, true`` arg returns NULL when the GUC is unset instead of raising.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# DDL — ALTER TABLE
# ---------------------------------------------------------------------------

_ADD_IS_FM_AUTHORED_SQL = """\
ALTER TABLE atlas.strategy_configs
    ADD COLUMN IF NOT EXISTS is_fm_authored BOOLEAN NOT NULL DEFAULT FALSE;
"""

_ADD_CREATED_BY_SQL = """\
ALTER TABLE atlas.strategy_configs
    ADD COLUMN IF NOT EXISTS created_by VARCHAR(64);
"""

_CREATE_FM_AUTHORED_INDEX_SQL = """\
CREATE INDEX IF NOT EXISTS idx_strategy_configs_fm_authored
    ON atlas.strategy_configs (is_fm_authored, created_at DESC)
    WHERE is_fm_authored = TRUE;
"""

# ---------------------------------------------------------------------------
# DDL — history table
# ---------------------------------------------------------------------------

_CREATE_HISTORY_TABLE_SQL = """\
CREATE TABLE IF NOT EXISTS atlas.atlas_strategy_history (
    id             SERIAL       PRIMARY KEY,
    strategy_id    UUID         NOT NULL REFERENCES atlas.strategy_configs(id),
    old_config     JSONB,
    new_config     JSONB,
    old_is_active  BOOLEAN,
    new_is_active  BOOLEAN,
    changed_by     VARCHAR(64),
    changed_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    change_reason  TEXT,
    user_ip        INET,
    user_agent     TEXT
);
"""

_CREATE_HISTORY_INDEX_SQL = """\
CREATE INDEX IF NOT EXISTS idx_atlas_strategy_history_strategy_id
    ON atlas.atlas_strategy_history (strategy_id, changed_at DESC);
"""

# ---------------------------------------------------------------------------
# Trigger function
# Fires only when config OR is_active changes (not on every UPDATE).
# ---------------------------------------------------------------------------

_CREATE_FUNCTION_SQL = """\
CREATE OR REPLACE FUNCTION atlas.fn_strategy_audit() RETURNS TRIGGER AS $$
DECLARE
    v_reason TEXT;
BEGIN
    IF (OLD.config IS DISTINCT FROM NEW.config)
        OR (OLD.is_active IS DISTINCT FROM NEW.is_active) THEN
        v_reason := current_setting('atlas.change_reason', true);
        INSERT INTO atlas.atlas_strategy_history (
            strategy_id,
            old_config, new_config,
            old_is_active, new_is_active,
            changed_by, change_reason
        ) VALUES (
            NEW.id,
            OLD.config, NEW.config,
            OLD.is_active, NEW.is_active,
            NEW.created_by, v_reason
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

_DROP_TRIGGER_SQL = """\
DROP TRIGGER IF EXISTS trg_strategy_audit ON atlas.strategy_configs;
"""

_CREATE_TRIGGER_SQL = """\
CREATE TRIGGER trg_strategy_audit
    AFTER UPDATE ON atlas.strategy_configs
    FOR EACH ROW EXECUTE FUNCTION atlas.fn_strategy_audit();
"""

_DROP_FUNCTION_SQL = """\
DROP FUNCTION IF EXISTS atlas.fn_strategy_audit();
"""

# ---------------------------------------------------------------------------
# Downgrade DDL
# ---------------------------------------------------------------------------

_DROP_FM_AUTHORED_INDEX_SQL = """\
DROP INDEX IF EXISTS atlas.idx_strategy_configs_fm_authored;
"""

_DROP_HISTORY_TABLE_SQL = """\
DROP TABLE IF EXISTS atlas.atlas_strategy_history;
"""


# ---------------------------------------------------------------------------
# Upgrade / downgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    # 1. Add columns to strategy_configs
    op.execute(sa.text(_ADD_IS_FM_AUTHORED_SQL))
    op.execute(sa.text(_ADD_CREATED_BY_SQL))
    # 2. Partial index for FM-authored rows
    op.execute(sa.text(_CREATE_FM_AUTHORED_INDEX_SQL))
    # 3. Create history table + index
    op.execute(sa.text(_CREATE_HISTORY_TABLE_SQL))
    op.execute(sa.text(_CREATE_HISTORY_INDEX_SQL))
    # 4. Create trigger function (CREATE OR REPLACE — idempotent)
    op.execute(sa.text(_CREATE_FUNCTION_SQL))
    # 5. Create trigger (drop-then-create — no CREATE OR REPLACE TRIGGER in PG<14)
    op.execute(sa.text(_DROP_TRIGGER_SQL))
    op.execute(sa.text(_CREATE_TRIGGER_SQL))


def downgrade() -> None:
    # Reverse order: trigger → function → history table + index → partial index → columns
    op.execute(sa.text(_DROP_TRIGGER_SQL))
    op.execute(sa.text(_DROP_FUNCTION_SQL))
    op.execute(sa.text(_DROP_HISTORY_TABLE_SQL))
    op.execute(sa.text(_DROP_FM_AUTHORED_INDEX_SQL))
    op.execute(
        sa.text("ALTER TABLE atlas.strategy_configs DROP COLUMN IF EXISTS created_by;")
    )
    op.execute(
        sa.text(
            "ALTER TABLE atlas.strategy_configs DROP COLUMN IF EXISTS is_fm_authored;"
        )
    )
