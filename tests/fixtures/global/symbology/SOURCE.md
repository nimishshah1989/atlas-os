# Identity directories — real files, dated snapshot

Verbatim copies of the three public identity files the symbology parsers read, fetched on
**2026-09-04 11:06 UTC** (both Nasdaq files carry `File Creation Time: 0904202607:00`).
They exist so `tests/unit/global_market/test_symbology.py` runs the parsers against real
records in CI (rule #0: never a fabricated fixture); `SYMBOLOGY_DIR=<dir>` points the same
tests at fresher downloads. Refresh by re-fetching, never by editing.

| File | Source | sha256 |
|---|---|---|
| `nasdaqlisted.txt` | https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt | `13d854464760097ac020af1aa8bae4522ff7de8c6efb3be37ea6bbc9355927ae` |
| `otherlisted.txt` | https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt | `41a1d26968098c9ddc8ef7a6fada6f8a13948c5d4156948df4297f641ee3aa28` |
| `company_tickers.json` | https://www.sec.gov/files/company_tickers.json (fetched with a contact `User-Agent`, per SEC fair-access) | `f987a9fba01e1c1858ddcf0c032d77be301843860d7a0571efaa92ec3f938926` |
