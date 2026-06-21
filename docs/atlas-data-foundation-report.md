# Atlas data foundation — harness baseline + PoC report

> Deliverable for the two-step kickoff (verification harness + thin PoC) from
> `docs/atlas-data-foundation.md`. **Full 10y backfill loop NOT started** — this
> is the review checkpoint before launching it in tmux.
> Date: 2026-06-19. Code: `scripts/foundation/` (see its README).

## TL;DR
- The 3-axis verification harness is built and runs read-only against either the
  **live** `de_*`/`atlas_*` tables or the clean **staging** schema.
- **Baseline (live, Nifty 500 stocks): GREEN 0/500.** Coverage 451/500, Cleanliness
  256/500, Metrics 0/30 (sampled). This quantifies the distance to all-green.
- **Thin PoC (10 symbols, real NSE Bhavcopy → TA-Lib → staging): GREEN 10/10** on
  all three axes. The pipeline shape and the harness contract are de-risked.

---

## 1. Verification harness (the "definition of done")
Three axes, evaluated per instrument; all-green = `green_count == universe_size`.

| Axis | Checks |
|---|---|
| **Coverage** | present in OHLCV; ≥10y deep (back to 2016 or listing date); rows ≥ 95% of the in-span trading calendar |
| **Cleanliness** | no null/≤0 closes; ≥99% of calendar days present (no gaps); ≤1 trading-day stale; **no >50% 1-day jump** on adjusted close (unadjusted-corp-action detector) |
| **Metrics** | EMA 21/50/200, RSI(14), returns (1d/1w/1m/3m/6m/12m), RS vs N50/N500 × 6 windows present for every priced date; **TA-Lib recompute-and-diff matches stored** |

- Trading calendar = dates in the `NIFTY 50` reference series (2,517 days, 2016-04-07→2026-06-18).
- Universe = current Nifty 500 from `de_instrument` (current-membership-for-all-history, per lock).
- TA-Lib **0.6.8** installed (primary locked choice; `pandas-ta` fallback not needed).
- Per-instrument detail written to `output/foundation_harness_{live,staging}.json`.

## 2. Baseline — how far live data is from all-green
Run: `harness.py --profile live --metrics-sample 30` over all 500 Nifty-500 names.

| Axis | Pass | Fail |
|---|---|---|
| Coverage | 451 | **49** |
| Cleanliness | 256 | **244** |
| Metrics (30 sampled) | 0 | **30** |
| **GREEN (all axes)** | **0 / 500** | |

**Coverage (49 fail):** 42 too-shallow (recent listings / <10y depth), 9 late first-date.
Mostly legitimate young constituents (e.g. AFCONS, ACUTAAS list in 2025), not corruption.

**Cleanliness (244 fail):**
- **204 names have a >50% single-day jump** in stored `close_adj` — i.e. `close_adj`
  is **not corporate-action-adjusted**. Verified example: **ADANIENT 2015-06-03,
  ₹637 → ₹109.75 (−82.8%)**, the demerger left unadjusted in both `close` and
  `close_adj`. Worst ratios reach ~530× (point spikes / near-zero closes).
- 52 names have calendar gaps; 2 are stale.
- This is the root cause class behind the FMCG +249.8% artifact in the doc.

**Metrics (0/30):** structural — live stores **20-EMA, not 21**, has **no RSI**
column, only 3 RS windows vs N500 (no N50, no 1d/6m/12m), and even where EMA50/200
exist they **diverge from a clean TA-Lib recompute** (worst Δ in the hundreds of ₹),
implying a different price basis / seeding in the legacy compute.

> Takeaway: storage isn't the problem (the doc was right) — **supply quality is**.
> Adjustments and the metrics contract are the biggest gaps; coverage is close.

## 3. Thin PoC — clean pipeline proven green
Run: `poc.py`. Symbols: 10 clean, full-depth Nifty-50 names (HCLTECH, SUNPHARMA,
BHARTIARTL, INDIGO, POWERGRID, CIPLA, HINDUNILVR, ASIANPAINT, COALINDIA, TECHM).

Pipeline exercised end-to-end:
1. Seeded deep adjusted history (2016→T-1) + N50/N500 indices into `foundation_staging`.
2. **Downloaded the real NSE UDiFF Bhavcopy for 2026-06-18** (3,388 CM rows + 158
   indices), parsed, and ingested the 10 names' rows.
3. **Reconciliation: max |our-parse − de_*| close diff = 0.0** across all 10 — our
   independent Bhavcopy parse is exact.
4. Computed TA-Lib technicals (25,940 rows) via the same module the harness recomputes.
5. Harness on staging:

| Axis | Result |
|---|---|
| Coverage | **10 / 10** |
| Cleanliness | **10 / 10** |
| Metrics | **10 / 10** (recompute matched stored on ~2,400–2,590 dates per metric) |
| **GREEN** | **10 / 10 ✅** |

Why these symbols: chosen as already-clean so GREEN reflects **pipeline correctness**,
not a claim that live data is clean (baseline = 0/500). Cleaning the dirty 204 via
deterministic corp-action back-adjustment is the loop's job, gated by the jump check.

## 4. Decisions confirmed / honoured
- Staging-only writes (`foundation_staging`); live `de_*`/`atlas_*` untouched.
- TA-Lib for all technicals; Decimal/`numeric` for money; tz-aware timestamps.
- EMA **21**/50/200; RS vs **N50 + N500** × 6 windows; current N500 membership.

## 4b. UPDATE (2026-06-20) — Zerodha Kite verified as the clean adjusted source
The corp-action blocker is **resolved by sourcing OHLCV from Kite** (already
split/bonus adjusted). Verified empirically through the harness, not on faith:

- **15/16 known live-failures are clean in Kite.** The catastrophic de_* spikes
  collapse to real market moves: ZEEL 50,741% → **40%** (Sony-merger news),
  IDFCFIRSTB 53,003% → 17% (COVID crash), DRREDDY 47,546% → 14%, **ABB 78% → 13%**
  (split de_* never adjusted). The lone residual is **ABFRL** (55.9% on 2025-05-22)
  — a *genuine demerger*, a true discontinuity even perfect data keeps.
- **End-to-end green:** ABB, HDFCBANK, ZEEL, BAJFINANCE, IDFCFIRSTB (all 0-green in
  de_*) → Kite → staging → TA-Lib → harness = **5/5 GREEN** on all three axes.
- **Coverage:** Kite has stocks **+ ETFs** (NIFTYBEES/GOLDBEES/…) **+ 136 indices**
  (NIFTY 50/500/BANK), full depth 2016→**today** (fresher than Bhavcopy's T-1).
- Code: `scripts/foundation/ingest_kite.py` (`--verify SYMBOL`, `--symbols …`),
  reusing the existing `atlas.intraday.auth` Kite session.

**New architecture call (recommended): Kite = single primary OHLCV source** for
stocks/ETFs/indices; no in-house split/bonus adjuster needed. NSE Bhavcopy retained
only as an optional independent cross-check (raw close + delivery %).

Residual items specific to the Kite path:
1. **Demerger calendar.** The jump-check correctly flags genuine demergers
   (ABFRL-class) as discontinuities. Add a small corp-action ex-date calendar to
   whitelist them so they don't read as data errors. (Far smaller than a full adjuster.)
2. **Extend `ingest_kite` to ETFs + indices** staging tables (currently stocks only).
3. **Daily token refresh.** Kite tokens expire midnight IST; the manual login won't
   scale to a nightly job — decide TOTP auto-login vs daily manual for production.
4. **Backfill is token-time-bound** — run the full pull while a token is valid.

## 5. Open items before the full loop (need a call)
1. ~~Corporate-action source~~ → **RESOLVED: use Kite (§4b).** Remaining: the small
   demerger-whitelist calendar.
2. **Backfill depth re-pull vs seed.** PoC seeded deep history from de_* (itself
   Bhavcopy-derived) to stay thin. The full loop should re-pull ~2,500 daily
   Bhavcopy files from archives (token-free Python) and recompute — confirm.
3. **ETFs + indices axes.** Harness currently scores stocks; ETF/index coverage+
   cleanliness checks are straightforward to add (the 24 thin / gappy indices the
   doc flagged will fail). Add before the loop so "all-green" covers them.
4. **Pooler timeout.** Loop queries must avoid cross-partition SQL sorts (2-min
   cap); the harness already pulls unsorted + sorts in pandas.

## 6. Stop point
Per instruction, **the full 10y backfill is not started.** Ready to launch the
tmux loop on staging once item 1 (corp-action source) is decided.
