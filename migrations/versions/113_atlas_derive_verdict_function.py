"""v6 — atlas.derive_verdict() SQL function (Stream C verdict composition).

Atlas verdict composer per spec §4 of
docs/superpowers/specs/2026-05-28-trader-view-redesign.html.

Mirrors the Python module atlas.verdict.derive — see commit 64a996f1 for the
byte-for-byte parity smoke test at scripts/verdict/verify_sql_matches_python.sql.

Inputs:
  p_cell_state    text     — 'POSITIVE' / 'NEUTRAL' / 'NEGATIVE'
  p_weinstein     int      — 1, 2, 3, 4, or NULL
  p_user_owns     boolean
  p_cap_tier      text     — 'Large' / 'Mid' / 'Small' / 'Micro'
                              (Q5 spec lock: Micro bypasses Weinstein veto)
  p_gate_strength boolean  — 5 gate booleans
  p_gate_direction boolean
  p_gate_risk      boolean
  p_gate_sector    boolean
  p_gate_market    boolean

Output:
  verdict text  — 'BUY' / 'ACCUMULATE' / 'WATCH' / 'HOLD' / 'AVOID' / 'SELL' / 'WAIT'
  reason  text  — NULL or a one-line explanation (e.g. 'Stage 4 vetoes positive cell',
                  'Risk gate fail', 'Stage 3 topping')

Vocabulary canon: CONTEXT.md §"Cell state vocabulary" (lines 509-547).

Note: the function body was already executed against Supabase by the Stream C
agent via mcp execute_sql; this migration documents the create in the alembic
chain. CREATE OR REPLACE makes re-application idempotent and safe.

Revision ID: 113
Revises: 112
Create Date: 2026-05-28 IST
"""

from alembic import op

revision = "113"
down_revision = "112"
branch_labels = None
depends_on = None


_CREATE_FUNCTION = """
CREATE OR REPLACE FUNCTION atlas.derive_verdict(
    p_cell_state    text,
    p_weinstein     int,
    p_user_owns     boolean,
    p_cap_tier      text,
    p_gate_strength boolean,
    p_gate_direction boolean,
    p_gate_risk      boolean,
    p_gate_sector    boolean,
    p_gate_market    boolean
) RETURNS TABLE(verdict text, reason text)
LANGUAGE plpgsql IMMUTABLE
AS $$
BEGIN
    -- 1. NEGATIVE cells — ownership decides verb
    IF p_cell_state = 'NEGATIVE' THEN
        RETURN QUERY SELECT
            CASE WHEN p_user_owns THEN 'SELL' ELSE 'AVOID' END,
            NULL::text;
        RETURN;
    END IF;

    -- 2. NEUTRAL cells — holding pattern
    IF p_cell_state = 'NEUTRAL' THEN
        RETURN QUERY SELECT
            CASE WHEN p_user_owns THEN 'HOLD' ELSE 'WATCH' END,
            NULL::text;
        RETURN;
    END IF;

    -- 3a. Weinstein Stage 4 veto (Micro exempt per Q5 spec lock)
    IF p_cap_tier != 'Micro' AND p_weinstein = 4 THEN
        RETURN QUERY SELECT 'WAIT', 'Stage 4 vetoes positive cell';
        RETURN;
    END IF;

    -- 3b. Gate vetoes — named failing gate, not just "veto"
    IF p_gate_strength  = false THEN RETURN QUERY SELECT 'WAIT', 'Strength gate fail';  RETURN; END IF;
    IF p_gate_direction = false THEN RETURN QUERY SELECT 'WAIT', 'Direction gate fail'; RETURN; END IF;
    IF p_gate_risk      = false THEN RETURN QUERY SELECT 'WAIT', 'Risk gate fail';      RETURN; END IF;
    IF p_gate_sector    = false THEN RETURN QUERY SELECT 'WAIT', 'Sector gate fail';    RETURN; END IF;
    IF p_gate_market    = false THEN RETURN QUERY SELECT 'WAIT', 'Market gate fail';    RETURN; END IF;

    -- 3c. Stage 3 ambiguity — downgrade to WATCH/HOLD (Q1 spec lock — never WAIT)
    IF p_cap_tier != 'Micro' AND p_weinstein = 3 THEN
        RETURN QUERY SELECT
            CASE WHEN p_user_owns THEN 'HOLD' ELSE 'WATCH' END,
            'Stage 3 topping';
        RETURN;
    END IF;

    -- 3d. Clear path — POSITIVE cell, no veto, Stage 1/2/NULL
    RETURN QUERY SELECT
        CASE WHEN p_user_owns THEN 'ACCUMULATE' ELSE 'BUY' END,
        NULL::text;
END;
$$;
"""

_DROP_FUNCTION = """
DROP FUNCTION IF EXISTS atlas.derive_verdict(text, int, boolean, text, boolean, boolean, boolean, boolean, boolean);
"""


def upgrade() -> None:
    op.execute(_CREATE_FUNCTION)


def downgrade() -> None:
    op.execute(_DROP_FUNCTION)
