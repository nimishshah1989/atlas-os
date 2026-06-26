# Atlas Six-Lens — NEEDED vs HAVE (coverage map, 2026-06-21)

Companion to `atlas-six-lens-data-spec.md`. Maps every lens sub-component to: the
data it needs, whether we HAVE it, the coverage on the ~2,093-stock universe, whether
it's genuinely **point-in-time (PIT)** or a today-snapshot, and whether the scorer is
**wired** to the right source yet. Numbers are live (the fundamentals backfill is still
filling — cells marked 🔄 will climb to ~95%).

> **UPDATE 2026-06-21 (post-backfill, authoritative):** the 🔄 cells below have LANDED.
> Fundamentals are now historical — income **97%** to 2026-03 (~39 quarters/stock) + a real balance
> sheet `financials_annual` **86%** (~12y/stock) → ROE/D-E real (the Screener warm-session fix).
> Technical ATR/BB/vol/52w **100%** (PIT from 25y OHLCV). Insider classify fixed. Sector map 95.6%.
> **TIME coverage** is the thing the % below hides: technical/catalyst/flow are decades-deep; fundamentals
> ~10–12y; **VALUATION is a single snapshot with ZERO history** (`tv_metrics`) — its history is BUILT in
> Loop C, not backfilled. **Two data-layer holes remain → Loop C:** sector-RS (0%) and P/B (0%, unit-safe
> in Loop C). Sub-component note: a lens-level % is one indicator, not "all sub-components" (e.g. Technical
> is 3½/4 — sector-RS missing).

Legend: ✅ have & PIT · 🟢 have (snapshot, not yet PIT) · 🔄 filling now · ⚠️ gap/needs work

| Lens · sub-component | Needs | Have? | Coverage | PIT? | Scorer wired? |
|---|---|---|---|---|---|
| **TECHNICAL · Trend** (EMA stack) | EMA 21/50/200 + price | ✅ technical_daily (25y) | 99% | ✅ PIT | ✅ |
| **TECHNICAL · Relative Strength** | RS vs N500 (+ sector) | ✅ rs_*_n500; ⚠️ sector-RS missing | 99% / sector ⚠️ | ✅ PIT | ✅ (N500) |
| **TECHNICAL · Vol Contraction** (ATR/BB) | ATR(14), BB-width over time | ⚠️ only tv_metrics snapshot — not derived from OHLCV | — | ❌ snapshot (leaky) | needs derive |
| **TECHNICAL · Volume/Participation** | volume vs 30/60d avg | ⚠️ only tv_metrics snapshot | — | ❌ snapshot (leaky) | needs derive |
| **FUNDAMENTAL · Profitability** (ROE/ROCE) | ROE history = PAT ÷ equity | 🔄 financials_annual (equity) + PAT; 🟢 tv_metrics today | annual 🔄 / today 100% | 🔄 (after fill) | not yet (Loop C) |
| **FUNDAMENTAL · Margin** (level + streak) | quarterly margins history | ✅ financials_quarterly → 2026-03 | 87% | ✅ PIT | not yet (Loop C) |
| **FUNDAMENTAL · Growth** (rev/eps YoY) | TTM YoY from quarters | ✅ financials_quarterly | 87% | ✅ PIT | not yet (Loop C) |
| **FUNDAMENTAL · Balance sheet** (D/E, deleveraging) | equity + borrowings history | 🔄 financials_annual (XBRL) + Screener | 🔄 (was 0) | 🔄 (after fill) | not yet (Loop C) |
| **VALUATION · Relative cheapness** (vs sector PE) | PE + complete sector map | ✅ PE; ⚠️ sector map only 750/2093 | PE 100% / sector 36% | 🟢 snapshot | partial |
| **VALUATION · Absolute cheapness** (PE/EV zones) | PE, EV/EBITDA | 🟢 tv_metrics (PIT-derivable from price÷EPS) | 100% | 🟢 snapshot | not PIT yet |
| **VALUATION · P/B** | book value (equity) | ⚠️ pb_fbs 0% — but NOW derivable from financials_annual equity | new capability | — | not yet |
| **VALUATION · EV/EBITDA** | EV, EBITDA | 🟢 tv_metrics | 100% | 🟢 snapshot | partial |
| **VALUATION · 52w position** | price, 52w hi/lo | 🟢 from OHLCV (currently tv_metrics snapshot) | 100% | ❌ snapshot (leaky) | not PIT yet |
| **CATALYST · Earnings/Capital/Governance** | filings (dated, bucketed) | ✅ lens_filings (2002→now) | 96% | ✅ PIT | ✅ |
| **FLOW · Promoter/insider** | insider txns classified | ⚠️ lens_insider 78% BUT signal_type 100% 'other' (classify broken) | 78% (dead) | ✅ dated | ⚠️ broken — fix Loop C |
| **FLOW · Institutional Δ** | shareholding QoQ | ✅ lens_shareholding (quarterly) | 96% | ✅ PIT (quarterly) | partial |
| **FLOW · Smart-money/bulk** | bulk deals (dated) | ⚠️ lens_bulk_deals 1% (snapshot-only, broken) | 1% | — | deferred (D2) |
| **POLICY · Sector tailwind** | sector map + policy registry | 🟢 15 policies; ⚠️ sector map 36% | sector 36% | static (ok) | ✅ |
| **RISK · auditor/CFO/downgrade** | filings | ✅ lens_filings | 96% | ✅ | ✅ |
| **RISK · pledge spike** | insider pledge events | ⚠️ depends on insider classify (broken) | — | — | ⚠️ fix Loop C |
| **RISK · solvency** | balance sheet | 🔄 financials_annual (now filling) | 🔄 | 🔄 | not yet |

## The honest summary — where we stand vs the spec

**The big one is solved at the DATA layer:** the spec's two "genuine data-sourcing TODOs"
were (1) financials *history* and (2) the catalyst/flow feeds. Catalyst ✅ and shareholding ✅
are in. Financials history — the hardest — is now in hand: income statement (XBRL, to 2026-03
via Screener), and the **balance sheet (ROE/D-E) that never existed before** is filling now.

**What's actually left (small, bounded — not a moonshot):**
1. **Derive from OHLCV** (we have 25y of it): technical ATR/BB-width, volume-vs-avg, and the
   52w-position — so those stop using the tv_metrics snapshot. + add sector-relative RS.
2. **Complete the sector map** 750 → 2,093 — unblocks valuation's sector-median-PE *and* policy.
3. **Derive P/B** from the balance-sheet equity we now have (fixes pb_fbs = 0%).
4. **Fix the insider `signal_type` classify** so promoter/pledge signals fire (currently 100%
   'other' → flow's promoter sub-component and the pledge risk-flag are dead).
5. **bulk_deals** — deferred (broken snapshot; minor flow modifier).
6. **Loop C wiring + IC** — point the fundamental/valuation/flow/technical scorers at these
   historical/derived sources (not snapshots), rebuild the journal point-in-time, learn the weights.

So: **data ≈ in hand; remaining work is a handful of derivations + the sector map + the Loop C
wiring.** Nothing here requires sourcing a feed we don't have.
