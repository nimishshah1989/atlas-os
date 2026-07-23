# Wealth: what lifetime transaction data unlocks

Status: brainstorm + tooling research (2026-07-21), ahead of receiving full buy/sell/switch/SIP
history for the ~220 clients already loaded in `wealth`. Companion to
`wealth-recommendation-framework.md`.

## Why this is the biggest possible data upgrade

Three fundamental changes, in increasing order of value:

1. **Inference → measurement.** Today we infer behaviour from one snapshot (SIP flag, flow
   summary). With dated transactions, every behavioural claim becomes a computed number.
2. **Estimates → exactness.** Benchmark alpha, tax lots, exit-load windows, switch dating —
   all currently approximated — become exact and auditable.
3. **No labels → labels.** Prediction needs historical outcomes. Transactions give thousands
   of labelled events (SIP stops, redemptions, switches, panic exits) — this is what makes
   ML legitimate here. n=220 clients is small; n=tens of thousands of *events* is not.

## Capability map

### Tier 1 — exact foundations (build first; everything else stands on these)

| Capability | Method | Notes |
|---|---|---|
| Reconciliation gate | reconstruct holdings from transactions; must equal the loaded valuation reports unit-for-unit | same DoD philosophy as the parser gates; catches missing/duplicate transactions |
| FIFO lot ledger + exact tax | reuse `atlas/portfolio`'s Indian FIFO tax ledger (PR #157): LTCG/STCG per lot, grandfathering (31-Jan-2018), exit-load windows | makes every recommendation's cost side exact instead of estimated |
| Exact XIRR + exact benchmark alpha | replay every true external flow into the Nifty-50 index fund (and later risk-matched blends) | removes the switch-in dating bias flagged in the current benchmark page |

### Tier 2 — the behavioural measurement engine (the differentiator)

| Insight | Method / model | Anchor |
|---|---|---|
| **Behaviour gap per client** (₹/yr lost to timing) | investor (money-weighted) return vs fund (time-weighted) return, per client × fund × year — Morningstar "Mind the Gap" methodology; US gap ≈ 1.1-1.2pp/yr | include the Hayley (2014) mechanical-gap critique; report the gap honestly, not all of it is "behaviour" |
| **Disposition effect** (selling winners, keeping losers) | Odean PGR/PLR: proportion of gains realized vs losses realized, per client | methodology from the `dispositionEffect` R package + published replications; direct Python port |
| **Performance chasing** | regress client inflows on trailing category/fund returns (flow-performance sensitivity per client) | the −31% 2026 commodity chasers, now measurable per client, in advance |
| **Panic fingerprint** | event study around drawdowns: who redeemed in Mar-2020 / 2022 / 2025-26 corrections vs who bought — a natural experiment already sitting in the history | the strongest risk-capacity signal that exists; beats any questionnaire |
| **SIP survival** | Kaplan-Meier / Cox on SIP streak lifetimes; covariates: market state, fund performance, client traits | predicts *when* discipline breaks, not just whether |
| **Switch-regret ledger** | for every historical switch: return of sold fund vs bought fund afterwards → was the switch worth it? | ALSO evaluates the house's own historical advice — advice-alpha per adoption wave (silver Aug-25, Defence May-25, Quant 2021…) |
| Herding / push detection | cross-client flow clustering by fund-month; organic vs distributor-driven waves | separates client behaviour from house behaviour in every other metric |

### Tier 3 — prediction (now legitimate, because labels exist)

| Model | Purpose | Tooling |
|---|---|---|
| Redemption / attrition early-warning | survival models (Cox, random survival forests) + gradient boosting on behavioural features; label = large redemptions/dormancy in history | `lifelines`, `scikit-survival`; direct AUM defence |
| Client lifetime value | BTYD-family (frequency/recency of purchases → expected future flows) | `lifetimes`-style models; prioritizes RM time |
| Next-action propensity | who tops up / accepts a rec if asked; later upgrade to uplift modelling once rec lifecycle logs accumulate | `causalml` / `EconML` for causal rec-impact measurement |
| Book cash-flow forecast | expected SIP inflows, redemptions, trail revenue by month | gradient boosting / classical TS; feeds business planning |
| Behavioural feature factory | automatic feature extraction from each client's transaction stream, then clustering into learned behavioural segments | `tsfresh` for features; k-means/HDBSCAN with bootstrap stability (n=220 caveat: keep clusters few) |
| Anomaly flags | isolation forest on transaction patterns | compliance + elder-protection angle |

### Tier 4 — counterfactual conversations (the pitch artillery)

Exact, per-client, rupee-quantified replays: *"if you had never stopped that SIP"*, *"if you
hadn't sold in March 2020"*, *"if none of your switches had happened"*, *"if the same flows had
gone to the index"*. These are deterministic replays against real NAV history — no model risk —
and they are the most persuasive client conversations this business can produce.

## Tooling research (verified)

- **[codereverser/casparser](https://github.com/codereverser/casparser)** — MIT, PyPI: parses
  CAMS/KFintech CAS PDFs to full transaction history with ISIN/AMFI mapping, even capital-gains
  (incl. 112A) reports. If the data arrives as CAS PDFs, ingestion is largely solved. There is
  also tooling around **RTA reverse-feed files** (the distributor-side data format Jhaveri
  likely receives) with FIFO position building.
- **[Morningstar Mind the Gap](https://www.morningstar.com/business/insights/research/mind-the-gap)** —
  the published investor-return methodology to replicate per client; critique to encode:
  [FAJ examination](https://www.tandfonline.com/doi/full/10.1080/0015198X.2026.2657253) of the
  mechanical component.
- **[dispositionEffect](https://marcozanotti.github.io/dispositionEffect/articles/de-analysis.html)**
  (R, methodology reference) + [aggregate-data Python variant](https://github.com/js-park/Disposition-effect-from-Aggregate-trading-data) —
  PGR/PLR computation spec; we port to Python over our schema.
- **[quantstats](https://github.com/ranaroussi/quantstats)** — tear-sheet metrics over return
  series (per-client and per-fund analytics pages).
- **[lifelines](https://github.com/topics/survival-analysis?l=python)** / **scikit-survival** —
  SIP survival + churn timing (worked churn examples:
  [survival churn](https://github.com/ejeej/Survival_Analysis_Customers_Churn),
  [churn + LTV](https://github.com/archd3sai/Customer-Survival-Analysis-and-Churn-Prediction)).
- **[tsfresh](https://github.com/blue-yonder/tsfresh)** — automatic feature extraction from
  event/time series with built-in feature-significance filtering; the behavioural feature factory.
- `causalml` / `EconML` — uplift & heterogeneous treatment effects for measuring recommendation
  impact causally once the rec lifecycle log has volume.
- `PyPortfolioOpt` / `riskfolio-lib` / `skfolio` — constrained optimization for the seat-shift
  engine (max quality at ≤ current risk, ≤ N moves, tax budget) when we graduate from greedy swaps.

No single repo does the whole thing; the moat is the combination over proprietary data.

## Schema + gates (when data arrives)

`wealth.transactions` (client_id, scheme_id, folio, txn_date, txn_type
[buy|sell|switch_in|switch_out|sip|swp|div_payout|div_reinvest|stt/stamp rows], units, nav,
amount, source_file, load provenance). Same discipline as before: loader refuses files that
fail unit/amount×NAV checks; a full-book gate reconstructs holdings from transactions and
diffs against `wealth.holdings` — mismatches are named, never silently loaded.

## Honest constraints

- **220 clients is small** for client-level ML; the power is at event level (likely 10-50k
  transactions). Client-level models stay simple and interpretable; event-level models can be richer.
- Behaviour-gap numbers carry a mechanical component (Hayley) — report the gap with its
  decomposition, not as pure "investor error".
- Advice-attribution (switch-regret on house pushes) is internally sensitive — it will grade
  Jhaveri's own historical calls. That honesty is exactly what makes the forward engine credible.
- Survivorship: the book only contains clients who stayed. Departed-client history (if included
  in the feed) is gold for churn models; ask for it explicitly.

## Build order

1. Ingest + reconciliation gate (+ casparser/RTA route depending on format)
2. FIFO lot ledger reuse → exact tax on every rec (upgrades the existing rules engine immediately)
3. Exact XIRR/benchmark + behaviour-gap engine (client-facing gold)
4. Behavioural fingerprints (disposition, chasing, panic, SIP survival) → segments v2
5. Switch-regret + advice-alpha ledger (internal first)
6. Churn early-warning + CLV → RM priority queue v2
7. Counterfactual conversation pack per client
8. Uplift measurement loop on recommendations (needs lifecycle log volume)
