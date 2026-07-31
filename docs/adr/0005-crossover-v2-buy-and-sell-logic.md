# 0005 — Crossover v2: the buy and sell logic for every EMA-cross book

- **Status:** Accepted (2026-07-30)
- **Context chunk:** Crossover v2 (issue #204, spec `docs/superpowers/specs/2026-07-30-crossover-v2.md`)
- **Supersedes:** the timing half of `docs/superpowers/specs/2026-07-22-intraday-cross-eod-fill-design.md`

## Context

The 4 stock EMA-cross books detected a crossover only at the daily **close** and filled
at the **next** session's close, and the FM learned of a trade only after it was booked.
The cost was concrete: MRPL's 13/34 golden cross flashed intraday on 2026-07-16 and the
book bought on 2026-07-20 at ₹174.49 — a lag the FM never agreed to.

A 22-July spec was approved to fix it. Its Phase 1 merged to `main` but was gated behind
`params.intraday`, which no portfolio ever set, so it never ran. Phase 2 was never built.

This ADR records the rule that is now locked, and — more usefully — the three
alternatives that were tested against 8 years of real records and rejected.

## Decision

### BUY — all 4 stock crossover books

| Stage | Trigger | When |
|---|---|---|
| Alert | 5-min live price breaches P\*, computed from the PRIOR close's confirmed EMAs | 09:15–15:30 IST |
| Confirm | that day's **close** has fast EMA > slow EMA | after the close |
| Book | fill at the **next session's `open_adj`** | next morning |

Non-confirmation means no trade; the name re-arms. `entry_confirm="close"`,
`entry_fill="next_open"`.

### SELL — all 4 stock crossover books

| Stage | Trigger | When |
|---|---|---|
| Alert | 5-min live price breaches the down-cross level | 09:15–15:30 IST |
| Confirm | the breach **still holds at 15:15** | 15:15 IST |
| Book | fill at **that day's `close_adj`** | after the close |

A breach that recovers before 15:15 is logged `disarmed` and never becomes a trade.
`exit="death_cross"`, `exit_fill="same_close"`.

The asymmetry is deliberate and is the FM's rule: buys wait for tomorrow's open, sells
go out the same day because the next open can gap further down.

### Telegram

Three messages per trade — provisional, confirmed, booked — each naming its book in the
first line. Only the 13/34 book(s) send. The other six senders are removed.

## Alternatives rejected

### 1. Fill on the intraday breach alone, no close confirmation

This was decision #1 of the 22-July spec and, for most of this session, the
recommendation — on 13/34 it returned 428.4% against the close-confirmed 409.7%, with a
better drawdown (−35.3% vs −42.3%).

**Rejected because the backtest cannot model it honestly.** Detection uses the daily
HIGH, which captures every intraday touch including a single-tick spike; the fill is
then taken at the close. The variant therefore preferentially buys days that spiked and
reversed, at the cheap end of the day's range — and a 5-minute poll cannot reproduce
those fills.

The 10/21 book made the artifact impossible to miss:

| book | variant | 8y return | plausible? |
|---|---|---|---|
| 13/34 | close-confirmed | 409.7% | yes — stored curve ends at 407.6% |
| 13/34 | intraday | 428.4% | borderline |
| 10/21 | close-confirmed | 219.6% | yes |
| 10/21 | **intraday** | **178,972.9%** | **no** |

A 155% CAGR on a 12-slot equity book is not an edge. The faster the EMA pair, the more
crossings, the more the artifact compounds. The close-confirmed variant touches no
high/low on the entry side at all, and it reproduces the stored curve to within 2
percentage points — which is why it is trusted and the other is not.

### 2. Exit on price losing the fast EMA (the "EMA13 close" twin)

The FM asked for this as a second **live** book.

| exit | 8y return | max DD | trades | avg hold |
|---|---|---|---|---|
| death cross | 428.4% | −35.3% | 1,032 | 67d |
| fast EMA | 34.5% | −42.9% | 5,580 | 12d |

**Rejected for live capital.** 12× worse return, 5.4× the trades, and a worse drawdown —
it loses on every axis at once. This independently reproduces a finding already recorded
in `portfolio_run.py` before this work began ("a fast-EMA trail whipsaws them 4-5x,
13/34 +423%→+45%"): two separate implementations, same verdict.

It remains fully built and selectable via `exit="fast_ema"`, and is intended to run as a
**paper** book so the FM can watch it forward. It does not get capital until its own live
track earns it.

### 3. Rewriting the live track record under the new rule

Decision #4 of the 22-July spec was to re-book existing live trades. **Rejected**: the 28
booked trades stand. A track record that is retroactively edited is one nobody can
trust, and a replay bug would silently corrupt real cash and position state. The rule
change carries a dated marker on the chart instead.

## Consequences

- **A permanent backtest/live divergence remains, and must stay on the page.** The
  backtest sees every intraday touch via the daily low; a 5-minute poll does not. Sell
  signals will therefore appear more often in the backtest than they fire live. Kite
  minute history does not reach 8 years, so this cannot be closed — only disclosed.
- **The 15:15 lock has no backtest equivalent.** Daily bars hold no 15:15 price, so the
  backtest proxies it with the close. Live uses the real quote.
- Prices are the **adjusted** series. Booked live prices are frozen, but a future
  split or bonus silently restates historical *backtest* fill prices.
- Every engine-written trade now carries a `rationale` and a `composite_at_signal`, so a
  fill explains itself on the row rather than saying only "signal".

## Verification

`scripts/foundation/portfolio_sweep.py` replays the entry × exit grid over real history
and writes nothing back. It is the artifact that produced every number above and is how
any future rule change gets decided.

## Switch-on runbook

The behaviour is entirely param-driven, so turning it on is one statement — and turning
it off is the same statement with the keys removed. **Order matters: the schema must go
first, or the nightly mark fails on its first INSERT.**

**1. Schema** (additive, reversible; prod is managed directly, not by alembic — there is
no `alembic_version` table, so `alembic upgrade head` would try to replay the 0001
baseline dump over a live schema). Apply the DDL in
`migrations/versions/0002_crossover_v2_decision_trail.py` directly.

**2. Params** — all four stock crossover books at once:

```sql
UPDATE atlas_foundation.portfolio_master
   SET params = params || '{"intraday": true,
                            "entry_confirm": "close",
                            "exit": "death_cross"}'::jsonb
 WHERE strategy_key = 'ema_cross'
   AND asset_classes = '{stock}';          -- 10/21, 13/34, 21/50, 50/200
```

The 5 MF golden-cross books are excluded by the `asset_classes` filter and must stay
excluded: a fund prints one NAV a day, so it has no intraday, no high/low and no open.

**3. Verify before the next 19:30 cron**, since step 2 changes what the nightly mark
does:

```sql
SELECT name, params FROM atlas_foundation.portfolio_master
 WHERE strategy_key = 'ema_cross' ORDER BY name;
```

Then re-run the backtests so the stored curves match the live rule.

**Rollback:** `params = params - 'intraday' - 'entry_confirm' - 'exit'` restores the
pre-v2 behaviour with no code deploy, because every default in `EmaCross` and `replay()`
is the pre-v2 value.
