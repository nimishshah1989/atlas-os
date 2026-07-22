# Today — the Pulse change-feed

**Date:** 2026-07-22
**Status:** Approved to build (user greenlit 2026-07-22)
**Next gate:** `/tdd` — required by the `frontend/src/**` edit hook; enforces real-data tests (Rule #0).

## Goal

Import Google Finance's "what changed / what's happening now" DNA into Atlas,
contextualized to the fund-manager's loop: a glanceable, **conviction-ranked**
change-feed of what moved overnight. Not a retail watchlist — a professional
"what deserves attention today" surface. Inspiration, not replication.

The current board answers *"what is the state of the market?"* (breadth, regime).
It never answers *"what changed since I last looked, and what deserves attention now?"*
Today fills that gap, and does it through the lens of Atlas's own conviction scores —
the one thing Google Finance can't do.

## Scope (v1)

- New page **Today** under a **Pulse** nav group, sibling to the existing **Market Pulse** page.
- **The Market Pulse page/component is UNCHANGED** — same route (`/`), same content,
  same compute. Only `NAV_V4` gains a Pulse group + a Today link. The Market Pulse
  page file is not edited. (Today may be promoted to `/` later — a one-line flip —
  once it has proven itself.)
- **Aggregation-only: no new tables, no new ingestion, no new cron.** All four
  modules are read queries over existing `atlas_foundation` nightly output.
- **Nightly cadence** — overnight deltas: latest close (T) vs prior trading day (T−1).
  Intraday liveness and portfolio-personalization are explicitly deferred (separate tracks).

## Approach

**Aggregation-only** (chosen): new read queries + one new page + a nav tweak.
Diffing ~2k lens rows across two days is cheap and fits the existing ISR `revalidate` caching.

- *Alt A (rejected for v1):* pre-materialize overnight deltas into a nightly
  `atlas_today_changes` table. Faster page + auditable deltas, but it is schema
  growth (resisted per FM directive) and another cron to keep green. **Upgrade path
  if the in-query diff ever regresses — not v1.**
- *Alt B (rejected for v1):* fold in intraday + portfolio-personalization now — the
  two tracks that were deprioritized. Keeping them out is what makes v1 shippable.

## IA / nav

- `NAV_V4` (`frontend/src/components/nav/TopNavV4.tsx`) gains a **Pulse** dropdown group:
  `Today` (`/today`, listed first) + `Market Pulse` (`/`).
- `/` remains Market Pulse, unchanged.

## Page: `/today`

Server component, `export const revalidate = 300` (matches the current home).
Header: `Today · as of {latest close date}` + the reused `RegimeChip`.
Four stacked, labeled modules (Google-Finance-style modular dashboard):

### 1. Conviction moves (flagship)

- **Source:** `atlas_lens_scores_daily` (`asset_class='stock'`), at latest date T and
  prior trading day T−1. `composite` (0–100) per instrument; decile via
  `ntile(10) OVER (PARTITION BY cap ORDER BY composite)` computed per date (reuse the
  `getStocksDecileList` logic verbatim so deciles are defined identically to the rest of the board).
- **Three sub-lists** (limit ~8 each):
  - **Entered leadership** — crossed *into* D≥8 (`LEAD_DECILE`) between T−1 and T.
  - **Fell out** — dropped *below* D≥8 between T−1 and T.
  - **Biggest score jumps** — top |Δcomposite|.
- **Row:** symbol · name · sector · decile T−1→T · Δcomposite · direction arrow.
  Links to `/stocks/[symbol]`.
- **Precondition:** ≥2 trading days of history in `atlas_lens_scores_daily`. If only
  one day exists, the module renders a graceful "baseline building" empty state —
  **never fabricated deltas** (Rule #0).

### 2. Catalysts today

- **Source:** `lens_filings` where `filing_date` = latest available; join
  `instrument_master` (symbol/name) + latest `atlas_lens_scores_daily`
  (composite/decile) for the conviction tag.
- **Order:** priority (HIGH → MEDIUM → LOW), then conviction (decile desc).
- **Row:** priority chip · bucket · subject · symbol · a "★ liked" tag when decile ≥ D≥8 ·
  link to the NSE `url` and to `/stocks/[symbol]`. Limit ~15 + "…N more".
- Reuse the priority/bucket gloss vocabulary from `StockAnnouncementsPanel` via a
  shared helper (extract, do not duplicate).

### 3. Movers

- **Source:** `ohlcv_stock` close at T vs T−1 → pct change.
  **Gainers** / **Losers** (limit ~8 each) + **Conviction movers** (top |Δcomposite|,
  reuses module 1's data — no extra query).
- Three mini-columns or a segmented control. Rows link to `/stocks/[symbol]`.
- Note: EOD movers = last close vs prior close (nightly world). Intraday movers deferred.

### 4. Market context

- **Source:** reuse `getCurrentRegime()` + `getBreadthSeries()` — no new query.
- Compact strip: regime state + deployment %, % above 50/200-EMA, net new highs.
  "See full Market Pulse →" link to `/`.

## New query functions (`frontend/src/lib/queries/`)

- `getConvictionMoves()` → `{ entered, fellOut, jumps }` from `atlas_lens_scores_daily` (T, T−1).
- `getTodayCatalysts()` → filings at the latest date + conviction join from `lens_filings`.
- `getTodayMovers()` → gainers / losers from `ohlcv_stock` (T, T−1).
- Market context reuses existing `getCurrentRegime` / `getBreadthSeries`.

All real `atlas_foundation` reads. No synthetic inputs anywhere.

## Testing (Rule #0)

- Real-record tests only: each query is tested against real `atlas_foundation` rows.
  - `getConvictionMoves`: assert returned deltas reconcile to two real dated rows for
    the same instrument (composite T − composite T−1).
  - `getTodayCatalysts`: assert returned rows match a real `filing_date`'s `lens_filings` rows.
  - `getTodayMovers`: assert pct change reconciles to two real `ohlcv_stock` closes.
- Definition-of-done asserts on real produced output, never synthetic fixtures.
- Graceful empty states verified (thin history → module 1 baseline state; a date with no filings).

## Non-goals (v1)

Intraday liveness · portfolio-personalization ("my names") · global search / ⌘K ·
richer instrument pages · any new table / ingestion / cron. Each is a separately-scoped
future track.

## Eng review findings (2026-07-22, folded)

Verified against the real DB (Rule #0), then locked these engineering decisions:

- **Data precondition SATISFIED (was the #1 risk):** `atlas_lens_scores_daily`
  holds **1875 distinct trading days** (2019-01-01 → 2026-07-21), 498 stocks/day,
  all `composite`-scored. The overnight-diff flagship module has 7+ years of real
  history. T=2026-07-21, T−1=2026-07-20. No backfill needed; the "≥2 days" empty
  state is a safety net that won't trigger in practice.
- **T−1 = prior *distinct trading date*, not calendar −1.** Compute T−1 as the
  second-most-recent `DISTINCT date` in the table (holiday/weekend safe). Never `date - 1`.
- **Universe is naturally liquid (movers junk risk resolved):** the scored set is
  **498 names (Nifty 500)**. Deciles and movers operate over this set only — no
  micro-cap ±20% noise. Gainers/losers join the scored universe, not all of `ohlcv_stock`.
- **Decile consistency:** reuse the exact `cap` CTE from `getStockDecile`
  (`de_index_constituents` index_code → large/mid/small/micro) and the same
  `ntile(10) PARTITION BY cap ORDER BY composite`, computed independently for T and
  T−1, so "entered D≥`LEAD_DECILE`" is apples-to-apples across days.
- **Cap-tier drift edge case (P3, accepted):** a name whose `cap` changes between
  T−1 and T shifts decile partitions. Rare; surfaces as a move, not a crash. Not special-cased in v1.
- **Connection discipline:** 498 rows × 2 days is small, but still respect the
  `max=14` session pooler — don't fan every module query into one unbounded `Promise.all`.
- **Empty states per module (Rule #0):** a date with no HIGH filings, or a thin
  history, renders an explicit "nothing today" state — never a fabricated row.
- **Outside voice (Codex) not run** — low-risk, no-schema, feature-flaggable aggregation;
  the user greenlit the build. Available on demand.

## Perf / deploy

- Query cost: ~2k lens rows × 2 days + one filings read + one ohlcv delta read — all
  cached by ISR `revalidate`. If page latency regresses, the upgrade path is Alt A
  (nightly-materialized `atlas_today_changes`), not v1.
- Deploy per `docs/deploy-hygiene.md`: rebuild to completion → confirm `.next/BUILD_ID`
  → clear `.next/cache/fetch-cache` → reload once. Static-ISR "as of" advances on rebuild.
