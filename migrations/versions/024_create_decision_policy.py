"""Create atlas_decision_policy table, audit trigger, and seed rows.

Revision ID: 024
Revises: 023
Create Date: 2026-05-09 06:00:00.000000

Creates two tables:
  - ``atlas.atlas_decision_policy`` — FM-tunable gate policies and multiplier maps
  - ``atlas.atlas_decision_policy_history`` — audit log of every value change

Creates ``atlas.fn_decision_policy_audit`` PL/pgSQL trigger function and the
``trg_decision_policy_audit`` AFTER UPDATE trigger (parallel to M13's
``fn_threshold_audit`` / ``trg_threshold_audit``).

When a row's ``policy_value`` changes, the trigger inserts a row into
``atlas.atlas_decision_policy_history`` capturing old/new values, the modifier
(``NEW.last_modified_by``), and the optional change reason read from the
session GUC ``atlas.change_reason``.

The GUC is read via ``current_setting('atlas.change_reason', true)`` — the
second argument ``true`` causes it to return NULL if the GUC is not set in
the current session, rather than raising an error.  The calling Server Action
sets it inside a transaction via ``SET LOCAL atlas.change_reason = $1`` before
the UPDATE.

Seed rows (idempotent via ON CONFLICT DO NOTHING):
  - 6 stock gate policies  (gate_states)
  - 2 ETF gate policies    (gate_states)
  - 2 fund gate policies   (gate_states)
  - 2 multiplier maps      (multiplier_map)

Idempotent:
- ``CREATE TABLE IF NOT EXISTS`` for both tables.
- ``CREATE OR REPLACE FUNCTION`` on the trigger function.
- ``DROP TRIGGER IF EXISTS`` before ``CREATE TRIGGER`` (Postgres has no
  ``CREATE OR REPLACE TRIGGER`` syntax prior to PG 14).
- ``INSERT ... ON CONFLICT (policy_key) DO NOTHING`` for seed rows.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# Table DDL
# ---------------------------------------------------------------------------

_CREATE_POLICY_TABLE_SQL = """\
CREATE TABLE IF NOT EXISTS atlas.atlas_decision_policy (
    policy_key          VARCHAR(64)  NOT NULL PRIMARY KEY,
    policy_kind         VARCHAR(16)  NOT NULL,
    policy_value        JSONB        NOT NULL,
    description         TEXT         NOT NULL,
    methodology_section VARCHAR(16),
    last_modified_by    VARCHAR(64)  NOT NULL DEFAULT 'system',
    last_modified_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    is_active           BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_policy_kind CHECK (policy_kind IN ('gate_states', 'multiplier_map'))
);
"""

_CREATE_POLICY_INDEX_SQL = """\
CREATE INDEX IF NOT EXISTS idx_decision_policy_kind
    ON atlas.atlas_decision_policy (policy_kind) WHERE is_active = TRUE;
"""

_CREATE_HISTORY_TABLE_SQL = """\
CREATE TABLE IF NOT EXISTS atlas.atlas_decision_policy_history (
    id                   SERIAL       PRIMARY KEY,
    policy_key           VARCHAR(64)  NOT NULL REFERENCES atlas.atlas_decision_policy(policy_key),
    old_value            JSONB,
    new_value            JSONB        NOT NULL,
    changed_by           VARCHAR(64)  NOT NULL,
    changed_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    change_reason        TEXT,
    triggered_reclassify BOOLEAN      NOT NULL DEFAULT FALSE,
    reclassify_run_id    UUID,
    user_ip              INET,
    user_agent           TEXT
);
"""

_CREATE_HISTORY_INDEX_SQL = """\
CREATE INDEX IF NOT EXISTS idx_decision_policy_history_key
    ON atlas.atlas_decision_policy_history (policy_key, changed_at DESC);
"""

# ---------------------------------------------------------------------------
# Trigger function (parallel to fn_threshold_audit from migration 023)
# ---------------------------------------------------------------------------

_CREATE_FUNCTION_SQL = """\
CREATE OR REPLACE FUNCTION atlas.fn_decision_policy_audit() RETURNS TRIGGER AS $$
DECLARE
    v_reason TEXT;
BEGIN
    IF OLD.policy_value IS DISTINCT FROM NEW.policy_value THEN
        v_reason := current_setting('atlas.change_reason', true);
        INSERT INTO atlas.atlas_decision_policy_history (
            policy_key, old_value, new_value, changed_by, change_reason
        ) VALUES (
            NEW.policy_key, OLD.policy_value, NEW.policy_value,
            NEW.last_modified_by, v_reason
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

_DROP_TRIGGER_SQL = """\
DROP TRIGGER IF EXISTS trg_decision_policy_audit ON atlas.atlas_decision_policy;
"""

_CREATE_TRIGGER_SQL = """\
CREATE TRIGGER trg_decision_policy_audit
    AFTER UPDATE ON atlas.atlas_decision_policy
    FOR EACH ROW EXECUTE FUNCTION atlas.fn_decision_policy_audit();
"""

_DROP_FUNCTION_SQL = """\
DROP FUNCTION IF EXISTS atlas.fn_decision_policy_audit();
"""

# ---------------------------------------------------------------------------
# Seed rows — current code defaults extracted from decisions_stock/etf/fund.py
# (key, kind, value_json, description, methodology_section)
# ---------------------------------------------------------------------------

_SEEDS: tuple[tuple[str, str, str, str, str], ...] = (
    # Stock gate policies (gate_states) — §13.1-13.4, §11.4, §10
    (
        "strength_gate_stock",
        "gate_states",
        '["Leader","Strong","Emerging"]',
        "Stock RS states that pass the strength gate",
        "13.1",
    ),
    (
        "direction_gate_stock",
        "gate_states",
        '["Accelerating","Improving"]',
        "Stock momentum states that pass the direction gate",
        "13.2",
    ),
    (
        "risk_gate_stock",
        "gate_states",
        '["Low","Normal"]',
        "Stock risk states that pass the risk gate",
        "13.3",
    ),
    (
        "volume_gate_stock",
        "gate_states",
        '["Accumulation","Steady-Buying"]',
        "Stock volume states that pass the volume gate",
        "13.4",
    ),
    (
        "sector_gate_stock",
        "gate_states",
        '["Overweight","Neutral"]',
        "Sector states that pass the sector gate (used by stock investability)",
        "11.4",
    ),
    (
        "market_gate",
        "gate_states",
        '["Risk-On","Constructive","Cautious"]',
        "Regime states that pass the market gate (Risk-Off blocks investability)",
        "10",
    ),
    # ETF gate policies (gate_states) — §13.5
    (
        "strength_gate_etf",
        "gate_states",
        '["Leader","Strong","Consolidating","Emerging"]',
        "ETF RS states that pass the strength gate",
        "13.5",
    ),
    (
        "direction_gate_etf",
        "gate_states",
        '["Accelerating","Improving"]',
        "ETF momentum states that pass the direction gate",
        "13.5",
    ),
    # Fund gate policies (gate_states) — §13.6
    (
        "nav_strong_states_fund",
        "gate_states",
        '["Leader NAV","Strong NAV"]',
        "Fund NAV states considered strong (Recommended/Hold tier)",
        "13.6",
    ),
    (
        "nav_positive_states_fund",
        "gate_states",
        '["Leader NAV","Strong NAV","Average NAV","Emerging NAV"]',
        "Fund NAV states allowing investability",
        "13.6",
    ),
    # Multiplier maps (multiplier_map) — §13.3, §10
    (
        "risk_multipliers_stock",
        "multiplier_map",
        '{"Low":1.2,"Normal":1.0,"Elevated":0.6,"High":0.0,"Below Trend":0.0}',
        "Position-size multiplier per stock risk_state",
        "13.3",
    ),
    (
        "market_multipliers",
        "multiplier_map",
        '{"Risk-On":1.0,"Constructive":0.7,"Cautious":0.4,"Risk-Off":0.0}',
        "Deployment multiplier per regime_state",
        "10",
    ),
)

_SEED_SQL = """\
INSERT INTO atlas.atlas_decision_policy (
    policy_key, policy_kind, policy_value, description,
    methodology_section, last_modified_by, is_active
) VALUES (
    :key, :kind, CAST(:value AS jsonb), :description,
    :section, 'migration_024', TRUE
)
ON CONFLICT (policy_key) DO NOTHING
"""


def _build_seed_stmt(
    key: str, kind: str, value_json: str, description: str, section: str | None
) -> "sa.TextClause":
    """Bind-param the seed INSERT so JSON colons don't trip psycopg2's % parser.

    Earlier f-string approach broke at runtime: a JSON value like
    ``{"Low":1.2,...}`` contains ``:`` which psycopg2 treats as a parameter
    prefix when fed as a literal SQL string. SQLAlchemy's bindparams resolves
    the format mismatch by passing values through the DBAPI's escape path.
    """
    return sa.text(_SEED_SQL).bindparams(
        key=key,
        kind=kind,
        value=value_json,
        description=description,
        section=section,
    )


# ---------------------------------------------------------------------------
# Upgrade / downgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    # 1. Create policy table + index
    op.execute(sa.text(_CREATE_POLICY_TABLE_SQL))
    op.execute(sa.text(_CREATE_POLICY_INDEX_SQL))
    # 2. Create history table + index
    op.execute(sa.text(_CREATE_HISTORY_TABLE_SQL))
    op.execute(sa.text(_CREATE_HISTORY_INDEX_SQL))
    # 3. Create trigger function
    op.execute(sa.text(_CREATE_FUNCTION_SQL))
    # 4. Create trigger (drop-then-create, idempotent)
    op.execute(sa.text(_DROP_TRIGGER_SQL))
    op.execute(sa.text(_CREATE_TRIGGER_SQL))
    # 5. Seed rows (idempotent). Bind-param values so JSON colons don't trip
    # psycopg2's `%` parameter parser when the literal hits the wire.
    for key, kind, value_json, description, section in _SEEDS:
        op.execute(_build_seed_stmt(key, kind, value_json, description, section))


def downgrade() -> None:
    # Reverse order: trigger → function → history table → policy table
    op.execute(sa.text(_DROP_TRIGGER_SQL))
    op.execute(sa.text(_DROP_FUNCTION_SQL))
    op.execute(
        sa.text("DROP TABLE IF EXISTS atlas.atlas_decision_policy_history;")
    )
    op.execute(
        sa.text("DROP TABLE IF EXISTS atlas.atlas_decision_policy;")
    )
