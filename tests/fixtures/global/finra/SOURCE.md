# FINRA consolidated short interest — provenance

Three verbatim API responses from
`https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest`, gzipped with `gzip -9`
and otherwise unmodified. Fetched **2026-09-09** by POST with a JSON body filtering on `symbolCode`.
Public market data, no key required, no client data.

| Fixture | Rows | Settlement dates covered | sha256 of the decompressed JSON |
|---|---|---|---|
| `short_interest_AAPL.json.gz` | 208 | 2017-12-29 → 2026-08-14 | `748f8fd18fc2e22cb3b56b919dd946b155e07dff8061a28f2ec1929185f67846` |
| `short_interest_JPM.json.gz` | 208 | 2017-12-29 → 2026-08-14 | `c9b1ba10c837a0c123b3da3ad458824eb265e06f4b33f48b4e69fd8402322ef6` |
| `short_interest_VZ.json.gz` | 208 | 2017-12-29 → 2026-08-14 | `faf016172b5abedf099706debb9f423e04401ad3f518d7495dd4319564ca5613` |

The same three companies as the `edgar/`, `submissions/` and `form4/` fixtures, so a claim made by
one lens about a name can be checked against the others.

## Why the flow lens is built on this feed

`plan.md` §B orders the flow lens "Form 4 first, add 13F and short interest after IC ≥ floor". The
census in `../form4/SOURCE.md` measured what that would give: across the eighteen most recent Form 4s
from these same three companies there is **not one open-market purchase**, and **every** sale was made
under a 10b5-1 plan adopted months earlier. Both halves of the insider signal are mechanical for
large-cap US issuers.

Short interest is the opposite on every axis that matters:

| | Form 4 (measured) | Short interest (measured) |
|---|---|---|
| Coverage | sparse and one-sided | every listed name, twice a month |
| Depth | — | **208 settlements per name, back to 2017** |
| Discretionary content | none in this sample | the position itself |
| Cost | one request per filing | one request per settlement date |
| Can the lens be IC-tested? | no — too few observations | yes — nine years of them |

So short interest goes first. Form 4 is still worth adding as a sparse, high-value **overlay** — a
code-`P` purchase is a strong signal precisely because it is rare — but not as the whole lens.

## What the API demands, and two things that cost time to learn

* The dataset is **partitioned by `settlementDate`**. A sorted query is rejected outright unless
  every partition key is pinned with an `EQUAL` compare filter, so the natural access pattern is one
  settlement date at a time (or one symbol across all of them, which is what these fixtures are).
* Filters must go in a **POST body**. Passing the same JSON in the query string fails: it has to be
  URL-encoded, and unencoded it is rejected as a malformed request.

## What 624 real readings actually reach

Scoring every reading in these three fixtures against the seeded ladder:

| Days-to-cover rung | Count | | Change rung | Count |
|---|---|---|---|---|
| low (≤ 2 days) | 310 | | covering, big (≤ −20%) | 11 |
| ok (≤ 4) | 290 | | covering, moderate | 113 |
| high (≤ 8) | 24 | | flat | 369 |
| **extreme (> 8)** | **0** | | building, moderate | 109 |
| | | | building, big (≥ +20%) | 22 |

Three healthy megacaps are never crowded shorts, so the extreme rung is never exercised here. It is
asserted to exist and to be the harshest penalty; whether it is the right *size* is a question only a
heavily shorted name can answer, and the tests say so rather than implying otherwise.

## What this feed cannot give, and what is used instead

Short interest as a percent of **float** is the measure everyone quotes, and it is not computable
here: nothing in `atlas_global` carries a float, and inferring one from shares outstanding less
insider holdings would be a derived number wearing a real one's clothes (rule #0). FINRA publishes
`daysToCoverQuantity` — the short position divided by average daily volume — and `changePercent`
itself, so both sub-scores stand on figures FINRA computed, not on arithmetic invented here.
