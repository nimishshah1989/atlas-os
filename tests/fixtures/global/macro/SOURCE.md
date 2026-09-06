# FRED DTB3 — real observations, dated snapshot

Verbatim copy of FRED's keyless CSV export for `DTB3` (3-month Treasury bill, secondary market,
percent p.a.) from 2016-01-01, fetched on **2026-09-04 13:58:00 UTC**:

| File | Source | sha256 |
|---|---|---|
| `DTB3.csv` | https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3&cosd=2016-01-01 | `dfb4fdaf0cbc868698a6ca968f5390b603368afb06f0e27a6dc0c8f71fbf8c42` |

Header `observation_date,DTB3`; 2,783 observation rows, 2016-01-04 → 2026-09-02; an EMPTY value
marks a day the bond market did not publish (e.g. 2025-10-13, Columbus Day — the stock market was
open, so SPY has a session that day and the macro forward-fill must carry 2025-10-10's 3.86 onto
it). It exists so `tests/unit/global_market/test_ingest_macro.py` exercises the session
forward-fill on real observations without a FRED API key (the API tests themselves run only with
`FRED_API_KEY`). The nightly ingest uses the JSON API via `providers/fred.py`, never this export.
Refresh by re-fetching, never by editing.
