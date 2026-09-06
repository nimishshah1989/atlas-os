# Global Atlas — US-market sibling platform (final plan, 2026-09-04)

## Context

Atlas today is a discovery-first equity-intelligence board for Indian markets: nightly real-data
ingestion → six-lens scoring → glass-box Next.js board over one Postgres schema
(`atlas_foundation`). The FM wants a **second platform in the same repo** — separate URL,
separate (much better) UI — for the US market: **S&P 500 stocks + US-listed ETFs**, whose
product is **baskets** (ETF-first, later stocks) sold under an investment-adviser licence with
fractional shares, built through a **conversational interface**, with an **execution engine**
later. The intelligence to build: (1) a **classification engine** for ETFs far more nuanced
than India's 21 sectors (country, sector, sub-sector, theme, "picks-and-shovels" role, AUM,
liquidity, structure flags); (2) a **scoring methodology** in the Atlas lens/composite style over
the data points the US market actually gives us, on ≥3 years (target 2016→) of clean adjusted
OHLCV so any-period returns are computable.

A US platform (`us_atlas` schema, 16 tables, Stooq-fed crons) **already existed here and was
dropped** (FM decision D7, `docs/table-census.md`) because its producers fed only orphan routes —
"compute with no consumer". This plan is consumer-first: every producer names the board
surface that reads it, in the same phase.

## Decisions locked with the FM (this session)

| Decision | Choice |
|---|---|
| ETF universe | **Every US-listed ETF (any exchange) is classified**; **scoring + basket eligibility above a liquidity floor** — trailing-60-day median $ volume ≥ `atlas_thresholds.liquidity_min_traded_value_usd` (the `scripts/foundation/universe_core.py` predicate), FM sets the floor from the real ADV$ distribution printed in Phase 1. Not a top-N-by-AUM cut, so niche-but-traded ETFs survive. |
| Data cost | **Free-first behind a provider abstraction; one paid feed slot allowed later** only if a free source fails the data gates. |
| DB placement | **New schema `atlas_global` in the same Supabase project.** Rule #1 becomes "one schema per market, zero cross-schema references" — ADR + gate edits in Phase 0. |
| Milestone 1 | **Classification engine + full scoring methodology implemented + proper views, including a dedicated country-ETF view** (ETFs tracking a single country's market) that becomes its own **country-basket product line**. |
| Price fallback | FM can hand-download **Stooq bulk CSVs** (`d_us_txt.zip`, ticker-only files like `AAPL.US`); a first-class importer + ticker→identity bridge is in Phase 1. |
| Tooling | gstack / ponytail / graphify / headroom are real but **not installed in this cloud environment**. Phase 0 vendors what can be vendored; headroom is laptop-side (`headroom wrap claude`). |

## Non-negotiables inherited from Atlas (apply verbatim to `atlas_global`)

- **Rule #0 — no synthetic/derived data.** Every number traces to a real feed or a stated
  computation over real feeds; gates assert on produced output, never fixtures
  (`scripts/foundation/validate_lenses.py`: one assertion per past incident).
- **No hardcoded methodology numbers** — every weight/threshold/floor in
  `atlas_global.atlas_thresholds`, edited from the global admin.
- **Decimal for money, tz-aware datetimes** — USD, `America/New_York`; no `_cr` names.
- **One EOD anchor** — `eod_cutoff()` in `scripts/global_market/_gdb.py` (17:00 ET); every writer
  stamps from it (the `date.today()` bug in `ingest_mf_holdings.py` hid a fresh snapshot for a month).
- **Producer registry** (`scripts/ops/freshness_guard.py:82-107` + `tests/unit/test_producer_registry.py`)
  copied day one: the unit test goes red the moment a guarded table loses its cron step.
- **Point-in-time discipline** — availability = actual EDGAR `filed` date; forward-only
  `universe_snapshot`; as-of loaders everywhere.
- **Glass box everywhere; no raw stats on user pages** (CONTEXT.md language rule); IC/z-scores
  only on `/methodology` and `/admin`.
- **Model proposes, deterministic code executes** (`atlas/desk/__init__.py` contract) for every
  LLM step; constrained output + per-claim validation + fallback (CONTEXT.md "LLM factuality guard").
- **Repo is public** — keys only in `.env` / Vercel env; gitleaks stays on.
- File-size tiers, modulith boundaries, pyright ratchet, `make gate` before every PR.

## Architecture

### Repo layout (new paths)

```
atlas/db.py                        + get_engine(session_tz="Asia/Kolkata") (one cached engine per tz value); _VALID_SCHEMAS = {atlas_foundation, atlas_global}
atlas/config.py                    + MarketConfig dataclass, MARKETS["india"|"us"] (schema, tz, close_hour, calendar anchor, ccy, history_start)
atlas/global_market/               NEW bounded context (`atlas/global` is a Python keyword)
  calendar.py                      sessions = presence of SPY bars (membership-by-presence, as India does with NIFTY 50)
  providers/{base,alpaca,stooq_bulk,edgar,issuer_holdings,symbology,fred}.py   the ONLY off-box boundary
  classify/{taxonomy,exposures,rules,llm,validate}.py
  scoring/{blend,etf_lenses,stock_catalyst,stock_flow,fundamentals_us}.py
  pipeline_etf.py / pipeline_stock.py   loads → pure scorers → writers
scripts/global_market/_gdb.py      re-exports scripts/foundation/_db helpers; SCHEMA="atlas_global"; eod_cutoff() at 17:00 ET
scripts/global_market/ddl/00_core.sql … 06_baskets.sql   idempotent DDL (source of truth); apply_ddl.py
scripts/global_market/{build_identity,ingest_prices,import_stooq,ingest_macro,ingest_index_membership,ingest_issuer_holdings,
  ingest_nport,ingest_financials,ingest_filings_8k,ingest_form4,ingest_13f,ingest_short_interest,compute_technicals,
  build_exposures,classify_etfs,score_stocks,score_etfs,build_country_views,build_universe_snapshot,eval_signal,
  validate_global,freshness_guard,write_health_snapshot,mark_baskets}.py
scripts/ops/atlas_global_daily.sh  01:00 UTC Tue–Sat (= 21:00 ET, after extended hours; 06:30 IST, before India's day)
scripts/ops/atlas_global_weekly.sh Sat 01:00 UTC (India weekly is 07:00 UTC, daily 10:30 UTC — no CPU overlap)
migrations/versions/0002_atlas_global.py   op.execute() of the DDL files so CI's fresh-PG17 job proves they apply
tests/unit/global_market/          producer-registry copy, boundary test, blend parity, symbology parsers on real file rows
tests/integration/global_market/   real-data reconciliation (scorer vs stored rows), exposure sums, calendar
frontend-global/                   NEW Next.js 15 app (App Router, React 19, TS, Tailwind v4)
docs/adr/0006-second-schema-atlas-global.md · docs/global/{taxonomy,data-sources,methodology,runbook}.md
```

### Edits to existing code (all Phase 0, all small)

- `scripts/hooks/check_module_boundaries.py` — the hook is context-level and skips packages not in
  `CONTEXTS`. Add `"atlas.global_market"` to `CONTEXTS`; add an `ALLOWED_SUBTREE_EDGES` check by
  module prefix with `("atlas.global_market", "atlas.lenses.compute")`,
  `("atlas.global_market", "atlas.compute.signal_eval")`, `("atlas.global_market", "atlas.compute._session")`,
  `("atlas.global_market", "atlas.portfolio.engine")`. `atlas.lenses.data` / `atlas.lenses.pipeline`
  stay forbidden. Do **not** widen `SHARED_KERNEL`.
- `scripts/ops/schema_gate.py` — today the regex `(atlas|public|us_atlas|global_atlas|mfwatch)\.`
  would not even see `atlas_global.`. Rewrite as "one schema per tree, zero cross-references":
  India live list may not mention `atlas_global.`; a new GLOBAL list
  (`scripts/global_market/**`, `atlas/global_market/**`, `frontend-global/src/lib/queries/**`)
  may not mention `atlas_foundation.` / `public.`. Both run in CI.
- `atlas/db.py` — `get_engine(session_tz)` (line 40-43 listener parameterised; India callers
  unchanged); `_VALID_SCHEMAS = {"atlas_foundation", "atlas_global"}` (drop the dead names) and
  fix `tests/unit/test_load_thresholds_callers.py`, which passes `"atlas"`.
- `atlas/lenses/compute/composite.py` is **not edited**: lens names are a module constant
  (line 32) and missing thresholds fall back to `_DEFAULT_*`. `atlas/global_market/scoring/blend.py`
  = weighted mean over present lenses + tier cut over a dict, **parity-tested against
  `compute_composite` on real `atlas_foundation` rows**; the global pipeline asserts every weight
  key exists in `atlas_global.atlas_thresholds` (no silent defaults).
- `scripts/foundation/universe_core.py:members()` reused verbatim (`floor_inr` is just a Decimal).
- `scripts/foundation/technicals.py` imported as-is; add a relative-form `compute_relative_strength`
  variant (ADR-0002 form) rather than editing India's difference form.

### Schema `atlas_global` — core tables (USD `numeric`, one weight scale)

- `instrument_master` — `instrument_id uuid` (uuid5 over a **stable** identity:
  `us:{class}:{cik}:{symbol}` when the SEC identity is known, else
  `us:{class}:{symbol}:{listing_date}` — never the bare symbol: US tickers are recycled after
  delistings and a recycled ticker is a new instrument; amended 2026-09-04 after review),
  `asset_class` (stock|etf), `symbol` unique among **active** rows (partial index), `name`,
  `exchange`, `cik`, `series_id`, `class_id`, `alpaca_asset_id`, `tradable`, `fractionable`,
  `listing_date`, `delisted_at`, `is_active`, `sector_gics`, `sub_sector_id`, `source`.
  `build_identity.py` is its **only** writer.
- `symbol_alias` — `(source, source_symbol, valid_from)` → `instrument_id` (`AAPL.US`, `BRK-B` vs
  `BRK.B`; renames create an alias, never a second instrument).
- `ohlcv_daily` — PK `(instrument_id, date)`: raw `open/high/low/close/volume`, `close_adj`
  (split-only, for charts), `close_tr` (splits + dividends, for every return/RS/score),
  `trade_count`, `vwap`, `source` (alpaca|stooq_csv), `adjustment_source`. **One table for stocks
  and ETFs.** Calendar = `DISTINCT date WHERE instrument_id = SPY`.
- `benchmark_master` — `code → instrument_id, role` (SPY market, QQQ growth, IWM small, VXUS intl,
  AGG bond, GLD gold, BIL cash). Benchmarks are ETFs with their own total-return bars — **no
  separate benchmark-price table.** `macro_daily` — FRED `SP500` (price-only, cross-check),
  `VIXCLS`, `DGS10`, `DTB3` (risk-free), `DTWEXBGS`.
- `index_membership` — `(index_code, instrument_id, effective_from, effective_to, weight_frac)`
  from SSGA SPY daily holdings + `fja05680/sp500` history.
- `technical_daily` — EMA 10/13/21/34/50/200 + flags, RSI, `ret_{1d…36m}`, `rs_{w}_spy`,
  `rs_{w}_peer` (relative form on `close_tr`), ATR, BB width, vol ratios, `pos_52w`,
  `adv_usd_60d_median`, `vol_63d_ann`, `mdd_12m`, `beta_spy_252`, `compute_run_id`.
- `etf_meta` — issuer, family, inception, `expense_ratio` (+`expense_source`), `aum_usd`
  (+`aum_as_of`, `aum_source` ∈ nport|issuer_list|yfinance_unofficial), `shares_outstanding`
  (+source), `index_tracked`, `is_active_mgmt`, `leveraged_factor`, `is_inverse`,
  `is_currency_hedged`, `derivatives_share`. `etf_shares_daily` — flow-lens input.
- `etf_holdings` — PK `(instrument_id, as_of_date, holding_key)`; `holding_instrument_id` (nullable),
  `weight_frac numeric(12,8)` **fraction, always** (name carries the unit; gate Σ|w| ∈ [0.9,1.1] for
  non-leveraged), `market_value_usd`, `country_iso2`, `asset_category`, `source` (issuer_csv|nport).
  Append-only snapshots; readers take `max(as_of_date) ≤ lens date`.
- `etf_exposure_daily` — `country_vec`, `sector_vec`, `asset_vec` (jsonb of fractions),
  `top_country`, `top_country_w`, `equity_w`, `n_holdings`, `top10_w`, `hhi`, `lookthrough_scored_w`.
- Taxonomy: `taxonomy_sector` (level 1 = GICS 11, level 2 = sub-sector e.g. `energy_renewable_solar`,
  `energy_midstream_transmission`, `energy_nuclear_uranium`, `utilities_grid`; level 3 = theme),
  `taxonomy_geo` (country|region|global, ISO2, region roll-up), `taxonomy_role`
  (pure_play | picks_and_shovels | diversified | not_applicable). Seeded from `docs/global/taxonomy.md`
  (FM-reviewed, versioned).
- `etf_classification` — `(instrument_id, version)`: `sector_id`, `sub_sector_id`, `theme_ids[]`,
  `geo_focus_type` (single_country|region|global), `country_codes[]`, `country_pure`, `role_id`,
  `leveraged`, `inverse`, `hedged`, `active`, `basket_eligible`, `confidence`, `rationale`,
  `evidence jsonb` (cited holdings), `classified_by` (rules|llm:<model>|human:<email>),
  `status` (auto|review|confirmed|override), `valid_from/to`. `etf_classification_override` —
  per-field sticky human overrides, re-applied on every run. `classification_validation_log`.
- `stock_financials_pit` — PK `(instrument_id, period_end, form, filed)`: revenue, operating
  income, net income, EPS diluted, shares, equity, assets, debt, cash, D&A; **`filed` is the PIT key**.
- `filings_8k` (items[]), `insider_form4`, `holders_13f_q`, `short_interest` (FINRA bi-monthly).
- `lens_scores_daily` (stocks; same shape as `atlas_foundation.atlas_lens_scores_daily` + `cap_cohort`),
  `etf_scores_daily` (`technical, risk, cost_liquidity, flow, quality` + sub-scores, `composite`,
  `conviction_tier`, `peer_group`, `asset_group`, `lenses_active`, `evidence`, `compute_run_id`),
  `country_daily` (`iso2, date, representative_id, n_etfs, composite, rs_{w}_spy, aum_usd_total`),
  `universe_snapshot` (`in_universe, in_sp500, adv_usd_median_60d, floor_usd, aum_usd, basket_eligible`),
  `atlas_signal_ic` (+ `entity` stock|etf).
- `atlas_thresholds` — identical 13 columns to India's (so `load_thresholds(schema="atlas_global")`
  and the admin panel work unchanged) + `atlas_thresholds_audit`.
- Ops: `atlas_pipeline_runs`, `atlas_validator_results`, `atlas_health_daily` (India shapes, so
  `write_health_snapshot.py` is a 1:1 copy), `ingest_state`, `provider_calls` (free-tier budget is
  a monitored metric).
- `app_user` (`email`, `role` fm|analyst|client, invite-only). M2: `basket_master` (`kind`
  etf|country|stock), `basket_constituents` (`target_weight_frac`, Σ=1 trigger), `basket_trades`,
  `basket_nav_daily` (`qty numeric(18,6)` for fractionals). M3: `chat_session`, `chat_message`, `chat_tool_call`.

DB role `atlas_global_app` (used by Vercel): SELECT on all `atlas_global`; DML only on `basket_*`,
`etf_classification_override`, `atlas_thresholds(+audit)`, `app_user`, `chat_*`. No grants on
`atlas_foundation`, and the India role gets none on `atlas_global`.

### Frontend + hosting + auth

- `frontend-global/`: Next.js 15 App Router, React 19, TS, Tailwind v4 CSS-first with its own token
  set, Radix primitives + shadcn-style components (build with `frontend-design:frontend-design`;
  charts per `dataviz`). postgres.js against the **transaction-mode pooler (:6543)**, `max: 5` per
  function instance, `prepare: false`; audit rows carry `changed_by`/`change_reason` as columns
  (India's `db.ts` needs session mode for `SET LOCAL` and already holds 14 of the 15 session slots).
- **Auth from day one** (India board has none): Supabase Auth via `@supabase/ssr` (magic link +
  Google), middleware redirect, `requireUser()` against the `app_user` allowlist; roles
  `fm | analyst | client`.
- **Hosting: Vercel Pro** ($20 per deploying seat per month in 2026; the Hobby tier prohibits
  commercial use), Git integration with root `frontend-global/`, `regions: ["bom1"]` next to
  Supabase `ap-south-1` (verify region availability day 1; fallback `sin1`), preview deploy per PR,
  ISR 300 s + on-demand `revalidateTag('eod')` called by the orchestrator only when all gates pass —
  the board advances without a rebuild. The prod box stays Python-only: its two racing deploy
  paths, the 2-vCPU nightly, and pm2 never touch the global app.
- **No Python spawn from route handlers.** Nightly Python is the book of record; SQL functions
  (`composite_preview(weights)`, `recompute_composite_latest()`, `basket_preview_nav(...)`) serve
  interactive previews and are **parity-tested against the Python on real rows** (the
  `fund_rank_core.py` ↔ `fundScore.ts` pattern). Long jobs go through a `job_queue` table drained
  by the box's cron.
- Routes (M1): `(auth)/login` · `/` today · `/etfs` (virtualised table; facets = every
  classification dimension, AUM/ADV$/expense sliders, `lenses_active` chip) · `/etfs/[symbol]`
  (facts with source + as-of, classification card with rationale/confidence/status, exposure
  donut, holdings look-through, score derivation tree, RS matrix, chart, **any-period return
  calculator** on `close_tr` vs `close_adj` vs SPY) · `/countries` + `/countries/[iso2]` ·
  `/sectors` + `/sectors/[id]` (sector → sub-sector → theme, pure-play vs picks-and-shovels split)
  · `/stocks` + `/stocks/[symbol]` · `/methodology` + `/methodology/signal` · `/health` ·
  `/admin/{thresholds,classify,data-status}`. M2 adds `/baskets`, `/baskets/[id]`, `/baskets/new`;
  M3 adds `/chat`.
- Ports (not imports): `ScoreDerivationTree.tsx`, `DecileMeter.tsx`, the `*ToDerivation` adapter
  pattern, `ThresholdsPanelV4` flow (Edit → Save → Preview → Commit), `DataStatusPanel`,
  `signal_quality.ts` grading, `health.ts` tracked-tables shape. CI gets a `frontend-global` job
  (tsc + vitest) and a Playwright smoke against the Vercel preview URL.

### Orchestration (copy `step()`/`gate()`/runfile/Telegram from `scripts/ops/atlas_daily.sh`)

```
atlas_global_daily.sh   EOD=$(python -c "import _gdb; print(_gdb.eod_cutoff())")   (abort loudly if no SPY bar for EOD)
 1 ingest_prices --eod            → ohlcv_daily (+SPY calendar)      surface: /health, price on every card
 2 ingest_macro                   → macro_daily                       pulse strip, SPY cross-check
 3 ingest_filings_8k, ingest_form4 (daily EDGAR index)                /stocks/[s] catalyst + flow evidence
 4 ingest_issuer_holdings (iShares/SSGA daily)                        etf_holdings, etf_shares_daily
 5 compute_technicals (incremental)                                   → technical_daily   charts, RS matrix
 6 build_exposures --changed      → etf_exposure_daily                 ETF detail, /countries
 7 score_stocks --as-of $EOD      → lens_scores_daily                  /stocks
 8 score_etfs   --as-of $EOD      → etf_scores_daily                   /etfs
 9 build_country_views            → country_daily                      /countries
10 build_universe_snapshot        → universe_snapshot                   /methodology/universe
11 eval_signal --start EOD-730d   → atlas_signal_ic                     /methodology/signal   (step, not gate)
GATES  validate_global --check A|B|C|D · freshness_guard --eod $EOD      fail → no revalidate, Telegram push
12 write_health_snapshot ; all green → POST Vercel revalidate (tag 'eod')

atlas_global_weekly.sh  build_identity → ingest_index_membership → ingest_nport (long tail + AUM) →
  ingest_financials (companyfacts, changed filers) → ingest_13f → ingest_short_interest →
  classify_etfs --delta (rules + LLM for new/changed only) → build_exposures --all →
  score_etfs --backfill-week → validate_global --check E (classification coverage)
```
`scripts/global_market/freshness_guard.py`: `KEY_TABLES` (ohlcv_daily 0, technical_daily 0,
lens_scores_daily 0, etf_scores_daily 0, country_daily 0, macro_daily 3), `BOARD_TABLES`
(etf_holdings 8, etf_exposure_daily 8, etf_meta 8, etf_classification 8, stock_financials_pit 95),
`PRODUCERS` map, `ORCHESTRATORS = [atlas_global_daily.sh, atlas_global_weekly.sh]`; lag counted in
SPY sessions. Its registry test lands in Phase 0 (empty-but-valid).

## Data sources (verified 2026-09-04) and fallbacks

| Need | Primary (free, official) | Cadence | Fallback | Gate |
|---|---|---|---|---|
| OHLCV 2016→ | **Tiingo** (decided 2026-09-04 — Alpaca ruled out by the FM as too cumbersome to start; full decision, licence tiers and the FEED gate in `docs/global/phase1.md` §1): per-ticker daily bars with raw + adjusted OHLCV and `divCash`/`splitFactor` on every row, 60+ yrs, 99.9% of today's 5,655 listed ETFs, delisted kept | nightly per-ticker (~6,200 calls); backfill 2016→ in one call per ticker | **Stooq importer** (FM-downloaded `d_us_txt.zip`) as cross-check and emergency spine; yfinance only as a third cross-check | **FEED gate** (`validate_global --check FEED`), then gate A |
| Corporate actions | Tiingo per-row `splitFactor` / `divCash` (amended 2026-09-04; Alpaca out) | daily | derive from `all` vs `split` bar ratios, flagged `source='derived_from_adjustment'` (needs FM approval — rule #0) | every `|ret_1d| > 0.5` on `close_adj` has a matching action |
| Index / macro | FRED (`SP500`, `VIXCLS`, `DGS10`, `DTB3`, `DTWEXBGS`) — key already in India `.env` | daily | — | through EOD-1 |
| ETF universe | Nasdaq Trader `nasdaqlisted.txt` + `otherlisted.txt` (ETF = Y, exchange, test-issue flag) | weekly | Alpaca `/v2/assets` | 3,300–4,000 rows, every one with an exchange |
| S&P 500 | **SSGA SPY daily holdings CSV** (constituents, weights, GICS sector column — verify columns on first fetch) via `etf-scraper`; history `fja05680/sp500` | daily / one-time | Wikipedia list | 500–505 names, weights ≈ 100% |
| Identity | Nasdaq directory; SEC `company_tickers.json` (stocks → CIK) and `company_tickers_mf.json` (funds → CIK/series/class; verify field names); SEC `submissions` API (SIC code); Alpaca assets (tradable, fractionable) | weekly | `symbol_alias` manual rows | CIK on 100% of stocks; series_id on ≥95% of ETFs; alias round-trip for 20 punctuation tickers |
| ETF holdings + exposures | **EDGAR N-PORT via `edgartools`** for the whole universe — per holding `name, cusip, ticker, balance, value_usd, pct_value, asset_category, investment_country`; per fund `net_assets, total_assets, series_id` (`Fund(ticker).get_portfolio()`); public only for the quarter-end month, ~60-day lag | weekly | — | holdings on ≥90% of ETFs by count, ≥98% by AUM |
| Fresh holdings (big four) | Issuer CSVs via `etf-scraper` (iShares daily incl. history since 2010; SSGA, Vanguard, Invesco current); `query_listings()` for issuer product lists (AUM, expense) | daily | N-PORT | Σ|weight_frac| ∈ [0.9, 1.1] for ≥97% of non-leveraged ETFs |
| Stock fundamentals | **EDGAR XBRL company facts via `edgartools`** (`filed` per fact = PIT) | weekly (changed filers) | — | ≥95% of S&P 500 with ≥8 quarters; continuity checks |
| Catalysts / flow | EDGAR 8-K (item codes), Form 4, 13F via `edgartools`; **FINRA Equity Short Interest** (free files + `api.finra.org`, twice monthly, archives to 2014) | daily / per publication | — | filing-rich names score catalyst > 0 |
| Taxonomy seed | `FinanceDatabase` (MIT) sector/industry approximations + ETF category/family — seed and cross-check only | one-time | — | — |

Rejected as spine: Polygon free (2-year cap), Tiingo free (500 symbols/month), yfinance
(unofficial, rate-limited), Stooq API (daily-hit limits; bulk download CAPTCHA-gated → manual).

## Open-source building blocks — what we build on, what we already have, what we reject

The honest framing: the famous "trading repos" are backtesters, RL/ML alpha labs, crypto bots
or LLM trading-agent demos. None of them solves our three actual problems — a gated real-data
foundation, a classification engine, and a glass-box scoring methodology. The reuse that pays
is in **data access**, **metric math**, and **portfolio construction**, and half of it is
already installed in `pyproject.toml`.

| Repo / package | Licence | What we take | Where in the build |
|---|---|---|---|
| **Already installed** — `TA-Lib` (`scripts/foundation/technicals.py`), `pandas-ta` (`atlas/compute/primitives.py`, `breadth.py`) | BSD/MIT | EMA/RSI/ATR/Bollinger, breadth math — the existing technicals pipeline runs unchanged on US bars | Phase 1 `compute_technicals` |
| **Already installed** — `empyrical-reloaded` (core dep) | Apache-2.0 | Sharpe, Sortino, Calmar, max drawdown, alpha/beta, annualised vol — the ETF `risk` lens inputs and every basket metric | Phases 3–4 |
| **Already installed** — `alphalens-reloaded` + `statsmodels` (`[intelligence]`) | Apache-2.0 / BSD | Factor tear-sheets: quantile returns, IC decay, turnover — complements `atlas/compute/signal_eval.py` on `/methodology/signal` | Phase 3 |
| **Already installed** — `PyPortfolioOpt` 1.6.0 (Feb 2026) + `vectorbt` (`[simulation]`) | MIT / Apache-2.0 | HRP / min-variance / risk-parity weights for basket templates; vectorised what-if backtests if the SQL preview is too slow | M2 baskets |
| **Already installed** — `anthropic`, `pydantic` | MIT | Structured-output classification (`messages.parse`), chat tool-use | Phases 2, 5 |
| **Already installed** — `yfinance` | Apache-2.0 | Cross-check only (never the spine) | Phase 1 gates |
| **Add** — `alpaca-py` (official SDK; `StockBarsRequest(adjustment, feed, …)`, corporate-actions and assets clients; later the Broker API) | permissive — verify | Price spine, tradable/fractionable flags, corporate actions; execution later | Phases 1, 6 |
| **Add** — `edgartools` (dgunning) | MIT | XBRL company facts (PIT by `filed`), 8-K items, Form 4, 13F, N-PORT holdings/net assets — one library for every SEC feed | Phases 2–3 |
| **Add** — `etf-scraper` (nikulpatel3141) | MIT | Issuer holdings (iShares daily + history, SSGA, Vanguard, Invesco) and issuer product listings (AUM/expense); SPY holdings = S&P 500 membership + GICS sector | Phases 1–2 |
| **Add** — `financedatabase` (JerBouma) | MIT | 300k-symbol seed taxonomy (loose GICS approximations, ETF category/family) — seed and cross-check for L2/L3, never authoritative | Phase 2 |
| **Add, decide at Phase 3 start** — `financetoolkit` (JerBouma) | MIT | 200+ ratio formulas that accept **custom statement DataFrames** (our XBRL `stock_financials_pit`), transparent formulas for the stock metrics catalogue; if its custom-normalisation path fights our tags, compute the ~14 ratios we score on directly (the India `fundamental_pit.py` pattern) | Phase 3 |
| **Add (small)** — `exchange_calendars` (or `pandas_market_calendars`) | Apache-2.0 / MIT | Expected NYSE sessions for the "missing session" gate only; the live calendar stays membership-by-presence of SPY bars | Phase 1 gate |
| **Optional, M2** — `quantstats` (active, v0.0.81 Jan 2026), `skfolio` 1.0 (2026) | Apache-2.0 / BSD-3 | HTML tear-sheets; sklearn-style optimisers with time-series CV — only if PyPortfolioOpt/empyrical prove insufficient | M2 |
| **Data files (not packages)** — `fja05680/sp500` (membership history), Nasdaq Trader symbol directory, SEC `company_tickers*.json`, FINRA short-interest files, FRED | public | Identity, universe, membership history, short interest, macro | Phase 1 |

**Considered and rejected, with the reason:**
- **OpenBB Platform** — the one repo that *is* a provider abstraction (30+ providers, SEC N-PORT
  included), but **AGPLv3**: offering a modified build as a network service obliges source
  release, an unacceptable ambiguity for a licensed commercial product; also 30 providers where
  we need four. We keep our own thin `providers/` layer (≈ 5 adapters) and borrow nothing but ideas.
- **TradingAgents, ai-hedge-fund** — LLM multi-agent *trading decision* demos (analyst/risk/PM
  agents that debate and vote). Atlas already has a stricter version (`atlas/desk/`: model
  proposes, audited engine executes, validators per role). Nothing in them builds a data
  foundation or a taxonomy; they run on yfinance/FMP with no data gates — the opposite of rule #0.
- **backtrader, zipline-reloaded, bt, Lean** — backtest/execution engines. Atlas has
  `atlas/portfolio/engine.py` with fill-timing parity tests; a second engine would break the
  "one accounting truth" discipline. `vectorbt` is already available for vectorised what-ifs.
- **Qlib, FinRL** — ML/RL alpha-research platforms; black-box factor mining is the opposite of
  a glass-box, FM-locked methodology.
- **freqtrade, hummingbot** — crypto bots.
- **mstarpy, finvizfinance, tvdatafeed, yahooquery** — unofficial scrapers; at most a
  cross-check, never a source of a number we display.
- **Polygon / Tiingo / FMP free tiers, Stooq API** — see the data-source table.

**Provider abstraction** (`providers/base.py`, Protocols; adapters do the I/O):
`PriceProvider.bars(symbols, start, end, adjustment) → DataFrame[symbol,date,o,h,l,c,v,trade_count,vwap]`,
`AssetProvider.assets()`, `HoldingsProvider.holdings(instrument, as_of) → DataFrame[holding_key, weight_frac, market_value_usd, country_iso2, asset_category]`.
Selected by `GLOBAL_PRICE_PROVIDER=alpaca|stooq_bulk`; `ingest_prices.py` writes `source` per row
and never mixes sources within one instrument-day without `--override`. Alpaca adapter: `end`
clamped to `eod_cutoff() − 1 min`, `limit=10000`, `page_token` loop, the `_rate_limit` from
`scripts/foundation/ingest_kite.py`.

**Stooq importer** (`import_stooq.py --zip d_us_txt.zip`): walks `data/daily/us/{nasdaq,nyse,nysemkt} {etfs,stocks}/…/<ticker>.us.txt`
(`<TICKER>,<PER>,<DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<VOL>,<OPENINT>`); `AAPL.US → AAPL`,
`BRK-B.US → BRK.B` via `symbology.normalise()` + `symbol_alias(source='stooq')`; unmapped tickers
are logged, never dropped silently; **adjustment auto-detect** per file against overlapping Alpaca
`close_adj` / `close_tr` (min |diff| wins, written to `adjustment_source`); a file whose best match
exceeds 0.5% median error is refused and logged — no guessing. Stooq doubles as the
cross-source-agreement check for Alpaca.

## Universe

- **Stocks**: current S&P 500 (SPY holdings) ∪ trailing members since history start
  (`index_membership` effective ranges) for honest backtests; scored = current members.
- **ETFs**: all listed are classified; **in scope for scoring/baskets** iff
  `adv_usd_60d_median ≥ liquidity_min_traded_value_usd` (NULL never passes;
  `liquidity_min_observations_60d`, `liquidity_recency_trading_days` ported) OR held in any live
  basket. `basket_eligible = ¬leveraged ∧ ¬inverse ∧ fractionable ∧ adv ≥ floor ∧ aum ≥ floor`.
  Phase 1 prints the ADV$ percentile table so the FM sets the floor from data.
- Delisted ETFs keep their bars, `is_active=false` (survivorship honesty).

**FM decisions of 2026-09-06**, taken from the real distribution in
`docs/global/reports/adv_usd_2026-09-03.md` and implemented in `build_universe_snapshot.py`:

1. **Stocks: S&P 500 only.** `in_universe` for a stock requires `in_sp500` on that date AND the
   ADV$ floor — the snapshot had been wider than this section. 3,389 liquid non-members dropped
   out; all 503 members on 2026-09-03 clear the floor, so stocks in the universe = 503. Trailing
   members stay `in_universe` on the dates they were members (`in_sp500` is per date), so the
   backtest history is unaffected.
2. **The floor is $1,000,000**, seeded from that decision (`seed_thresholds.py`, 61 rows). 2,114
   of 5,656 ETFs clear it. ONE floor serves both asset classes. `build_universe_snapshot` still
   exits 2 when the row is missing or inactive — the guard for a half-provisioned schema.
3. **Leveraged and inverse ETFs are out of the universe** — 749 leveraged, 166 inverse, 125
   both, 790 distinct (363 of them clear the floor), leaving 1,751 ETFs. They keep their
   snapshot row with `in_universe = false` and the rule that excluded them in `--report`.
   Universe on 2026-09-03: **2,254** of 13,155 active instruments (1,751 ETFs + 503 stocks).

## Classification engine (the moat)

Dimensions per ETF: `asset_class` (equity / fixed_income / commodity / currency / multi_asset /
alternative) · `geo` (focus type, country ISO2 list, region, `country_pure`) · `sector →
sub_sector → theme[]` · `role` (pure_play / picks_and_shovels / diversified) · `strategy`
(broad / factor / sector / thematic / country / commodity / bond duration / leveraged) · structure
flags (leveraged, inverse, currency-hedged, active). Stocks: `sector_gics` from the SPY holdings
CSV (official, daily), `sub_sector` from a deterministic SIC map + the same LLM pass over the
10-K business description; our own layer starts at theme/role.

Layers — deterministic first, model last, human final:
- **L0 facts** — `etf_holdings` (N-PORT for all; issuer CSV for freshness), `etf_meta`, name,
  issuer, index tracked, description.
- **L1 exposures** (`exposures.py`, pure) — Σ `weight_frac` by country and by sector (holding's
  own `sector_gics` when it is a scored stock, else N-PORT asset category / issuer sector column),
  `equity_w`, HHI, top-10, `lookthrough_scored_w`. Unit-tested on real snapshots.
- **L2 rules** (`rules.py`, pure; ordered first-match like `etf_sector.py`, but on structured
  inputs) — leveraged/inverse from name regex (`2X|3X|ULTRA|BEAR|INVERSE|-1X|DAILY…BULL`) ∧ issuer ∧
  `derivatives_share`. **This file exists** as `atlas/global_market/classify/rules.py`, started
  early on 2026-09-06 for the universe filter above: `leverage_flags(name)` is the name half only,
  over all 5,656 ETF names, with the issuer read off the front of the name. Phase 2 SUPERSEDES it
  with holdings + `derivatives_share` + `etf_meta`; the known name-only misses (return-stacked
  and "100% A & 100% B" funds, whose 200 % notional is nowhere in the name) are listed in the
  file's docstring and in phase1.md P1-E. Hedged from name; active from N-PORT/issuer;
  `single_country` iff
  `top_country_w ≥ cls_country_pure_min_weight` ∧ `equity_w ≥ cls_country_equity_min`; region/global
  by ISO→region roll-up; `sector_id` when one sector ≥ `cls_sector_pure_min`. All thresholds in
  `atlas_thresholds`. Unambiguous rows get `status='auto'`.
- **L3 LLM** (`llm.py`) — Claude API via the `anthropic` SDK already declared in `[intelligence]`;
  model chosen with the `claude-api` skill at build time (start `claude-opus-5`; drop to
  `claude-sonnet-5` if the eval set shows parity); `client.messages.parse(..., output_format=ETFClassification)`
  where the Pydantic enums are **built at runtime from the taxonomy tables** (allowlist enforced
  by the schema, not prose); stable system prompt (taxonomy + definitions) with `cache_control`;
  per-ETF message = name, issuer, index, L1 vectors, top-25 holdings, L2 outputs. Bulk pass via the
  Message Batches API (50% cost; roughly tens of dollars — verify with current pricing); nightly
  deltas as single calls. Output: `sector_id, sub_sector_id, theme_ids(≤3), geo_focus_type,
  country_codes, role_id, structure flags, confidence, rationale (≤60 words), evidence_tickers`.
- **Validation** (`validate.py`, deterministic — the factuality-guard pattern): ids ∈ taxonomy;
  `evidence_tickers ⊆` supplied holdings; a `single_country` claim must agree with L1; structure
  flags must equal L2 (rules win); `confidence < cls_llm_min_confidence` → `review`; any failure →
  rule-only fields kept, LLM fields NULL, `status='review'`, row in `classification_validation_log`.
- **Human loop** — `/admin/classify` queue (review rows by AUM, rule-vs-LLM disagreements, top AUM
  sample); confirm/override → `etf_classification_override`, sticky across re-runs, versioned.
  `status='confirmed'|'auto'` is what the board and baskets read.
- **Eval set before auto-confirm** — 150 ETFs hand-labelled by the FM (stratified by issuer/type)
  in `tests/fixtures/global/etf_labels_<date>.csv`; gates sector ≥ 0.92, geo ≥ 0.95, structure
  = 1.00. This closes STATE.md's "no eval set for any model output" for this surface.
- Re-classify only on holdings drift, taxonomy version bump, or FM request.

## Methodology spec — metrics, lenses, weights

Every number below is either (a) a metric computed from a real feed by a stated formula, or
(b) a **starting threshold** that is seeded into `atlas_global.atlas_thresholds` by an
FM-approved `seed_thresholds.py`, is editable from `/admin/thresholds`, and is never a literal in
code (rule #4). Starting values are seeds, not conclusions: a lens gets composite weight only
after the IC report shows it carries signal. Windows are trading sessions (1w=5, 1m=21, 3m=63,
6m=126, 12m=252, 24m=504, 36m=756). Technicals (EMAs, ATR, Bollinger) run on `close_adj`
(split-only, as India does); every return, RS and risk metric runs on `close_tr` (total return).

### A. Metrics computed per instrument, nightly

| Group | Metrics (table) | Source |
|---|---|---|
| Returns (stocks + ETFs) | `ret_{1d,1w,1m,3m,6m,12m,24m,36m}`, YTD; any-period return on demand in the UI (`technical_daily`) | `ohlcv_daily.close_tr` |
| Trend structure | EMA 10/13/21/34/50/200 + `above_ema_*` flags, EMA stack alignment, EMA-21 slope proxy (`ret_1w`), RSI 2/14, ATR-14 (% of price), Bollinger width, `pos_52w` (0–100), `vol_ratio_30d/60d` (today ÷ SMA), IBS | `close_adj`, volume (TA-Lib via `technicals.py`) |
| Relative strength | `rs_{1w,1m,3m,6m,12m,24m}_spy` and `rs_{w}_peer` in the relative form `(1+r_i)/(1+r_b) − 1` (ADR-0002); peer = GICS-sector ETF for stocks, taxonomy peer-group median for ETFs | `close_tr` |
| Risk | realised vol 20/63/252d (annualised), downside deviation 63d, max drawdown 12m and 36m, beta and correlation to SPY 252d, Sharpe/Sortino 12m (rf = FRED `DTB3`), Calmar 36m | `close_tr`, `empyrical-reloaded` |
| Liquidity | ADV$ 20d mean, **ADV$ 60d median** (the universe floor), zero-volume days 60d, turnover = ADV$ ÷ AUM (ETFs), days-to-cover = short interest ÷ ADV (stocks). Spread proxy (Corwin–Schultz) only if the FM approves a derived estimator | volume × close; FINRA |
| ETF structure & cost (`etf_meta`) | AUM (+ source, as-of), expense ratio, age since inception, shares outstanding + Δ21d/Δ63d (creations proxy), distribution yield (trailing 12m cash dividends ÷ price, from corporate actions), holdings count, top-10 weight, HHI, equity share, derivatives share, leverage factor, inverse / hedged / active flags, 12m tracking difference vs its category benchmark ETF (stated as vs-ETF, not vs-index) | issuer CSV, N-PORT, corporate actions |
| ETF exposures & classification | country vector, sector vector, asset-class vector, `top_country_w`, `lookthrough_scored_w`; sector → sub-sector → themes, role, geo focus, `country_pure`, strategy, `basket_eligible` | Phase 2 engine |
| Stock fundamentals (PIT by `filed`) | Quarterly: revenue, gross profit, operating income (EBIT), D&A → EBITDA, net income, diluted EPS, diluted shares, equity, total debt, cash, current assets/liabilities, operating cash flow, capex → FCF. TTM: revenue, EBIT, net income, EPS, FCF. Growth YoY: revenue, EPS. Ratios: ROE (NI TTM ÷ avg equity), ROCE (EBIT TTM ÷ (equity + debt)), gross/operating/net margin, D/E, current ratio, interest cover, operating leverage (ΔEBIT% ÷ Δrevenue%), FCF margin, buyback yield (−Δshares), dividend yield | EDGAR XBRL via `edgartools`; ratio formulas via `financetoolkit` custom statements or `fundamentals_us.py` |
| Stock valuation | PE (close ÷ TTM diluted EPS), PB, EV/EBITDA (EV = market cap + debt − cash), EV/Sales, FCF yield, earnings yield, **sector-relative PE** (÷ cross-sectional GICS-sector median), 52-week position | XBRL + `close_tr` |
| Stock events | 8-K item codes with dates (365d window), Form 4 open-market net buys/sells 90d ($, count of insiders), cluster-buy flag (≥3 insiders in 30d — threshold), 13F holder count + Δ QoQ (45-day lag respected), short interest % of float + Δ, days-to-cover | `edgartools`, FINRA |
| Basket-level (M2) | NAV series, period returns, CAGR, vol, Sharpe/Sortino, max drawdown, beta/alpha vs SPY, tracking vs chosen benchmark ETF, weighted expense ratio, weighted ADV$, look-through country/sector exposure, concentration, `fractional_ready`, drift since last rebalance | `basket_nav_daily`, `empyrical-reloaded` |

### B. Stock lenses (S&P 500) — six computed, four in the composite

| Lens | Sub-scores (points) | Formula / rules | Threshold keys (seed values) |
|---|---|---|---|
| **Technical** (`score_technical` verbatim) | Trend 0–25: EMA alignment (21>50>200 → 10; partial → 6), price vs EMA200 (> +5% → 5, > 0 → 3, > −5% → 1), EMA-21 slope via `ret_1w` (> +2% → 5, > 0 → 3, flat-down → 1), ×1.25. RS-structure 0–25: EMA50 > EMA200 → 10, EMA21 > EMA50 → 15 | lens = mean(present subs) × 4 | `ema_aligned_all` 10, `ema_aligned_partial` 6, `price_above_ema200_strong` 0.05, `price_below_ema200_weak` −0.05, `slope_strong_pct` 0.02, `slope_weak_pct` −0.02, `rs_golden_cross_pts` 10, `rs_fast_above_mid_pts` 15 |
| **Fundamental** (`score_fundamental` verbatim over XBRL inputs) | five subs each 0–20: profitability (ROE step 11/9/7/4/2 + ROCE 7/5/3/2/1 + net-margin steps, + continuous ROE premium), margin (operating/net-margin bands), growth (revenue & EPS YoY bands), balance sheet (D/E, current, quick ratio bands — skipped for `is_financial_co`), operating leverage | lens = Σ ÷ (20 × n_present) × 100 | `prof_roe_{high,good,ok,low}` 20/15/12/8, `prof_roce_*`, `prof_nm_*`, `margin_op_*`, `margin_net_*`, `growth_rev_*`, `growth_eps_*`, `bs_de_*`, `bs_cr_*`, `bs_qr_*`, `olev_*` — **seeded from the actual S&P 500 cross-sectional quartiles on the first run**, not India's numbers |
| **Valuation** (`score_valuation` verbatim; overlay → zone + multiplier, not in composite) | PE vs sector 0–25 (continuous: 25 at r→0, 0 at r ≥ 1.5 × sector median), absolute PE 0–25, P/B 0–15, EV/EBITDA 0–20, 52-week position 0–15; renormalised over present dims | zones DEEP_VALUE ≥75 / CHEAP ≥55 / FAIR ≥35 / EXPENSIVE ≥20 / OVERVALUED | **India's absolute bands (PE < 8 → 25 pts) are wrong for the S&P 500** (median PE well above 20): seed the absolute PE / PB / EV-EBITDA bands as **index percentiles** (P20/P40/P60/P80 of the live cross-section) stored as thresholds — FM to lock |
| **Catalyst** (**new** `stock_catalyst.py`; same 3-bucket shape and decay as India) | earnings/strategy (w 0.55): 2.02 results filed, 1.01 material agreement +10, 2.01 acquisition completed +8, 8.01 with contract-win / guidance-raise keywords +10. capital action (w 0.30): dividend increase or initiation +8, buyback authorisation +10, secondary offering / dilution −8, 3.02 unregistered sales −3. governance (w 0.15): 4.01 auditor change −12, 5.02 CEO/CFO departure −8, 4.02 non-reliance/restatement −15, 3.01 delisting notice −15, 1.03 bankruptcy −25, NT 10-K/10-Q −10. Insider cluster buy +12 / cluster sell −6 | bucket = 50 + Σ(points × decay), clamped 0–100; decay 1.0 / 0.8 / 0.5 / 0.3 at 90 / 180 / 365 d; lens = Σ w_bucket × bucket | `catalyst_w_earnings` 0.55, `catalyst_w_capital` 0.30, `catalyst_w_governance` 0.15, `catalyst_recency_t1/t2/t3` 90/180/365, `catalyst_pts_<event>` per row above |
| **Flow** (**new** `stock_flow.py`; centred at 50) | insider: Form 4 net open-market buying 90d as % of market cap → ±(5/10/15) at ±0.01/0.05/0.20%; institutions: 13F holder-count Δ QoQ → ±(5/10) at ±2%/±5% (lagged 45 d); short interest Δ (bi-monthly) → rising −(5/10), falling +(5/10), > 20% of float flags risk | lens = 50 + Σ sub-points, clamped; **ship with Form 4 only**, add 13F and short interest after IC ≥ floor | `flow_insider_*`, `flow_13f_*`, `flow_si_*`, `flow_si_extreme_pct` 20 |
| **Risk flags** (overlay, stored not applied — India's stance) | NT 10-K/10-Q, 4.02, 1.03, 3.01, auditor change, dividend cut, insider net selling > `insider_net_sell_usd`, short interest > extreme, price < EMA200 − `price_below_200dma_pct` | `degradation_score` floored at `degradation_floor` −30 | `penalty_*`, `degradation_floor` |
| Policy | not ported — zero weight in India; no honest US registry | — | — |

**Stock composite** = Σ wᵢ · lensᵢ ÷ Σ wᵢ over the *present* lenses in {technical, fundamental,
catalyst, flow} (`blend()`, parity-tested against `compute_composite`). Seed weights:
`lens_weight_technical` 0.30, `lens_weight_fundamental` 0.30, `lens_weight_catalyst` 0.25,
`lens_weight_flow` 0.15 (India's are 0.222/0.222/0.278/0.278; US flow is thinner at launch, so it
starts lighter — IC decides). Conviction tiers (same keys as India): HIGHEST ≥ 70 & ≥ 3 lenses,
HIGH ≥ 58 & ≥ 2, MEDIUM ≥ 45, WATCH ≥ 30, else BELOW_THRESHOLD. Deciles within `cap_cohort`
(SPY-weight terciles: mega / large / mid); **Leader = top decile within cohort** (the
`v_stock_leader` rule).

### C. ETF lenses — five computed, materialised nightly, backfilled to 2016 for price lenses

(India rolls ETFs up from stocks on read; here ETFs are the product and most hold nothing in the
scored S&P 500, so they need lenses of their own.)

| Lens | Sub-scores (each 0–25; lens = mean(present subs) × 4) | Rules (seed values) |
|---|---|---|
| **Technical** (weight seed 0.35) | Trend (`_score_trend` verbatim on `close_adj`) · RS vs SPY (3m/6m/12m relative form: > +`rs_spy_strong` → 8/8/9, > 0 → half, else 0) · RS vs peers (percentile of 6m return within peer group: top quintile 25, then 20/15/10/5) · Structure (EMA50 > EMA200 → 10, EMA21 > EMA50 → 15) | `rs_spy_strong` 0.05; peer group min size `peer_group_min_members` 8, else parent group |
| **Risk** (weight seed 0 — overlay until the FM sets one) | 63d annualised vol percentile within asset group (lowest quintile 25 → highest 5) · 12m max drawdown percentile · downside-deviation percentile · beta band (equity only: ≤ 0.8 → 25, ≤ 1.0 → 18, ≤ 1.3 → 10, else 3) | `risk_beta_*`; non-equity ETFs get 3 subs |
| **Cost & liquidity** (weight seed 0.20) | expense-ratio percentile within asset group (cheapest quintile 25 …) · ADV$ bands (≥ $50M 25, ≥ $10M 20, ≥ $2M 15, ≥ $500k 10, else 3) · AUM bands (≥ $10B 25, ≥ $1B 20, ≥ $250M 15, ≥ $50M 10, else 3) · concentration (top-10 ≤ 30% 25, ≤ 50% 18, ≤ 70% 10, else 5; absent for single-asset commodity/currency ETFs) | `cost_adv_*`, `cost_aum_*`, `cost_top10_*` — bands re-seeded from the live distribution |
| **Flow** (weight seed 0.15; absent where no shares-outstanding series) | Δ shares outstanding 21d and 63d → centred 50 ± (8/15/25) at ±2%/±5%/±10%, combined and clamped | `flow_so_*` |
| **Quality / look-through** (weight seed 0.30; present only where `lookthrough_scored_w ≥ 0.60`) | 0.7 × holdings-weighted constituent stock composite + 0.3 × (weight in Leader stocks × 100) | `etf_lookthrough_min_coverage` 0.60, `quality_w_composite` 0.7, `quality_w_leaders` 0.3 |

**ETF composite** over present lenses (renormalised; `lenses_active` on every card — "3 of 5
lenses"); conviction tiers with ETF-specific keys (`etf_conviction_*`); **deciles within peer
group** = asset class × strategy (equity-sector, equity-country, equity-broad, equity-factor,
equity-thematic, fixed-income-by-duration, commodity, …), min 8 members else the parent group;
Leader = top decile within peer group. Leveraged/inverse ETFs are scored but `basket_eligible=false`.

### D. Roll-ups (pure, the `composite.py` roll-up shape)

- **Sector / sub-sector / theme** pages: AUM-weighted mean of member ETF composites,
  breadth (% members with composite ≥ `rollup_breadth_min` 60), dispersion, median 3m return,
  % members above EMA200; pure-play vs picks-and-shovels shown side by side.
- **Country** (`country_daily`): composite and RS = the representative ETF's (largest AUM among
  ¬hedged ∧ ¬leveraged ∧ ¬active); breadth over all member ETFs; AUM total; hedged variants listed
  separately. The country-basket product reads only `country_pure ∧ basket_eligible` rows.
- **Baskets** (M2): NAV on `close_tr` with weights fixed per version, drifting until the next
  version; metrics from group A "Basket-level".

### E. Validation before trust (Phase 3 gate, then nightly)

- Rank-IC (Spearman) of each lens and the composite vs forward 1/3/6/12m returns, within cohort
  (stocks: cap tercile; ETFs: asset group), trailing 2y and full history — `signal_eval.py`
  verbatim; decile spread (D10 − D1) and hit rate; `alphalens-reloaded` tear-sheets for IC decay
  and turnover. All on `/methodology/signal` (raw stats allowed there only).
- **Weight rule**: a lens keeps its seed weight only if its IC clears `ic_floor_{tenure}` (seed
  0.02 at 1m / 0.04 at 3m / 0.05 at 6m / 0.04 at 12m — India's per-tenure floors) on the full
  backfill; otherwise its weight is set to 0 (overlay) until it does. The FM locks the final
  weights from `/admin/thresholds`; the board states "weights validated on N years" on `/methodology`.
- **Full-history backfill makes this possible at launch**: prices to 2016 (Alpaca), XBRL facts
  and 8-K/Form 4 history are all available back to 2016 from EDGAR, so stock and ETF score
  journals are backfilled and IC exists before anyone sees a score.
- Nightly `validate_global --check C` copies India's wrong-number guards: composite ∈ [0,100],
  `stddev(composite) ≥ 10`, each lens `stddev ≥ 2`, decile monotone in composite within
  cohort/peer group, `|ret_1d| ≤ 1`, RS recomputation spot-check.

**Countries** (`country_daily`): country set = `geo_focus_type='single_country' ∧ country_pure`;
representative = max AUM among ¬hedged ∧ ¬leveraged ∧ ¬active (tie → lower expense); country
composite/RS = representative's; `/countries` heatmap = representative RS vs SPY over 1/3/6/12m,
US as a row with an ex-US default toggle; `/countries/[iso2]` lists every member ETF with
composite, AUM, ADV$, expense, hedged/leveraged flags. This is the surface of the **country-basket
product**: basket kind `country` accepts only `country_pure ∧ basket_eligible` ETFs — enforced by a
DB trigger, not only the UI.

## Later milestones (designed now, built after M1)

- **M2 Baskets** — `basket_master` kinds `etf | country | stock`; fraction weights (Σ=1 trigger);
  `fractional_ready` = all constituents `fractionable`; NAV = buy-and-hold on `close_tr` with
  weights fixed per version and drifting until the next version (no daily-rebalance fiction);
  `basket_preview_nav(...)` SQL for the builder, nightly `mark_baskets.py` (reuse
  `atlas.portfolio.engine.replay` with a fractional quantum) as the record, parity test between
  them; metrics per the `portfolio-management` skill (CAGR, Sharpe with FRED `DTB3`, max drawdown,
  beta/alpha vs SPY, XIRR once cash flows exist), always "as of"; IA-licence disclosure block.
- **M3 Conversational** — Next.js route handler → Claude API (Messages + tool use; models/params
  per the `claude-api` skill). Tools are read-only SQL-backed functions (`search_etfs`, `get_etf`,
  `compare`, `draft_basket` → validates eligibility/Σweights/concentration caps from thresholds and
  runs `basket_preview_nav`, `save_basket` → explicit UI confirm). Numbers rendered only from tool
  results; per-claim factuality check; template fallback; `chat_*` tables; **eval set of ≥50
  golden prompts with expected tool calls gates client exposure**.
- **M4 Execution (design only)** — Alpaca Broker API (fractional orders) behind an
  `ExecutionProvider` Protocol; order-intent table + human approval + audit; no code before the
  IA licence and a written order-handling policy. Choosing Alpaca for data now keeps this path open.

## Process and quality rules (FM direction, 2026-09-04)

- **Goal-driven chunks, gstack-driven loop.** Every chunk of work carries a `GOAL:` block (one
  sentence + the definition-of-done checks) and loops implement → run the checks → fix until every
  check passes; nothing is "done" on a partial. Mechanics: `<!-- gstack:verify: make gate -->` in
  `CLAUDE.md` + `gstack-verify-gate --trust` (a Stop hook that refuses to end a turn while the verify
  command is red); `spec` for anything vague; `plan-eng-review` before a new module; `review` (gstack
  pre-landing review) **and** `ponytail-review` on every diff before it lands; `qa` on every frontend
  URL; `cso` before a release; `ship` → `land-and-deploy` for PRs; `verification-before-completion`
  before any "done" claim. Chunks are dispatched to parallel subagents on disjoint file sets
  (`dispatching-parallel-agents`, `subagent-driven-development`) and integrated by one integrator.
- **No hand-written formulae where a maintained library exists.** Technicals: TA-Lib / pandas-ta
  (`technicals.py`). Risk & performance: `empyrical-reloaded` (`max_drawdown`, `annual_volatility`,
  `sharpe_ratio`, `sortino_ratio`, `calmar_ratio`, `downside_risk`, `alpha_beta`). Ratios:
  `financetoolkit` on our XBRL statements (decided Phase 3). Optimisation: `PyPortfolioOpt`.
  Statistics: `scipy`/`statsmodels`. The relative-form RS and the composite blend are the only
  bespoke arithmetic, and each has a **parity test against an independent implementation**
  (`blend()` ↔ `compute_composite`; SQL preview ↔ Python record; RS recomputed from raw closes in the
  nightly gate).
- **Every calculation is double-checked** by construction: cross-source agreement for prices
  (Alpaca ↔ Stooq ↔ FRED), recompute-and-diff for technicals, parity tests for scores, and the
  per-incident wrong-number guards in `validate_global`. A number with one implementation and no
  cross-check does not ship on a user page.
- **Thresholds and weights are a frontend input layer that can rerun Atlas.** `/admin/thresholds`
  edits every row of `atlas_global.atlas_thresholds` (lens weights, bands, tiers, classification
  thresholds, liquidity floor) with server-side clamping and an audit row; **Preview** re-blends
  the latest date from cached sub-scores (`composite_preview` SQL, parity-tested); **Rerun** enqueues
  a job (`job_queue`: `kind` = `rescore_latest | rescore_backfill | reclassify | rebuild_country`,
  `params`, `requested_by`, `status`, `started_at`, `finished_at`, `log`) that the box's
  `scripts/global_market/job_worker.py` (cron every 5 min, single-flight via flock) executes with
  the same scripts the nightly runs, then the page shows the job's progress and the resulting
  score deltas. The frontend never computes a score and never spawns Python; it writes a job row.

## Phased build with definition-of-done gates (assert on REAL produced data)

**Phase 0 — Foundation (~1 week)**
1. FM actions: Alpaca paper account + keys; EDGAR identity email; Anthropic key; Vercel Pro
   project (`bom1`); Supabase Auth enabled; `atlas_global` schema + role created; keys go to
   `.env` on box/laptop and Vercel env only.
2. **SIP gate first** (`validate_global.py --check SIP`) — result recorded in
   `docs/global/data-sources.md`; on FAIL the Stooq decision is logged and the paid slot opened.
3. ADR-0006 + CLAUDE.md rule #1 wording; `schema_gate.py` two-tree rewrite; boundary-hook
   context + subtree edges; `get_engine(session_tz)`; `_VALID_SCHEMAS` + caller test fix;
   `MarketConfig`; `_gdb.py` with `eod_cutoff()`; DDL files + `0002_atlas_global.py`;
   provider Protocols; `blend()` + parity test; producer-registry test (empty-but-valid);
   `atlas_global_daily.sh` skeleton; `frontend-global/` scaffold with auth + `/health` reading
   `atlas_pipeline_runs` (a consumer exists from the first run); CI jobs.
   New dependencies in a `[global]` extra of `pyproject.toml`: `alpaca-py`, `edgartools`,
   `etf-scraper`, `financedatabase`, `exchange_calendars` (and `financetoolkit` only if the
   Phase 3 decision goes that way); everything else is already installed. `seed_thresholds.py`
   inserts the seed threshold rows from §Methodology B/C (FM-approved before it runs).
4. Tooling: vendor gstack + ponytail as repo skills (or install via a SessionStart hook using the
   `session-start-hook` skill — verify each project's install steps first); run graphify locally
   (`uv tool install graphifyy && graphify install`, `/graphify .`) and commit `graphify-out/` if
   < ~5 MB else regenerate in the hook; headroom = laptop `uv tool install "headroom-ai[all]"` +
   `headroom wrap claude` (no repo change; does not apply to cloud sessions); commit a project
   `.claude/settings.json` so the planning-skill gate is portable.
- DoD: `make gate` green; CI migrations job applies 0002 on fresh PG17; `schema_gate.py` = 0
  cross-references in both trees; `python -m atlas.db` shows `atlas_global`; SIP gate PASS or an
  explicit logged FAIL; `/health` renders a real run.

**Phase 1 — Identity, prices, metadata, first surfaces (~2 weeks)**
- `build_identity`, `ingest_prices` (2016→ backfill, both adjustments), `ingest_macro`,
  `ingest_index_membership`, `compute_technicals`, `build_universe_snapshot` (+ ADV$ percentile
  report for the floor), `freshness_guard`, `write_health_snapshot`, both orchestrators croned;
  `import_stooq` ready; frontend `/universe`, `/etfs` (facts, price, RS — no scores yet),
  `/etfs/[symbol]` facts; Vercel prod URL live.
- DoD (`--check A`): ≥3,300 ETFs and 500/500 S&P names with ≥3 years of bars (or since inception);
  completeness ≥99% of prior session at EOD; 0 rows with `|ret_1d| > 1`; `max_abs_log_jump` < 0.4
  on `close_adj` for ≥99% (the unit-bug detector); SPY `close_tr` returns vs FRED `SP500`
  correlation ≥ 0.999; `technical_daily` recompute-and-diff < 1e-6 on 50 random instruments;
  identity gates (CIK 100%, series_id ≥95%, alias round-trip); every in-scope ETF has AUM with
  source + as-of; Alpaca-vs-Stooq closes within 0.1% on a 50-ticker sample; freshness PASS.

**Phase 2 — Classification engine + review UI (~2–3 weeks)**
- Taxonomy v1 (`docs/global/taxonomy.md`, FM-reviewed) → tables; `ingest_nport`,
  `ingest_issuer_holdings`, `etf_meta` (expense/AUM with source columns); `build_exposures`;
  `rules.py`; LLM batch pass; `validate.py`; `/admin/classify`; overrides; facets on `/etfs`;
  `/countries`, `/sectors` on confirmed/auto rows; the FM's 150-label eval set (week 1).
- DoD (`--check E`): holdings on ≥90% of ETFs by count / ≥98% by AUM; Σ|weight_frac| ∈ [0.9, 1.1]
  for ≥97% of non-leveraged ETFs; expense ratio on ≥90% (AUM-weighted ≥98%); 100% of active ETFs
  have a classification row; `review` backlog ≤5% by AUM; eval accuracy sector ≥0.92 / geo ≥0.95 /
  structure 1.00; every ProShares/Direxion ETF `basket_eligible=false`; `evidence_tickers ⊆
  holdings` = 100%; 3 known overrides survive a full re-run byte-equal; every `country_pure` ETF
  appears under exactly one country.

**Phase 3 — Scoring + validation + full views = Milestone 1 (~3 weeks)**
- `ingest_financials`, `ingest_filings_8k`, `ingest_form4`, `ingest_13f`, `ingest_short_interest`;
  `score_stocks`, `score_etfs` (with backfill), `build_country_views`, `eval_signal`; admin
  thresholds (Edit → Save → Preview via `composite_preview` → Commit via
  `recompute_composite_latest`); `/stocks`, scored `/etfs` + `/etfs/[symbol]` glass box,
  `/sectors`, `/countries`, `/methodology`, `/methodology/signal`.
- DoD (`--check B/C`, each India assertion copied): ≥95% of S&P 500 scored; each stock lens
  non-null ≥80% where inputs exist; every lens `stddev ≥ 2`, composite `stddev ≥ 10`; composite ∈
  [0,100]; decile monotone within cohort/peer group; catalyst > 0 for ≥60% of names with ≥20 8-Ks;
  ≥95% of in-scope ETFs scored, `lenses_active ≥ 3` for ≥80% by AUM, `quality` present iff
  `lookthrough_scored_w ≥ threshold` (both directions); 20 ETFs' `rs_3m_spy` recomputed from
  `close_tr` within 1e-6; every `country_pure` country has a `country_daily` row with an
  unleveraged, unhedged representative (0 violations); ≥250 historical dates in both journals;
  `blend()` parity vs `compute_composite` exact; `composite_preview` SQL == `blend()` on the latest
  date; Playwright smoke on the live URL: no "Unmapped", no NaN, no raw stats on user pages;
  freshness + producer-registry green.

**Phase 4 — Baskets + country-basket product (~2–3 weeks)** — DoD: SQL preview == Python replay
NAV for 5 real baskets over 3 years (|diff| ≤ $0.01/day); fractional quantities reconcile to
capital within cash residue; a leveraged ETF is refused at API and DB; a non-`country_pure` ETF
is refused in a `country` basket at the DB; marks fresh to EOD in the freshness guard.
**Phase 5 — Conversational builder** — DoD: 50-prompt eval passes; every numeric claim traces
to a tool result; no basket saved without explicit confirm. **Phase 6 — Execution (design only).**

Build cadence per feature: `/tdd` (the PreToolUse gate needs a planning skill in-session) →
implement → `make gate` → `/ponytail-review` the diff → PR → CI → merge; UI with
`frontend-design:frontend-design`; `superpowers:verification-before-completion` before "done".

## Reuse map

| Verbatim (import / copy unchanged) | Adapt (copy + US params) | Replace (no US analogue) |
|---|---|---|
| `atlas/lenses/compute/{technical,fundamental,valuation}.py` scorers; `atlas/compute/signal_eval.py`; `scripts/foundation/technicals.py`; `_db.py` helpers via `_gdb`; `universe_core.members`; `ingest_kite.py:_rate_limit`; `atlas_daily.sh` step/gate/runfile/Telegram; `test_producer_registry.py`; `write_health_snapshot.py`; frontend `ScoreDerivationTree`, `DecileMeter`, `classifySignal`, health tables (ported) | `compute_composite` → `blend()` (parity-tested); `thresholds_view.nest_thresholds` (lens list param); `risk_flags.py`; `fundamental_pit.py` (US-GAAP tags, `filed` PIT); `eval_signal.py` loaders; `build_universe_snapshot.py` (USD, AUM, basket_eligible); `validate_lenses.py` → `validate_global.py` (same `Gate` class); `freshness_guard.py`; `ingest_macro.py:_fred()`; `check_module_boundaries.py`; `schema_gate.py`; `atlas/db.py`; `atlas/config.py`; `etf_sector.py` ordered-rule shape → L2; `desk/prompts.py` validators → classify/chat validators; `narrate_audit_packs.py` fallback pattern; `PortfolioBuilder.tsx` ideas | `catalyst.py` keyword taxonomy; `flow.py` delivery %; `policy.py`; `cap_cohort.py` SEBI ranks (→ SPY-weight terciles); `adapters.py` NIFTY 50 calendar (→ SPY presence); `ohlcv_etf` ticker-keyed shape; `de_*_holdings` dual weight scale; Python-spawn API routes (→ SQL fns + job queue); session-pooler `db.ts` (→ transaction pooler) |

## Risks and open questions

1. **Alpaca SIP entitlement on a paper-only account** — unverified; Phase 0's first gate; fallback
   designed (Stooq spine + paid slot). Also confirm Alpaca's terms on displaying derived data
   and the corporate-actions endpoint's plan tier.
2. **Index licensing** — naming "S&P 500" / showing membership in a commercial adviser product
   may carry S&P DJI obligations; I am not certain — legal to confirm before launch.
3. **Issuer site terms** for automated holdings downloads — gentle cadence, caching; N-PORT is the
   licence-clean source and already carries the whole universe (lagged).
4. **N-PORT lag (~60 days, quarter-end month)** — classification and `quality` lens are
   stale-by-design for non-big-four ETFs; shown as `holdings_as_of` on the card.
5. **Look-through covers only S&P 500 constituents** — international/small-cap ETFs lose the
   `quality` lens (composite renormalises); decide later whether to score the Russell 1000
   (EDGAR financials are free, prices already ingested).
6. **Two implementations of preview math (SQL) vs record (Python)** — accepted with parity tests;
   if they drift, the SQL side is deleted and previews become Python-precomputed scenarios.
7. **Backend/cron code has no CI deploy** (open India gap) — the global cron inherits the box's
   git fast-forward; propose fixing in Phase 1 if the FM agrees.
8. **Free expense-ratio/AUM coverage for the long tail** — `company_tickers_mf.json` field names
   and issuer list columns verified day 1; `*_source` columns make any unofficial fill visible.
9. **LLM cost is small; the FM's 150-label eval set is the real cost** — schedule in Phase 2 week 1.
10. Country-product semantics to lock in Phase 2: `country_pure` threshold, regional ETFs
    ("Asia ex-Japan"), hedged share classes, frontier markets.
11. Alpaca 1Day bar finalisation time — the 01:00 UTC run assumes bars are final after extended
    hours; verify on the first nights and move the cron if not.

## Verification (end-to-end, per milestone)

1. Run `scripts/ops/atlas_global_daily.sh` against prod with a real EOD; inspect
   `atlas_pipeline_runs` / `atlas_validator_results` / `atlas_health_daily`; all gates green;
   the Vercel revalidate fired and `/health` shows the run.
2. `make gate` (lint + unit + pyright ratchet); `frontend-global`: `tsc --noEmit`, vitest,
   Playwright smoke against the preview URL; `schema_gate.py` both trees = 0.
3. Spot-check real instruments end-to-end: SPY, QQQ, EWJ (country_pure Japan), INDA, ICLN
   (renewables), AMLP (midstream), URA (uranium), SMH vs SOXX (semis pure-play vs
   picks-and-shovels debate), TQQQ (leveraged → not basket-eligible), HEDJ (hedged), AAPL, JPM
   (financial-company fundamentals path).
4. FM review sessions: liquidity floor from the printed distribution (Phase 1), taxonomy v1 +
   150-label eval set (Phase 2), threshold lock + IC review (Phase 3).
