# Turning stored history into actionable intelligence — open-source survey

**Date of research: 2026-09-11.** Target: Global Atlas (`atlas_global`, ~1,750 US ETFs + S&P 500, nightly
daily-bar pipeline, Postgres-backed, glass-box Next.js board).

## How this was verified

Every star count, licence, version and date below comes from one of three primary sources, named per claim:

- **GitHub repo page** (`github.com/<owner>/<repo>`) — stars, licence label, language.
- **GitHub commits page** (`/commits/<branch>/`) — last-commit dates, rendered exactly as GitHub shows them.
- **PyPI JSON API** (`pypi.org/pypi/<pkg>/json`) — latest version, `upload_time_iso_8601` of the newest
  artefact, licence field and licence classifiers. This is the most reliable "is it alive" signal.

What I could **not** verify is listed in the last section. The GitHub REST API and `gh` were unavailable in
this session (the proxy allows API access only to this repo), so star counts are GitHub's own rendered
abbreviations ("9.1k"), not exact integers. Treat them as ±100 and as of 2026-09-11.

"Abandoned" below means **last commit or release older than ~18 months** (i.e. before ~2025-03-11).

---

## Where Atlas actually stands (read this before the shortlist)

The recommendations only make sense against what is already built. From the repo:

| Capability | India (`atlas_foundation`) | Global (`atlas_global`) |
|---|---|---|
| Signal IC study | **Built.** `scripts/foundation/eval_signal.py` (307 lines) + pure maths in `atlas/compute/signal_eval.py` (118 lines) → `atlas_foundation.atlas_signal_ic`; board reads it via `frontend/src/components/methodology/SignalQuality.tsx` | **Table exists, producer does not.** `scripts/global_market/ddl/05_scores.sql:175` creates `atlas_global.atlas_signal_ic`; `scripts/global_market/gate_c.py:32` states plainly that until `eval_signal` exists "the weights are seeds and the board says so" |
| Regime classification | **Built, rules-based.** `atlas/compute/regime.py` (691 lines): four breadth families + volatility → 4 states, plus a `DISLOCATION_SUSPENDED` override. Primitives in `atlas/compute/breadth.py` (330 lines): A/D line, McClellan, new highs/lows, MA breadth | Not surveyed here |
| Paper portfolios | — | **Built.** `basket_master` / `basket_constituents` / `basket_nav_daily`, marked nightly on total return |
| Risk/perf metrics | — | **Built.** `technical_daily` already carries beta, Sharpe, Sortino, Calmar, max drawdown 12m/36m, vol 20/63/252d, downside deviation |

Three consequences that drive every verdict below:

1. **Atlas does not need a factor-research framework. It needs four more columns.** `atlas/compute/signal_eval.py`
   already computes per-(date, cohort) `rank_ic`, `n`, `decile_spread`, and summarises to `mean_ic`, `hit_rate`,
   `t_stat`, `mean_spread`. What the `atlas_global.atlas_signal_ic` DDL is **missing** versus the standard
   factor-validation panel is: **turnover**, **rank autocorrelation**, **ICIR**, and **decay**. That is the
   actual deliverable, and it is ~80 lines of pandas — not a dependency.
2. **In-memory panel libraries fight the architecture.** `eval_signal.py`'s own docstring explains why forward
   returns are computed in Postgres: the box has 2 vCPUs and the India price table is 6.1M rows, so "pandas must
   receive a reduced frame, never raw prices to shift". Every factor library in this survey wants the opposite —
   a wide in-memory price frame. This is the single biggest reason to copy maths rather than adopt frameworks.
3. **Glass-box is a hard filter on the ML options.** A gradient-boosted anomaly score cannot be traced to a rule
   and a row. This eliminates most of area 5 on principle, not on quality.

---

## Ranked shortlist

### Tier 1 — Adopt now (take the dependency)

| # | Repo | Why | Licence |
|---|---|---|---|
| 1 | **bashtage/linearmodels** | `FamaMacBeth` + `PanelOLS`. Answers the question alphalens *cannot*: "does this lens still pay after controlling for size, vol and momentum?" That is the question a fund manager actually asks. ~15 lines of integration against a frame Atlas can already produce in SQL. | NCSA (permissive) |
| 2 | **statsmodels** (`tsa.regime_switching`) | `MarkovRegression` with `switching_variance=True` on SPY returns returns `smoothed_marginal_probabilities` — a regime **probability**, not a label, which is strictly better for a glass-box board than Atlas's current hard 4-state rules output. Almost certainly already a transitive dependency. | BSD-3-Clause |
| 3 | **dgunning/edgartools** | Released **2026-09-08** (3 days before this survey). Typed parsers for 8-K, Form 3/4/5, 13F, XBRL financials **and N-PORT fund holdings** — the exact four feeds Atlas ingests. Adopt as a cross-check oracle for the existing parsers at minimum; it likely replaces the N-PORT parser outright. | MIT |
| 4 | **skfolio/skfolio** | Only if/when baskets move past equal-weight. sklearn-API portfolio optimisation: HRP, Nested Clusters, **Benchmark Tracking**, entropy pooling, and — the part that matters at 1,750 assets — a deep bench of shrinkage/denoising covariance estimators. Last commit **2026-09-09**. | BSD-3-Clause |

### Tier 2 — Copy the maths, do not take the dependency

| # | Source | What to lift |
|---|---|---|
| 5 | **stefan-jansen/alphalens-reloaded** → `src/alphalens/performance.py` | `quantile_turnover`, `factor_rank_autocorrelation`, `average_cumulative_return_by_quantile` (the decay curve), `compute_mean_returns_spread`. These are precisely the four gaps in `atlas_signal_ic`. Dormant since 2025-06-02; do not depend on it. |
| 6 | **microsoft/qlib** → `qlib/contrib/eva/alpha.py` | `calc_ic` computes **both** Pearson IC and Spearman rank IC per date — Atlas computes only rank IC. The whole file is 215 lines; `calc_ic` is 6 lines of pandas. Copy the semantics, ignore the 48.5k-star platform around it. |
| 7 | **MacKinlay (1997) event-study method** | No maintained Python library exists (see area 7). Build it: market-model abnormal return, CAR windows, Patell/BMP t-stats. Atlas has every input already — `filings_8k`, `insider_form4`, `short_interest`, `ohlcv_daily`, `beta` in `technical_daily`, SPY. ~150 lines, and it is the **highest-value item in this entire report**. |
| 8 | **deepcharles/ruptures** | Either copy or depend (it is small and BSD-2). Pelt + rbf cost on the breadth vector dates regime changes retrospectively. Critical caveat most write-ups miss: change-point detection is **retrospective by construction** — valid for labelling history on the board, invalid as a nightly live signal. |
| 9 | **pmorissette/bt** + **ffn** | Do not wire into the pipeline — Atlas already marks `basket_nav_daily` nightly. Use offline, once, as an independent oracle: feed it the same weights and prices and check the NAV series matches. Actively developed (last commit **2026-09-10**), and its `PTE_Rebalance` algo is a good reference for tracking-error-bounded rebalancing. |
| 10 | **ranaroussi/quantstats** | Same role: an offline cross-check oracle for the Sharpe/Sortino/Calmar/max-drawdown numbers `technical_daily` already produces. Its HTML tearsheet output is a dead end for a Next.js glass-box board. |
| 11 | **ETF holdings overlap** | Nothing worth adopting exists (area 6). Build it: weighted overlap `Σ min(w_i^A, w_i^B)` plus Jaccard on the name sets — ~15 lines of SQL. Blocker: `etf_exposure_daily` stores only **top-10** weight; real overlap needs full holdings, which is what edgartools N-PORT (#3) unlocks. |

### Tier 3 — Ignore

**On licence grounds (hard stops for a private commercial deployment):**
`polakowo/vectorbt` (Apache-2.0 **+ Commons Clause**), `OpenBB` (**AGPL-3.0-only**),
`SeldonIO/alibi-detect` (**Business Source License 1.1**), `hudson-and-thames/mlfinlab` (**proprietary**,
pulled from PyPI).

**Abandoned:** `mementum/backtrader` (last commit 2023-04-19), `quantopian/empyrical` (2020-10-14),
`arundo/adtk` (2020-04-17), `LemaireJean-Baptiste/eventstudy` (2021-04-03), `salesforce/Merlion` (2024-06-20),
`hmmlearn` (2024-10-31).

**Over-engineering for a 1,750-instrument daily-bar board:** `QuantConnect/Lean` (C#/.NET event engine),
`nautechsystems/nautilus_trader` (nanosecond Rust engine), `stefan-jansen/zipline-reloaded` (bundle ingestion
ceremony), `cvxgrp/cvxportfolio` (multi-period convex, GPLv3), `unit8co/darts`, `online-ml/river`.

**Toys or unvalidated:** `TauricResearch/TradingAgents` (~105k stars, zero out-of-sample validation),
`microsoft/RD-Agent` (read the paper, ignore the code), `AI4Finance/FinRL`, every `market-regime-detection`
repo surfaced by search, every ETF-overlap repo surfaced by search.

---

## Area 1 — Factor / signal research and validation

This is the area Atlas's `atlas_signal_ic` table points at, and the survey result is clearer than expected:
**the canonical library is dormant, and its maths is short enough to copy.**

### stefan-jansen/alphalens-reloaded — copy the maths

- **644 stars · Apache-2.0 · Python · last commit 2025-06-02 · PyPI `alphalens-reloaded` 0.4.6 uploaded 2025-06-02.**
- Dormant: exactly one commit ("V0.4.5") in the 15 months before this survey; the commit before that was
  2024-09-25. Not yet abandoned by the 18-month rule, but a one-maintainer project in maintenance mode.
- **What it does:** takes a panel of factor values and forward returns and produces the standard
  factor-validation battery. Verified from `src/alphalens/performance.py`:
  `factor_information_coefficient` (Spearman rank IC vs N-period forward returns), `mean_information_coefficient`,
  `mean_return_by_quantile`, `compute_mean_returns_spread`, `quantile_turnover` ("the proportion of names in a
  factor quantile that were not in that quantile in the previous period"), `factor_rank_autocorrelation`,
  `average_cumulative_return_by_quantile`, `factor_returns`, `factor_alpha_beta`, `factor_weights`, `positions`.
- **Atlas data needed:** verified from `src/alphalens/utils.py`, `get_clean_factor_and_forward_returns` wants a
  factor as "a MultiIndex Series indexed by timestamp (level 0) and asset (level 1)" plus prices as "a wide form
  Pandas DataFrame indexed by timestamp with assets in the columns", optional `groupby` for peer groups,
  `quantiles` or `bins` (not both), `periods`, and `max_loss`. Atlas has all of it —
  `lens_scores_daily` is the factor, `ohlcv_daily` the prices, peer group the `groupby`.
- **Verdict: copy the maths.** Three reasons. (a) The wide price frame is the exact shape
  `eval_signal.py` deliberately refuses to materialise on a 2-vCPU box. (b) Atlas already computes rank IC and
  decile spread; only four pieces are missing. (c) Taking a dormant single-maintainer dependency for ~80 lines of
  pandas is a bad trade. Lift `quantile_turnover`, `factor_rank_autocorrelation`, ICIR (`mean_ic / std_ic`), and
  the `average_cumulative_return_by_quantile` decay curve into `atlas/compute/signal_eval.py`, then add the
  matching columns to `atlas_global.atlas_signal_ic`.
- **Licence:** Apache-2.0 — no problem, including for copied code (retain the notice).

Note on forks: `cloudQuant/alphalens` (28 stars, 12 commits) is a toy despite claiming modernisation; the
original `quantopian/alphalens` is dead. `stefan-jansen/alphalens-reloaded` remains the only serious line.

### microsoft/qlib — copy `calc_ic`, ignore the platform

- **48.5k stars · MIT · Python · last commit 2026-07-23 · PyPI `pyqlib` 0.9.7 uploaded 2025-08-15.**
- Note the release/commit divergence: the latest **GitHub release** is v0.9.0 (2022-12-09) while the code is
  actively committed. Active project, stale release process.
- **What it does:** a full AI-quant platform — data handler, model zoo, RL, nightly workflow. The 1% Atlas cares
  about is `qlib/contrib/eva/alpha.py` (215 lines total), verified by reading the source: `calc_ic` returns
  `(ic, rank_ic)` by grouping on the date level and taking Pearson and Spearman correlations;
  `calc_long_short_return` takes `nlargest`/`nsmallest` of `quantile` per date and returns
  `(r_long - r_short) / 2` plus the cross-sectional average; `calc_long_short_prec` gives long/short hit rates;
  `calc_pred_autocorr` gives signal autocorrelation.
- **Atlas data needed:** a MultiIndex `(datetime, instrument)` Series of scores and one of labels. Atlas has this.
- **Verdict: copy the maths.** The useful insight is cheap and specific: **report both Pearson IC and Spearman
  rank IC**. Atlas computes only rank IC; the pair together tells you whether the signal's *magnitude* carries
  information or only its *ordering* — which is exactly the kind of distinction a glass-box board should surface.
  Adopting qlib itself means its data format, its cache layout and its model abstractions: grossly
  over-engineered here, and its opinionated ingestion would collide with `atlas_global`.
- **Licence:** MIT — fine.

### bashtage/linearmodels — adopt (the sleeper pick)

- **1.1k stars · NCSA · Python · PyPI `linearmodels` 7.0 uploaded 2025-10-21.**
- **What it does:** the panel and asset-pricing estimators statsmodels lacks. Verified from the docs:
  `linearmodels.panel.model.FamaMacBeth(dependent, exog, *, weights=None, check_rank=True)` runs a separate
  cross-sectional regression each period and averages the coefficients, `β̂ = T⁻¹ Σₜ β̂ₜ`, with the standard
  errors computed from the dispersion of the per-period estimates. Also `PanelOLS` (fixed effects), IV/2SLS,
  and 2-/3-step factor asset-pricing models.
- **Atlas data needed:** a panel keyed by (entity, time) with the lens score as a regressor, forward return as
  dependent, and controls. Atlas has every control it needs already in `technical_daily` (vol, beta, returns
  1d..36m for momentum) and `etf_meta` / market cap for size. Nothing missing.
- **Verdict: adopt.** This is the strongest recommendation in the report and the one nobody asks for, because
  alphalens-style IC answers "is this signal correlated with forward returns?" while Fama-MacBeth answers "is
  this signal *paid* once I control for the things I already knew". For a board whose entire pitch is that a fund
  manager can trace and challenge any number, a t-statistic on a controlled panel regression is the single most
  defensible artefact you can put next to a lens weight. It also gives you an honest basis for the thresholds in
  `atlas_thresholds` instead of seeds.
- **Licence:** NCSA (University of Illinois/NCSA Open Source License) — permissive, BSD/MIT-style, requires
  attribution. No problem commercially.

### ranaroussi/quantstats — offline oracle only

- **7.6k stars · Apache-2.0 · Python · last commit 2026-01-13 · PyPI `quantstats` 0.0.81 uploaded 2026-01-13.**
  Releases v0.0.78 ("2026 Modernization Update", adding Monte Carlo and type hints) and v0.0.81 both landed
  2026-01-13. Active but bursty — the 2026 activity is one modernisation push.
- **What it does:** consumes a returns Series (plus optional benchmark) and emits metrics + plots + HTML
  tearsheets. Returns-based, not trade-based.
- **Atlas data needed:** a daily total-return series and a benchmark series. Atlas has exactly this in
  `basket_nav_daily` and SPY in `ohlcv_daily`. Zero new data.
- **Verdict: reference/oracle, not a dependency.** `technical_daily` already stores Sharpe, Sortino, Calmar,
  max drawdown 12m/36m, downside deviation and annualised vol at three horizons. Adding quantstats would
  duplicate all of it with *different conventions* (annualisation factor, risk-free handling, geometric vs
  arithmetic), which is worse than not having it. Its real value: run it once offline against a basket's NAV
  series and reconcile, so you can state on the board which convention Atlas uses and that it agrees with a
  7.6k-star reference. There is also a maintained fork, `Lumiwealth/quantstats_lumi` (PyPI `quantstats-lumi`
  1.1.5, uploaded 2026-06-01, Apache-2.0) if you ever need one that is being actively curated.
- **Licence:** Apache-2.0 — fine.

### pyfolio-reloaded / empyrical-reloaded — skip

- `stefan-jansen/pyfolio-reloaded`: Apache-2.0, Python, **last commit 2025-06-02**, PyPI 0.9.9 uploaded
  2025-06-02. One commit in 15 months (a NumPy 2.0 compatibility fix).
- `stefan-jansen/empyrical-reloaded`: Apache-2.0, Python, **last commit 2025-07-29** (a README typo), PyPI
  0.5.12 uploaded 2025-06-01.
- `quantopian/empyrical` (the original, 1.5k stars, Apache-2.0): **last commit 2020-10-14 — abandoned**, 71
  months. `quantopian/pyfolio` likewise dead post-Quantopian.
- **Verdict: skip all four.** empyrical is a metrics library Atlas has already out-competed in
  `technical_daily`; pyfolio is a tearsheet generator for Jupyter, which is the wrong output medium for a
  glass-box web board. The "-reloaded" line exists to keep Stefan Jansen's book examples runnable, not to be a
  production dependency.

### polakowo/vectorbt — ignore on licence

- **9.1k stars · Python · last commit 2026-08-02 · PyPI `vectorbt` 1.1.0 uploaded 2026-07-05.** Genuinely
  actively maintained (recent commits include switching rolling std to Welford's algorithm for numerical
  stability).
- **Licence — the blocker.** Verified from `LICENSE.md`: **Apache 2.0 with Commons Clause**, Licensor Oleg
  Polakow. The Commons Clause removes the right to "Sell", defined as "practicing any or all of the rights
  granted to you under the License to provide to third parties, for a fee or other consideration (including
  without limitation fees for hosting or consulting/support services related to the Software), a product or
  service whose value derives, entirely or substantially, from the functionality of the Software."
- **Verdict: ignore.** This is **not** an open-source licence despite the Apache-2.0 base. A commercial
  equity-intelligence platform sold to fund managers, whose signal-validation numbers came out of vectorbt, is
  close to the centre of what that clause prohibits. The README also states the OSS repo is "the open-source
  community edition of VectorBT PRO" — a deliberate funnel to a paid product. Do not put it in the dependency
  tree, and do not copy its code either (the clause attaches to the code, not just the package).

### Also checked, area 1

- `bashtage/arch` — 1.6k stars, NCSA per PyPI, PyPI `arch` 8.0.0 uploaded 2025-10-21. GARCH/EGARCH/TARCH,
  unit-root tests (ADF, KPSS, Zivot-Andrews), cointegration, block bootstraps. Relevant to area 4, see below.
- Newer LLM-driven factor-mining systems (QuantaAlpha, AlphaLogics, XALPHA, FactorEngine) appear as arXiv
  preprints citing RD-Agent as a baseline. **I did not verify their repositories** — see the unverified section.

---

## Area 2 — Backtesting engines

Atlas already has a working book: `basket_master` / `basket_constituents` / `basket_nav_daily` marked nightly on
total return, plus basket trades. **The question is not "which engine should we adopt" but "is our NAV engine
right".** That reframing changes the answer completely.

| Repo | Stars | Licence | Language | Last activity | Verdict |
|---|---|---|---|---|---|
| **pmorissette/bt** | 3.0k | MIT | Python | **commit 2026-09-10**; PyPI `bt` 1.2.0 2026-04-25 | **Offline oracle.** Best fit of the six. |
| pmorissette/ffn | unverified | MIT | Python | PyPI `ffn` 1.1.5 2026-03-24 | Companion to bt; same role. |
| mementum/backtrader | 23.2k | GPLv3+ | Python | **commit 2023-04-19 — abandoned (41 months)** | Ignore. |
| stefan-jansen/zipline-reloaded | 1.9k | Apache-2.0 | Python | commit 2025-11-13 (dependabot); PyPI 3.1.1 2025-07-19 | Over-engineering. |
| nautechsystems/nautilus_trader | 28.8k | LGPL-3.0 | Rust + Python | PyPI 1.231.0 2026-08-02; 2.0.0 RC | Wrong problem. |
| QuantConnect/Lean | 21.6k | Apache-2.0 | C# (+Python) | **commit 2026-09-10** | Wrong stack. |

### pmorissette/bt — the one worth reading

- **What it does:** strategies are composed as a tree of "algos" run in sequence — `RunMonthly`, `SelectAll`,
  `WeighEqually`, `Rebalance` — over nested `Strategy`/`Security` nodes, so a strategy can hold other strategies.
  This is structurally the closest match in the survey to Atlas's weight-vector-and-NAV model.
- Recent commits are substantive and on-point: "Respect security multipliers in `PTE_Rebalance`" and "Preserve
  filtered universe order" (both 2026-09-10). `PTE_Rebalance` — rebalance only when permitted tracking error is
  breached — is directly relevant if Atlas ever wants turnover-aware baskets.
- **Atlas data needed:** a wide price frame and target weights. Atlas has both; again the wide frame is a
  memory cost Atlas deliberately avoids nightly, which is fine for a one-off offline reconciliation.
- **Verdict: reference implementation / offline oracle.** Run one basket through bt once, reconcile against
  `basket_nav_daily`, write the delta into the docs, then delete the script. Do **not** add it to the nightly
  orchestrator: Atlas's NAV engine is already there, already gated, already traceable, and replacing a
  transparent SQL mark with a library's internal accounting would *reduce* glass-box quality.
- **Licence:** MIT — no problem. (Note `ffn`, by the same author, is also MIT and carries the metrics half.)

### Why the other five are wrong for this board

- **backtrader — abandoned.** Last commit 2023-04-19, last PyPI release 1.9.78.123 on 2023-04-19. 23.2k stars
  is historical momentum, not health. Also GPLv3+, which is a distribution question you do not need.
- **zipline-reloaded — over-engineering.** Apache-2.0 and fine legally, and the last ten months of commits are
  dependabot bumps. The real cost is architectural: zipline wants data ingested into its own bundle format and
  run through its own event loop and Pipeline API. Atlas's entire design premise is that Postgres is the
  system of record and boards read it directly. Adopting zipline means maintaining a second copy of the universe
  in a second format — a direct violation of the one-schema-per-market discipline in spirit if not in letter.
- **nautilus_trader — solving a different problem.** 28.8k stars, LGPL-3.0, Rust-native, "nanosecond-resolution
  data", built for multi-venue live execution with contingent order types. Atlas is long-only, daily-bar,
  paper-marked, no execution. Nothing in the nanosecond machinery earns its complexity here, and LGPL-3.0 brings
  dynamic-linking obligations you would have to reason about for no benefit.
- **Lean — wrong stack.** 21.6k stars, Apache-2.0, extremely active (commits 2026-09-10), and a genuinely
  professional engine. It is C# on .NET 10. Introducing a .NET runtime into a Python + Postgres + Next.js box to
  backtest daily bars is not a trade worth discussing.
- **vectorbt** — see area 1. Fast and well-engineered; legally unusable here.

---

## Area 3 — Portfolio construction and risk

All four serious candidates need the same thing Atlas does not yet have a dedicated artefact for: **an asset ×
asset covariance matrix over the basket's candidate set**. Atlas has the raw material (`ohlcv_daily` returns)
but note the conditioning problem — a 1,750 × 1,750 sample covariance from 252 daily observations is
rank-deficient and its inverse is noise. That fact, not the API, is what should decide the pick.

| Repo | Stars | Licence | Last activity | Adds over equal-weight | Verdict |
|---|---|---|---|---|---|
| **skfolio/skfolio** | 2.4k | BSD-3-Clause | **commit 2026-09-09**; PyPI 1.0.6 2026-09-08 | HRP, Nested Clusters, **Benchmark Tracking**, entropy pooling, Black-Litterman, and a deep bench of covariance estimators (Ledoit-Wolf, Denoised, Detoned, Gerber, Graphical Lasso) | **Adopt when needed** |
| dcajasn/Riskfolio-Lib | 4.5k | BSD-3-Clause | commit 2026-06-22; PyPI 7.3.0 2026-05-31 | 26 convex risk measures (MAD, Gini mean difference, CVaR, Tail Gini, EVaR, CDaR, max DD), HRP, NCO, worst-case MV | Strong second |
| PyPortfolio/PyPortfolioOpt | 6.0k | MIT | commit 2026-07-07; PyPI 1.6.0 2026-02-26 | Efficient frontier, Black-Litterman, `HRPOpt`, CVaR | Simplest; fine if you only want HRP |
| cvxgrp/cvxportfolio | unverified | **GPLv3** | PyPI 1.5.1 2025-07-06 (14 months) | Multi-period optimisation with explicit transaction-cost and holding-cost models | **Ignore** — over-engineering + copyleft |
| hudson-and-thames/mlfinlab | unverified | **proprietary** | **removed from PyPI** | — | **Ignore** |

### skfolio — the pick

- **What it does:** wraps portfolio construction in the scikit-learn estimator API, so optimisers, prior
  estimators and covariance estimators compose and can be cross-validated with the standard sklearn machinery.
  Verified from the README: optimisers include Mean-Risk, Risk Budgeting, Hierarchical Risk Parity, Nested
  Clusters Optimization and Benchmark Tracking; priors include Empirical, Black-Litterman, factor models and
  Entropy Pooling.
- **Why it wins here specifically:** two features nothing else combines. **Benchmark Tracking** is the right
  objective for a long-only book judged against SPY, which is exactly what Atlas's baskets are. And the
  covariance estimator bench (Denoised/Detoned per López de Prado, Ledoit-Wolf shrinkage, Graphical Lasso) is the
  direct answer to the 1,750-asset conditioning problem above. An optimiser without shrinkage at this universe
  size will produce confident nonsense.
- **Atlas data needed:** a returns matrix — `ohlcv_daily` gives it. Factor models would want characteristics,
  which `etf_classification` / `etf_meta` / `stock_financials_pit` partly supply. **What Atlas does not have:**
  nothing blocking. This is the rare candidate with no data gap.
- **Verdict: adopt, but only when there is a real decision to make.** While baskets are equal-weight by policy,
  adding an optimiser adds a black box for no gain. The moment someone asks "why these weights", skfolio is the
  answer — and it is the only one of the four whose sklearn lineage makes the resulting weights reproducible and
  testable in the way `make gate` would demand.
- **Licence:** BSD-3-Clause — no problem.

### The others, briefly

- **Riskfolio-Lib** (4.5k, BSD-3): more risk measures than anyone needs (26 convex measures, 37 for hierarchical
  clustering), HRP and NCO both present, CVXPY-backed. Genuinely good. Loses to skfolio on two counts: a
  bespoke `Portfolio`-object API rather than sklearn, and recent commits are documentation-only (2026-06-22 and
  three "Update docs" on 2026-06-03), so the code cadence is slower than skfolio's.
- **PyPortfolioOpt** (6.0k, MIT): note the repo **moved** — it is now `PyPortfolio/PyPortfolioOpt`, not
  `robertmartin8/PyPortfolioOpt`, with last commit 2026-07-07 and 1.6.0 on PyPI 2026-02-26. Cadence in 2026 is
  CI and dependabot plus a few enhancements. It is the easiest to read and `HRPOpt` is ~100 lines; if all you
  want is hierarchical risk parity, copy from here rather than depending on anything.
- **cvxportfolio** (GPLv3, 1.5.1 on 2025-07-06): the Boyd group's multi-period convex framework with explicit
  cost models. Academically excellent, and exactly the over-engineering this board should refuse — multi-period
  optimisation matters when you trade; Atlas paper-marks nightly. GPLv3 is additionally a question you should
  not have to answer.
- **mlfinlab:** confirmed dead as an option. **Not on PyPI.** `LICENSE.txt` is a custom commercial licence —
  verified quotes: a "non-exclusive license to use … in the Licensees internal Business Environment", "shall not
  lease, loan, resell, sublicense or otherwise distribute", and explicitly "not permitted to create API
  endpoints or create data or forecast services using the Licensed Material without the Company's explicit
  written authorization". That last clause describes Global Atlas. Get HRP from skfolio instead.

---

## Area 4 — Regime detection / market state

**Atlas already has a regime classifier**, and it is a good one: `atlas/compute/regime.py` (691 lines) combines
trend, MA breadth, A/D breadth, new highs/lows and strength breadth with volatility into four states
(Risk-On 1.0× / Constructive 0.7× / Cautious 0.4× / Risk-Off 0.0×) plus a volatility-dislocation override.
`atlas/compute/breadth.py` supplies McClellan oscillator, A/D line, new highs/lows and MA breadth.

So the gap is not "Atlas needs regime detection". The gap is that a **rules-based classifier has no measure of
its own confidence**, and no statistical validation that its states are real. That is what to import.

### statsmodels `tsa.regime_switching` — adopt

- **BSD-3-Clause · PyPI `statsmodels` 0.15.0 uploaded 2026-08-27.** The most maintained thing in this report.
- **What it does:** verified from the docs — `MarkovRegression` and `MarkovAutoregression` in
  `statsmodels.tsa.regime_switching` estimate a dynamic regression whose parameters switch with a latent state,
  `y_t = μ_{S_t} + y_{t-1}β_{S_t} + ε_t`, by maximum likelihood (Hamilton filter). It estimates regime-specific
  intercepts and coefficients, the **transition probability matrix**, and optionally regime-specific variances
  (`switching_variance=True`). Outputs include `smoothed_marginal_probabilities` (probability of each regime at
  each date) and `expected_durations`. The official example notebook fits models on federal funds rate data and
  **S&P 500 absolute returns** — i.e. on precisely the series Atlas has.
- **Atlas data needed:** one daily return series (SPY from `ohlcv_daily`). Optionally the breadth vector from
  `atlas/compute/breadth.py` as exogenous regressors. Nothing missing.
- **Verdict: adopt.** Two concrete wins. (a) A 2-state switching-variance model on SPY returns yields a daily
  *probability* of being in the high-volatility state — strictly more informative than a hard label, and the
  transition matrix and expected durations are human-readable parameters you can put on the methodology page.
  (b) It gives you an independent series to **cross-check the rules-based classifier against**: if the
  rules say Risk-Off on days the Markov model puts 15% probability on the stressed state, that disagreement is
  itself intelligence and a validator you can gate on.
- **Glass-box caveat, stated honestly:** MLE regime probabilities are traceable to a likelihood and a parameter
  vector, not to a rule a fund manager can read off. Publish it as a *second opinion* alongside the rules-based
  state, never as a replacement. The existing rules classifier is the more defensible primary.
- **Licence:** BSD-3-Clause — no problem.

### deepcharles/ruptures — adopt lightly or copy

- **2.1k stars · BSD-2-Clause · Python · last commit 2026-05-26 · PyPI `ruptures` 1.1.10 uploaded 2025-09-10.**
  Active (recent work added an `L1Potts` class, type hints, Python 3.14 support, dropped 3.9).
- **What it does:** offline change-point detection — "exact and approximate detection for various parametric and
  non-parametric models". Search methods include Pelt (the pruned exact linear-time method) with selectable cost
  functions (`rbf`, `l2`, etc.). Input is a NumPy array of shape `(n_samples, dim)`, so it handles multivariate
  signals natively.
- **Atlas data needed:** a `(dates × k)` matrix. The breadth families from `atlas/compute/breadth.py` are
  already exactly this shape. Nothing missing.
- **Verdict: copy or depend — it is small and BSD-2, either is defensible.** The genuinely useful application is
  *dating* regime boundaries on history so the board can show "this score was earned in a different market", and
  segmenting the IC study into eras (the `atlas_signal_ic` table already has an `era` column — ruptures could
  derive those eras from the data rather than hand-picking them, which would be a real glass-box upgrade).
- **The caveat that matters:** Pelt is an *offline, retrospective* segmentation. A change point near the end of
  the series will move as new data arrives. Never surface the most recent change point as a live signal; use it
  for historical labelling only. Most of the blog literature on this is silent about it.
- **Licence:** BSD-2-Clause — no problem.

### hmmlearn — flagged, prefer statsmodels

- **BSD-3-Clause · PyPI `hmmlearn` 0.3.3 uploaded 2024-10-31 · last commit 2024-10-31.** That is **~22 months**
  — past the 18-month flag. Not dead (it is a long-stable library with a careful maintainer) but not developing.
- **Verdict: not worth it** given statsmodels covers the same ground with `MarkovRegression`, is actively
  developed, and is almost certainly already in the dependency tree. A Gaussian HMM on returns and a 2-state
  Markov-switching regression are close cousins; take the maintained one.

### bashtage/arch — optional, for the volatility half

- **1.6k stars · NCSA · PyPI `arch` 8.0.0 uploaded 2025-10-21.** GARCH/EGARCH/TARCH/EWMA with three error
  distributions, plus unit-root tests and block bootstraps.
- **Verdict: worth it only for one specific thing** — the stationary/block bootstrap, which gives you honest
  confidence intervals on Sharpe and IC without assuming i.i.d. returns. That is a genuinely defensible
  glass-box artefact ("this lens's IC is 0.04, bootstrap 95% CI [0.01, 0.07]"). The GARCH side duplicates what
  `technical_daily`'s realised vol already gives the board. Licence NCSA — permissive, fine.

### The "market regime detection" repos on GitHub — ignore all of them

Search surfaced `KabirUberoi/Market-Regime-detection-using-Hidden-Markov-Models`,
`Sakeeb91/market-regime-detection`, `vigp17/market-regime-detection`, `taylorjmellon/market-regime-detection`,
`francescodemarte/regime-detection`, `shortthirdman/Market-Regime-Detection`, `theo-dim/regime_detection_ml`,
`yvesdhondt/MarketMoodRing` and `tianyu-z/Kritzman-Regime-Detection`. **I did not verify stars, licences or
commit dates for any of them** — but every one is a personal project or course artefact wrapping `hmmlearn` or
`sklearn.cluster.KMeans` in a notebook. There is no serious, maintained, market-regime library. Use statsmodels
directly; the wrapper adds nothing but a dependency you would have to audit.

---

## Area 5 — Anomaly / change detection for a "what changed last night" digest

**This is the area where the survey result is mostly negative, and the negative result is the finding.**

The glass-box requirement does most of the work: a fund manager must trace any number to the rule and the row.
An IsolationForest or autoencoder anomaly score fails that test by construction. So the digest should be built
from **explainable statistics over day-over-day deltas**, which is SQL plus a handful of formulas, not a
library.

### What to build (no dependency)

Over the tables Atlas already writes nightly, a digest is a union of rule-named deltas:

- **Robust cross-sectional z-score** of each day's change, using **median and MAD** rather than mean and
  standard deviation, so one dislocated name does not mask the rest. Report it as "RSI 14 fell 22 points,
  4.1 robust-σ versus its peer group" — traceable to a rule and a row.
- **Rank migration:** decile today vs decile yesterday in `lens_scores_daily`, and conviction-tier transitions.
  This is the single most actionable line in any such digest and it is a `LAG()` window function.
- **Threshold crossings:** the `above_ema_*` flags and 52-week position in `technical_daily` already encode
  state; a crossing is a boolean changing. Zero new maths.
- **Flow/exposure shifts:** top-10 weight changes in `etf_exposure_daily`, short-interest changes, new
  `filings_8k` and `insider_form4` rows.
- **Novelty of magnitude:** "today's move is the largest in N sessions" — one window function, and much easier
  to defend than any model-based anomaly score.

Every one of those names its own rule. That is the digest. Resist the urge to add a detector.

### Libraries assessed

| Repo | Stars | Licence | Last activity | Verdict |
|---|---|---|---|---|
| yzhao062/pyod | 10.0k | BSD-2-Clause | PyPI `pyod` 3.6.5 2026-08-17 | **Narrow exception** — see below |
| stumpy-dev/stumpy | unverified | BSD-3-Clause | PyPI `stumpy` 1.14.1 2026-02-08 | Copy the idea, not the code |
| unit8co/darts | 9.5k | Apache-2.0 | PyPI `darts` 0.47.0 2026-09-04 | Over-engineering |
| online-ml/river | unverified | BSD-3-Clause | PyPI `river` 0.26.1 2026-08-21 | Wrong paradigm (streaming) |
| SeldonIO/alibi-detect | unverified | **BSL 1.1** | PyPI 0.13.0 2025-12-11 | **Ignore — licence** |
| salesforce/Merlion | unverified | 3-Clause BSD | PyPI 2.0.4 **2024-06-20** | **Ignore — ~27 months** |
| arundo/adtk | unverified | MPL-2.0 | PyPI 0.6.2 **2020-04-17** | **Ignore — abandoned** |
| blue-yonder/tsfresh | unverified | MIT | PyPI 0.21.2 2026-05-31 | Not for this |

**pyod — the one narrow exception.** 10k stars, BSD-2-Clause, very active (3.6.5 on 2026-08-17), and per its
README "61 detectors across tabular, time series, graph, text, image, and audio data, one API". Almost all of
those are disqualified here. Two are not: **ECOD** and **COPOD** are parameter-free, deterministic, and
*explainable* — they estimate per-dimension empirical tail probabilities and aggregate them, so the output
decomposes into "which feature made this row anomalous and how far into its tail it sat". That decomposition is
publishable on a glass-box board in a way that an isolation-forest path length is not. If you want one
model-based detector over the nightly cross-section of `technical_daily` features, use ECOD and show the
per-feature contributions. If you do not want one, you lose very little.

**stumpy** — matrix profile (BSD-3, 1.14.1 on 2026-02-08, active). The idea worth stealing: the matrix profile
answers "is today's 60-day window unlike any other 60-day window in this instrument's own history?" — a
per-name novelty measure that needs no cross-sectional peer group. That is a genuinely different and useful
question from a z-score. But it is O(n·m) per instrument per night over 1,750 names, and "this window is unusual
for this ETF" is hard to convert into an action. Copy the idea if a specific question demands it; do not add it
speculatively.

**darts** (9.5k, Apache-2.0, 0.47.0 on 2026-09-04) has a real anomaly module — `darts.ad`, with Scorers
(`KMeansScorer`, `NormScorer`, `WassersteinScorer`, `PyODScorer`, NLL variants), Detectors
(`ThresholdDetector`, `QuantileDetector`, `IQRDetector`) and `ForecastingAnomalyModel` /
`FilteringAnomalyModel` that score by comparing a forecasting model's predictions to actuals. Architecturally
elegant. Wrong for Atlas: it makes an anomaly contingent on a *forecast*, so every digest line would inherit a
model you now have to explain and validate. Over-engineering.

**alibi-detect — licence stop.** PyPI reports its licence as **Business Source License 1.1** with the
classifier `License :: Other/Proprietary License`. BSL is a delayed-open licence with use restrictions; do not
put it in a commercial deployment without legal review, and there is no reason to here.

**Merlion and adtk — abandoned.** Merlion's last PyPI release was 2024-06-20 (~27 months); adtk's was
2020-04-17 (~77 months). Both appear in "best anomaly detection library" listicles. Both are dead.

---

## Area 6 — Peer / similarity, clustering, and ETF holdings overlap

### There is no serious ETF holdings-overlap library. Build it.

Searching specifically for this returned only small personal projects: `IV1T3/PortfolioOverlap` (CLI comparing a
portfolio to popular ETFs), `sorgmi/pyetfoverlap` (explicitly "only iShares links are supported"),
`slihn/overlap` (a sparse-matrix performance exercise), `ethansilvas/etf-portfolio-analyzer` (a course project)
and a public gist. **I did not verify stars or licences for these** — it does not matter, because none is a
dependency you would take.

That is the right answer anyway, because the maths is trivial and the value is in the data:

- **Weighted overlap** between funds A and B: `Σ_i min(w_i^A, w_i^B)` over the union of holdings. One number in
  [0, 1], completely traceable.
- **Jaccard** on the name sets for a holdings-agnostic view: `|A ∩ B| / |A ∪ B|`.
- **Active share** versus a benchmark: `0.5 · Σ_i |w_i^A − w_i^B|`.

Each is a few lines of SQL against a holdings table. **The blocker is data, not code:** `etf_exposure_daily`
stores only **top-10 weight**, which is enough for a concentration metric and nowhere near enough for overlap.
Two ETFs can both show 35% top-10 weight and share nothing. Full holdings must land first — which is what
edgartools (below) is for.

This is worth building precisely because it is the question an ETF board uniquely can answer and a stock board
cannot: "you already own QQQ; here is what VGT actually adds."

### dgunning/edgartools — adopt (the data unlock)

- **2.7k stars · MIT · Python · PyPI `edgartools` 5.57.0 uploaded 2026-09-08** — three days before this survey.
  Extraordinarily active release cadence.
- **What it does:** turns EDGAR filings into typed Python objects across "20+ other filing types" — 10-K/10-Q
  income statement, balance sheet and cash flow via XBRL standardisation, Form 3/4/5 insider transactions,
  13F-HR institutional holdings, 8-K items, and **N-PORT fund holdings**.
- **Atlas relevance:** Atlas already ingests 8-K, financials and N-PORT holdings from EDGAR directly. So this
  is not new capability — it is a **maintained, tested, MIT-licensed second implementation of parsers Atlas
  maintains by hand**. That makes it valuable in two ways: as a differential-testing oracle against the existing
  parsers (parse the same accession both ways, assert agreement — and that is a real test on real records, which
  RULE #0 would approve of), and as a candidate replacement for the N-PORT parser, which is the hardest of the
  three and the one gating full-holdings overlap above.
- **Verdict: adopt, starting as a cross-check.** MIT, no licence issue.

### Clustering and hierarchical risk parity

- The clustering itself needs **no new dependency**: `scipy.cluster.hierarchy` (linkage, dendrogram,
  fcluster) on a correlation-derived distance `d_ij = sqrt(0.5 · (1 − ρ_ij))` is the whole of the HRP tree step,
  and scipy is already present.
- **HRP implementations to read rather than import:** `PyPortfolioOpt`'s `HRPOpt` is the shortest and clearest;
  `Riskfolio-Lib` and `skfolio` both implement HRP and Nested Clusters Optimization with more options.
- **Atlas data needed:** a returns correlation matrix over the candidate set — available from `ohlcv_daily`.
  Note that correlation clustering over returns and overlap clustering over *holdings* answer different
  questions and will disagree; showing both, and where they disagree, is more interesting than either alone.
- **Verdict:** copy the maths. A peer-group or cluster assignment that a fund manager can trace to a correlation
  matrix and a linkage method is glass-box; one that comes out of an imported optimiser is less so.

### global-capital-allocation-project/public-US-funds-data — reference only

- **15 stars · Python + Stata + Bash · licence not displayed on the repo page (unverified).** A full pipeline to
  download, parse, clean and assemble SEC N-PORT filings into research-ready datasets, with a configurable
  quarterly range (the README example runs 2019q4–2024q4).
- **Verdict: reference implementation.** The Stata dependency rules it out as a dependency. But it is the only
  serious N-PORT assembly pipeline found, and worth reading for its cleaning rules — share-class consolidation,
  duplicate filings and identifier mapping are where N-PORT work actually goes wrong, and someone has already
  made those mistakes here.

---

## Area 7 — Event studies over 8-K / insider / short interest

**Verified conclusion: there is no maintained, serious Python event-study library.** This is the largest gap
between what Atlas's data supports and what open source offers — and therefore the biggest opportunity.

| Package | Version / last release | Licence | Status |
|---|---|---|---|
| `LemaireJean-Baptiste/eventstudy` | 0.1a12, **2021-04-03** | GPLv3 | **Abandoned (~65 months), never left alpha** |
| `Darenar/easy-event-study` (`easy_es`) | 0.1.8, 2025-10-10 | not declared on PyPI (unverified) | Alive but tiny, unaudited |
| `py_event_studies` | 0.3.0, 2025-05-20 | not declared on PyPI (unverified) | Built around the CRSP database — wrong data source |
| R: `sipemu/eventstudy`, `LisaLechner/event2car` | unverified | unverified | Wrong language for this stack |

### Build it. Atlas has every input and the maths is standard.

The classical market-model event study (MacKinlay 1997 is the canonical reference; **I have not verified the
exact citation details**, so check it before citing in the methodology page):

1. **Estimation window** (e.g. t−250 to t−30): regress `r_i,t = α_i + β_i · r_SPY,t + ε_i,t`.
   Atlas already stores **beta** in `technical_daily`, so this step may reduce to a lookup.
2. **Abnormal return** in the event window: `AR_i,t = r_i,t − (α̂_i + β̂_i · r_SPY,t)`.
3. **CAR** over windows — (0,+1), (0,+5), (0,+21) — and **average CAR** across events.
4. **Significance:** a cross-sectional t-test at minimum; Patell standardised residuals or the BMP
   (Boehmer-Musumeci-Poulsen) test if you want to handle event-induced variance. **I have not verified the
   Patell or BMP primary citations** — verify before publishing them as methodology.

**Atlas data needed vs has:** `filings_8k` (event dates and item codes), `insider_form4` (event dates,
direction, size), `short_interest` (change events), `ohlcv_daily` (returns), `technical_daily` (beta),
SPY (market return), `index_membership` (to avoid survivorship bias in the event sample), `etf_classification` /
market cap (to cut results by peer group). **Nothing is missing.** This is rare and should be acted on.

**Why this is the highest-value item in the report:** it converts `filings_8k`, `insider_form4` and
`short_interest` from *lists of things that happened* into *statements about what such things are worth* — "8-K
Item 5.02 in small-cap industrials has averaged −1.8% CAR(0,+5) across N events since 2019, t = −2.3". That is
actionable intelligence, it is glass-box (every number traces to a regression on real rows), it requires no new
ingestion, and no library is going to hand it to you. ~150 lines.

**One discipline note:** the event study is also the place where look-ahead bias is easiest to introduce
accidentally — the estimation window must end before the event, `stock_financials_pit` exists precisely because
point-in-time matters, and an 8-K's *filing* timestamp is not its *event* timestamp. Whatever gets built here
needs the same care `eval_signal.py` already shows about excluding rather than coercing absent data.

---

## Area 8 — Notable and recent, including LLM-over-market-data

Be sceptical here. One finding dominates: **star count measures GitHub virality, not investment validity.**

### TauricResearch/TradingAgents — a toy, at 100k+ stars

- **~105k stars** as rendered on the repo page; an independent tracker showed **102.1k** — so call it
  102–105k. **Apache-2.0 · Python · last commit 2026-09-07** (genuinely active; recent commits add LLM model
  pickers and point-in-time guards).
- **What it does:** a multi-agent LLM simulation of a trading firm — Fundamentals, Sentiment, News and
  Technical analysts, Bullish and Bearish researchers who debate, a Trader agent, then Risk Management and a
  Portfolio Manager. Reads financials, prices, indicators, headlines, social sentiment and macro; emits trading
  decisions with narrative justification.
- **Verdict: ignore, and say why plainly.** The README itself states it is "designed for research purposes" and
  that "backtest results are not guaranteed to match any published figure", with performance varying by "the
  chosen backbone language models, model temperature, trading periods, the quality of data, and other
  non-deterministic factors". I found **no out-of-sample validation** in the material reviewed. A
  non-deterministic pipeline whose output changes with model temperature is the exact opposite of Atlas's
  "model proposes, deterministic code executes" rule and of glass-box traceability. The 100k stars reflect a
  viral README, not evidence.

### microsoft/RD-Agent — read the paper, ignore the code

- **14.6k stars · MIT · Python.** Paper: "R&D-Agent-Quant: A Multi-Agent Framework for Data-Centric Factors and
  Model Joint Optimization", Li, Yang, Yang, Xu, Wang, Liu, Bian — arXiv v1 2025-05-21, v2 2025-09-25,
  reported as NeurIPS 2025 accepted.
- **What it does:** a closed loop that proposes factors, writes the implementing code, backtests in qlib, reads
  the performance metrics, and refines the next proposal.
- **Requires:** an LLM chat API plus an embedding model (via LiteLLM), **Docker**, **qlib**, and historical
  market data in qlib's format. That is a second platform inside your platform.
- **The claim, quoted exactly:** "at a cost under \$10, RD-Agent(Q) achieves approximately 2× higher ARR than
  benchmark factor libraries while using over 70% fewer factors". The abstract says "real markets" but **does
  not name the market**; qlib's own benchmark suite is built on CSI300/CSI500 (Chinese A-shares), and
  third-party papers using RD-Agent as a baseline report CSI300/CSI500 experiments. So **I could not verify that
  any of these results are on US equities.** Treat the headline number as unvalidated for Atlas's universe.
- **Verdict: read the paper for the loop design, ignore the code.** The interesting transferable idea is the
  *shape*: propose → implement deterministically → evaluate on held-out data → keep or discard, with the
  evaluation being the authority. Atlas already has the evaluation half (`atlas_signal_ic`) and the rule that
  deterministic code executes. An automated factor-acceptance loop without a human reading the Fama-MacBeth
  t-stat would, however, produce exactly the overfit-and-publish failure mode that RULE #0 exists to prevent.

### OpenBB — licence stop

- **PyPI `openbb` 4.7.2 uploaded 2026-05-26 · AGPL-3.0-only.** A broad financial-data aggregation platform.
- **Verdict: ignore.** AGPL-3.0 is the one copyleft that reaches network-served software: serving a board whose
  functionality derives from AGPL code can trigger the obligation to offer corresponding source to users.
  Atlas's repo is public, which softens the question but does not answer it, and `atlas/global_market/providers/`
  already covers ingestion. Not worth the legal surface.

### AI4Finance FinRL — stale

- **MIT · PyPI `FinRL` 0.3.7 uploaded 2024-04-12** — ~29 months, past the flag on PyPI (repo commit cadence
  unverified). Deep reinforcement learning for trading. Even if maintained: an RL policy is the least traceable
  artefact imaginable for a glass-box board, and daily-bar long-only equity allocation is not a problem RL wins.
  **Ignore.**

### Honourable mentions, unverified

Search surfaced recent arXiv preprints on LLM-driven alpha mining — QuantaAlpha, AlphaLogics, XALPHA,
FactorEngine, "Cognitive Alpha Mining via LLM-Driven Code-Based Evolution", AlphaForge. **I did not verify any
of their repositories, stars, licences or maintenance status**, and several appear to be paper-companion code.
Listed only so the category is not silently omitted. The pattern to be sceptical of is universal in this
literature: results reported on Chinese A-share indices over a single backtest split, with the factor search
itself performed on data overlapping the test period.

---

## Licence risk register

| Project | Licence | Risk for a private commercial deployment |
|---|---|---|
| polakowo/vectorbt | Apache-2.0 **+ Commons Clause** | **Hard stop.** Prohibits selling a product whose value derives substantially from the software, including hosting and support fees. Verified from `LICENSE.md`. |
| OpenBB | **AGPL-3.0-only** | **Hard stop without legal review.** Network copyleft reaches served applications. |
| SeldonIO/alibi-detect | **BSL 1.1** (classifier: Other/Proprietary) | **Hard stop without legal review.** Delayed-open with use restrictions. |
| hudson-and-thames/mlfinlab | **Proprietary commercial** | **Hard stop.** Internal use only; explicitly forbids creating "API endpoints or … data or forecast services" without written authorisation. Not on PyPI. |
| cvxgrp/cvxportfolio | GPLv3 | Avoidable. Strong copyleft on distribution; no reason to take it on. |
| mementum/backtrader | GPLv3+ | Avoidable, and abandoned anyway. |
| nautechsystems/nautilus_trader | LGPL-3.0 | Manageable but needless — dynamic-linking obligations for no benefit here. |
| **Everything in Tier 1 and Tier 2** | MIT / BSD-2 / BSD-3 / Apache-2.0 / NCSA | **No problem.** Retain notices; Apache-2.0 also wants a NOTICE file if one is shipped. |

## Abandonment register (last release or commit older than ~18 months, i.e. before ~2025-03-11)

| Project | Last activity | Age at 2026-09-11 |
|---|---|---|
| arundo/adtk | PyPI 0.6.2, 2020-04-17 | ~77 months |
| quantopian/empyrical | commit 2020-10-14 | ~71 months |
| LemaireJean-Baptiste/eventstudy | PyPI 0.1a12, 2021-04-03 | ~65 months |
| mementum/backtrader | commit + PyPI, 2023-04-19 | ~41 months |
| AI4Finance/FinRL | PyPI 0.3.7, 2024-04-12 | ~29 months (PyPI only) |
| salesforce/Merlion | PyPI 2.0.4, 2024-06-20 | ~27 months |
| hmmlearn | commit + PyPI, 2024-10-31 | ~22 months |

**Dormant but not yet flagged** (worth knowing before depending on them): `alphalens-reloaded` and
`pyfolio-reloaded` (both last commit 2025-06-02, ~15 months, one commit each in the preceding year);
`empyrical-reloaded` (2025-07-29, ~13 months); `cvxportfolio` (PyPI 2025-07-06, ~14 months);
`zipline-reloaded` (2025-11-13, ~10 months, dependabot only).

---

## Claims I could NOT verify

Listed so nothing above is mistaken for a verified fact.

**Access limitations.** The GitHub REST API and `gh` CLI were unavailable (the session proxy permits GitHub API
access only to this repository), and GitHub commit Atom feeds returned empty. All GitHub figures therefore come
from rendered HTML pages, which means:

1. **All star counts are GitHub's rounded labels** ("9.1k", "48.5k", "6,000"), not exact integers, as of
   2026-09-11. Treat as ±100.
2. **Exact last-commit timestamps** are GitHub's rendered dates, without times or time zones.

**Specific unverified items:**

3. **Star counts not obtained at all** for: `pyfolio-reloaded`, `empyrical-reloaded`, `cvxportfolio`,
   `Lumiwealth/quantstats_lumi`, `pmorissette/ffn`, `statsmodels`, `hmmlearn`, `online-ml/river`,
   `stumpy-dev/stumpy`, `SeldonIO/alibi-detect`, `salesforce/Merlion`, `arundo/adtk`, `blue-yonder/tsfresh`,
   `hudson-and-thames/mlfinlab`, `AI4Finance-Foundation/FinRL`, `OpenBB`.
4. **`cvxportfolio` release date discrepancy.** PyPI reports v1.5.1 uploaded **2025-07-06**; one fetch of the
   GitHub releases page rendered the same tag as "July 6, 2024". The commits page for `main` showed only
   automated daily-reconciliation commits ending 2024-08-09. I have used the PyPI date as authoritative, but the
   project's true development cadence is **unverified**.
5. **`arch` licence** — PyPI reports `NCSA`; I did **not** read the repo's LICENSE file to confirm. Same for
   `linearmodels` (repo page shows the label "NCSA"; full text unread).
6. **`quantopian/alphalens` last commit** — not fetched. Inferred dead from Quantopian's 2020 shutdown.
   **`quantopian/pyfolio`** likewise not fetched.
7. **`microsoft/qlib` and `nautilus_trader` and `edgartools` last-commit dates** — for qlib I have commits to
   2026-07-23; for nautilus_trader and edgartools I relied on PyPI upload dates (2026-08-02 and 2026-09-08), not
   commit pages.
8. **RD-Agent's benchmark market.** The arXiv abstract says "real markets" without naming one. Third-party
   papers report CSI300/CSI500 for RD-Agent baselines, and qlib's bundled benchmarks are CSI300/CSI500. **I
   could not confirm whether RD-Agent(Q)'s headline 2× ARR result involves US equities at all.** The "NeurIPS
   2025 accepted" status comes from secondary reporting, not the proceedings.
9. **`TradingAgents` star count** is 102.1k–105k depending on source; both sources are reported above. Its
   absence of out-of-sample validation is an absence of evidence in the README and repo page I reviewed — **I
   did not audit the full repository or its paper** to prove no validation exists anywhere.
10. **ETF-overlap and market-regime repos** (`IV1T3/PortfolioOverlap`, `sorgmi/pyetfoverlap`, `slihn/overlap`,
    `ethansilvas/etf-portfolio-analyzer`, and all nine regime repos listed in area 4): **stars, licences and
    commit dates unverified.** Assessed as toys from their descriptions alone.
11. **`global-capital-allocation-project/public-US-funds-data`**: 15 stars verified; **licence not displayed**
    on the repo page, maintaining institution and accompanying paper **unverified**, last commit date
    **unverified**.
12. **`easy_es` and `py_event_studies` licences** — neither declares a licence in its PyPI metadata; repos not
    inspected.
13. **Academic citations.** MacKinlay (1997) for event-study methodology, Patell and BMP (Boehmer-Musumeci-
    Poulsen) for the standardised-residual tests, and López de Prado for HRP and covariance
    denoising/detoning — **I cited these from background knowledge and did not verify a single one against a
    primary source in this session.** Verify every one before it appears on a methodology page.
14. **Newer LLM alpha-mining projects** (QuantaAlpha, AlphaLogics, XALPHA, FactorEngine, AlphaForge,
    "Cognitive Alpha Mining"): surfaced as arXiv PDFs in search results only. **Repositories, authors, stars,
    licences and maintenance status all unverified.** Named solely to mark the category.
15. **`skfolio`, `Riskfolio-Lib` and `PyPortfolioOpt` feature lists** come from their README / repo pages, not
    from reading source. The specific claim that skfolio's "Benchmark Tracking" optimiser suits a long-only
    SPY-relative book is my assessment from its description, **not verified against its implementation.**
