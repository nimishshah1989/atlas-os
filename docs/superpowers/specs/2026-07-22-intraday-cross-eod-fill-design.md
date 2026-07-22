# Intraday-cross detection, same-day EOD fills, and Telegram alerts

**Date:** 2026-07-22
**Status:** approved (FM), ready for implementation plan
**Scope:** the 4 **stock** EMA-cross portfolios — `10/21`, `13/34`, `21/50`, `50/200`.
The 5 MF golden-cross variants stay on daily-close logic (NAV prints once a day —
no intraday).

## Problem

The engine detects a crossover only at the daily **close** and fills the **next**
session ([engine.py:5-7](../../../atlas/portfolio/engine.py#L5-L7),
[engine.py:97](../../../atlas/portfolio/engine.py#L97)). For MRPL in the 13/34
portfolio this booked a buy on **2026-07-20 @ ₹174.49**, when the golden cross
actually flashed **intraday on the 16th**: MRPL opened ₹163.75, ran to ₹178.40 on
~25× volume (204M sh), then faded to close ₹157.47. The provisional cross threshold
that day was **₹163.88** — breached from the open. The daily-*close* EMA only
confirmed on the 17th (close ₹173.33). Net: the +1-session lag cost ~10% of entry.

The EMA math is **not** at fault — [primitives.py:100](../../../atlas/compute/primitives.py#L100)
uses pandas-ta's SMA-seeded EMA (same seeding as TradingView), warmed up over years,
and an independent recompute matched the stored `ema_13`/`ema_34` exactly. The gap
is purely **daily-close vs intraday**.

## Decisions (FM)

1. **Signal rule:** intraday cross → fill at **that day's EOD close**. Act on the
   intraday cross even if it reverses by close (earliest entry; accepts whipsaw).
2. **Backtest parity:** the daily **high** (entry) / **low** (exit) is a sufficient
   statistic for "did the provisional cross happen intraday", so the model is
   backtestable on the daily OHLC we already hold back years.
3. **Live detection:** real-time 15-min Kite fetch (new infra) — the FM wants the
   intraday desk, not just an EOD alert.
4. **History:** full backtest re-run for the 4 portfolios + re-book existing live
   trades under the new rule.
5. **Alerts:** both a real-time intraday heads-up AND an authoritative EOD
   booked-trade message. Start with 13/34.

## Components

### A. Crossover-threshold primitive (shared core)

Pure function: given prior-day confirmed `ema_fast`, `ema_slow` and spans
`fast`,`slow`, return the price `P*` at which a provisional EMA (yesterday's EMA +
today's live price as the forming bar) makes fast = slow.

```
α_n = 2/(n+1)
P* = [ema_slow·(1−α_slow) − ema_fast·(1−α_fast)] / (α_fast − α_slow)
```

Since `α_fast > α_slow`, price **> P\*** ⇒ fast>slow (golden), **< P\*** ⇒ death.
One formula feeds **both** consumers below, so backtest and live cannot diverge.
Ships an assert self-check (MRPL 16th: `P*≈163.88`).

### B. Intraday-cross event detection

New state machine over daily OHLC + prior-day confirmed EMAs, replacing the
`fast>slow` close-comparison for these 4 portfolios:

- **flat → entry** on day D if `high(D) ≥ P*(D)` (P\* from EMA(D−1), prior fast<slow)
- **long → exit** on day D if `low(D) ≤ P*(D)`

State tracks **intraday-cross events, not the daily-close EMA relationship** — they
diverge on reversal days (the 16th crossed intraday, closed below). ≤1 entry + ≤1
exit per name per day. Implemented as an opt-in mode on `EmaCross` so only these 4
portfolios use it; the MF variants keep the close-comparison state.

### C. Engine same-day fill

Per-portfolio `same_day_fill` flag in `replay()`: when set, an event on day D fills
at **close(D)** instead of the next session. Gated so every other portfolio keeps
the no-lookahead next-session timing untouched. Small change to the
`entries_at`/`exits_at` mapping.

### D. Full backtest re-run + live re-book

Re-run the backtest for the 4 portfolios under the new logic (rewrites the track
record the FM replicates); correct existing live trades (MRPL 20th @174.49 → 16th
@157.47). `validate_portfolios.py` stays green.

### E. Real-time 15-min alerter + Telegram (13/34 first)

New cron script reusing [atlas_intraday.sh](../../../scripts/ops/atlas_intraday.sh)
+ [auth.py](../../../atlas/intraday/auth.py) Kite session +
[notify.py](../../../atlas/intraday/notify.py). Every 15 min during 09:15–15:30 IST:
fetch quotes for the portfolio universe, compute provisional EMAs via **A**, fire
Telegram the moment a name crosses. Dedup with a small intraday alert-log table
(once per name/direction/day). Two alert types:

- **Intraday heads-up:** `🟢 EMA 13/34 · MRPL · EMA13 crossed above EMA34 · BUY signal · ~₹164`
- **EOD booked-trade** (nightly batch, authoritative): `✅ EMA 13/34 · BOUGHT MRPL · 476 @ ₹157.47`

The live trade still **books at EOD** in the nightly `portfolio_run.py mark` batch
(intraday is heads-up + MOC prep, not a separate intraday fill).

### F. Verification gate (definition of done, #2)

Independently recompute EMAs + re-derive every trade for 13/34, 21/50, 50/200 from
**real records** (rule #0 — no fixtures) and diff against the system. Done for 13/34
(exact match); extend to 21/50 and 50/200.

## Phasing

- **Phase 0:** F — verify current calc is correct (read-only).
- **Phase 1:** A+B+C+D — signal fix + corrected track record (backtestable, no live
  infra). Fixes the MRPL-style late entry on its own.
- **Phase 2:** E — real-time intraday alerter + Telegram, 13/34 first.

## Data facts (grounding)

- 4 stock ports: `10/21` (18ff8998), `13/34` (33ba1022), `21/50` (fa1232aa),
  `50/200` (89379c8e); all `[stock]`, `max_position_pct=0.08` (~12 slots).
- `EMA_PERIODS = (10, 13, 21, 34, 50, 200)` — every needed period is computed
  ([technicals.py:28](../../../scripts/foundation/technicals.py#L28)).
- EMAs read from `atlas_foundation.technical_daily`; prices/OHLC from `ohlcv_stock`.
- Telegram env: `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` (graceful no-op if unset).

## Key risk

The intraday rule will sometimes **enter on a spike that fully reverses** — a false
entry the old close-confirmation filtered. Phase 1's full backtest re-run quantifies
the net effect (win rate, avg entry improvement, added whipsaw) across all four
portfolios before real capital is committed.
