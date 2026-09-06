# S&P 500 membership — provenance of the real source files

The index-membership parsers (`atlas/global_market/providers/ssga.py`,
`atlas/global_market/providers/sp500_history.py`) and the interval logic
(`atlas/global_market/index_membership.py`) are tested on REAL records only (rule #0). What is
committed here and what is fetched live is decided by licence and size:

| File | Source | Licence | In the repo? |
|---|---|---|---|
| `holdings-daily-us-en-spy.xlsx` (SPY) | https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx | SSGA's disclosure rows: *"The whole or any part of this work may not be reproduced, copied or transmitted or any of its contents disclosed to third parties without SSGA's express written consent."* | **No — fetched live** by the tests (`tests/unit/global_market/live_files.py`, cache `INDEX_FIXTURE_CACHE`) and by the weekly step. Internal cross-check only; holdings are never shown to clients without consent. |
| `holdings-daily-us-en-{xlb,xlc,xle,xlf,xli,xlk,xlp,xlre,xlu,xlv,xly}.xlsx` (the eleven Select Sector SPDRs) | same URL pattern, one file per fund | same notice | **No — fetched live** (they give `instrument_master.sector_gics` by membership: the SPY workbook's own `Sector` column is `-` on every row) |
| `sp500_ticker_start_end.csv` | https://raw.githubusercontent.com/fja05680/sp500/master/sp500_ticker_start_end.csv | MIT (https://raw.githubusercontent.com/fja05680/sp500/master/LICENSE — "Copyright (c) 2019-2020 Farrell J. Aultman") | **Yes** (27,977 bytes; fetched 2026-09-04 13:49:31 UTC; sha256 `39c488ebd6ce6838599e54751adbe8c8e4b68d5801dd77d29b6d137dd77388ac`). Refresh by re-fetching, never by editing. |
| `S&P 500 Historical Components & Changes (Updated).csv` | https://raw.githubusercontent.com/fja05680/sp500/master/S%26P%20500%20Historical%20Components%20%26%20Changes%20(Updated).csv | MIT (same) | **No — fetched live** (5.5 MB; the tests cache it as `sp500_historical_components_and_changes.csv`) |

## What the 2026-09-03 files held (measured 2026-09-04, printed by the tests beside the live numbers)

SPY (54,422 bytes, sha256 `b054eec1d502fe551ed17b9d3a4c4b00fd35f4a450290a0d721cef68eeee36fb`): 505 holding rows
= 503 equities + the cash line (`US DOLLAR`, ticker `-`, identifier `999USDZ92`) + one contra/escrow
line (`CONTRA HOLOGIC INCORPO`, ticker `2602335D`, weight 0.000003). Σ Weight = 99.936168 (percent).
`Identifier` = CUSIP on every row (NVDA 67066G104, AAPL 037833100, MSFT 594918104). Class shares are
spelled with a dot (`BRK.B`, `BF.B`) — the Nasdaq ACT spelling. The `Sector` column is `-` on all
505 rows.

Select Sector SPDRs, all "As of 03-Sep-2026", same header as SPY, each with a cash line and one
index-futures line (`IXTU6` in XLK) that is not in SPY: XLB 26, XLC 25, XLE 22, XLF 77, XLI 84,
XLK 74, XLP 35, XLRE 31, XLU 32, XLV 61, XLY 48 ticker rows (515 = 504 + 11 futures lines). Every one
of SPY's 504 ticker rows (503 equities + the contra line) is in EXACTLY ONE sector file — 0 in none,
0 in several; ticker and CUSIP keys agree.

fja05680/sp500: `sp500_ticker_start_end.csv` 1,259 spells, 503 current, 52 tickers with more than
one spell; the components file 2,718 rows, 1996-01-02 → **2026-06-30** (sha256
`39a9202c9ef69a74c0ff07e2113ad41fb6da7c8c5b6cd9541f0185fb4391e717`); the spells re-derived from the
components agree with `start_end` exactly. `start_date` is inclusive and `end_date` exclusive
(verified row by row — provider docstring). The author's caveats (README): hand-maintained from
Wikipedia since 2019; the 1996–2019 base file came as a download associated with Andreas Clenow's
*Trading Evolved* and was merged and cleaned by the author; 1996–2001 rows are incomplete —
irrelevant from 2016.
