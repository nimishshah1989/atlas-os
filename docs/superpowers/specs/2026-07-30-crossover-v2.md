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

One new table. No change to `run_type` or `reason` CHECKs (both books use
`live`/`backtest` and `signal`/`inception`).

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
6. Re-run 13/34 Deathcross Close backtest: MRPL entry moves from 20-Jul @ ₹174.49 to **16-Jul @ ₹157.47**.
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

---

## Testing Plan

| Layer | What | Count |
|---|---|---|
| Unit | `ema_cross_price` both directions; `exit` param level selection; `entry_fill`/`exit_fill` enum resolution; alert-format strings incl. book suffix | +9 |
| Unit | Default-path regression: `exit="death_cross"` + default fills == today's output on a real panel | +2 |
| Integration | `EmaCross(exit=...)` over real 13/34 technicals; MRPL 16-Jul entry; both variants' divergence on a real name | +4 |
| Integration | `replay()` open-fill and same-close-fill against real stored OHLCV; 19-book default-unchanged sweep | +3 |
| Integration | `crossover_monitor` dedup across repeated runs; 15:15 promote/disarm | +3 |
| Gate | `validate_portfolios.py` extended to assert both books' fill prices match the stored OHLCV column their `*_fill` param names | +1 |

All fixtures are real DB reads. No invented inputs (rule #0).

---

## Rollback

| Change | Undo |
|---|---|
| Params on 5 books | Restore prior `params` JSONB (captured pre-change). Behaviour is param-driven, so this alone reverts the signal rule. |
| New EMA13 book | `status='retired'` on `portfolio_master`; its rows are namespaced by `portfolio_id`. |
| `crossover_alerts` table | `DROP TABLE` — read-only feed, nothing else references it. |
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
| Tests (22) + validator gate | 4h |
| Backtest re-run + verification of all 4 books | 2h |
| **Total** | **~21h** |

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
| `migrations/versions/` | `crossover_alerts` |
| `frontend/src/lib/strategyDescription.ts` | crossover-v2 explainer, 11 items |
| `frontend/src/components/portfolios/PortfolioDetailV4.tsx` | twin-book cross-link; divergence note |
| `scripts/foundation/validate_portfolios.py` | fill-price assertion |
| `tests/unit/` · `tests/integration/portfolio/` | 22 tests |

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
