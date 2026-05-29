"""v6 — mv_stock_landscape_trader composite_score fallback amendment.

User feedback (2026-05-28): the migration 115 view defaulted to NEUTRAL
(→ WATCH) for any stock without an open signal_call. That over-WATCH'd
475 of 747 stocks. Per the discussion:

> "Just because we don't have a high-conviction call doesn't mean it's
> neutral. We are following a statistical method and giving conviction
> + confidence. Even without that, like TradingView gives strong-buy /
> buy for things we have no context on. And even if IC is low, we can
> still give a call with low confidence + color coding."

This migration:
1. Extends the verdict source to a 3-way priority chain —
   (a) open signal_call.action  (high-confidence cell math)
   (b) composite_score sign     (statistical fallback, conviction_tier
                                  surfaces strength)
   (c) NEUTRAL → WATCH          (only when both NULL — genuinely no data)

2. Adds a new column `verdict_source` to the view with values
   'signal_call' | 'composite_score' | 'no_data' — frontend uses this
   to render appropriate context ("no Atlas math yet" badge for the
   third case).

3. Sets `verdict_reason = 'No Atlas math yet'` when both signal_call and
   composite_score are NULL, so the trader knows WATCH is "we don't
   have an opinion" not "we examined and concluded NEUTRAL."

Expected distribution shift on the current data:
   Before: 58 BUY · 214 AVOID · 475 WATCH  (75% WATCH — most are
                                            false WATCH from missing
                                            signal_calls)
   After:  ~288 BUY · ~408 AVOID · ~45 WATCH (~6% WATCH — only stocks
                                              with composite NULL or
                                              composite = 0)

Conviction_tier (T1-T5, already in mv_stock_landscape via SELECT l.*)
surfaces the confidence axis. UI color-codes the verdict pill:
T1 vibrant, T5 faded.

References:
 - CONTEXT.md §"Cell state vocabulary" — amended in same commit with
   the "Verdict source priority" clarification
 - docs/superpowers/specs/2026-05-28-trader-view-redesign.html §4

Revision ID: 116
Revises: 115
Create Date: 2026-05-28 IST
"""

from alembic import op

revision = "116"
down_revision = "115"
branch_labels = None
depends_on = None


_CREATE_VIEW = """
CREATE OR REPLACE VIEW atlas.mv_stock_landscape_trader AS
WITH latest_open_call AS (
  SELECT
    sc.instrument_id,
    sc.action,
    sc.date,
    ROW_NUMBER() OVER (
      PARTITION BY sc.instrument_id
      ORDER BY sc.date DESC, sc.computed_at DESC
    ) AS rn
  FROM atlas.atlas_signal_calls sc
  WHERE sc.exit_date IS NULL
)
SELECT
  l.*,
  -- Verdict source axis (3-way priority chain per spec amendment)
  CASE
    WHEN sc.action IS NOT NULL              THEN 'signal_call'
    WHEN l.composite_score IS NULL          THEN 'no_data'
    ELSE                                         'composite_score'
  END                                       AS verdict_source,

  v.verdict                                 AS combined_verdict,

  -- When the verdict is WATCH because we genuinely have no math, surface
  -- that. Otherwise the function's reason (gate fail / Stage 3) wins.
  CASE
    WHEN sc.action IS NULL AND l.composite_score IS NULL
    THEN 'No Atlas math yet'
    ELSE v.reason
  END                                       AS verdict_reason,

  sc.date                                   AS first_called_at,

  CASE
    WHEN sc.date IS NOT NULL
     AND p_now.close   IS NOT NULL
     AND p_entry.close IS NOT NULL
     AND p_entry.close <> 0
    THEN ROUND((p_now.close::numeric / p_entry.close::numeric - 1)::numeric, 6)
    ELSE NULL
  END                                       AS since_call_return
FROM atlas.mv_stock_landscape l
LEFT JOIN latest_open_call sc
  ON sc.instrument_id = l.instrument_id
 AND sc.rn = 1
LEFT JOIN atlas.atlas_v6_clean_ohlcv p_now
  ON p_now.symbol = l.symbol
 AND p_now.date   = l.as_of_date
LEFT JOIN atlas.atlas_v6_clean_ohlcv p_entry
  ON p_entry.symbol = l.symbol
 AND p_entry.date   = sc.date
CROSS JOIN LATERAL atlas.derive_verdict(
  -- 3-way priority chain:
  --  1. open signal_call.action  → cell math has fired
  --  2. composite_score sign     → statistical fallback
  --  3. NEUTRAL                  → no data (composite NULL)
  COALESCE(
    sc.action::text,
    CASE
      WHEN l.composite_score IS NULL THEN 'NEUTRAL'
      WHEN l.composite_score >  0    THEN 'POSITIVE'
      WHEN l.composite_score <  0    THEN 'NEGATIVE'
      ELSE                                'NEUTRAL'
    END
  ),
  NULL::int,
  false,
  l.cap_tier::text,
  true, true, true, true, true
) v;
"""

# Downgrade restores migration 115 body (signal_call-only fallback).
_DOWNGRADE_VIEW = """
CREATE OR REPLACE VIEW atlas.mv_stock_landscape_trader AS
WITH latest_open_call AS (
  SELECT
    sc.instrument_id, sc.action, sc.date,
    ROW_NUMBER() OVER (
      PARTITION BY sc.instrument_id
      ORDER BY sc.date DESC, sc.computed_at DESC
    ) AS rn
  FROM atlas.atlas_signal_calls sc
  WHERE sc.exit_date IS NULL
)
SELECT
  l.*,
  v.verdict        AS combined_verdict,
  v.reason         AS verdict_reason,
  sc.date          AS first_called_at,
  CASE
    WHEN sc.date IS NOT NULL
     AND p_now.close   IS NOT NULL
     AND p_entry.close IS NOT NULL
     AND p_entry.close <> 0
    THEN ROUND((p_now.close::numeric / p_entry.close::numeric - 1)::numeric, 6)
    ELSE NULL
  END              AS since_call_return
FROM atlas.mv_stock_landscape l
LEFT JOIN latest_open_call sc
  ON sc.instrument_id = l.instrument_id AND sc.rn = 1
LEFT JOIN atlas.atlas_v6_clean_ohlcv p_now
  ON p_now.symbol = l.symbol AND p_now.date = l.as_of_date
LEFT JOIN atlas.atlas_v6_clean_ohlcv p_entry
  ON p_entry.symbol = l.symbol AND p_entry.date = sc.date
CROSS JOIN LATERAL atlas.derive_verdict(
  COALESCE(sc.action::text, 'NEUTRAL'),
  NULL::int, false, l.cap_tier::text,
  true, true, true, true, true
) v;
"""


def upgrade() -> None:
    # DROP first — this revision renames combined_verdict -> verdict_source,
    # which CREATE OR REPLACE VIEW refuses to do (Postgres rejects column
    # renames in REPLACE). Matches the pattern used in 115.
    op.execute("DROP VIEW IF EXISTS atlas.mv_stock_landscape_trader;")
    op.execute(_CREATE_VIEW)


def downgrade() -> None:
    op.execute(_DOWNGRADE_VIEW)
