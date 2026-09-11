# Global Atlas — from representation to intelligence

**Written 2026-09-11.** A proposal, ranked. Companion to `intelligence-research.md` (the survey of what exists
in the open, with every claim's source and a list of what could not be verified). This document is the
opinion; that one is the evidence.

## The premise, stated bluntly

The board is now a good instrument for *seeing*. It is not yet an instrument for *knowing*, and the reason is
not a missing library — it is that nothing on the board has been measured against what happened next.

Two facts decide everything below:

1. **The composite is built from 2 of 5 lenses and its weights are seeds.** `/methodology` now says so on
   the page. A ranking whose predictive value has never been measured is a hypothesis with a decoration.
2. **Every input for measuring it is already stored.** Daily scores back to the first scored session,
   total-return closes, peer groups, and an `atlas_signal_ic` table with no producer. India already has the
   producer (`scripts/foundation/eval_signal.py`, `atlas/compute/signal_eval.py`).

So the order is: **measure what you have → derive what the data can say on its own → then add signals.**
Adding intelligence on top of an unvalidated score is adding storeys to a building nobody has surveyed.

ELI5 (Feynman): a score is a *bet* that a high number today means a better return later. You do not know if
the bet pays until you write down the number, wait, and check. Everything else is bookkeeping around that.

---

## Tier A — derivable tonight from tables that already exist

### A1. Signal validation — port `eval_signal` to Global, then extend it

**What it answers:** does a high lens score on day *t* precede a higher return over the next 21 / 63 / 126
sessions, within the peer group? Per lens, per composite, per era.

**How:** India's `eval_signal.py` computes forward returns in Postgres (the box has 2 vCPUs — this matters)
and rank IC, hit rate, t-stat and decile spread in ~120 lines of pure pandas. Port it over
`etf_scores_daily` / `lens_scores_daily` and `ohlcv_daily.close_tr`, partitioned by peer group. Then add the
four panels the table lacks and every serious factor study has: **turnover** of the top decile, **rank
autocorrelation** (is the signal stable day to day, or noise?), **ICIR** (mean IC ÷ its stdev), and the
**decay curve** (how many days the edge lasts). Copy the maths from alphalens-reloaded's `performance.py`;
do not take the dependency (dormant, and it wants an in-memory price panel the box cannot afford).

**What the FM sees:** on `/methodology`, beside each lens: "IC +0.04 over 21 sessions, hit rate 56%, t = 2.3,
edge gone by day 40" — or "no measurable edge", which is the more important sentence. And the lens weights
stop being seeds: the page's own promise ("a lens keeps its weight only once its signal is measured") becomes
a rule the nightly enforces.

**Effort:** approximately a week including tests on real rows. **Blocked on:** nothing.

### A2. The overnight digest — "what changed last night that matters"

**What it answers:** the question every FM asks at 6:30 IST and currently answers by scrolling.

**How:** SQL over consecutive sessions, each line named by its rule so it is glass-box by construction:

- **Decile migration:** `LAG(decile)` per instrument within peer group — entered the top decile, fell out of
  it, tier moved (Watch → High). The single most actionable line, and one window function.
- **Threshold crossings:** an `above_ema_*` flag flipping; `pos_52w` entering the top or bottom 2 points.
- **Novelty of magnitude:** "today's move is the largest in 250 sessions for this fund."
- **Robust cross-sectional outliers:** the day's change in each technical as a *robust* z-score (median and
  MAD, not mean and stdev, so one broken row does not mask the rest) within the peer group. This is also
  the check that would have caught the 30,000-percent volatility before it reached the map.
- **Filings and flow:** new 8-K item codes, short-interest settlements, holdings snapshots that moved
  top-ten weight.

Ranked by peer-group size and traded value so a $30bn fund's decile change outranks a $2M fund's. Surfaces on
`/pulse` as an "Overnight" strip, every line a door into the instrument.

**Effort:** approximately three days. **Blocked on:** nothing. Resist adding a model: every line above names
its own rule, which is the whole point.

### A3. Event studies over 8-K and short interest

**What it answers:** what is a filing *worth*? "8-K Item 5.02 (officer departure) in Industrials averaged
−1.8% cumulative abnormal return over the next five sessions across N events since 2019, t = −2.3." Today
`filings_8k` is a list of things that happened; this turns it into evidence about what such things do.

**How:** the classical market-model event study — estimation window regression of the stock on SPY (beta is
already in `technical_daily`), abnormal return in the event window, cumulative abnormal return over (0,+1),
(0,+5), (0,+21), cross-sectional t-test. ~150 lines. **No maintained Python library exists for this** (the
survey checked); build it. The discipline that matters is look-ahead: the estimation window ends before the
event, and an 8-K's *filing* timestamp is not its *event* timestamp. `insider_form4` has a table and no
wired producer (`ingest_form4` is commented out in the nightly); the same machinery applies the day it lands.

**What the FM sees:** on the catalyst lens's fold in `/methodology`, a table of item codes × sector with
average CAR and N, so the lens's points-per-item stop being a guess. And on a stock's page: "this filing
type has historically been worth −1.8% here."

**Effort:** approximately a week. **Blocked on:** nothing for 8-K and short interest.

### A4. Regime, with a confidence

**What it answers:** how broad is the market, and how sure are we? India already has a rules-based
classifier (`atlas/compute/regime.py`: breadth families + volatility → Risk-On / Constructive / Cautious /
Risk-Off). Global computes the same breadth nightly for `/pulse` and does not classify it.

**How:** port the rules classifier over Global's breadth (the S&P 500 universe, SPY as the index). Then add a
second opinion: `statsmodels.tsa.regime_switching.MarkovRegression` with switching variance on SPY daily
returns gives a daily *probability* of the calm vs stressed state, with a transition matrix and expected
durations that are human-readable. Publish both — "Constructive by the rules · 78% calm by the model" — and
gate on their disagreement: when the rules say Risk-Off and the model says 15% stressed, that disagreement
is itself a line in the digest.

**What the FM sees:** the regime on `/pulse`; every basket's NAV chart shaded by regime, so a return is read
in context ("earned in a Risk-Off month" means something different).

**Effort:** approximately four days. **Blocked on:** nothing. Glass-box caveat: the Markov probability
traces to a likelihood, not a rule; it is the second opinion, never the primary.

---

## Tier B — one data step away

### B1. The quality lens — the third lens, from tables that already exist

`etf_holdings` (N-PORT, weekly) and `lens_scores_daily` (nightly stock scores) both exist. The quality lens
is their join: the holdings-weighted mean of the held stocks' composites, and the share held in top-decile
names. `etf_lenses.py` already declares the sub-scores and returns `None` until they exist. **Building this
moves the board from "2 of 5" to "3 of 5" without a new feed.** Coverage will be partial (N-PORT is ingested
for ~400 funds a week and only equity funds look through to scored stocks) and the row must say so.

**Effort:** approximately four days. **Blocked on:** N-PORT coverage of the universe (check
`etf_holdings` row counts before starting).

### B2. Holdings overlap — "what does this add to what I already hold?"

The one question an ETF board can answer and a stock board cannot. Weighted overlap `Σ min(w_A, w_B)` over the
union of holdings; active share versus SPY; a basket's *effective* concentration ("your four-fund basket is
61% the same forty stocks"). A few lines of SQL over `etf_holdings`. No serious open-source implementation
exists (checked); nothing worth depending on.

**What the FM sees:** on a fund's page, its nearest neighbours by holdings, with the overlap; on a basket,
its look-through concentration.

**Effort:** approximately three days. **Blocked on:** the same N-PORT coverage as B1.

### B3. Basket versioning (already filed as a task)

Not intelligence, but it gates three things above: attribution over a changing book, rebalancing to a
regime, and "add to an existing basket." The marker refuses any non-inception trade today.

---

## Tier C — later, or never

- **Fama–MacBeth (linearmodels, NCSA):** "is the technical lens still paid after controlling for size,
  volatility and momentum?" The right question, *after* A1 exists. Two days on top of it.
- **Portfolio construction (skfolio, BSD-3):** hierarchical risk parity, benchmark-tracking optimisers. Only
  once baskets move past equal weight, and only with B3 in place. Until then, equal weight is the honest
  statement "I have not decided yet."
- **Anomaly models:** ignored on principle. A robust z-score names its rule; an isolation forest does not.
  The single defensible exception is pyod's ECOD (per-feature tail probabilities, so it decomposes), and it
  is not needed while A2's rules cover the ground.
- **LLM trading agents (TradingAgents, RD-Agent):** ignore. Non-deterministic output that varies with model
  temperature is the opposite of "model proposes, deterministic code executes," and neither has out-of-sample
  validation on US equities that the survey could confirm.
- **Licence hard stops:** vectorbt (Commons Clause), OpenBB (AGPL), alibi-detect (BSL), mlfinlab
  (proprietary). None is worth the legal surface for a private commercial board.

---

## What I would do first, and why

**A1 then A2**, in that order, before anything else.

A1 because until the score is measured every other piece of intelligence is built on a number of unknown
worth — and because the methodology page now promises it in writing. A2 because it is three days of SQL that
converts the nightly from a table refresh into a briefing, and because its robust-outlier line is the
data-quality check the map showed we lack.

A3 next: it is the highest ratio of new knowledge to new code in the whole survey, and every input is on
disk. B1 the week after, because "3 of 5 lenses" changes what the conviction tier can say.

## Two things worth verifying before any of this

1. **The 30,000-percent row.** Gate A checks impossible daily moves over the scored universe. Either the bad
   print predates its window, or the gate flagged it and publish went ahead anyway. Find out which — the
   answer decides whether A2's outlier line is a nice-to-have or a gate.
2. **`atlas_signal_ic`'s `era` column.** India hand-picks eras. `ruptures` (BSD-2, small) can date regime
   boundaries from the breadth vector itself — retrospectively only, never as a live signal — and would make
   the IC study's eras data-derived rather than chosen. Cheap, and a real glass-box improvement.
