# Fund Category vs Benchmark — `/funds/compare`

**Status:** approved 2026-08-04 · **Scope:** frontend only, additive · **Owner:** Atlas

A self-contained page under Funds that builds an equal-weighted composite equity curve for a
mutual-fund category and plots it against benchmark indices, with a returns table, rolling-return
statistics, the constituent fund list, and a print-clean layout for HTML/PDF export.

Deliberately isolated: nothing in `atlas/`, the nightly pipeline, or the core lens compute changes.
This is a read-only analytical view over data that already lands in `atlas_foundation`.

---

## 1. Data reality (verified against the live DB, 2026-08-04)

These facts constrain the design and must be surfaced on the page itself.

| Fact | Number | Consequence |
|---|---|---|
| Active funds in `de_mf_master` | 4,207 | — |
| Funds with **any** NAV history | 953 | "all funds in the category" means *all funds we hold NAV for* |
| Funds with **current** NAV | 584 | some categories have thin recent coverage |
| Inactive funds with NAV **and** category | **0** | dead funds are absent from the source snapshot |
| `de_mf_nav_daily` span / rows | 2006-04-01 → 2026-07-31, 2.41M | deep history available |
| `index_prices` latest date | 2026-08-03 | NAV lags the index by ~3 days |
| TRI rows in `index_prices` | **0** | every benchmark is price-return |
| Broad categories present | Equity only | no debt or hybrid categories |
| Distinct categories | 18 | plus 36 funds with a NULL category (excluded) |
| Categories with a dead NAV feed | **3** | see §1.3 — the page must warn, not render silently |

Per-category NAV coverage (active funds with any NAV / total active):

```
Index Funds                    245/1278    Focused Fund                 30/177
Flexi Cap                       91/288     Equity - Infrastructure      24/132
ELSS (Tax Savings)              84/207     Value                        23/168
Large & Mid-Cap                 77/237     Sector - Healthcare          21/120
Large-Cap                       74/315     Sector - Technology          15/102
Small-Cap                       73/231     Equity - ESG                 12/59
Multi-Cap                       55/194     Sector - Energy               5/36
Mid-Cap                         55/228     Sector - FMCG                 1/7
Sector - Financial Services     36/217
```

### 1.1 Survivorship bias — known, disclosed, not fixable here

The Morningstar snapshot we ingest carries live funds only: 2 of 4,209 master rows are inactive,
and none of those has both NAV history and a category. Funds that closed or merged away are simply
not in our data, so the composite is survivorship-biased upward at source.

The composite is nonetheless **built** so that fund entry and exit are handled correctly (see §3) —
when dead-fund history is ingested, the curve corrects itself with no code change. Until then the
page states the bias plainly. Backfilling closed/merged funds is separate ingestion work, out of
scope for this spec.

### 1.2 Price-return vs total-return mismatch

Fund NAVs (growth plans) are total-return; every index in `index_prices` is price-return. The
composite is therefore flattered by roughly the market dividend yield, ~1–1.5%/yr. No synthetic
adjustment is applied — the page discloses the mismatch in the chart footnote and the table footer.
(The existing per-fund `FundEquityCurves.tsx` carries the same unstated flaw; noted, not changed
here.)

---

### 1.3 Three categories have a dead NAV feed

Discovered while verifying the composite query. This is a pre-existing pipeline defect, not
something this page introduces, but a four-month-old curve rendered without comment would read as
current:

| Category | Funds w/ NAV | Fresh (≥2026-07-25) | Newest NAV |
|---|---:|---:|---|
| India Fund Index Funds | 245 | **0** | 2026-05-15 |
| India Fund Focused Fund | 30 | **0** | 2026-05-15 |
| India Fund Equity - ESG | 12 | **0** | 2026-04-06 |
| India Fund Value | 23 | **1** | 2026-07-31 |

Every other category is fresh to 2026-07-31. 238 of the 245 Index Funds stopped on the same day
(2026-04-02), which points at an ingestion break rather than fund-level attrition.

The page shows each category's last NAV date in the picker and puts a warning banner above a stale
curve. Fixing the feed is separate ingestion work, out of scope here.

Note also that "Index Funds" mixes gilt and bond index funds in with equity ones, so its composite
is not an equity read. Not a defect; the constituents table makes it visible.

## 2. Route, controls, and state

Route: `frontend/src/app/funds/compare/page.tsx`, reached from a link on `/funds`.

All control state lives in the URL query string; the page is a server component that re-renders on
navigation. No client state library, no date-picker dependency — native `<select>` and
`<input type="date">`.

| Param | Values | Default |
|---|---|---|
| `cat` | one of the 18 `category_name` values | `India Fund Flexi Cap` |
| `period` | `1m` `3m` `6m` `1y` `2y` `3y` `5y` `max` `custom` | `3y` |
| `from`, `to` | ISO dates, used only when `period=custom` | — |
| `view` | `growth` `rolling` | `growth` |
| `window` | `1y` `3y` `5y` — rolling window, used only when `view=rolling` | `3y` |

Category options are labelled with their fund count and, where the feed has stopped, its last NAV
date — e.g. `Flexi Cap · 91 funds`, `Index Funds · 245 funds · stale to 2026-05-15` — so thin or
dead coverage is visible before selection rather than after. The `India Fund ` display prefix is stripped for labels via the
existing `cleanCat` convention in `FundsPageV4.tsx`; filtering uses the raw value.

Invalid or unknown param values fall back to the defaults rather than erroring.

---

## 3. Composite construction

**Chain-linked daily equal-weighted returns.** For each date, take the simple daily return of every
fund alive on both that date and the prior observation, average those returns equally, then compound
the averages forward.

This is not an average of rebased NAV levels. 215 funds' NAV histories begin in 2026 alone; averaging
levels would let a newcomer rebased at 100 drag the composite. Chain-linking makes fund entry and
exit a non-event: a fund contributes only on days where it has both endpoints of a return.

Computed in SQL (aggregation belongs in Postgres per the data-engineering rules):

```sql
WITH nav AS (
  SELECT n.mstar_id, n.nav_date, n.nav,
         lag(n.nav) OVER (PARTITION BY n.mstar_id ORDER BY n.nav_date) AS prev
  FROM atlas_foundation.de_mf_nav_daily n
  JOIN atlas_foundation.de_mf_master m USING (mstar_id)
  WHERE m.category_name = $cat
    AND n.nav_date BETWEEN $from AND $to
    AND n.nav > 0
),
daily AS (
  SELECT nav_date, avg(nav / prev - 1) AS r, count(*) AS n_funds
  FROM nav
  WHERE prev IS NOT NULL AND prev > 0 AND nav / prev - 1 > -1
  GROUP BY nav_date
)
SELECT nav_date,
       100 * exp(sum(ln(1 + r)) OVER (ORDER BY nav_date)) AS composite,
       n_funds
FROM daily
ORDER BY nav_date;
```

Notes:
- Postgres has no product aggregate; `exp(sum(ln(1+r)))` is the standard chain-link. The
  `r > -1` guard keeps `ln` defined — a NAV collapse to zero would otherwise abort the whole series.
- `n_funds` per date is returned and charted as a thin count strip, so the reader can see coverage
  changing under the curve.
- The date filter is applied before the window function, so the scan is bounded by the selected
  period, not the full 2.41M rows.
- The `prev > 0` filter and `nav > 0` filter together mean a NULL or zero NAV produces no return for
  that fund that day rather than a zero return — a missing NAV must never read as a flat day.

**Benchmarks** are joined **as-of** — the last close on or before each NAV date — not on date
equality, then rebased to 100 at the first date on which the composite exists so all four lines
share an origin. The as-of join is load-bearing, not defensive: `index_prices` has no row for
2024-03-31, 2025-03-31 or 2026-03-31 while fund NAVs exist on all three, and an equality join
silently drops those points. `LEFT JOIN LATERAL (… WHERE date <= nav_date ORDER BY date DESC
LIMIT 1)` supplies the real prior close instead.

(The existing per-fund `FundEquityCurves.tsx:207-208` uses an equality join and has the same
latent hole — noted, not changed here.)

**Constituents** are a separate lightweight query: each fund's first and last NAV inside the window,
its return over that span, and whether it was present for the full window.

---

## 4. Benchmark mapping

Three benchmark lines: **Nifty 50**, **Nifty 500**, and the **category index**.

The category index comes from a module constant — a reference mapping, not a methodology number, so
it does not belong in `atlas_thresholds`. All 15 distinct codes were verified present in
`index_prices` with 3,795+ days of history each.

| `category_name` | `index_code` |
|---|---|
| India Fund Index Funds | `NIFTY 500` |
| India Fund Flexi Cap | `NIFTY 500` |
| India Fund ELSS (Tax Savings) | `NIFTY 500` |
| India Fund Focused Fund | `NIFTY 500` |
| India Fund Large-Cap | `NIFTY 100` |
| India Fund Large & Mid-Cap | `NIFTY LARGEMID250` |
| India Fund Mid-Cap | `NIFTY MIDCAP 150` |
| India Fund Small-Cap | `NIFTY SMLCAP 250` |
| India Fund Multi-Cap | `NIFTY500 MULTICAP` |
| India Fund Value | `NIFTY500 VALUE 50` |
| India Fund Equity - Consumption | `NIFTY CONSUMPTION` |
| India Fund Equity - Infrastructure | `NIFTY INFRA` |
| India Fund Equity - ESG | `NIFTY100 ESG` |
| India Fund Sector - Financial Services | `NIFTY FIN SERVICE` |
| India Fund Sector - Healthcare | `NIFTY HEALTHCARE` |
| India Fund Sector - Technology | `NIFTY IT` |
| India Fund Sector - Energy | `NIFTY ENERGY` |
| India Fund Sector - FMCG | `NIFTY FMCG` |

`de_mf_master.primary_benchmark` is **not** used: it holds Morningstar display strings
("Nifty Smallcap 250 TR INR", "BSE 500 India TR INR") that join to nothing we store, and its BSE
entries have no series in `index_prices` at all.

When a category index has a shorter history than the selected window (only `NIFTY100 ESG`, from
2011), that line starts late rather than being back-filled.

---

## 5. Page composition

1. **Header** — category name, window, fund count, composite as-of date, and the staleness note
   (NAV runs ~3 days behind the index). For a category whose feed has stopped (§1.3), a warning
   banner naming the last NAV date sits directly above the chart. A second note counts the dates
   where fewer than half the category reported a NAV — mostly weekends and holidays where a few
   schemes still stamp one (Small-Cap over 5y: 22 of 1,240 days, worst 2 funds of 71 on
   2025-11-02). The composite averages whoever reported, so those single-day moves are noise, and
   the coverage strip alone squashes them into a spike the eye dismisses.
2. **Controls** — the five inputs from §2, hidden in print.
3. **Chart** — `AtlasLightweightChart`. In `growth` view: composite plus three benchmarks, all
   rebased to 100 at the window start. In `rolling` view: the composite's rolling return through
   time against the category index's, with a zero line. Under either view, a thin strip plots the
   per-date constituent count from §3, so changing coverage is visible beneath the curve.
4. **Returns table** — composite and each benchmark across 1M/3M/6M/1Y/2Y/3Y/5Y, plus excess vs each
   benchmark. Absolute return below one year, CAGR at one year and above (per the financial-domain
   rules). Cells for periods longer than the available history read `—`, never 0.
5. **Rolling statistics table** — min / 25th / median / 75th / max rolling return for the composite
   and the category index, plus the percentage of rolling windows in which the composite beat it,
   and the window count the statistics are computed over.
6. **Constituents table** — every fund in the composite over the window, sorted by return, each name
   linking to `/funds/[mstar_id]`, with a marker for funds present for only part of the window.
7. **Footer** — data sources, the price-return disclosure, and the survivorship-bias disclosure.
8. **Print** — reuse `components/maal/PrintButton.tsx`; the page root carries `report-page` so the
   existing `@media print` block in `globals.css` handles pagination, the light palette, and hiding
   the fixed nav. Controls carry `print:hidden`. Tables carry `break-inside-avoid`.

Formatting follows the existing frontend rules: right-aligned tabular numerals, signed percentages,
`sig-pos` / `sig-neg` tones, `DD-MMM-YYYY` dates.

---

## 6. Files

| File | Purpose | Kind |
|---|---|---|
| `frontend/src/app/funds/compare/page.tsx` | route shell; parses searchParams, composes sections | new |
| `frontend/src/lib/queries/fund_category_curve.ts` | the three SQL reads — composite, benchmarks, constituents | new |
| `frontend/src/lib/fundCategoryCurve.ts` | pure builders — rebase, period returns, CAGR, rolling windows, stats | new |
| `frontend/src/lib/__tests__/fundCategoryCurve.test.ts` | unit tests over the pure builders | new |
| `frontend/src/components/funds/CategoryCompareControls.tsx` | the five inputs (client component) | new |
| `frontend/src/components/funds/CategoryCompareReport.tsx` | chart + the three tables + footer (server) | new |
| `frontend/src/components/funds/FundsPageV4.tsx` | add the entry link | edit |

Every file stays inside the tiered size limits (600 source / 800 test / 250 page shell).

### 6.1 Module boundaries

- `fundCategoryCurve.ts` is pure: it takes arrays of `{ date, value }` and returns arrays and
  numbers. No DB, no React, no dates-from-now. This is where all the arithmetic lives and where the
  tests point.
- `fund_category_curve.ts` owns SQL and nothing else — it returns plain typed rows.
- The components own layout and formatting, no arithmetic.

---

## 7. Testing

Per Atlas rule #0, tests use **real records pulled from the data layer** — no invented NAVs, no
fabricated index levels. Following the convention already set by
`frontend/src/lib/__tests__/fundEquityCurve.test.ts`, fixtures are real rows inlined in the test
file under a header comment naming the mstar_id, the source table, the date range, and the
extraction date, plus why that particular window was chosen.

Two real windows carry most of the load, picked because they exercise the hard cases naturally
rather than requiring contrived inputs:

- **`India Fund Sector - Energy`, 2025-08-05 → 2026-04-07** — five funds with staggered real start
  dates (2024-03 through 2025-08) and one that stops reporting on 2026-04-02, with genuine NAV gaps
  on 2026-03-30 and 2026-04-01. Entry, exit and gaps, all real.
- **`India Fund Sector - FMCG`** — exactly one fund with NAV (ICICI Pru FMCG Gr), so the category
  composite must equal that fund's own rebased NAV. This is the single-fund identity check.

The SQL itself gets an integration test guarded on `ATLAS_DB_URL` (present on the laptop, absent in
CI), so the chain-link is locked against regression without making the unit suite need a database.

Cases the tests must cover:

1. **Chain-link correctness** — the composite over a single fund equals that fund's own rebased NAV
   series. This is the load-bearing check: if it holds for one fund, the compounding is right.
2. **Fund entry mid-window** — a fund whose history starts inside the window contributes only from
   its second observation, and its arrival does not step the composite.
3. **Fund exit mid-window** — a fund whose history ends inside the window stops contributing, and
   its departure does not step the composite.
4. **NAV gap** — a fund missing a day produces no return for that day, not a zero return, and the
   composite for that day is the average of the funds that did report.
5. **Rebase origin** — composite and all benchmarks equal exactly 100 on the first shared date.
6. **CAGR gate** — periods under one year return absolute return; one year and over return CAGR
   computed on actual day count, `(end/start)^(365.25/days) - 1`.
7. **Insufficient history** — a period longer than the available series returns `null`, never 0.
8. **Rolling windows** — window count, and the beat-rate against the benchmark, are correct on a
   real series of known length.
9. **Rolling windows anchor on calendar months, never shortening** — a 1Y window anchors on the
   last observation on or before (date − 12 months). Where that lands between observations the
   window errs long, not short: a window shorter than the one requested would understate the return
   and mislabel it. A day-count anchor and a calendar anchor disagree around leap days, so this is
   pinned by a real case (2025-02-28 anchors to 2024-01-31, not 2024-02-29).

10. **Thin-coverage detection** — dates where the contributing fund count fell below half the
    category's running peak are counted and the worst named. Peak is a running maximum so a
    category that grew from 40 funds to 70 is not retroactively judged thin for its early years.

Coverage target on the new pure module: ≥80%.

Note on harness: query modules were previously untestable — `lib/db.ts` imports `server-only`,
which throws outside a React Server Component, and vitest loads none of Next's env files. The
build aliases `server-only` to its own no-op in `vitest.config.ts` and loads `.env.local` via
Node's stdlib `process.loadEnvFile` in `vitest.setup.ts`. No new dependency.

---

## 8. Performance

The composite query scans `de_mf_nav_daily` filtered by category join and date range. Measured
2026-08-04 over the `aws-1-` pooler from the laptop, worst case (Index Funds, 245 funds):

| Window | Rows | Warm |
|---|---:|---:|
| 1y | 183 | 0.64s |
| 3y | 679 | 2.80s |
| 5y | 1,174 | 2.52s |
| max | 4,957 | 2.88s |

Cold was 8.2s. Notably 3y is no faster than max, so the cost is the NAV scan, not the row count and
not the benchmark LATERAL. The build checks the query plan; if it shows a sequential scan, resolving
the category to an explicit `mstar_id` list first should let the planner use
`ix_de_mf_nav_daily_mstar_id_nav_date`. Otherwise the page revalidates hourly so the cost is paid
once per category per hour. Not in scope either way: moving the aggregation into Python, or adding a
materialized view.

---

## 9. Out of scope

- Repairing the dead NAV feeds for Index Funds, Focused Fund and Equity-ESG (§1.3) — 287 funds. The
  page exposes the defect; the cause is in `scripts/foundation/`.
- Backfilling closed and merged funds (fixes the survivorship bias; separate ingestion work).
- Ingesting NSE TRI series (fixes the PR/TR mismatch; separate pipeline work).
- Fixing the equality join in `FundEquityCurves.tsx:207-208`, which drops benchmark points on dates
  the index did not trade — the same bug this page avoids with an as-of join.
- Debt and hybrid categories (no such data).
- A PDF generation library — browser print-to-PDF, as with the Maal report.
- AUM-weighted or expense-adjusted composites.
- Any change to the nightly pipeline, `atlas/`, or the lens compute.
