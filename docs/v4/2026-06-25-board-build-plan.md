# Atlas — gap-fill + transparent-frontend build plan (board: 2026-06-27)

Goal: every number on the frontend is **real, validated, and fully explained** — and every
score's depth (lens → sub-component → raw inputs → the exact rule applied) is **visible on the
detail pages, nothing behind wrappers**. Simple logic, no synthetic data (Rule #0).

Driving artifacts: the methodology doc (`docs/v4/atlas-scoring-methodology.html`), the gap list
(`docs/v4/2026-06-25-data-gap-list.md`), the data-integrity gate
(`scripts/foundation/validate_data_integrity.py`) + `validate_lenses.py`.

---
## Decisions needed from FM BEFORE build (gating)
| # | Decision | Why it gates |
|---|---|---|
| D1 | **P/E + ratios: compute (close÷EPS) or ingest pre-computed from the screener?** | Determines whether P/B + EV/EBITDA get filled, and how valuation is sourced. |
| D2 | **Lens weights: keep IC-optimized (0.302309…) or move to simple, legible numbers?** | Board-explainability vs current. |
| D3 | **Valuation weight: stay 0% (display-only) or count toward conviction?** | Changes the model. |
| D4 | **Profitability (and the other step-scorers): keep simple 5-bucket, or continuous?** | You asked for simple — confirm we keep steps but feed them clean real data. |
| D5 | **Sector fold: the real NSE 31→≤21 map + how to source the 111 no-`de_instrument` stocks.** | Greens taxonomy + mapping. |
| D6 | **Kite daily auth: how to automate the token** (the freshness root cause). | "Runs every day" depends on it. |

---
## Phase 0 — Freshness + make-it-daily (foundation)  · gstack: none (ops)
- 0.1 Kite unblock (FM) → run `ingest_kite` → `ohlcv_stock` to 06-24.
- 0.2 Run the chain once: `compute_all → lens_daily → m3 → MV refresh → consolidate` → `technical_daily`
      + lens journal to 06-24. Recreate `mv_sector_breadth`/`mv_sector_cards` with the EMA21 + ret_12m
      DDL (already staged) and do the frontend ema20→ema21 rename together.
- 0.3 **Wire `compute_all`+`lens_daily`+`consolidate`+the gate into the nightly cron** (the structural
      "runs smoothly every day" fix) + D6 token automation.
- ✅ greens: technicals-fresh, lens-current, sector-MV-fresh; A1 breadth + A4 ret_12m verify here.

## Phase 1 — Fill the data gaps (every number real)  · gstack: /investigate per feed
- 1.1 **XBRL balance-sheet extraction** → fill `roic, roa, gross_margin, current_ratio, quick_ratio`
      (currently 100% empty) into `financials_quarterly/annual`. Real source: XBRL.
- 1.2 **ROE validity guard** — drop tiny/negative-equity denominators (kills the −3,754%…+1,598% tails).
- 1.3 **Valuation ratios per D1** — P/B (book value ÷ shares) + EV/EBITDA, or ingest pre-computed.
- 1.4 **Wire institutional flow** — `de_mf_holdings` (6 monthly snapshots) → MoM Σ(weight_pct) delta →
      real institutional sub-score (replaces modal 50). Stocks with no MF holding = genuine neutral.
- 1.5 **Sector fold per D5** — seed the real NSE rollup, apply `canonical_sector`, map the 111.
- 1.6 **A4b outlier** — re-check Defence after recompute; if still >80%, robust-weight (FM sign-off).
- ✅ data-integrity gate → 15/15; `validate_lenses` green; the 4 placeholder columns now real distributions.

## Phase 2 — Scoring correctness  · gstack: /plan-eng-review (this plan), /review (diffs)
- 2.1 Apply D2 (weights), D3 (valuation weight), D4 (keep simple steps on clean data).
- 2.2 **Policy → out of the score**; reframe as an informational **alert layer** (flag a policy
      counterproductive to an otherwise-green sector) + roadmap a separate news-monitoring agent.
- 2.3 Re-run lens pipeline; verify every sub-score traces to real data (no NULL/placeholder shipped).

## Phase 3 — Transparent frontend (the core ask)  · gstack: /plan-design-review → /design-review, frontend-design
- 3.1 **Stock detail = full glass box.** For each lens: show the lens 0–100, then EVERY sub-component
      with (a) its raw input value(s), (b) the exact rule/threshold it hit, (c) the points it earned.
      Nothing summarized away. E.g. Technical→Trend: "EMA21>50>200 ✓ +10 · price +6.2% vs EMA200 +5 ·
      RSI 61 (healthy) +5 · 1w +1.8% +3 = 23/25".
- 3.2 **In-app methodology page** — port `atlas-scoring-methodology.html` to a real route + link every
      sub-component on the detail page to its methodology entry.
- 3.3 **Data-lineage chips** — each displayed number carries its source (Kite / XBRL / NSE) on hover.
- 3.4 **No-synthetic audit** — sweep every surface (both themes); anything NULL/placeholder is fixed or
      removed, never shown as a fake number.
- 3.5 Design to the locked language (Daylight/Graphite, DecileLadder, Inter numerals); right detailing.

## Phase 4 — Board readiness  · gstack: /qa, /review, /ship, /land-and-deploy, /canary
- 4.1 Gate 15/15 + `validate_lenses` green on REAL output.
- 4.2 `/qa` the live app (both themes) — every detail page renders full depth, no blanks.
- 4.3 `/review` + `/ship` the branch; `/land-and-deploy`; `/canary` post-deploy.

---
## gstack skills mapped
- **Now:** `/plan-eng-review` (harden this plan) + `/plan-design-review` (Phase-3 transparency UX).
- **Per data feed:** `/investigate` (XBRL extraction, MF wiring).
- **Build:** `frontend-design` + `/design-review` (Phase 3); `/review` on every diff.
- **Ship:** `/qa` → `/review` → `/ship` → `/land-and-deploy` → `/canary`.

## Sequencing logic
Phase 0 unblocks everything (no point scoring stale data). Phase 1 makes inputs real. Phase 2 makes the
blend correct. Phase 3 exposes all of it transparently. Phase 4 proves it. Each phase ends on a
green gate / validation — no phase advances on unverified data.
