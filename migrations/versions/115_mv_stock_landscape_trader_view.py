"""v6 — atlas.mv_stock_landscape_trader view (verdict + tracking columns).

Adds the trader-view layer on top of mv_stock_landscape — exposes
combined_verdict (canonical vocabulary), verdict_reason, first_called_at,
and since_call_return. The /stocks/[symbol] page reads these directly.

Implemented as a non-materialized VIEW (not a MV) to avoid duplicating
the 300-line mv_stock_landscape body. Per-row compute is trivial — at
most 2 atlas_v6_clean_ohlcv PK lookups + one atlas.derive_verdict() call.
For per-stock queries (the common case), the view is sub-100ms.

Columns added (on top of mv_stock_landscape's existing 35 columns):
  - combined_verdict   text       — BUY / ACCUMULATE / WATCH / HOLD /
                                    AVOID / SELL / WAIT per CONTEXT.md
                                    canonical vocabulary
  - verdict_reason     text|null  — named gate fail or "Stage 3 topping";
                                    NULL for clean verdicts
  - first_called_at    date|null  — entry_date of the open signal_call,
                                    or NULL if no open signal_call exists
  - since_call_return  numeric|null — close_today / close_at_entry − 1,
                                      computed via atlas_v6_clean_ohlcv

Inputs to atlas.derive_verdict() (set conservatively for data-readiness):
  - cell_state:    COALESCE(sc.action, 'NEUTRAL')  — when no open
                   signal_call, default to NEUTRAL → WATCH verdict
  - weinstein:     NULL — no production atlas_stock_weinstein table
                   exists yet. Per A3 amendment, Weinstein is a
                   why-strip context chip, not a verdict input.
  - user_owns:     false — atlas_paper_portfolio is empty (0 rows).
                   Ownership wiring is a v7 broker-integration task.
  - cap_tier:      from mv_stock_landscape
  - gates:         all true — no per-stock gate data wired yet.
                   When wired (Stream B/C followup), the view rebuilds.

This means the verdict surface today emits only BUY / AVOID / WATCH
(never ACCUMULATE / HOLD / SELL / WAIT). That matches the available
data; ownership-aware + gate-aware variants land when their data
sources land.

Refresh: not needed (view, not materialized). Reads transparently from
the underlying mv_stock_landscape refresh.

Revision ID: 115
Revises: 114
Create Date: 2026-05-28 IST
"""

from alembic import op

revision = "115"
down_revision = "114"
branch_labels = None
depends_on = None


_CREATE_VIEW = """
CREATE OR REPLACE VIEW atlas.mv_stock_landscape_trader AS
WITH latest_open_call AS (
  -- A stock can have multiple open signal_calls (different cell × tenure).
  -- For the trader-view we want ONE primary verdict per stock.
  -- Picks the most recent open call, same pattern as mv_stock_landscape's
  -- open_signals_latest CTE in migration 106.
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
  ON sc.instrument_id = l.instrument_id
 AND sc.rn = 1
LEFT JOIN atlas.atlas_v6_clean_ohlcv p_now
  ON p_now.symbol = l.symbol
 AND p_now.date   = l.as_of_date
LEFT JOIN atlas.atlas_v6_clean_ohlcv p_entry
  ON p_entry.symbol = l.symbol
 AND p_entry.date   = sc.date
CROSS JOIN LATERAL atlas.derive_verdict(
  COALESCE(sc.action::text, 'NEUTRAL'),
  NULL::int,
  false,
  l.cap_tier::text,
  true, true, true, true, true
) v;
"""

_DROP_VIEW = """
DROP VIEW IF EXISTS atlas.mv_stock_landscape_trader;
"""


def upgrade() -> None:
    # DROP first so the column set can change across upgrades. Plain
    # CREATE OR REPLACE VIEW refuses to drop or rename columns, which
    # blocked the original out-of-band creation (different shape) from
    # being replaced by the migration definition. See migration 116
    # docstring for the column drift this resolves.
    op.execute(_DROP_VIEW)
    op.execute(_CREATE_VIEW)


def downgrade() -> None:
    op.execute(_DROP_VIEW)
