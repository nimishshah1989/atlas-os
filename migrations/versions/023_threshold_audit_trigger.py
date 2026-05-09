"""add AFTER UPDATE trigger to atlas_thresholds for audit history

Revision ID: 023
Revises: 022
Create Date: 2026-05-09 05:00:00.000000

Creates ``atlas.fn_threshold_audit`` PL/pgSQL function and the
``trg_threshold_audit`` trigger on ``atlas.atlas_thresholds``.

When a row's ``threshold_value`` changes, the trigger inserts a row into
``atlas.atlas_threshold_history`` capturing old/new values, the modifier
(``NEW.last_modified_by``), and the optional change reason read from the
session GUC ``atlas.change_reason``.

The GUC is read via ``current_setting('atlas.change_reason', true)`` — the
second argument ``true`` causes it to return NULL if the GUC is not set in
the current session, rather than raising an error.  The calling Server Action
sets it inside a transaction via ``SET LOCAL atlas.change_reason = $1`` before
the UPDATE.

Idempotent:
- ``CREATE OR REPLACE FUNCTION`` on the function.
- ``DROP TRIGGER IF EXISTS`` before ``CREATE TRIGGER`` (Postgres has no
  ``CREATE OR REPLACE TRIGGER`` syntax prior to PG 14, and we want broad
  compatibility).
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None

_CREATE_FUNCTION_SQL = """\
CREATE OR REPLACE FUNCTION atlas.fn_threshold_audit() RETURNS TRIGGER AS $$
DECLARE
  v_reason TEXT;
BEGIN
  IF OLD.threshold_value IS DISTINCT FROM NEW.threshold_value THEN
    v_reason := current_setting('atlas.change_reason', true);
    INSERT INTO atlas.atlas_threshold_history (
      threshold_key, old_value, new_value, changed_by, change_reason
    ) VALUES (
      NEW.threshold_key, OLD.threshold_value, NEW.threshold_value,
      NEW.last_modified_by, v_reason
    );
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

_DROP_TRIGGER_SQL = """\
DROP TRIGGER IF EXISTS trg_threshold_audit ON atlas.atlas_thresholds;
"""

_CREATE_TRIGGER_SQL = """\
CREATE TRIGGER trg_threshold_audit
AFTER UPDATE ON atlas.atlas_thresholds
FOR EACH ROW EXECUTE FUNCTION atlas.fn_threshold_audit();
"""

_DROP_TRIGGER_DOWN_SQL = """\
DROP TRIGGER IF EXISTS trg_threshold_audit ON atlas.atlas_thresholds;
"""

_DROP_FUNCTION_SQL = """\
DROP FUNCTION IF EXISTS atlas.fn_threshold_audit();
"""


def upgrade() -> None:
    op.execute(sa.text(_CREATE_FUNCTION_SQL))
    # Postgres has no CREATE OR REPLACE TRIGGER; drop-then-create is idempotent.
    op.execute(sa.text(_DROP_TRIGGER_SQL))
    op.execute(sa.text(_CREATE_TRIGGER_SQL))


def downgrade() -> None:
    op.execute(sa.text(_DROP_TRIGGER_DOWN_SQL))
    op.execute(sa.text(_DROP_FUNCTION_SQL))
