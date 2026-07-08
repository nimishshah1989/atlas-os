# EMA crossover strategies — deep dive

*Second- and third-degree analysis of the four crossover books (50/200, 21/50, 10/21,
13/34), from the 8-year survivor-only backtests. Written before implementing any filters,
so we choose them with eyes open. All numbers are stored engine output on real
`atlas_foundation` data.*

## 1. Why the backtests look so good — and why that's partly a mirage

The headline returns (+300% to +423% over ~7.5y) are real arithmetic, independently
verified to the paisa. But **three structural effects inflate them**, and only the first
is visible on the board:

1. **Survivorship (the big one).** The backtest universe is *today's* Atlas-scored names
   applied backwards. Of ~2,093 names ever scored since 2019, only 498 are in the current
   set — **1,595 names (76%) never enter the backtest at all.** Worse, our price data
   (`ohlcv_stock`) only contains instruments that still exist: **zero delisted names.** A
   momentum strategy that buys breakouts is *exactly* the kind that would have held the
   disasters — Yes Bank, DHFL, SME blow-ups — and those are **invisible here.** The
   backtest cannot show a single trade that went to zero, because the data has none.
   → Real drawdowns are worse than any number below. Treat returns as an **upper bound.**

2. **No transaction slippage / impact.** Fills are at the close, costs are STT+stamp+GST
   only. The small-cap breakouts that produce the biggest wins (and losers like AIIL,
   TECHNOE, VIJAYA below) would move on the fills at real size.

3. **Point-in-time universe unavailable.** We can't reconstruct the true historical
   index membership, so selection is made with 2026 hindsight.

**This is the answer to "why isn't everyone doing this?"** — the backtest is a
survivor-only, frictionless, hindsight-selected best case. The live experience is lower
return, deeper drawdown, and (point 4) psychologically brutal.

## 2. The engine of returns: low win rate, fat right tail

| Book | Win rate | Avg win | Avg loss | Payoff | Winner hold | Loser hold |
|---|---|---|---|---|---|---|
| 50/200 | **27%** | +₹89.8k | −₹10.8k | **8.3×** | 681d | 92d |
| 21/50 | 35% | +₹42.5k | −₹11.2k | 3.8× | 167d | 36d |
| 13/34 | 35% | +₹33.0k | −₹9.3k | 3.6× | 107d | 25d |
| 10/21 | 35% | +₹21.8k | −₹7.4k | 3.0× | 70d | 18d |

The whole edge is **"cut losers fast, ride winners long."** 50/200 loses on ~3 of every 4
trades but wins 8× as much as it loses, and holds winners ~7× longer than losers. This is
textbook trend-following and it is *structurally* sound — but note the trade-offs:

- **The slower the book, the higher the payoff but the lower the win rate.** 50/200 is the
  purest expression (8.3× payoff, 27% win rate); the fast books trade the payoff down for a
  slightly higher hit rate and far more churn (10/21: 942 sells vs 122 for 50/200).
- **Losses are fat-tailed.** In every book the **worst 10% of losers is ~30–36% of all
  losses.** A handful of bad trades dominate the loss column — so tail control matters more
  than average-loss control (which is why a fixed 10% stop, tested, doesn't help — see §4).

## 3. What the losers actually are

The biggest losers are **fast whipsaws — false breakouts that reversed within days:**

| Book | Worst trades (loss / hold) |
|---|---|
| 13/34 | RKFORGE −₹66k/7d · JINDALSAW −₹55k/44d · HINDZINC −₹54k/14d · TECHNOE −₹53k/17d |
| 10/21 | AIIL −₹53k/7d · RKFORGE −₹52k/8d · ENGINERSIN −₹50k/28d · VIJAYA −₹44k/15d |
| 21/50 | WELSPUNLIV −₹57k/42d · TECHNOE −₹52k/14d · TRAVELFOOD −₹42k/42d |
| 50/200 | TECHM −₹49k/77d · CASTROLIND −₹46k/34d · PETRONET −₹42k/45d |

Two clear patterns:
- **Fast books (10/21, 13/34): the worst losers are held 7–17 days.** These are momentum
  head-fakes — a cross fires, the name pops, then rolls over. RKFORGE appears as a top-3
  loser in *two* books on the same date. These are **not** fundamental disasters; they're
  noise trades the fast EMAs can't filter.
- **Slow book (50/200): losers are held 34–77 days** — slower momentum *failures* (a real
  uptrend that quietly died), not whipsaws. Fewer, but the strategy is slow to give up.

Many are **mid/small-caps** (AIIL, TECHNOE, WELSPUNLIV, TRAVELFOOD) — which ties back to
the capacity and slippage caveats in §1.

## 4. When the strategy faltered — it's market beta, not stock picking

Drawdown timing for 50/200 (representative):

- **Max DD −34.3% on 24 Mar 2020 — the COVID crash.** The book was fully invested going in;
  every position fell together. The crossover exit (death cross) lags a crash by weeks, so
  it rode the whole way down before de-risking.
- **2025: −28.8% intra-year** (a sharp 2025 correction). **2022: −17.5%.**

**The drawdowns are systematic (market-wide), not idiosyncratic.** This is the crucial
insight for risk management: crossover DD is **beta to fast market crashes**, so a
per-position stop can't fix it (all names crash together, and by the time each is 10% down
the portfolio already is). This is exactly why:

- The **10% entry stop was rejected** on crossovers — it barely fires on the way into a
  crash (positions gap down together) and otherwise just cuts winners that dipped (it
  *halved* 21/50's return).
- The **fast-EMA trailing stop whipsaws** (13/34 +423%→+45%) — it fires constantly in the
  choppy tapes between crashes.
- The **peak-trailing stop helped only 50/200** and hurt the faster books.

**The right tool for crossover drawdown is a market-regime filter, not a price stop:** stop
*entering* new breakouts when the broad market itself is below its own trend (e.g. NIFTY
500 < its 200-DMA, or breadth collapsing), and/or de-risk the whole book to cash in a
confirmed risk-off regime. That attacks the actual cause (being fully invested into a
systematic crash) instead of the symptom (individual names dropping).

## 5. Hidden risks not visible on the board

1. **Invisible losers (survivorship)** — §1. The single largest unmodelled risk.
2. **Fully-invested-into-a-crash** — no regime awareness; −34% in COVID is the proof.
3. **Psychological ruin risk** — a **27–35% win rate** means long strings of losses. Most
   people (and many FMs) abandon a trend system during its inevitable drawdown/loss-streak,
   locking in the losses and missing the fat-tailed winners that pay for everything. The
   backtest can't feel this; a live investor does.
4. **Capacity / liquidity** — the biggest wins and losses cluster in mid/small-caps whose
   real fills at ₹10L+ size would differ from the close.
5. **Regime dependence** — trend-following mints money in trending markets (2020–2021,
   2023–2024 here) and bleeds via whipsaw in choppy/sideways/mean-reverting years. A backtest
   dominated by a few strong trends overstates the steady-state.

## 6. Candidate filters to test next (your pick)

Ranked by expected impact on the *real* (not survivor) risk:

- **A · Market-regime gate (highest priority).** No new entries when NIFTY 500 < its
  200-DMA (or a breadth trigger); optionally move the book to cash in confirmed risk-off.
  Directly targets the −34% systematic-crash drawdown that stops can't. *Cost:* misses the
  first leg of V-shaped recoveries.
- **B · Breakout-quality filter.** Require the entry to also clear a relative-strength /
  above-200-EMA / volume-confirmation bar, to reject the RKFORGE/TECHNOE-style head-fakes
  that dominate the loss tail. Especially valuable for the fast books.
- **C · Liquidity floor.** Minimum ADV / market-cap to enter, capping capacity risk and the
  small-cap slippage that flatters the backtest.
- **D · Catastrophe-only stop (wide, e.g. 25–30% from peak).** Not for DD reduction (proven
  not to work) but purely as live tail insurance against the invisible-loser scenario the
  backtest can't show — accept a small in-sample cost for real-world protection.

**Recommendation:** test **A + B** first (regime gate + breakout quality). They attack the
two things that actually drive crossover risk — systematic crashes and false breakouts —
whereas stops (C/D aside) fight the wrong enemy. We prototype, show before/after on all four
books, and you decide what goes live.

---

*Data: 8y backtests, `atlas_foundation.portfolio_*`, survivor-only universe. Independent
verification of the arithmetic: reproduced to the paisa. The honest caveat on every number
is §1.*
