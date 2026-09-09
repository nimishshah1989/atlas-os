# SEC submissions payloads — provenance

Three verbatim downloads of `https://data.sec.gov/submissions/CIK##########.json`, gzipped with
`gzip -9` and otherwise unmodified. Fetched **2026-09-09** with the `User-Agent` the SEC's fair-access
policy requires. They are public filing metadata: form types, dates, accession numbers and 8-K item
codes. No key, no position, no client data.

| Fixture | Filer | CIK | Rows in `filings.recent` | 8-K rows | `recent` covers | sha256 of the decompressed JSON |
|---|---|---|---|---|---|---|
| `submissions_AAPL.json.gz` | Apple Inc. | 0000320193 | 1,000 | 105 | 2015-07-22 → 2026-09-03 | `7c67278a0c4009db2cfd62ac23fbdb16d935867ad44fdfde9eaef77837386440` |
| `submissions_JPM.json.gz` | JPMORGAN CHASE & CO | 0000019617 | 25,985 | 26 | 2025-09-09 → 2026-09-09 | `05ffe3a2c86e92ca2fc7b7cb0e33a97637f723d3c78142fa127adb0a068aa500` |
| `submissions_VZ.json.gz` | VERIZON COMMUNICATIONS INC | 0000732712 | 1,001 | 58 | 2023-11-22 → 2026-09-08 | `37bf968f45ac2ef748eb452b8c823483fbd3b803e8a015cb6c72cda68e85e3ba` |

The same three filers as `tests/fixtures/global/edgar/`, deliberately: the fundamental lens and the
catalyst lens are then tested on the same companies, so a claim about one can be checked against the
other.

## What these were kept for

**The `items` field is real, and it is the whole reason the catalyst lens reads item codes.** Every
8-K row carries its SEC item codes as a comma-separated string — `"2.02,9.01"` on Apple's results
filings, `"5.02"` on a director change. That is the registrant's own classification of what the
filing is, asserted on the form. It removes any need to keyword-match press-release prose.

**Most 8-K traffic carries no scoreable item.** Across these three filers:

| Item | Apple | JPMorgan | Verizon | What it is |
|---|---|---|---|---|
| 9.01 | 82 | 20 | 35 | Financial Statements and Exhibits — boilerplate on almost any filing with a press release |
| 8.01 | 25 | 9 | 17 | Other Events — says only that something happened |
| 2.02 | 45 | 4 | 11 | Results of Operations *(scored)* |
| 5.02 | 18 | 3 | 16 | Departure/Election of Directors or Officers *(scored)* |
| 7.01 | 4 | 6 | 13 | Regulation FD Disclosure |
| 5.07 | 11 | 1 | 3 | Submission of Matters to a Vote |
| 5.03 | 6 | 4 | 1 | Amendments to Articles/Bylaws |
| 3.03 | — | 1 | — | Material Modification to Rights *(scored)* |
| 1.01 | — | — | 1 | Entry into a Material Definitive Agreement *(scored)* |

The lens is silent about 9.01, 8.01, 7.01, 5.07 and 5.03 on purpose — none can be read without
parsing the attached prose — and it reports that silence in its own evidence rather than letting it
pass as "nothing happened".

## The operational finding JPMorgan carries

`filings.recent` is capped at roughly **1,000 filings by COUNT, not by time**. Apple files little
besides its own reports, so its 1,000 rows reach back to 2015. JPMorgan files prospectuses and
424B supplements continuously — 25,985 rows — and its `recent` window therefore covers exactly
**2025-09-09 → 2026-09-09**, one year.

The catalyst lens looks back `catalyst_recency_t3` days (seeded at 365). For a filer like JPMorgan
that is *only just* covered, and a heavier filer would be short. So the ingest must compare what
`recent` actually covers against the lookback it needs and say when it falls short, rather than
scoring a company on a window that quietly got smaller. `Submissions.covers` and
`Submissions.older_batches` exist for exactly that check: 70 additional batches of older filings
sit in `filings.files` for JPMorgan and this parser deliberately does not fetch them.
