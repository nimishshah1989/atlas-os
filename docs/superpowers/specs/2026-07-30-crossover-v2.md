# Crossover v2 — intraday detection, 3-event execution, and twin exit books

**Date:** 2026-07-30
**Status:** draft — awaiting FM sign-off
**Supersedes:** [2026-07-22-intraday-cross-eod-fill-design.md](2026-07-22-intraday-cross-eod-fill-design.md)
(Phase 1 of that spec merged to `main` but was never enabled; Phase 2 was never built.)

---

## Context

The 4 stock EMA-cross books allocate real capital and are the FM's most-watched
page. Today they detect a crossover only at the daily **close** and fill at the
**next** session's close, and the FM only learns about a trade *after* it is
booked. The 22-July spec was approved to fix exactly this. Its code merged
(`af6de395`, `ed1d6777`, `d91b83a0`, `7a784df5`) but is **opt-in via
`params.intraday`, and no portfolio ever set the flag** — so it has never run.

The cost is measurable and live: MRPL's 13/34 golden cross flashed intraday on
16 Jul (provisional level ₹163.88, breached from the open) and the book bought it
on **20 Jul @ ₹174.49**. That trade is still in the book. Roughly 10% of entry,
given away to a timing lag the FM never agreed to.

Second gap: the FM wants to run and compare **two exit rules** on the 13/34
rulebook, not pick one blind. The two are far apart. On MRPL at Wednesday's
close of ₹160.03, the death-cross sell level is P\* = **₹121.22** while the
EMA13 sell level is **₹165.55** — a 26.8% gap on the same name on the same day.
One rule holds, the other sells. Only live twins settle which is right.

---

## Current State (verified 2026-07-30 against the live DB)

| Layer | Where | Behaviour today |
|---|---|---|
| EMAs | `technical_daily.ema_{n}` | TA-Lib EMA over `ohlcv_stock.close_adj`, nightly via `compute_all`. Verified correct by independent recompute (22-Jul spec, Phase 0). |
| Detection | [ema_cross.py:61-65](../../../atlas/portfolio/strategies/ema_cross.py#L61-L65) | `fast > slow` compared between consecutive stored **closes**. Intraday ignored. |
| Fill | [engine.py:99-112](../../../atlas/portfolio/engine.py#L99-L112) | Next session's **close** (`searchsorted(side="right")`). |
| Alert | [portfolio_run.py:471](../../../scripts/foundation/portfolio_run.py#L471) | Inside the nightly `mark`, i.e. **after** the fill. One message per booked trade. |
| Intraday | [atlas_intraday.sh](../../../scripts/ops/atlas_intraday.sh) | Runs every 5 min in market hours; does sector-RS + `desk_monitor` Kite quotes. No crossover awareness. |

### The 4 books

| Book | portfolio_id | params | live NAV rows | backtest ends |
|---|---|---|---|---|
| 10/21 | `18ff8998` | `{fast:10, slow:21}` | 19 (from 03-Jul) | 2026-07-08 |
| **13/34** | `33ba1022` | `{fast:13, slow:34, notify:true}` | 17 (from 07-Jul) | 2026-07-21 |
| 21/50 | `fa1232aa` | `{fast:21, slow:50}` | 19 | 2026-07-08 |
| 50/200 | `89379c8e` | `{fast:50, slow:200}` | 19 | 2026-07-08 |

All `[stock]`, `max_position_pct = 0.08` → **12 slots**. None carries a risk stop
(deliberate — [portfolio_run.py:117-137](../../../scripts/foundation/portfolio_run.py#L117-L137)).

### Data sufficiency (checked, not assumed)

- `ohlcv_stock.open_adj` — **100% non-null, 2000 → today.** Next-session-open fills are fully backtestable across 8 years.
- `high_adj` / `low_adj` — already wired into the runner for intraday detection ([portfolio_run.py:270-286](../../../scripts/foundation/portfolio_run.py#L270-L286)).
- `atlas.primitives.ema_cross_price` — the P\* primitive exists and is unit-tested.
- `desk_alerts` — existing intraday alert-dedup table; the pattern to copy, not extend.

### Telegram senders today (7, all on one `TELEGRAM_CHAT_ID`)

1. `portfolio_alerts.notify_new_trades` — **keep**
2. [desk_monitor.py:103](../../../scripts/foundation/desk_monitor.py#L103) — desk stop/target, **every 5 min**
3. `desk_orders.send_memo` ← `desk_run.py` — nightly desk memo
4. [atlas_daily.sh:149](../../../scripts/ops/atlas_daily.sh#L149) — nightly pipeline failures
5. [atlas_weekly.sh:60](../../../scripts/ops/atlas_weekly.sh#L60) — weekly pipeline failures
6. [qa_weekly.py:108](../../../scripts/ops/qa_weekly.py#L108) — Sunday QA report
7. `systemd/atlas-intraday-notify.service` → `scripts/kite_daily_notify.py` — **this script does not exist in the repo**

---

## Decisions (FM, locked)

| # | Decision |
|---|---|
| **D1** | Both exit rules run as **separate live portfolios**, not executor+shadow. Each has its own cash, positions, NAV and Telegram alerts. |
| **D2** | Naming suffix states how the position closes: `· Deathcross Close` and `· EMA13 Close`. |
| **D3** | Existing book `33ba1022` **becomes** the Deathcross Close book (rename only). Its 28 booked trades and 12 positions are untouched. |
| **D4** | Live history is **forward-only** for the deathcross book — no retroactive re-booking of the 28 existing trades. Rule change carries a dated marker on the chart. *(FM defaulted, flagged for override.)* |
| **D5** | New EMA13 Close book is **seeded by replay from 07-Jul-2026**, the deathcross book's inception, so both live curves are comparable from day one. Real stored prices/EMAs only (rule #0). *(Assumption, flagged for override.)* |
| **D6** | Timing logic (intraday alert → confirm → fill) applies to **all 4 stock crossover books**. Twin EMA-close books: 13/34 only for now. |
| **D7** | Telegram: **only** the two 13/34 books alert. Senders 2-7 above are removed. |
| **D8** | Poll cadence: reuse the existing **5-min** cron rather than the FM's stated 15 min — 3× detection fidelity, zero new infrastructure. *(Recommended, flagged for override.)* |
| **D9** | **BUY = `entry_confirm="close"`** — the intraday breach only alerts; the position opens on the first close that confirms, and fills at the next session's open. Settled by the 8-year sweep, not by argument. See ADR 0005. |
| **D10** | **SELL = `exit="death_cross"`** with the 15:15 lock, filling at that day's close. The `fast_ema` twin returned 34.5% against 428.4% over the same 8 years with 5.4× the trades, so it ships as a **paper** book, not a funded one. See ADR 0005. |

---

## Proposed Change

### The signal contract

**BUY — all 4 books**

| Event | Trigger | When | Telegram |
|---|---|---|---|
| 1 ALERT | live price ≥ P\*(up), P\* from prior close's confirmed EMAs | any poll tick, 09:15–15:30 | provisional, explicitly labelled |
| 2 CONFIRM | that day's **close** also has `fast > slow` | after close | "will execute at tomorrow's open" |
| 3 BOOK | fill at **next session's `open_adj`** | next morning | booked confirmation |

Non-confirmation at close → no trade, name re-arms.

**SELL — level depends on the book's exit rule**

| Event | Trigger | When | Telegram |
|---|---|---|---|
| 1 ALERT | live price ≤ sell level | any poll tick | provisional, explicitly labelled |
| 2 CONFIRM | breach **sustains** at the **15:15** price | 15:15 IST | "will execute at today's close" |
| 3 BOOK | fill at **that day's `close_adj`** | after close | booked confirmation |

Sell level per book: `Deathcross Close` → P\*(down) from `ema_cross_price`.
`EMA13 Close` → `ema_13` itself.

Recovery above the level by 15:15 → no trade, name re-arms tomorrow.

Asymmetric by FM design: buys wait for the next open, sells exit same-day because
the next open can gap further down.

### A. Exit-rule parameter on `EmaCross`

New `exit` param: `"death_cross"` (default, preserves every existing book) or
`"fast_ema"`. Drives which level `events()` uses for exits. One param on the
existing strategy — no new strategy class, no registry change.

**Do not reuse the engine's existing `stop_ema` path.** It fires on *prior*
close < EMA with a next-session fill and books `reason='stop'`; the new rule is
same-day with `reason='signal'`. Different timing, different semantics. The
`stop_ema` code stays as-is (pre-existing, used by no active book — mentioned,
not deleted).

### B. Per-side fill timing in `replay()`

Today `same_day_fill: bool` covers the whole strategy. Buys and sells now differ,
so replace with two enums, defaults preserving current behaviour exactly:

- `entry_fill: 'next_close' (default) | 'next_open' | 'same_close'`
- `exit_fill: 'next_close' (default) | 'same_close'`

Crossover v2 books use `entry_fill='next_open'`, `exit_fill='same_close'`.

`replay()` takes an optional `open_prices` panel (date × instrument, `open_adj`).
Used **only** for `next_open` entry fills. NAV valuation stays on `close_adj`.

### C. Intraday alerter (`scripts/foundation/crossover_monitor.py`)

New script on the existing 5-min cron. Per tick:

1. Load the 4 books' universes + open positions.
2. Pull prior-close `ema_fast`/`ema_slow` from `technical_daily`.
3. Compute P\* via `ema_cross_price`; sell level per book's `exit` param.
4. One Kite `quote()` call for the union of tokens (mirrors `desk_monitor`).
5. Emit ALERT events for fresh breaches, deduped one per (book, symbol, direction, date).
6. At the **15:15** tick only: re-evaluate armed sells → CONFIRM or disarm.

Reads only; books nothing. The nightly `mark` remains the sole writer of trades.

### D. Two portfolios

```
33ba1022  rename → "EMA Crossover 13/34 · Deathcross Close"
          params  → {fast:13, slow:34, notify:true, exit:"death_cross",
                     entry_fill:"next_open", exit_fill:"same_close"}

<new uuid>         "EMA Crossover 13/34 · EMA13 Close"
          params  → {fast:13, slow:34, notify:true, exit:"fast_ema",
                     entry_fill:"next_open", exit_fill:"same_close"}
          inception 2026-07-07, seeded by replay (D5)
```

Other 3 books gain `entry_fill`/`exit_fill` only; `exit` stays `death_cross`.

`_RESERVED_PARAMS` in [portfolio_run.py:80](../../../scripts/foundation/portfolio_run.py#L80)
needs `entry_fill`/`exit_fill` handling — they are runner-level, not strategy-ctor args.

### E. Telegram alert format — book identity leads

```
🟡 EMA 13/34 · EMA13 CLOSE — SELL SIGNAL (PROVISIONAL)
MRPL · ₹163.40 broke below EMA13 ₹165.55
Not a trade yet. Confirms only if it holds below at 15:15.

🔴 EMA 13/34 · EMA13 CLOSE — SELL CONFIRMED
MRPL · held below EMA13 at 15:15 (₹162.90 vs ₹165.55)
Executing at today's close.

✅ EMA 13/34 · EMA13 CLOSE — SOLD
MRPL · 476 @ ₹161.20 · 2026-07-30
```

The two books alert on the same names with different verdicts — the suffix in
every line is what makes that legible rather than confusing.

### F. Telegram reduction (D7)

Delete the `send_message_sync` call from senders 2, 3, 5, 6 and the failure alert
in 4. Resolve sender 7 (phantom script) by removing the systemd unit from the box.

**Stated once, then executed as instructed:** pipeline-failure pushes (4, 5, 6)
are how a broken feed surfaces within a day instead of a week. After removal that
signal lives only in `/health`, `/admin/data-status` and the nightly snapshot —
pull, not push. The FM has reaffirmed; proceeding.

### G. Frontend (`strategyDescription.ts` + `PortfolioDetailV4.tsx`)

`describeStrategy` gains crossover-v2 copy. Every item below is currently absent
from the page and must appear:

1. The 3-event buy sequence with the actual times.
2. The 3-event sell sequence with 15:15 named.
3. Which level this book sells on, with the plain-English contrast to its twin.
4. Fill prices: buys at next session's **open**, sells at same day's **close**.
5. Price basis is the **adjusted** close/open, not the raw traded price.
6. Prioritisation: highest Atlas composite on the signal day wins the slot; tie-break by instrument key; **unfilled candidates are dropped, not queued**; `min(NAV×8%, cash/remaining)` sizing means later names can be cash-squeezed.
7. Exits clear slots before entries in the same session.
8. These books carry **no risk stop**, deliberately.
9. **The three backtest/live divergences below**, stated on the page not buried here.
10. A link between the twin books so either page reaches the other.
11. MF golden-cross books: state plainly that they cannot do intraday (one NAV per day) and stay on daily-NAV logic.

### I. Decision trail — every trade says why it happened

**Current state:** `portfolio_trades.rationale` (nullable `text`) already exists and is
already populated for desk fills via `desk_rationale()`
([portfolio_run.py:545](../../../scripts/foundation/portfolio_run.py#L545)) — **80/80
desk trades carry it, 0/25,584 `signal` trades do.** The frontend query never selects
it, so [TradesTable.tsx:72](../../../frontend/src/components/portfolios/TradesTable.tsx#L72)
shows only the bare `reason` word. The column is the right home; it is simply unused
by the strategy path. No new mechanism.

#### I.1 One new column

`reason` stays the CHECK-constrained *kind*; `rationale` carries the prose. Conviction
is a **number you will want to sort and filter on**, so it gets its own column rather
than being parsed back out of a sentence:

```sql
ALTER TABLE atlas_foundation.portfolio_trades
  ADD COLUMN composite_at_signal numeric(20,4);
```

Nullable — historical rows stay NULL until their next backtest rebuild repopulates them.
No change to the `reason` CHECK: a death-cross exit and an EMA13 exit are both `signal`,
and the book's own `exit` param already says which is which.

#### I.2 Where it is generated

Inside `engine._book()`. The engine is the **only** place that knows the full decision
context at the moment of the fill: the sorted candidate list, each name's composite, how
many slots were open, who was passed over, and whether sizing hit the 8% cap or ran out
of cash. Reconstructing that after the fact is guesswork; generating it there is free.

The engine stays pure — the rationale is composed from values already in scope and
returned in the trades frame. No new I/O.

#### I.3 What each rationale says

**Buy (signal):** rule fired, both levels, both dates, conviction, rank, slots, who lost
the slot, and why the size is what it is.

```
EMA13 crossed above EMA34 intraday on 16-Jul at ₹163.88; close confirmed ₹173.33.
Filled at 17-Jul open. Conviction 61.4 — ranked #2 of 5 names that crossed, 3 slots
open. Passed over: SUNPHARMA (54.2), TATAMOTORS (49.8). Sized to the 8% cap.
```

Cash-constrained variant, so a small position never looks like a mistake:

```
... Sized to ₹73,673 — cash-limited, not the 8% cap; 4 names shared the remaining cash.
```

**Sell (signal), death-cross book:**

```
EMA13 crossed below EMA34 intraday at ₹121.22; still below at 15:15 (₹120.40).
Closed at that day's close. Exit rule for this book is the death cross.
```

**Sell (signal), EMA13 book:**

```
Price broke below EMA13 ₹165.55 intraday at ₹163.40; still below at 15:15 (₹162.90).
Closed at that day's close. Exit rule for this book is the EMA13 break.
```

**Sell (stop)** — not used by these books, but the generator is shared:

```
Stop hit: prior close ₹412.30 is more than 10% below entry ₹458.10. Sold at this
session's close.
```

**Buy (inception)** — FM baskets:

```
FM basket pick at inception, sized to its target weight of 25% of capital.
```

Rationale carries **reasoning only**. Numbers that already have columns
(`realized_pnl`, `holding_days`, `cost`, `tax`) are never restated in prose.

#### I.4 Why-this-one-and-not-that-one

The "passed over" clause is the part that answers the FM's actual question. `_enter`
already builds the ranked candidate list and slices it to `open_slots`
([engine.py:224-225](../../../atlas/portfolio/engine.py#L224-L225)); the dropped names are
currently discarded silently. They are not trades, so they get no row of their own —
naming them in the rationale of the trades that *did* fill is the whole answer at zero
schema cost.

#### I.5 Shared-engine consequence (deliberate, not scope creep)

`_book()` serves all 19 books and all 5 reasons. Adding the generator there means the
Rank, Desk and MF books get commentary too. That is the correct outcome: a NULL
rationale on some rows next to prose on others reads as broken. Desk fills keep their
agent-authored thesis — `desk_rationale()` wins where it is already set, the generator
never overwrites it.

Backtest rows get it free on the next rebuild (§H), so the full 8-year trade log
becomes self-documenting.

#### I.6 Frontend

- Trades query selects `rationale` + `composite_at_signal`.
- `TradesTable` gains a sortable **Conviction** column and a **Why** cell. Prose is long, so the cell truncates with the full text on hover/expand rather than wrecking the row height.
- **Twin cross-reference is derived at read time, not stored.** On a 13/34 page, show what the twin book did with the same name on the same date ("twin: still holding"). Both books' trades are already queryable, so this needs no writer-side coupling between books — and it stays live rather than frozen into a string at book time.
- CSV export includes both new fields (per the frontend rule that every table is exportable).

### H. Backtest freshness (the FM's original complaint)

The 13/34 backtest curve is frozen at **2026-07-21** because nothing rebuilds it —
`rebuild_backtest()` is manual-CLI-only and in no cron. Every book is stale:
13/34 at 21 Jul, the other 3 stock + 4 rank books at **08 Jul**, MF books at 27 Jul.

Add `portfolio_backtest_rebuild` as a step in [atlas_weekly.sh](../../../scripts/ops/atlas_weekly.sh)
(weekly is enough for an 8-year replay × 19 books; nightly is wasteful).

---

## The three honest divergences (must be on the page, not just here)

1. **A 5-min poll cannot see what the daily low sees.** Live samples the price ~78×/day; the backtest uses `low_adj`, the true intraday minimum, catching dips that recover inside one poll window. **The backtest will show more sells than live fires.** Kite minute history doesn't reach 8 years, so replaying poll-resolution bars is impossible. Permanent and structural.
2. **There is no 15:15 price in daily data.** The backtest proxies the 15:15 lock with the close; live uses the real 15:15 quote.
3. **`close_adj`/`open_adj` are adjusted series.** Booked live prices are frozen once written, but a future split/bonus silently restates historical *backtest* fill prices.

---

## Schema

One new table and one new column. No change to `run_type` or `reason` CHECKs (both
books use `live`/`backtest` and `signal`/`inception`).

```sql
-- decision trail (§I): conviction gets a real column so it is sortable/filterable;
-- the prose lives in the existing portfolio_trades.rationale
ALTER TABLE atlas_foundation.portfolio_trades
  ADD COLUMN composite_at_signal numeric(20,4);
```

```sql
CREATE TABLE atlas_foundation.crossover_alerts (
  alert_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  portfolio_id  uuid NOT NULL REFERENCES atlas_foundation.portfolio_master(portfolio_id),
  instrument_id uuid NOT NULL,
  symbol        text NOT NULL,
  direction     text NOT NULL CHECK (direction IN ('buy','sell')),
  stage         text NOT NULL CHECK (stage IN ('provisional','confirmed','disarmed')),
  alert_date    date NOT NULL DEFAULT (now() AT TIME ZONE 'Asia/Kolkata')::date,
  level         numeric(20,4) NOT NULL,
  quote         numeric(20,4) NOT NULL,
  ema_fast      numeric(20,4),
  ema_slow      numeric(20,4),
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (portfolio_id, instrument_id, direction, stage, alert_date)
);
CREATE INDEX ON atlas_foundation.crossover_alerts (portfolio_id, alert_date);
CREATE INDEX ON atlas_foundation.crossover_alerts (instrument_id);
```

`numeric` not float (money). Tz-aware. FK indexed. Per global DB conventions.

---

## Acceptance Criteria

1. `ema_cross_price` self-check asserts MRPL 16-Jul-2026 `P* ≈ 163.88` from real stored EMAs.
2. `EmaCross(exit="death_cross")` emits **byte-identical** events to today's `EmaCross` on the same real panel — the default path provably does not move.
3. `EmaCross(exit="fast_ema")` on real 13/34 data emits a sell for MRPL on the session its low first breaks `ema_13`, and the death-cross variant does **not**.
4. `replay(entry_fill='next_open')` books the entry at the next session's `open_adj`; `replay(exit_fill='same_close')` books the exit at that session's `close_adj`. Asserted against real stored OHLCV.
5. `replay()` defaults (`next_close`/`next_close`) reproduce all 19 books' existing backtest NAV series unchanged.
6. Re-run the 13/34 backtest: MRPL's entry confirms at the **17-Jul** close (the 16th's close left ema13 154.89 under ema34 155.44, so it only alerted) and fills at the **20-Jul open, ₹172.00** — against the ₹174.49 the live book actually paid at that day's close. **This criterion originally claimed 16-Jul @ ₹157.47; that outcome is only reachable WITHOUT the close-confirmation step, and D9 rejected that variant.**
7. Both 13/34 books show ≥8y `backtest` and a `live` series starting 2026-07-07, with different trade counts.
8. `crossover_monitor.py` on a real Kite session emits exactly one `provisional` row per (book, symbol, direction, day) across repeated 5-min runs.
9. The 15:15 tick promotes a sustained breach to `confirmed` and marks a recovered one `disarmed`; the nightly `mark` books only `confirmed`.
10. `grep -rn "send_message_sync" scripts/ atlas/` returns **only** `portfolio_alerts.py` and `notify.py` itself.
11. A Telegram alert from either 13/34 book names its own book in the first line.
12. Both portfolio pages render all 11 items of §G; a fresh reader can state both sell levels, both fill prices, and the slot-priority rule from the page alone.
13. `validate_portfolios.py` and `make gate` green.
14. `scripts/ops/schema_gate.py` still 0.
15. After the weekly orchestrator runs, every book's backtest `max(date)` is within 7 days of EOD.
16. Zero synthetic data anywhere — every test asserts on real records pulled from `atlas_foundation` (rule #0).
17. **Every** trade written by the engine has a non-NULL `rationale`. `select count(*) from portfolio_trades where run_type='live' and rationale is null` returns 0 for rows booked after switch-on.
18. Every `signal` buy has a non-NULL `composite_at_signal` matching `atlas_lens_scores_daily.composite` as-of that trade's signal date, asserted against real stored scores.
19. A buy rationale on a day where candidates exceeded open slots **names the passed-over instruments and their scores**; the count of named also-rans equals `candidates − slots_filled`.
20. A cash-limited buy says so explicitly and a cap-limited buy says so; the two are distinguishable from the text alone.
21. Death-cross and EMA13 sell rationales state different rules and different levels for the same symbol on the same date across the twin books.
22. Desk fills keep their agent-authored thesis — the generator never overwrites a rationale that `desk_rationale()` already set (assert on a real desk trade).
23. `TradesTable` renders a sortable Conviction column and a Why cell; CSV export contains both fields.
24. The twin cross-reference is computed at read time — no stored rationale string mentions the other book.

---

## Testing Plan

| Layer | What | Count |
|---|---|---|
| Unit | `ema_cross_price` both directions; `exit` param level selection; `entry_fill`/`exit_fill` enum resolution; alert-format strings incl. book suffix | +9 |
| Unit | Default-path regression: `exit="death_cross"` + default fills == today's output on a real panel | +2 |
| Integration | `EmaCross(exit=...)` over real 13/34 technicals; MRPL 16-Jul entry; both variants' divergence on a real name | +4 |
| Integration | `replay()` open-fill and same-close-fill against real stored OHLCV; 19-book default-unchanged sweep | +3 |
| Integration | `crossover_monitor` dedup across repeated runs; 15:15 promote/disarm | +3 |
| Unit | Rationale generator: all 5 reasons; cap-limited vs cash-limited wording; also-ran clause count; death-cross vs EMA13 phrasing; desk-thesis not overwritten | +7 |
| Integration | `composite_at_signal` matches `atlas_lens_scores_daily` as-of the signal date on real trades; no NULL rationale after a real replay | +2 |
| Gate | `validate_portfolios.py` extended to assert both books' fill prices match the stored OHLCV column their `*_fill` param names, **and** that no engine-written trade has a NULL rationale | +1 |

All fixtures are real DB reads. No invented inputs (rule #0). **31 tests total.**

---

## Rollback

| Change | Undo |
|---|---|
| Params on 5 books | Restore prior `params` JSONB (captured pre-change). Behaviour is param-driven, so this alone reverts the signal rule. |
| New EMA13 book | `status='retired'` on `portfolio_master`; its rows are namespaced by `portfolio_id`. |
| `crossover_alerts` table | `DROP TABLE` — read-only feed, nothing else references it. |
| `composite_at_signal` column | `DROP COLUMN` — additive and nullable; nothing computes off it. |
| Rationale generator | Text-only, no behavioural effect. Reverting the commit leaves `rationale` NULL on new rows exactly as today. |
| Engine `*_fill` enums | Defaults reproduce current behaviour (AC #5), so unset params = today's system. |
| 5-min cron step | Remove the line from `atlas_intraday.sh`; the alerter writes no trades. |
| Telegram removals | Revert the commit; `send_message_sync` is a one-line call per site. |
| Deathcross backtest re-run | `run_type='backtest'` rows are deleted + rewritten idempotently by `rebuild_backtest`. Live trades never touched (D4). |

Deploy per [docs/deploy-hygiene.md](../../deploy-hygiene.md): build to completion → confirm `BUILD_ID` → clear fetch-cache → reload **once**.

---

## Effort

| Component | Est. |
|---|---|
| A — `exit` param on `EmaCross` | 1h |
| B — per-side fill timing in `replay()` + open panel | 3h |
| C — `crossover_monitor.py` + 15:15 lock + dedup | 4h |
| D — migration + params + seed replay of the new book | 2h |
| E — 3-stage alert formats | 1h |
| F — Telegram reduction (6 sites + systemd unit) | 1h |
| G — frontend copy, 11 items, both books cross-linked | 3h |
| H — weekly backtest rebuild step | 30m |
| I — rationale generator in `_book()`, all 5 reasons | 2h |
| I — `composite_at_signal` column + migration | 30m |
| I — trades-table Conviction + Why columns, twin cross-ref, CSV | 2h |
| Tests (31) + validator gate | 5h |
| Backtest re-run + verification of all 4 books | 2h |
| **Total** | **~26h** |

---

## Files Reference

| File | Change |
|---|---|
| `atlas/portfolio/strategies/ema_cross.py` | `exit` param; per-variant exit level in `events()` |
| `atlas/portfolio/engine.py:99-112` | `entry_fill`/`exit_fill` enums; `open_prices` panel |
| `scripts/foundation/portfolio_run.py:80` | `_RESERVED_PARAMS` += fill params; load open panel |
| `scripts/foundation/portfolio_data.py:116` | `load_open_prices()` |
| `scripts/foundation/portfolio_alerts.py` | 3-stage formats; book-name prefix |
| `scripts/foundation/crossover_monitor.py` | **new** — intraday alerter + 15:15 lock |
| `scripts/ops/atlas_intraday.sh` | add the monitor step |
| `scripts/ops/atlas_weekly.sh` | add `portfolio_backtest_rebuild` |
| `scripts/foundation/desk_monitor.py:103` · `desk_orders.py:385-387` · `qa_weekly.py:106-108` · `atlas_daily.sh:149` · `atlas_weekly.sh:60` | remove `send_message_sync` |
| `systemd/atlas-intraday-notify.service` | remove (phantom script) |
| `migrations/versions/` | `crossover_alerts` + `portfolio_trades.composite_at_signal` |
| `atlas/portfolio/engine.py` (`_book`, `_enter`) | rationale generator; conviction + also-rans into the trades frame |
| `frontend/src/lib/strategyDescription.ts` | crossover-v2 explainer, 11 items |
| `frontend/src/components/portfolios/PortfolioDetailV4.tsx` | twin-book cross-link; divergence note |
| `frontend/src/components/portfolios/TradesTable.tsx:72` | sortable Conviction column; Why cell; CSV fields |
| `frontend/src/lib/queries/portfolios.ts` | select `rationale` + `composite_at_signal`; twin read-time lookup |
| `scripts/foundation/validate_portfolios.py` | fill-price + no-NULL-rationale assertions |
| `tests/unit/` · `tests/integration/portfolio/` | 31 tests |

---

## Out of Scope

- EMA-close twins for 10/21, 21/50, 50/200 — they get v2 *timing* only (D6).
- The 5 MF golden-cross books — one NAV/day, no intraday possible. Documented on their pages, logic unchanged.
- The 4 Rank and 4 Desk books.
- Re-booking the deathcross book's 28 existing live trades (D4).
- Any real-money order routing. Atlas books trades; it does not place them.
- A gap-up guard on next-open buy fills. FM rule is "earliest possible price", unqualified.

---

## Key Risks

1. **The intraday rule will sometimes buy a spike that fully reverses** — the close-confirmation step filters the worst of it (a reversal that closes back below never confirms), but a name that closes above and rolls over tomorrow is a real new failure mode. The 8-year re-run quantifies it before capital moves.
2. **Twin books double the alert volume on the same names with opposite verdicts.** Mitigated by the book suffix leading every line; if it still reads as noise, the FM's next lever is muting the shadow-ish book, not changing the rule.
3. **Divergence #1 is structural.** If the FM later reads the backtest as a promise about live fills, that is a misread the page must actively prevent — hence §G item 9 being an acceptance criterion, not a footnote.
