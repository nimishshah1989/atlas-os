# SEC EDGAR company facts — real payloads, dated snapshot

Three real `data.sec.gov` XBRL **company-facts** downloads, fetched on **2026-09-09** with a
contact `User-Agent` (SEC fair access). They exist so `tests/unit/global_market/test_fundamentals.py`
and `test_ingest_financials.py` run the tag map, the ratios and the row extraction against real
filings, offline and with no database (rule #0: never a fabricated fixture, never a `Mock()`
filing). **Refresh by re-fetching, never by editing.**

## What was changed, and what was not

Each file is the download with the us-gaap tags atlas does not map **removed**, and the `dei`
taxonomy dropped (nothing here reads it). That is the only change. Within every kept tag,
**all** of its facts are present and every `val`, `unit`, `form`, `filed`, `start`, `end`, `fy`,
`fp`, `accn` and `frame` is exactly as SEC served it — including the year-to-date durations and
the `8-K` / `DEF 14A` facts the ingest deliberately filters out, so the filters are exercised
rather than assumed. Each file carries a top-level `_atlas_note` saying the same thing; the
loaders ignore it. Trimming was needed for size only: Apple's untrimmed payload is 3.8 MB and
JPMorgan's 7.9 MB, against the repo's 1 MB per-file pre-commit cap.

| File | Source URL | Fetched (UTC) | sha256 of the **untrimmed** download | Kept | Trimmed sha256 |
|---|---|---|---|---|---|
| `companyfacts_AAPL_CIK0000320193.json` | https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json | 03:19 | `73a86c6aedc31f77cac2ea4df5f80f0b3bd7e6eb58bb4e01444fbedf3afb9c43` | 29 tags · 4,341 facts · 2006-09-30 → 2026-06-27 | `50e935b7d4e11335f40c936a38ef56440365ec6752f7517ea328c2ffdb86dd4e` |
| `companyfacts_JPM_CIK0000019617.json` | https://data.sec.gov/api/xbrl/companyfacts/CIK0000019617.json | 03:21 | `90b3cf44a1bf3ae4f3bdacb7de530c239f8ce4fa02e8ff97146947d264fb20b9` | 18 tags · 2,502 facts · 2007-12-31 → 2026-06-30 | `2530da058eb2f7fd251b2c027ed895d8629617cfa8f9c377850bcf36fd43a211` |
| `companyfacts_VZ_CIK0000732712.json` | https://data.sec.gov/api/xbrl/companyfacts/CIK0000732712.json | 03:21 | `e319d31a81cf3f17423edbb3e18d129653b348cfd8c902034e5a329bf2bf0624` | 29 tags · 4,428 facts · 2006-12-31 → 2026-06-30 | `75b8e84b747cdcb51ef0c9c8e1cb12ee033e90d1306d3cabc5e9a72afe4d8f60` |

## Why these three companies

They are not samples; each one is the counter-example to a way the mapping can be wrong.

* **Apple (AAPL)** — the ordinary path, and the only one of the three that still has a fiscal
  year in which a **discrete fourth quarter** was tagged (FY2020: the SEC dropped the
  selected-quarterly-data requirement in 2021). That is what lets `ratios.implied_q4` be tested
  against a real Q4 rather than against itself, and what lets a trailing-twelve-month figure be
  checked against the reported annual one. It also carries the revenue-element change of 2018
  (`SalesRevenueNet` → `RevenueFromContractWithCustomerExcludingAssessedTax`) and the **August
  2020 four-for-one split**, whose restated FY2019 diluted share count (4,648,913 thousand as
  filed in 2019, 18,595,651 thousand as re-filed in 2020) is the point-in-time test case.
* **JPMorgan (JPM)** — the financial-company path. It files **no** `OperatingIncomeLoss`, no
  `GrossProfit`, no `AssetsCurrent`, no `LiabilitiesCurrent` and no capital expenditure at all,
  and its only quarterly top line is `RevenuesNetOfInterestExpense`. It is the payload that
  proves a missing concept yields `None` and not a zero, and that the `is_financial` flag
  suppresses the balance-sheet ratios rather than the profitability ones.
* **Verizon (VZ)** — the fallback path. Its equity exists **only** as
  `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest`, its D&A only as
  `DepreciationAndAmortization`, its long-term debt as
  `LongTermDebtAndCapitalLeaseObligations` (no plain `LongTermDebtNoncurrent` since 2013), and
  its interest expense moved to `InterestExpenseNonoperating` in 2024. It also files **both**
  `NetIncomeLoss` (3,835M for the June 2026 quarter) and `ProfitLoss` (3,949M), which is what
  pins the parent-attributable element as the one that must win. Five of the map's corrections
  fire on this one filer. And it files no `PaymentsToAcquirePropertyPlantAndEquipment`, which is
  a real, reported coverage gap: capex, and therefore free cash flow, are `None` for it after
  2019.

## Refreshing

    curl -A "$EDGAR_IDENTITY" -o CIK0000320193.json \
      https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json

then trim to `atlas.global_market.fundamentals.xbrl_map.TAG_CONCEPTS` and update the table
above (both hashes, the fetch time and the fact counts). Values in these files are dated: a
refresh moves the newest period, so the tests that name a 2026 quarter move with it — the
FY2019/FY2020 assertions do not, because those filings are closed.
