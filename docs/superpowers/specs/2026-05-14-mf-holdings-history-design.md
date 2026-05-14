# MF Holdings History & Fund Manager Decision Tracking

**Date:** 2026-05-14
**Status:** Approved — ready for implementation planning

---

## Overview

Mutual fund holdings data arrives monthly from Morningstar via the JIP data core into `public.de_mf_holdings`. Atlas currently reads this table on-demand to show current holdings on a fund's detail page, but never computes or stores what changed between disclosures.

This spec adds a holdings change-tracking layer to Atlas: a granular entry/exit log per fund per disclosure period, pre-computed decision quality scores, and 1m + 3m outcome enrichment. The result surfaces on four UI locations: a new tab and summary card on the fund detail page, a dedicated fund manager decisions page, and new columns on the main funds listing.

**Not in scope:** calling the Morningstar API directly from Atlas. JIP handles data ingestion into `de_mf_holdings`. Atlas reads from it.

---

## Data Source

`public.de_mf_holdings` — append-only, one row per `(mstar_id, as_of_date, instrument_id)`. JIP adds a new batch of rows each month when Morningstar publishes updated disclosures. Atlas reads this table; it does not write to it.

Key columns used:
- `mstar_id` — Morningstar fund identifier
- `as_of_date` — disclosure date
- `instrument_id` — stock identifier (joins to `atlas_universe_stocks`)
- `weight_pct` — holding weight as percentage of AUM

---

## Schema

### Table 1: `atlas.atlas_fund_holdings_changes`

One row per stock action per disclosure period per fund.

```sql
mstar_id              VARCHAR(32)   NOT NULL  -- FK → atlas_universe_funds
from_date             DATE          NULL       -- prior disclosure; NULL for first-ever
to_date               DATE          NOT NULL   -- current disclosure
instrument_id         TEXT          NOT NULL
symbol                VARCHAR(20)   NOT NULL   -- denormalized for display speed
action                VARCHAR(10)   NOT NULL   -- entry | exit | increase | decrease
weight_before         NUMERIC(10,4) NOT NULL   -- 0 for entries
weight_after          NUMERIC(10,4) NOT NULL   -- 0 for exits
weight_delta          NUMERIC(10,4) NOT NULL   -- weight_after - weight_before

-- Signal quality (filled at compute time)
rs_state_at_action    VARCHAR(20)   NULL
momentum_state_at_action VARCHAR(20) NULL
signal_quality        VARCHAR(10)   NULL       -- high | low | neutral

-- 1-month outcome (filled ~30 days after to_date)
outcome_rs_state_1m   VARCHAR(20)   NULL
outcome_ret_1m        NUMERIC(10,4) NULL
outcome_quality_1m    VARCHAR(10)   NULL       -- good | bad | neutral

-- 3-month outcome (filled ~90 days after to_date)
outcome_rs_state_3m   VARCHAR(20)   NULL
outcome_ret_3m        NUMERIC(10,4) NULL
outcome_quality_3m    VARCHAR(10)   NULL

id                    UUID          PK
created_at            TIMESTAMPTZ   NOT NULL
updated_at            TIMESTAMPTZ   NOT NULL
```

**Indexes:** `(mstar_id, to_date)`, `(mstar_id, from_date, to_date)`, `instrument_id`

**Signal quality derivation** (deterministic):

| Action | RS State | signal_quality |
|--------|----------|----------------|
| entry | Leader / Strong / Emerging | high |
| entry | Weak / Laggard | low |
| exit | Weak / Laggard | high |
| exit | Leader / Strong / Emerging | low |
| increase / decrease | any | neutral |
| entry / exit | unknown / outside universe | neutral |

**Weight change threshold:** `increase` / `decrease` actions are only written when `|weight_delta| ≥ 0.25%`. Threshold stored in `atlas_thresholds` as `holdings_weight_change_min_pct`. Changes below this are treated as noise and skipped.

---

### Table 2: `atlas.atlas_fund_decision_scores`

One pre-computed row per fund per disclosure period.

```sql
mstar_id                  VARCHAR(32)   NOT NULL
period_date               DATE          NOT NULL   -- = to_date

-- Action counts
entries_count             INTEGER       NOT NULL DEFAULT 0
exits_count               INTEGER       NOT NULL DEFAULT 0
increases_count           INTEGER       NOT NULL DEFAULT 0
decreases_count           INTEGER       NOT NULL DEFAULT 0

-- Signal-based scores (filled at compute time)
quality_entries_pct       NUMERIC(10,4) NULL  -- % entries with signal_quality = high
quality_exits_pct         NUMERIC(10,4) NULL  -- % exits with signal_quality = high
signal_score              NUMERIC(10,4) NULL  -- (quality_entries_pct + quality_exits_pct) / 2

-- 1-month outcome scores (filled ~30 days after period_date)
outcome_entries_pct_1m    NUMERIC(10,4) NULL  -- % entry stocks that outperformed at 1m
outcome_exits_pct_1m      NUMERIC(10,4) NULL  -- % exit stocks that underperformed at 1m
outcome_score_1m          NUMERIC(10,4) NULL  -- (outcome_entries_pct_1m + outcome_exits_pct_1m) / 2

-- 3-month outcome scores (filled ~90 days after period_date)
outcome_entries_pct_3m    NUMERIC(10,4) NULL
outcome_exits_pct_3m      NUMERIC(10,4) NULL
outcome_score_3m          NUMERIC(10,4) NULL

-- State classification (pre-computed, updated when outcome scores are filled)
decision_state            VARCHAR(20)   NULL  -- Sharp | Average | Poor

id                        UUID          PK
created_at                TIMESTAMPTZ   NOT NULL
updated_at                TIMESTAMPTZ   NOT NULL

UNIQUE (mstar_id, period_date)
```

**`decision_state` thresholds** (stored in `atlas_thresholds`):
- `signal_score ≥ decision_score_sharp_threshold` (default 65) → `Sharp`
- `signal_score < decision_score_poor_threshold` (default 40) → `Poor`
- Between → `Average`

State is derived from `signal_score` initially. Once `outcome_score_1m` is available, `decision_state` is re-derived from `outcome_score_1m` (more reliable signal). Once `outcome_score_3m` is available, it takes precedence.

---

## Compute

### Module: `atlas/compute/lens_decisions.py`

Entry point: `run_lens_decisions(db_session, target_funds=None)`.

**Algorithm per fund:**

1. Pull all distinct `as_of_date` values from `de_mf_holdings` for this `mstar_id`, ordered descending.
2. Take the two most recent: `(to_date, from_date)`. For first-ever disclosures, `from_date = None`.
3. Check `atlas_fund_decision_scores` for an existing `(mstar_id, period_date=to_date)` row. If found, skip (idempotent).
4. Load both disclosure snapshots as DataFrames from `de_mf_holdings`.
5. Merge on `instrument_id`. Compute `weight_delta` for each stock.
6. Classify action per stock using threshold from `atlas_thresholds`.
7. JOIN changed stocks to `atlas_stock_states_daily` on `to_date` to get `rs_state`, `momentum_state`. Derive `signal_quality`.
8. Bulk insert into `atlas_fund_holdings_changes`.
9. Aggregate into one `atlas_fund_decision_scores` row and insert.

**Scale:** ~500 funds × ~20 changes/period = ~10K rows per monthly run. Pandas vectorized throughout; no iterrows.

### Runner: `scripts/run_fund_decisions.py`

Standalone CLI script. Accepts optional `--mstar-id` for single-fund runs. Logs row counts before and after each fund. Prints summary on completion.

### Enrichment job: `scripts/enrich_fund_decision_outcomes.py`

Runs daily (manually until M4 integration).

**1m pass:** Queries `atlas_fund_holdings_changes` where `outcome_quality_1m IS NULL AND to_date <= CURRENT_DATE - 30`. Looks up `atlas_stock_metrics_daily` for `ret_1m` and `atlas_stock_states_daily` for RS state ~30 days after `to_date`. Fills outcome columns. Recomputes and updates `atlas_fund_decision_scores` outcome_1m fields + `decision_state`.

**3m pass:** Same logic, condition `to_date <= CURRENT_DATE - 90`. Updates outcome_3m fields + `decision_state`.

**Outcome quality definition** (consistent with Atlas RS framework):
- For `entry` actions: `outcome_quality = good` if `outcome_rs_state` is Leader / Strong / Emerging; `bad` if Weak / Laggard; `neutral` otherwise.
- For `exit` actions: `outcome_quality = good` if `outcome_rs_state` is Weak / Laggard (confirming the exit was correct); `bad` if Leader / Strong / Emerging; `neutral` otherwise.
- `outcome_entries_pct` = % of entries where `outcome_quality = good`.
- `outcome_exits_pct` = % of exits where `outcome_quality = good`.

Both passes are idempotent (only fills NULLs).

---

## API

Both endpoints added to `atlas/api/funds.py`.

### `GET /api/funds/{mstar_id}/decision-history`

Returns scored periods for a fund. Used by the summary card and decisions page period selector.

**Query params:** `limit` (default 12, max 24)

**Response:**
```json
{
  "data": [
    {
      "period_date": "2026-04-30",
      "entries_count": 3,
      "exits_count": 2,
      "increases_count": 5,
      "decreases_count": 4,
      "signal_score": 72.5,
      "outcome_score_1m": 65.0,
      "outcome_score_3m": null,
      "decision_state": "Sharp"
    }
  ],
  "meta": { "mstar_id": "...", "data_as_of": "...", "fetched_at": "..." }
}
```

### `GET /api/funds/{mstar_id}/decisions/{period_date}`

Returns granular entry/exit rows for one period. Used by the dedicated decisions page.

**Query params:** `action` filter (optional — `entry | exit | increase | decrease`)

**Response:**
```json
{
  "data": [
    {
      "symbol": "RELIANCE",
      "action": "entry",
      "weight_before": "0.0000",
      "weight_after": "2.4500",
      "weight_delta": "2.4500",
      "rs_state_at_action": "Leader",
      "momentum_state_at_action": "Strong",
      "signal_quality": "high",
      "outcome_ret_1m": "4.20",
      "outcome_quality_1m": "good",
      "outcome_ret_3m": null,
      "outcome_quality_3m": null
    }
  ],
  "meta": { "mstar_id": "...", "period_date": "...", "fetched_at": "..." }
}
```

---

## Frontend

### Surface 1 — "Manager Decisions" tab on fund detail page

New tab in `frontend/src/app/funds/[mstar_id]/page.tsx` alongside the Holdings tab.

**Component:** `frontend/src/components/funds/FundDecisionSummaryCard.tsx`

- Recharts grouped bar chart — last 12 periods on x-axis. Primary bar: `signal_score`. Overlay bar: `outcome_score_1m` (greyed out when null, labeled "pending").
- Color coding: green ≥ 65, amber 40–65, red < 40.
- Summary stats row: entries / exits / increases / decreases badges for the latest period.
- "View full history →" link to `/funds/[mstar_id]/decisions`.

### Surface 2 — Dedicated decisions page

**Route:** `frontend/src/app/funds/[mstar_id]/decisions/page.tsx` (thin shell ≤ 250 LOC)

**Component:** `frontend/src/components/funds/FundDecisionsDetail.tsx`

Layout:
1. Period selector dropdown — all available `period_date` values, defaults to latest.
2. Score cards row — `signal_score`, `outcome_score_1m`, `outcome_score_3m`. Null shown as "Pending".
3. Action filter tabs — All | Entries | Exits | Increases | Decreases.
4. AG Grid table — Symbol, Action badge, Weight Before → After, Δ Weight, RS State, Signal Quality badge, 1m Outcome, 3m Outcome. Sortable. CSV export.

### Surface 3 — Main funds listing page (new columns)

Three new columns added to the main `/funds` page table via a LEFT JOIN to the latest `atlas_fund_decision_scores` row per fund:

| Column | Source | Display |
|--------|--------|---------|
| Decision Score | `signal_score` | Numeric, color-coded |
| 1m Outcome | `outcome_score_1m` | Numeric, "—" if null |
| Decision State | `decision_state` | Badge: Sharp / Average / Poor |

Query function in `frontend/src/lib/queries/funds.ts` — LEFT JOIN so funds with no decisions data still appear.

### Data fetching

Two new query functions added to `frontend/src/lib/queries/funds.ts`:
- `getFundDecisionHistory(mstar_id, limit)` — calls decision-history endpoint
- `getFundDecisionDetail(mstar_id, period_date, action?)` — calls decisions/{period_date} endpoint

---

## Migration

One new Alembic migration (next sequence number after 064):
- Creates `atlas.atlas_fund_holdings_changes`
- Creates `atlas.atlas_fund_decision_scores`
- Inserts two threshold rows into `atlas_thresholds`: `holdings_weight_change_min_pct = 0.25`, `decision_score_sharp_threshold = 65`, `decision_score_poor_threshold = 40`

---

## Rollout Order

1. Migration — schema + thresholds
2. `atlas/compute/lens_decisions.py` + `scripts/run_fund_decisions.py`
3. Backfill: run script against all historical disclosure pairs in `de_mf_holdings`
4. `scripts/enrich_fund_decision_outcomes.py` — backfill past 1m/3m outcomes
5. API endpoints
6. Frontend: main listing columns → fund detail tab → dedicated decisions page
7. Manual validation before M4 integration
