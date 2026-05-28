"""v6 — derive_verdict A3 amendment (Weinstein Stage 4 veto removed).

Stream A3 sector-confluence research (2026-05-28) found NO Weinstein
(cap_tier × lookback × confluence-subset) combination clears the production
gate (IC ≥ 0.05 AND ≥ 50 events/yr AND positive min OOS IC), even after
layering sector confluence (L5 — Weinstein's "buy leaders in leading groups"
rule). See docs/v6/2026-05-28-weinstein-a3-report.md.

Consequence: Stage 4 → WAIT veto removed from the verdict composer.
Weinstein stage is now a context chip on the why-strip, not a precedence-
ladder gate. Stage 3 → WATCH/HOLD downgrade retained (Q1 spec lock,
separate decision).

This migration replaces the function body created in migration 113.
CREATE OR REPLACE makes re-application idempotent.

Mirrors atlas/verdict/derive.py — parity verified via
scripts/verdict/verify_sql_matches_python.sql (re-run after this lands).

Revision ID: 114
Revises: 113
Create Date: 2026-05-28 IST
"""

from alembic import op

revision = "114"
down_revision = "113"
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

    -- 3a. Gate vetoes — named failing gate, not just "veto"
    IF p_gate_strength  = false THEN RETURN QUERY SELECT 'WAIT', 'Strength gate fail';  RETURN; END IF;
    IF p_gate_direction = false THEN RETURN QUERY SELECT 'WAIT', 'Direction gate fail'; RETURN; END IF;
    IF p_gate_risk      = false THEN RETURN QUERY SELECT 'WAIT', 'Risk gate fail';      RETURN; END IF;
    IF p_gate_sector    = false THEN RETURN QUERY SELECT 'WAIT', 'Sector gate fail';    RETURN; END IF;
    IF p_gate_market    = false THEN RETURN QUERY SELECT 'WAIT', 'Market gate fail';    RETURN; END IF;

    -- 3b. Stage 3 ambiguity — downgrade to WATCH/HOLD (Q1 spec lock — never WAIT)
    IF p_cap_tier != 'Micro' AND p_weinstein = 3 THEN
        RETURN QUERY SELECT
            CASE WHEN p_user_owns THEN 'HOLD' ELSE 'WATCH' END,
            'Stage 3 topping';
        RETURN;
    END IF;

    -- 3c. Clear path — gates pass, Stage 1/2/4/NULL all promote to BUY/ACCUMULATE.
    -- Stage 4 with positive cell renders as BUY with a Stage 4 warn-chip on the
    -- why-strip (UI responsibility, not derivation responsibility). A3 amendment.
    RETURN QUERY SELECT
        CASE WHEN p_user_owns THEN 'ACCUMULATE' ELSE 'BUY' END,
        NULL::text;
END;
$$;
"""

# Downgrade restores the migration 113 body (with the Stage 4 veto).
_DOWNGRADE_FUNCTION = """
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
    IF p_cell_state = 'NEGATIVE' THEN
        RETURN QUERY SELECT CASE WHEN p_user_owns THEN 'SELL' ELSE 'AVOID' END, NULL::text;
        RETURN;
    END IF;

    IF p_cell_state = 'NEUTRAL' THEN
        RETURN QUERY SELECT CASE WHEN p_user_owns THEN 'HOLD' ELSE 'WATCH' END, NULL::text;
        RETURN;
    END IF;

    IF p_cap_tier != 'Micro' AND p_weinstein = 4 THEN
        RETURN QUERY SELECT 'WAIT', 'Stage 4 vetoes positive cell';
        RETURN;
    END IF;

    IF p_gate_strength  = false THEN RETURN QUERY SELECT 'WAIT', 'Strength gate fail';  RETURN; END IF;
    IF p_gate_direction = false THEN RETURN QUERY SELECT 'WAIT', 'Direction gate fail'; RETURN; END IF;
    IF p_gate_risk      = false THEN RETURN QUERY SELECT 'WAIT', 'Risk gate fail';      RETURN; END IF;
    IF p_gate_sector    = false THEN RETURN QUERY SELECT 'WAIT', 'Sector gate fail';    RETURN; END IF;
    IF p_gate_market    = false THEN RETURN QUERY SELECT 'WAIT', 'Market gate fail';    RETURN; END IF;

    IF p_cap_tier != 'Micro' AND p_weinstein = 3 THEN
        RETURN QUERY SELECT CASE WHEN p_user_owns THEN 'HOLD' ELSE 'WATCH' END, 'Stage 3 topping';
        RETURN;
    END IF;

    RETURN QUERY SELECT CASE WHEN p_user_owns THEN 'ACCUMULATE' ELSE 'BUY' END, NULL::text;
END;
$$;
"""


def upgrade() -> None:
    op.execute(_CREATE_FUNCTION)


def downgrade() -> None:
    op.execute(_DOWNGRADE_FUNCTION)
