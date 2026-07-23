# Wealth: transactions build plan — ledger ingest → engine → dashboard

Status: EXECUTION PLAN (2026-07-23), written to be self-contained for a fresh session.
Supersedes the brainstorm in `wealth-transactions-roadmap.md` (kept for the tier narrative).
Prereq state: `wealth` schema live (219 clients / 3,309 holdings / ₹439.4 cr, scorecard,
flags, look-through — see `wealth-recommendation-framework.md`).

## 0. The data (format CONFIRMED from a real sample)

Source: Jhaveri back-office **"Folio Ledger" PDFs** — one per client, full lifetime
transaction history. Drive folder `1Ws0X1j4LXMpa_XpyOZ1bTwhkJWr0e3Vg`, subfolders per
advisor code (191612/191655/191860/191885/191931/191958 — same codes as the valuation
drop; **these are ADVISOR codes**, e.g. "Your Advisor : ANNAMMA JIJI [191612]").
Sample inspected: `R02568 - Renji Issac - FoliLedg.pdf` (78 pages, 1 client).
Local sample: `/home/ubuntu/jhaveri_data/sample_ledger.pdf`. Upload was in progress
2026-07-23; re-inventory the folder before building (reuse the embeddedfolderview
scrape from `download_missing.py` era, or the Drive MCP).

**Layout observed (same generator family as valuation reports; word-position parsing
with pdfplumber, fonts distinguish header vs data — see parse_jhaveri.py precedent):**

- Client header: name + [client code], report date, address, email/mobile,
  **joint holders** ("Renji Issac/Mini Renji Issac [Anyone or Survivor(s)]"),
  **Tax Status** (Resident Individual/NRI/…), **Advisor name [code] + Branch**,
  **KYC: Yes/No**, A/C Type. (Note OCR-ish spacing quirks: "K Y C :N o", "A/C Typ e".)
- Per fund-folio block: `Fund <official name> Regular-Growth / <ISIN> Folio No. <folio>`
  + Holding Type (Physical/Demat). **ISIN is printed** → identity join is direct
  (wealth.schemes already carries ISIN from the AMFI bridge; join on ISIN, fallback folio+name).
- Transaction rows, columns: Date (dd/mm/yy) | Description | Trade Price (NAV) |
  **Debits**(Amount, STT, Units) | **Credits**(Amount, Units) | **Balance Units**.
  Description values seen: Purchase, SIP, Switch In, Switch Out, Redemption, Dividend
  variants, `*** Stamp Duty Charges on Above ***` (amount-only annotation rows),
  `Opening Balance` (balance-only row — ledger may not reach true inception; treat
  opening balances as synthetic inflow at first-date NAV, FLAGGED as approximate).
- Description text can wrap to its own line below the numeric row (same continuation
  problem as valuation parser — reuse the y-gap + font approach).

## 1. Schema (add to scripts/wealth/schema.sql; same PII hardening: revoke anon/authenticated)

```sql
create table wealth.client_profile_ext (   -- new facts the ledger header carries
  client_id bigint primary key references wealth.clients,
  joint_holders text, holding_mode text,   -- "Anyone or Survivor(s)" etc.
  tax_status text, kyc_ok boolean, account_type text,
  advisor_name text, advisor_code text, branch text);

create table wealth.transactions (
  txn_id bigint generated always as identity primary key,
  client_id bigint not null references wealth.clients,
  scheme_id bigint references wealth.schemes,    -- via ISIN join; nullable until mapped
  isin text, folio text not null,
  txn_date date not null,
  txn_type text not null,       -- purchase|sip|switch_in|switch_out|redemption|swp|
                                -- div_payout|div_reinvest|opening_balance|other (raw kept)
  description_raw text not null,
  nav numeric(16,4), units numeric(20,3), amount numeric(18,2),
  stt numeric(12,2), stamp_duty numeric(12,2),   -- folded from annotation rows
  balance_units numeric(20,3),                   -- ledger's own running balance
  is_debit boolean not null,
  source_file text not null, page int,
  approx boolean not null default false,         -- opening-balance-derived rows
  created_at timestamptz not null default now());
create index on wealth.transactions (client_id, txn_date);
create index on wealth.transactions (scheme_id);
-- derived (rebuilt, not hand-edited):
--   wealth.lots            (FIFO lots: buy_date, units, cost, open/closed, ltcg_eligible)
--   wealth.client_behaviour(one row/client: behaviour-gap, PGR/PLR, chase beta, panic score,
--                           sip survival stats, switch counts …)
--   wealth.advice_ledger   (per switch: sold fund fwd return vs bought fund fwd return)
```

## 2. Parser: `scripts/wealth/parse_ledgers.py` (+ loader `load_ledgers.py`)

Follow parse_jhaveri.py conventions exactly (word positions, per-page column anchors from
the header row "Date Description Trade Price … Balance Units", bold/regular font rules,
CONT_GAP for wrapped descriptions; parser venv = `/home/ubuntu/jhaveri_data/venv`).
Stamp-duty/STT annotation rows attach to the PRECEDING transaction. Fund-block header
regex captures name / plan-option / ISIN / folio.

**Reconciliation gates (loader refuses failures, same DoD philosophy):**
G1 per-row: |prev_balance ± units − balance_units| ≤ 0.001 (the ledger self-checks).
G2 per-row: |units × nav − amount| ≤ max(₹3, 0.2%) where all three present.
G3 per fund-folio: final balance_units == wealth.holdings.balance_units for the same
   client+scheme+folio (as-on 14-Jul-2026 snapshot; tolerance 0.001 units) — the
   cross-dataset gate that proves both datasets. Mismatches listed by name, never loaded silently.
G4 per client: sum of external inflows/outflows ≈ client_reports flow summary (approx flag ok).

## 3. Engine modules (each a script writing a derived table; run order as listed)

1. **`build_lots.py`** — FIFO lot ledger from transactions → wealth.lots. Exact
   LTCG/STCG per lot incl. grandfathering (31-Jan-2018 equity), exit-load windows.
   REUSE the FIFO Indian tax ledger already in `atlas/portfolio` (PR #157).
   → upgrades rules-engine cost side from estimate to exact.
2. **`exact_benchmark.py`** — replay every true external flow (excl. switches as
   external) into the Nifty-50 index fund NAV (mstar F0GBR06R0H, in de_mf_nav_daily
   since 2006) → exact per-client benchmark XIRR + alpha; also risk-matched blend
   later. Replaces the approximation in client_analytics.py.
3. **`behaviour_gap.py`** — per client × fund × year: money-weighted (investor) vs
   time-weighted (fund) return; gap in ₹/yr. Methodology: Morningstar "Mind the Gap"
   (US gap ≈1.1-1.2pp/yr) with the Hayley-2014 mechanical-component caveat encoded
   (report the decomposition, don't oversell).
4. **`behaviour_fingerprints.py`** — per client: disposition effect (Odean PGR/PLR,
   port the `dispositionEffect` package methodology); chase beta (inflows ~ trailing
   category returns); panic score (event-study around Mar-2020/2022/2025-26 drawdowns:
   net flow sign & size); SIP survival (Kaplan-Meier/Cox via `lifelines`, streak
   detection from monthly SIP rows); dividend-leakage; all → wealth.client_behaviour.
5. **`advice_ledger.py`** — every switch: fwd 1y/3y return of sold vs bought fund
   → per-switch regret; roll up per fund-push wave / advisor / year. INTERNAL ONLY.
6. **`counterfactuals.py`** — deterministic replays per client: never-stopped-SIPs,
   no-panic-sales, no-switches, all-flows-to-index → ₹ deltas (pitch pack).
7. **`churn_clv.py`** (after 1-6 stable) — redemption early-warning (survival models,
   `scikit-survival`; features from `tsfresh` over txn streams) + BTYD-style CLV.
   n-caveat: client-level models stay simple/interpretable; power is at event level.
   ASK FM: ledgers for departed clients (survivorship fix for churn labels).
8. Later: uplift on recommendations (`causalml`/`EconML`) once rec lifecycle log has volume.

## 4. Dashboard (extends the existing artifact pattern; later auth-only board page)

Regenerate the tabbed HTML (see scratchpad jhaveri-wealth-dossier.html pattern: data
JSON injected inline, verified in headless browse before publish; beware python NaN→
invalid JSON). New/updated pages:
- **Behaviour** — cohort behaviour-gap ₹; panic/chaser/disciplined counts; per-client table.
- **vs Benchmark** — now EXACT; alpha by grade; below-benchmark pitch list.
- **Advice scorecard** (internal) — push-wave/advisor attribution from advice_ledger.
- **Counterfactuals** — per-client "what-if" ₹ table (RM call-sheet).
- **Rules → Actions v2** — flags now carry exact tax cost + behaviour context
  (e.g. don't pitch swaps to high-disposition clients the same way).
- Existing pages (Overview/Risk/Sectors/Fees) refresh from the same tables.
Plain-language edition mirrors it (full-width grid layout per FM preference; no "ELI5" framing).

## 5. Research links (verified 2026-07-21)

- casparser (NOT needed for this format, but reference for CAS route):
  https://github.com/codereverser/casparser
- Mind the Gap methodology: https://www.morningstar.com/business/insights/research/mind-the-gap ;
  critique: https://www.tandfonline.com/doi/full/10.1080/0015198X.2026.2657253
- Disposition effect methodology: https://marcozanotti.github.io/dispositionEffect/articles/de-analysis.html ;
  python variant: https://github.com/js-park/Disposition-effect-from-Aggregate-trading-data
- Survival/churn worked examples: https://github.com/ejeej/Survival_Analysis_Customers_Churn ;
  https://github.com/archd3sai/Customer-Survival-Analysis-and-Churn-Prediction
- Feature factory: https://github.com/blue-yonder/tsfresh
- Tear sheets: https://github.com/ranaroussi/quantstats
- Optimizer upgrades for seat-shift: PyPortfolioOpt / riskfolio-lib / skfolio
- Causal rec impact: causalml / EconML

## 6. Operational context for a fresh session

- Repo scripts: `scripts/wealth/` (parse_jhaveri, load_parsed, map_schemes, amfi_bridge,
  fetch_unmapped_holdings, fetch_missing_nav, build_scorecard, cohort_report,
  deep_analysis, client_analytics). Parser venv: `/home/ubuntu/jhaveri_data/venv`
  (pdfplumber); analytics run under repo `.venv` (pandas/numpy/psycopg2).
- Data (PII, OUTSIDE repo): `/home/ubuntu/jhaveri_data/` — pdfs/ (valuations),
  ledgers/ (create; download via inventory + curl loop w/ backoff — see
  download_missing.py), parsed.json, dossier_data.json, reports/ (shareable HTMLs).
- DB: `ATLAS_DB_URL` in repo `.env` (strip `+psycopg2` for psql). New libs (lifelines,
  scikit-survival, tsfresh) → jhaveri venv or a new analysis venv, NEVER prod .venv.
- Artifacts: detailed https://claude.ai/code/artifact/9fbd31d4-d30e-403d-bbbe-49e964499e01 ;
  plain-language https://claude.ai/code/artifact/a7de195b-d136-4b3d-ae4c-83918d3321d1 .
- Known blocker: `git push` classifier-blocked in agent sessions → FM pushes.
- Honesty rails (standing FM policy): quoted ₹ values = certain (fees/tax) or realized
  (historical spreads) only; forward-return claims gated on the 2015-26 walk-forward
  backtest (still the #1 research build); A-grade clients default to "stay the course".

## 7. Build order (first session with full data)

1. Inventory Drive folder → download ledgers → `parse_ledgers.py` on 3-5 samples →
   iterate to 100% gate-clean → all clients → `load_ledgers.py` (G1-G4).
2. `build_lots.py` + `exact_benchmark.py` → refresh rules engine + benchmark page.
3. `behaviour_gap.py` + `behaviour_fingerprints.py` → Behaviour page + segments v2.
4. `advice_ledger.py` + `counterfactuals.py` → internal scorecard + pitch packs.
5. Dashboard regen (all pages) → verify in headless browse → republish both artifacts.
6. `churn_clv.py` once departed-client question answered.
