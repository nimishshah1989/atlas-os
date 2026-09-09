# Global Atlas — Phase 2: a board that ranks (FM plan, 2026-09-09)

This is the handoff the FM asked for on 2026-09-09: what is wrong today, what gets built, in what
order, and what "done" means for each piece. Nothing in here is started before this document is
committed. The FM sees the result once, when every item below is green — not intermittently.

Supersedes nothing. `plan.md` remains the methodology source of truth (§B stock lenses, §C ETF
lenses, §D roll-ups, §E validation); `phase1.md` remains the price-spine and identity record. This
document is the Phase 2–3 execution plan and it records four FM decisions that change scope.

---

## 1. The four decisions of 2026-09-09

| # | Decision | Consequence |
|---|---|---|
| D1 | **Global gets one tab, and it is Countries.** The country grid is the entry point: the RS heat map the FM already designed, plus a ranking. | `/countries` becomes the board's front door; `/` redirects to it until a Today page earns its place. |
| D2 | **Rank everything the way Atlas already ranks.** Composite score → deciles/quartiles within a cohort → conviction tier. For countries AND for ETFs. | The India mechanism (`decile_core.py`, `compute_composite`, `DecileMeter`) is ported, not reinvented. |
| D3 | **Stop crowding the platform.** Stocks: the ~503 current S&P 500 members only, no trailing members. ETFs: nothing below the $1M ADV floor, nothing leveraged or inverse. | The board renders the in-universe set only. See §3 — the rule already exists and is simply not applied. |
| D4 | **Adopt the Jhaveri desk design language** (`rebalance.13-206-34-214.sslip.io`). The current one is rejected. | Full retheme: cream ground, navy top bar, gold active rule, serif throughout, dense tables. §7. |

Standing constraints unchanged: **rule #0** (no synthetic, mocked or placeholder numbers, anywhere,
including tests), every weight and threshold in `atlas_global.atlas_thresholds`, Decimal money,
tz-aware datetimes, one schema per market, the repo is public.

---

## 2. The correction the FM is owed

The FM asked why only the technical lens can be scored, "when we had all the sources done". He is
right and the earlier framing was wrong. Precisely:

* **Every source is identified, free, and documented** in `data-sources.md`: SEC EDGAR XBRL company
  facts (per-company financials, point-in-time by `filed`), EDGAR 8-K item codes, EDGAR Form 4
  (insider), EDGAR 13F (institutional), EDGAR N-PORT (fund holdings and net assets for the entire
  ETF universe), FINRA short interest, issuer product files (expense ratio, AUM, daily holdings).
* **None of their ingestors were ever written.** Four are commented out of
  `scripts/ops/atlas_global_daily.sh` — `ingest_filings_8k`, `ingest_form4`,
  `ingest_issuer_holdings`, `build_exposures`. The other four are absent from it entirely:
  `ingest_financials`, `ingest_13f`, `ingest_short_interest`, `ingest_nport`. **No script behind
  any of the eight exists.** `edgartools` is not yet a declared dependency (repo rule: a package
  is added in the PR that first imports it).
* **FRED is macro only** — SP500 index level, VIX, DGS10, DTB3, DTWEXBGS. It feeds the pulse strip
  and the price cross-check. It can never feed a per-company fundamental lens; nothing in FRED knows
  what Apple's return on equity is.

So the blocker was never data availability. It is missing producer code, which is Phase 2–3 work and
is planned below in full.

---

## 3. The state today, without euphemism

**Produced nightly and trustworthy:** `ohlcv_daily` (raw + split-adjusted + total-return closes),
`macro_daily`, `technical_daily` (60 metrics per instrument: six EMAs and their flags, RSI, ATR,
Bollinger width, nine return windows, six RS-vs-SPY windows in relative form, 52-week position,
ADV$, three volatility windows, downside deviation, 12m and 36m max drawdown, beta and correlation
to SPY, Sharpe, Sortino, Calmar), `universe_snapshot`, `country_daily` (representative fund + RS
only). Weekly: `instrument_master`, `index_membership` (SPY holdings → S&P 500 membership).

**Empty, with no producer anywhere:** `lens_scores_daily`, `etf_scores_daily`, `etf_classification`,
`etf_meta`, `etf_holdings`, `etf_exposure_daily`, `etf_shares_daily`, `stock_financials_pit`,
`filings_8k`, `insider_form4`, `holders_13f_q`, `short_interest`, `atlas_signal_ic`, `basket_*`.
`country_daily.composite` and `.breadth_pct` are NULL for the same reason.

**Built and unused:** `atlas/global_market/scoring/blend.py` (the composite blend, parity-tested
bit-for-bit against India's `compute_composite`, zero callers); the `DecileChip`, `LensBar` and
`CompositeNumeral` components; the entire `etf_classification` table.

**Classification runs every night and its verdicts are discarded.** `classify_strategy` sorts a fund
name into 17 strategy buckets (broad market, size/style, factor, dividend income, sector, thematic,
country, region, single stock, fixed income, commodity, currency, crypto, defined outcome, options
income, multi-asset, alternative); `leverage_flags` detects geared and inverse; `country_of` gives
ISO code and region; `is_currency_hedged` detects hedged share classes. All four are called at
runtime by the universe and country builders, used for one boolean each, and thrown away. About 22%
of fund names match no strategy rule — those are a review queue, not a silent bucket.

**The universe rule the FM asked for already exists.** `build_universe_snapshot.py` writes
`in_universe` with exactly D3's semantics — a stock must be a current S&P 500 member, an ETF must be
neither leveraged nor inverse and must clear the `liquidity_min_traded_value_usd` floor ($1M, set by
the FM from the real ADV$ distribution) — and `exclusion_reason` names the first rule each excluded
row failed (`no_bars`, `not_sp500`, `leveraged`, `inverse`, `below_floor`, insufficient
observations, stale). **The board ignores this flag.** `/etfs` lists all 5,655 funds with "Universe"
as an optional facet defaulting to "any", sorted alphabetically, so the first screen is illiquid
names with blank metrics. That is the "I can't read it, there's nothing I can do" complaint, and it
is a filter that was built and never switched on.

**Why the ETF table is unreadable**, mechanically: the Name column is declared `width: 0` in a
`table-layout: fixed` table, so it gets only the leftover of a 1,324px minimum spread across 13
sized columns; `white-space: nowrap; overflow: hidden; text-overflow: ellipsis` then clips every
fund name to a few characters. Fourteen columns of undifferentiated grey numerals force horizontal
scrolling below ~1400px, and nothing is colour-encoded, so the eye has no anchor.

---

## 4. What gets built, in order

Each chunk is a PR: implement → `make gate` → self-review the diff → merge → auto-deploy → verify on
the live host → next. The FM is not asked to test any of them.

### P2-A — Apply the universe (D3)

* `/etfs` and `/stocks` default to `in_universe = true` on the latest snapshot. An "Everything
  listed" toggle reveals the rest with its `exclusion_reason` shown per row, so nothing is hidden,
  it is just not the default.
* `compute_technicals` already defaults to `--scope universe`; confirm the nightly passes no
  `--scope all`, so the nightly stops computing 60 metrics for ~11,000 instruments nobody sees.
* Stock explorer drops the "S&P 500: any" facet — membership is the universe, not a filter.
* **History is not deleted.** Bars and metrics already computed for out-of-universe instruments stay
  in the database: deleting is irreversible, costs nothing to keep, and survivorship-honest
  backtests need trailing members later. They are simply not computed forward and not shown.
* **Done when:** `/etfs` first screen is the liquid, unleveraged set sorted by score, `/stocks` shows
  503 ± index changes, and the nightly's technicals target count drops accordingly in its own log.

### P2-B — Persist the classification

* New `scripts/global_market/classify_etfs.py`: one `etf_classification` row per active ETF from the
  four rule modules — `strategy`, `asset_class` (equity / fixed_income / commodity / currency /
  multi_asset / alternative, derived from the strategy bucket), `country_codes`, `geo_focus_type`,
  `leveraged`, `inverse`, `hedged`, `classified_by = 'rules'`, `evidence` = the matched text,
  `status = 'auto'` where a rule fired and `'review'` where none did.
* Nightly step + weekly full pass; registered in `freshness_guard.py` PRODUCERS.
* **No LLM in this chunk.** The ~22% unmatched are a visible "Unclassified" bucket on the board with
  their names listed. The LLM classification layer (`plan.md` §Classification L3) is Phase 3 and
  needs the FM's 150-name eval set before it is allowed to write a field.
* **Done when:** every active ETF has a row; the strategy distribution is printed and sanity-read;
  every ProShares/Direxion geared fund is flagged; a fund named "...ex Japan" is not a Japan fund.

### P2-C — ETF scoring and ranking

* New `atlas/global_market/scoring/etf_lenses.py` (pure, unit-tested) + `scripts/global_market/score_etfs.py`.
* Lenses computed in this chunk, exactly per `plan.md` §C, from `technical_daily` alone:
  * **technical** (seed weight 0.35): trend from EMA alignment and price vs EMA200; RS vs SPY at 3m,
    6m and 12m against the seeded `rs_spy_strong`; RS vs peers as the percentile of 6m return within
    peer group; structure from EMA50 > EMA200 and EMA21 > EMA50.
  * **risk** (seed weight 0, overlay — displayed, not blended, until the FM sets a weight): vol
    percentile, 12m max drawdown percentile, downside deviation percentile, beta band.
  * **cost_liquidity**: only its `cost_adv` sub-score is computable now; `cost_expense`, `cost_aum`
    and `cost_concentration` land in P3-C and the lens renormalises over present subs.
* **Peer group = asset class × strategy** (e.g. `equity:sector`, `equity:country`,
  `fixed_income:fixed_income`), falling back to the parent asset group when a group has fewer than
  the seeded `peer_group_min_members` (8). Every ETF is ranked against funds that do the same job —
  never against the whole universe, which was the FM's specific objection.
* **Deciles within peer group**, `ntile(10)` over composite, on non-null values only, the same rule
  `decile_core.py` applies within cap cohort for India. **Leader = top decile within peer group.**
  Quartiles are the same cut presented in fours where a decile is too fine for a small group.
* Conviction tiers from the seeded `lens_conviction_*` keys. With one lens active the tier ladder's
  own minimum-layer rule caps the result at MEDIUM — that is correct, not a bug, and the board says
  "1 of 5 lenses" beside every score.
* Geared and inverse funds are classified and listed but **never scored** (no row in
  `etf_scores_daily`), so they cannot appear in a ranking or a basket.
* **Done when:** every in-universe ETF has a score row; composite ∈ [0,100]; per-peer-group decile is
  monotone in composite; a hand-checked group (e.g. `equity:country`) ranks the way a person would
  order those funds by trend and relative strength.

### P2-D — Stock scoring and ranking

* `scripts/global_market/score_stocks.py` writing `lens_scores_daily` for the 503 members: the
  **technical** lens verbatim from India's scorer (`score_technical` is currency-agnostic), deciles
  within `cap_cohort` = SPY-weight terciles (mega / large / mid), tiers from the same seeded keys.
* Fundamental, valuation, catalyst and flow lenses land in P3-A and P3-B; the composite renormalises
  over present lenses and `lenses_active` is displayed.
* **Done when:** ≥95% of members scored; every lens `stddev ≥ 2`; composite `stddev ≥ 10`; deciles
  monotone within cohort.

### P2-E — Country ranking (D1)

* `build_country_views.py` gains `composite` (the representative fund's composite),
  `breadth_pct` (share of member funds at or above the seeded `rollup_breadth_min`), and a decile
  and quartile across markets.
* `/countries` becomes the board's front door: the FM's RS heat map, plus rank, composite, decile
  chip, breadth and the representative fund per market, grouped by region and sortable on every
  column. A market whose only funds are geared, inverse or hedged still appears and says so.
* `/` redirects to `/countries`.
* **Done when:** every market with a plain fund carries a composite and a decile; the ordering is
  defensible against the RS columns beside it.

### P2-F — The board surfaces rebuilt

* **ETF explorer**: default sort by composite descending within the in-universe set. Columns:
  symbol, name (a width it cannot lose), peer-group chip, composite with decile chip, technical lens
  bar, RS at 3m/6m/12m tinted the way the country grid tints, 52-week position, ADV$, volatility and
  max drawdown as the risk overlay. Exchange, listing date and SEC identity move to the detail page.
  A strip of peer-group chips with counts sits above the table, so thousands of funds read as two
  dozen groups first. Facets: peer group, country, region, decile, tier, and toggles for geared,
  inverse and unclassified.
* **Stock explorer**: the same shape, cohort instead of peer group, GICS sector facet retained.
* **Detail pages**: composite, decile within group, the score derivation tree down to sub-scores, the
  risk overlay, and a classification card naming the rule that fired and the words it matched.
* **Done when:** no name renders as an ellipsis at 1280px; the first screen answers "what is strong
  in this group" without scrolling sideways.

### P3-A — Company fundamentals (unblocks two lenses)

* `scripts/global_market/ingest_financials.py` via `edgartools` (added to the `[global]` extra in
  this PR): XBRL company facts for the 503 members → `stock_financials_pit`, keyed by `filed` so
  every ratio is point-in-time honest. Quarterly and TTM revenue, EBIT, EBITDA, net income, diluted
  EPS and shares, equity, debt, cash, operating cash flow, capex.
* `atlas/global_market/scoring/fundamentals_us.py`: the **fundamental** lens (profitability, margin,
  growth, balance sheet, operating leverage) and the **valuation** overlay (PE vs GICS-sector median,
  absolute PE, P/B, EV/EBITDA, 52-week position). **Bands are seeded from the live S&P 500
  cross-sectional quartiles, not from India's numbers** — India's "PE under 8 is cheap" is nonsense
  on this index.
* **Done when:** ≥95% of members carry ≥8 quarters; a hand-audit of five companies' ROE, margin and
  PE against their own filings agrees to the cent.

### P3-B — Events and flow

* `ingest_filings_8k.py` (item codes and dates), `ingest_form4.py` (insider open-market buys and
  sells), `ingest_short_interest.py` (FINRA files), `ingest_13f.py` (holder counts, 45-day lag
  respected) — all EDGAR/FINRA, all free.
* `stock_catalyst.py` and `stock_flow.py` per `plan.md` §B: the three-bucket catalyst score with the
  90/180/365-day decay, and the flow score centred at 50.
* **Done when:** catalyst > 0 for ≥60% of names with ≥20 filings in the window; no event double-counted.

### P3-C — ETF metadata, holdings, and the last two lenses

* `ingest_nport.py` via `edgartools`: holdings and net assets for the whole ETF universe (quarterly,
  ~60-day lag, licence-clean) → `etf_holdings`, `etf_meta.aum_usd`.
* `ingest_issuer_holdings.py`: plain CSV downloads from iShares, SSGA, Vanguard and Invesco for daily
  holdings, expense ratio and shares outstanding on the funds that carry most of the AUM.
  (`etf-scraper` the package is **not** used: its only release pins numpy < 2 and cannot coexist with
  this repo's pandas-ta. The files are plain downloads.)
* `build_exposures.py` → `etf_exposure_daily`: country, sector and asset vectors, top-10 weight, HHI,
  look-through coverage.
* Completes **cost_liquidity** (expense, AUM, concentration), **flow** (shares-outstanding deltas),
  and **quality** (holdings-weighted constituent composite and Leader weight, present only above the
  seeded look-through coverage floor).
* `holdings_as_of` is shown on every card: for non-big-four funds this data is stale by design and
  the board must say so.
* **Done when:** holdings on ≥90% of ETFs by count and ≥98% by AUM; Σ|weight| ∈ [0.9, 1.1] for ≥97%
  of unlevered funds; every ETF's `lenses_active` reflects what it actually has.

### P3-D — Validation before the scores are trusted

* `eval_signal.py` → `atlas_signal_ic`: rank information coefficient of each lens and the composite
  against forward 1/3/6/12-month returns, within cohort and peer group, plus decile spread and hit
  rate. **A lens keeps its seed weight only if its IC clears the seeded floor**; otherwise its weight
  goes to zero and it becomes an overlay until it earns one. The FM locks the final weights from
  `/admin/thresholds`.
* `validate_global --check B/C/E` wired as nightly gates.
* **Done when:** the methodology page can state "weights validated on N years of real US data" and
  point at the numbers.

---

## 5. Running in parallel (started 2026-09-09, disjoint file sets)

### W1 — The design language (D4)

The desk tool's stylesheet is public and its tokens were read verbatim: ground `#f4f0e5`, ink and
accent `#25394a`, top bar `#16294d` with a gold `#a17c2b` active underline, positive `#2c6b41`,
negative `#ab4425`, one 6px radius, serif display and body (Iowan Old Style / Palatino / Georgia),
14.5px body, tabular numerals, uppercase 10.5px muted table headers on a `#fbf9f4` panel, 9px×12px
cells, pill chips, KPI tiles with uppercase labels. The global board is entirely token-driven, so
this is a token swap plus a new shell: the left rail becomes the navy top bar with Countries, ETFs,
Stocks, Health (and a marked hook for Portfolios). Dark mode is removed — the desk tool is light
only. Every existing CSS class name is preserved, so all pages restyle at once.

### W2 — Portfolios

India's accounting engine (`atlas/portfolio/engine.py`: replay, fill timing with no lookahead, slot
model, Decimal money, marks carrying last price forward) is currency- and venue-agnostic and is
reused unchanged. The `basket_*` tables already exist in `atlas_global`. Built: `mark_baskets.py`
(inception trades at the last session close, then NAV daily), a 5-minute job worker so a new basket
is marked without waiting for the night, `validate_baskets.py` (NAV reconciles, cash never negative,
position cap, weights sum to 1), and `/portfolios` list, builder and detail with NAV against SPY,
holdings carrying each instrument's composite and decile, and the trade log.
**The India create-route pattern is not copied**: it spawns Python from a Next route handler, which
this repo forbids. The web tier writes rows and a job; the box's worker executes.
India's tax module (Indian financial year, STCG/LTCG, ₹ exemptions), the desk/MaaL/CPP layers and
the strategy evolver are **not** ported.

### W3 — Operating the nightly without the FM

`run-global-nightly.yml` (merged) runs or inspects the nightly over the same SSH path the deploy
uses: `status` prints cron entries, the last log's tail and the full status report; `run` executes
the orchestrator under the same lock the cron uses and prints every step's outcome with the reason
it now records. This exists because on 2026-09-09 the nightly had not run for a day and the only way
to learn why was a person typing on the box.

---

## 6. Explicitly deferred, with the reason

| Deferred | Why |
|---|---|
| LLM classification of the ~22% unmatched fund names | Needs the FM's 150-name labelled eval set first (`plan.md` §Classification). Until then they are an honest "Unclassified" bucket. |
| Baskets from client accounts, positions, holdings, PII | M2. The moment any of it renders, `ATLAS_GLOBAL_REQUIRE_AUTH=1` goes back on in the same PR (`openAccess.ts`). |
| Conversational builder, execution engine | M3/M4, unchanged from `plan.md`. |
| Pre-2016 archive history rescale | Open item #25; does not block any score, which needs 3 years. |
| Deleting out-of-universe history | Irreversible, no benefit; they are excluded from compute and display instead. |

---

## 7. Delivery protocol

1. Every chunk lands as its own PR with `make gate` green (lint, format, unit tests, pyright
   ratchet), the frontend's typecheck, tests and production build green, and the schema gate clean.
2. Merged PRs auto-deploy; each is verified against the live host before the next begins.
3. Verification chains use `pipefail` and read the real exit code. The 2026-09-08 lesson — a gate
   piped through `tail` reports the pipe's success, not the gate's — is not repeated.
4. **The FM is not asked to test intermittently.** He looks once, when §4's P2 chunks and §5's W1
   and W2 are all green on `global.jslwealth.in`.
5. Anything that turns out to be impossible or wrong is reported in one line with what was done
   instead — never quietly dropped.

## 8. Two facts that gate everything

* **The board's data is as of 7 September.** The nightly did not run on 8 or 9 September; the 8
  September run failed at price ingestion and the reason was never recorded (it is recorded from now
  on). W3's workflow runs it. If the failure is the burned Alpaca credential, only the FM can fix it,
  and that will be said the moment it is seen rather than worked around.
* **Five credentials pasted in plaintext chat on 2026-09-08 are still unrotated** (two Alpaca, three
  Supabase). They are burned. Nothing in this plan depends on them staying valid.
