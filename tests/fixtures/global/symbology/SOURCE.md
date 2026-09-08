# Identity directories — real files, dated snapshot

Verbatim copies of five of the six public identity files the symbology parsers and the identity
build read, all fetched on **2026-09-04** (times below; both Nasdaq files carry
`File Creation Time: 0904202607:00`). The sixth, `company_tickers_exchange.json`, is NOT kept: it
is optional to the build (`providers/directories.py` `OPTIONAL`) and added no identity the other two
SEC files lacked on 2026-09-04 (measured: the assembled frame is identical with and without it), so
the build reads it when the weekly fetch brings it and warns when a snapshot omits it. They exist so `tests/unit/global_market/test_symbology.py`,
`test_identity*.py` run the parsers and the identity rules against real records in CI
(rule #0: never a fabricated fixture), and so `build_identity.py --from-snapshot <this dir>`
reproduces the 2026-09-04 identity build offline. `SYMBOLOGY_DIR=<dir>` points the same tests
at fresher downloads. Refresh by re-fetching, never by editing.

| File | Source | Fetched (UTC) | sha256 |
|---|---|---|---|
| `nasdaqlisted.txt` | https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt | 11:06 | `13d854464760097ac020af1aa8bae4522ff7de8c6efb3be37ea6bbc9355927ae` |
| `otherlisted.txt` | https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt | 11:06 | `41a1d26968098c9ddc8ef7a6fada6f8a13948c5d4156948df4297f641ee3aa28` |
| `company_tickers.json` | https://www.sec.gov/files/company_tickers.json (fetched with a contact `User-Agent`, per SEC fair-access) | 11:06 | `f987a9fba01e1c1858ddcf0c032d77be301843860d7a0571efaa92ec3f938926` |
| `company_tickers_mf.json` | https://www.sec.gov/files/company_tickers_mf.json (contact `User-Agent`); columnar `fields`/`data`, 28,500 rows | 12:04 | `5e1d35e69f868300e59c2f8ad21a3612ce11be4256dbf1afab15384817c17fe3` |
| `supported_tickers.zip` | https://apimedia.tiingo.com/docs/tiingo/daily/supported_tickers.zip — Tiingo's public symbol list; the zip holds one `supported_tickers.csv` (108,553 rows, stamped 2026-09-04 06:05 by Tiingo; sha256 `c5f0106894ec8c14c7cbc2857f18940e75b94f27f65d158c7a37edc26cd908af`) | 12:07 | `9e90f691e261c153ea668a769d62a0f073f3f2f37a87374f8ff44f94468706d9` |
