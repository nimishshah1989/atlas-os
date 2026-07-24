# The Seven-Prompt Mutual-Fund Audit Framework (Stockizen Research)

Source: @stockizen_research (SEBI RA INH000017675). FM-designated as the
**client-facing narrative structure** for the Jhaveri capability demo's per-client
mutual-fund overview. Every held fund / whole portfolio is to be audited under these
seven headings, in plain language, numbers in rupees.

Thesis: "Most people don't own 8 different mutual funds — they own the same stocks
through multiple funds and pay separate fees for each. That is not diversification, it
is expensive duplication." These 7 prompts find the weak funds, the repeats, and the
fees you never see.

## Prompt 1 — Read the Statement
Act like a fee-only adviser reading a client portfolio for the first time. From the MF
holding / consolidated account statement, pull out, as ONE clean table (no opinion yet):
- every scheme name with its SEBI category and its AMC
- invested amount, current value, absolute gain per scheme
- whether each scheme is Direct or Regular plan
- weight of each scheme as % of total portfolio
- total number of schemes and total number of AMCs held

## Prompt 2 — The Label Lie
Act like a compliance officer checking whether a fund does what its name promises. From
a fund's monthly portfolio disclosure, check:
- actual large/mid/small-cap split vs the SEBI minimum for its category
- cash and debt sitting inside a scheme sold as equity
- drift in that split across the last four monthly disclosures
- whether a flexi-cap fund is quietly behaving like a large-cap fund
- top-10 holdings as % of total assets
SEBI: large = top 100 by full mcap, mid = 101–250, small = 251+. If the fund doesn't
match its label, say so plainly.

## Prompt 3 — The Overlap Trap
Act like an analyst hunting for duplication I'm paying twice for. From the full
portfolios of every fund owned:
- pairwise overlap % between every two funds held
- every stock appearing in three or more funds
- true rupee exposure to each of the top-10 underlying stocks
- which pairs overlap above 50% of portfolio weight
- the fund in each pair that adds the least new exposure
"Owning eight funds isn't diversification if they hold the same thirty stocks." How many
genuinely different bets do I actually own?

## Prompt 4 — What You Actually Pay
Act like a cost auditor, not a salesman. From schemes, plan types, current expense ratios:
- annual cost in rupees per scheme on the actual invested amount
- gap between Direct and Regular plan cost for the same scheme
- management fee shown separately from transaction costs and statutory levies
- what Regular costs over 10 years vs Direct, compounded
- any index fund or ETF charging more than a passive fund should
From 1 Apr 2026 SEBI splits the expense ratio into management fee + transaction costs +
statutory levies on actuals — compare only the management fee. Every figure in rupees.

## Prompt 5 — Beat the Benchmark?
Act like a performance auditor who distrusts point-to-point returns. From funds,
benchmarks, return history:
- rolling 3-year and 5-year returns (not trailing point-to-point)
- excess return over the correct benchmark Total Return Index per fund
- how many of the last twenty rolling periods the fund actually beat it
- downside capture in the three worst market falls in the period
- whether the record came from one lucky year or from consistency
"A single great year can carry a ten-year number. Strip that year out and tell me what's left."

## Prompt 6 — The Bloat Check
Act like a due-diligence analyst studying the size and the people behind a fund. From the
factsheet + scheme information document:
- current fund manager, joining date, and whether the track record is even theirs
- AUM growth over five years and whether the strategy still fits that size
- a small-cap fund whose AUM makes its stated strategy hard to execute
- portfolio turnover ratio and what it implies about hidden trading costs
- any change of mandate, benchmark, or scheme merger in the last three years
"Past returns may belong to a manager who has already left. Separate the record of the
fund from the record of the person."

## Prompt 7 — The Cut List
Act like an adviser paid to shrink my portfolio, not grow it. From the full audit output
of prompts 1–6:
- the funds worth keeping and the exact evidence for each
- the funds that add no new exposure once overlap is counted
- the exit load and capital-gains-tax cost of removing each weak fund
- the smallest number of funds that would hold the same exposure
- the order to unwind them in so tax and load damage stays lowest
"Do not suggest new funds. Judge only what I already own. If the data doesn't support a
cut, say so plainly."

## Mapping to the Atlas wealth engines (as of 2026-07-23)

| Prompt | Status | Where |
|---|---|---|
| 1 Read the Statement | ✅ BUILT | audit_packs `map` + holdings; client_reports (invested/MV/gain, direct-regular, weights, scheme/AMC counts) |
| 2 The Label Lie | ✅ BUILT | `build_label_check.py` → fund_label_check (SEBI 100/250 split, verdict, top-10, coverage caveat). Gap: 4-disclosure DRIFT not yet computed (single latest disclosure only) |
| 3 The Overlap Trap | ✅ BUILT | `build_overlap.py` → client_overlap + client_fund_overlap (pairwise %, stock-in-3+, top-10 rupee exposure, effective bets). Gap: ">50% pair" + "least-new-exposure fund in pair" not surfaced explicitly |
| 4 What You Actually Pay | ⚠️ PARTIAL | client_flags closet-index fee_save. Gap: direct-vs-regular 10yr compounded, mgmt-fee-only split (SEBI Apr-2026), per-scheme ₹ cost table |
| 5 Beat the Benchmark? | ⚠️ PARTIAL | `exact_benchmark.py` → client_benchmark (cashflow-matched yearly growth vs index). Gap: rolling 3/5yr, beat-count over 20 windows, downside capture in 3 worst falls, luck-vs-consistency — all at FUND level |
| 6 The Bloat Check | ❌ NOT BUILT | needs fund factsheet/SID data (manager tenure, AUM 5yr, turnover, mandate/merger changes) — new data source |
| 7 The Cut List | ⚠️ PARTIAL | `build_scorecard.py` (evidence-gated grade) + client_flags actions + tax_harvest (exit tax). Gap: "smallest fund set for same exposure" + explicit tax/load-minimising unwind ORDER |

**Implication:** prompts 1–3 are essentially done at cohort scale — the demo already
computes them for all 242 clients, it just doesn't PRESENT them under these headings.
The genuine build gaps are prompt 6 (new fund-level data), and the fund-level depth of
prompts 4/5/7. The per-fund MF-overview engine synthesises all seven per client×fund and
renders them as the client-page section the FM asked for.
