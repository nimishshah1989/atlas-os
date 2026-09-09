# Global Atlas — taxonomy v1

**Status: DRAFT for FM review, 2026-09-07.** Seeded into `atlas_global.taxonomy_sector`,
`taxonomy_geo` and `taxonomy_role` by `scripts/global_market/seed_taxonomy.py`. Nothing
classifies anything until this is reviewed: the vocabulary here is the allowlist the LLM
layer is constrained to, so an omission is not a gap the model can route around — it is a
fund with nowhere to go.

## How this was derived, and why that matters

Every category below was counted against the **5,656 real active ETF names** in
`instrument_master`, not chosen from a mental model of what the US market contains. The same
discipline produced the leverage rule, where the words turned out to lie: "Ultra Short" is
bond duration everywhere except ProShares, "Ultra-Small" is a size band, and a rule matching
"short" anywhere gets the two ProShares VIX funds exactly backwards.

It mattered here too, and it overturned the plan's design.

**The plan built the taxonomy around sector, then sub-sector, then theme, with strategy as a
secondary attribute. The universe says the opposite.** Sector funds are a minority. Counted:

| what the fund IS | funds | share |
|---|---:|---:|
| fixed income | 902 | 15.9% |
| defined outcome and buffer | 545 | 9.6% |
| region | 535 | 9.5% |
| single stock (geared) | 461 | 8.2% |
| size and style | 458 | 8.1% |
| sector | 372 | 6.6% |
| thematic | 272 | 4.8% |
| options income | 256 | 4.5% |
| factor | 168 | 3.0% |
| country | 150 | 2.7% |
| crypto | 133 | 2.4% |
| commodity | 131 | 2.3% |
| dividend and income | 129 | 2.3% |
| broad market | 71 | 1.3% |
| alternative | 58 | 1.0% |
| multi-asset | 27 | 0.5% |
| currency | 20 | 0.4% |
| **unmatched, and therefore the LLM's job** | **968** | **17.1%** |

Buffer and defined-outcome products alone outnumber every sector fund. Under the schema's
original eight strategy values — `broad, factor, sector, thematic, country, commodity,
bond_duration, leveraged` — the 543 buffer funds, 394 single-stock funds, 188 options-income
funds, 114 crypto funds and 87 multi-asset funds had **no value at all** and would have been
filed as `broad`. That is how a taxonomy stops meaning anything.

So **strategy is the primary axis**, and the sector hierarchy applies to the 539 funds
(`sector` + `thematic`) for which it is the right question.

## 1. Strategy — the primary axis

Seventeen values, stored in `etf_classification.strategy`. Ordered by precedence: the rules
layer takes the first match, and the order below IS that precedence.

| id | what it means | why it is above the ones below it |
|---|---|---|
| `single_stock` | tracks ONE underlying company | 394 funds. Detected by finding a real active stock symbol in the name alongside explicit gearing, never by pattern alone |
| `defined_outcome` | buffer, target outcome, autocallable | The payoff shape is the product; what it references is secondary |
| `options_income` | covered call, buy-write, YieldMax, YieldBOOST | Same: the wrapper defines it |
| `crypto` | bitcoin, ether, digital assets | Named before `alternative` so a crypto fund is not merely "alternative" |
| `fixed_income` | every bond fund, by any credit type or maturity | Replaces the plan's `bond_duration`. Duration is one attribute of 873 funds that differ at least as much by credit type |
| `commodity` | metals, energy commodities, agriculture | |
| `currency` | FX exposure | |
| `multi_asset` | allocation, balanced, target date | |
| `alternative` | managed futures, merger arbitrage, market neutral, volatility | The residue of non-traditional strategies |
| `thematic` | narrower than a sector: AI, uranium, cybersecurity | Above `sector` because a robotics fund is thematic, not "industrials" |
| `sector` | a GICS sector | |
| `country` | a single country | Above `region` so a Japan fund is not "Asia" |
| `region` | international, emerging, developed, global, regional | |
| `dividend_income` | equity chosen for dividends | Below the wrappers above so a covered-call fund is not merely "income" |
| `factor` | quality, momentum, low volatility, equal weight, multifactor | |
| `size_style` | large, mid, small cap; growth and value tilts | |
| `broad_market` | whole-market and headline-index trackers | Last: it is the fallback for a fund with no narrower claim |

**Gearing is deliberately NOT a strategy.** `leveraged` and `inverse` are boolean columns
that already exist. A 2x bitcoin fund is `crypto` with `leveraged=true`, which says both what
it tracks and how it is built. The plan's `leveraged` strategy value said only the second and
threw the first away, so it is removed.

**Rules alone reach 82.9%** (4,688 of the 5,656 real ETF names), measured 2026-09-09 by
`atlas/global_market/classify/strategy.py` and asserted by `test_coverage_is_what_we_claim`.

The table above is now the classifier's own output, one row per fund through the ordered
first-match table, and is exact rather than approximate. Earlier versions of this document
carried figures from an unordered probe that counted a fund under whichever vocabulary was
tested first; that provenance is gone.

Coverage moved from 77.5% on 2026-09-07 by widening nine rule groups against every listed
name rather than by guessing: the market had listed vocabulary the rules had never seen —
Innovator's "Defined Protection", Roundhill's "WeeklyPay", the short end of the curve
("T-Bill", "Ultra Short"), coins listed since (Chainlink, Avalanche), and "Large-Cap" written
with a hyphen, which `large ?cap` had never matched. Widening also FIXED wrong answers: a
Treasury-bill fund was filed as a region fund because its issuer is "Global X", and a shipping
fund for the same reason.

Precision was measured, not assumed. Every change was diffed against all 5,656 names, and the
four false positives the first draft produced are now regression tests
(`test_the_widening_does_not_reintroduce_its_own_false_positives`): ProShares spells -2x as
"UltraShort", which is not a duration; "AI Enhanced Value" uses AI as a method, not a theme;
a stablecoin-technology fund holds equity, not coins; and a "Dividend Accelerator" is not a
structured accelerator.

The remaining 17.1% go to the LLM layer with a `review` status and a human confirmation step.
That split is the design working, not a shortfall: the rules layer exists for precision, not
recall, and coverage was deliberately not chased by widening patterns. Two decisions that cost
coverage on purpose:

- **A US-market fund is not a `country` fund.** Every S&P 500 tracker states "U.S.", so taking
  the word at face value would file the entire American core of the universe as
  "country: United States" and leave `broad_market` holding nothing. A US-listed fund's home
  market is the default, not a bet on it. **Open for the FM** — this is the fifth question.
- **`AI` and `FANG` are excluded from the single-stock symbol match.** Both are real tickers
  (C3.ai, Diamondback Energy) and in every one of the 5,655 names measured, both were the
  theme or basket acronym instead. A genuine single-stock fund on either is a known miss here
  and is answered by holdings, never by widening the pattern.

## 2. Sector — the hierarchy, for the 539 funds it fits

**Level 1 is GICS 11**, unchanged, because it is the standard the SPY holdings workbook
already labels your stocks with, so ETF sectors and stock sectors agree by construction.
Measured fund counts, first-claim:

| id | GICS | funds |
|---|---|---:|
| `information_technology` | 45 | 190 |
| `energy` | 10 | 104 |
| `financials` | 40 | 83 |
| `utilities` | 55 | 80 |
| `real_estate` | 60 | 65 |
| `health_care` | 35 | 61 |
| `industrials` | 20 | 60 |
| `materials` | 15 | 58 |
| `consumer_discretionary` | 25 | 30 |
| `consumer_staples` | 30 | 23 |
| `communication_services` | 50 | 11 |

**Level 2 is sub-sector**, and it is where the nuance the FM asked for actually lives. The
plan named four examples and they all survive contact with the data: `energy_renewable_solar`,
`energy_midstream_transmission`, `energy_nuclear_uranium`, `utilities_grid`. Sub-sectors are
seeded only where funds exist to fill them; an empty sub-sector is a category nobody can use.

**Level 3 is theme**, and here is a caution worth the FM's attention. Themes are small:

| theme | funds | | theme | funds |
|---|---:|---|---|---:|
| `ai` | 64 | | `nuclear_uranium` | 12 |
| `infrastructure` | 51 | | `clean_energy` | 10 |
| `space_defence` | 37 | | `quantum` | 8 |
| `semiconductors` | 34 | | `cloud` | 6 |
| `genomics` | 21 | | `fintech` | 6 |
| `cybersecurity` | 16 | | `water` | 6 |
| `robotics` | 14 | | `gaming_esports` | 6 |
| `ev_battery` | 13 | | `cannabis` | 4 |

`peer_group_min_members` is 8. **Nine of these sixteen themes cannot form their own peer
group**, so a fund scored within its theme would be ranked against too few competitors to
mean anything, and the scorer falls back to the parent sector. That is the correct behaviour
and it is worth knowing before anyone reads a theme decile as a real ranking.

## 3. Geography

`taxonomy_geo` holds three kinds. `country` rows carry an ISO-3166 alpha-2 code and reference
`atlas_global.country`; `region` rows are roll-ups; `global` is the single catch-all.

Regions: `north_america`, `europe`, `developed_europe`, `asia_pacific`, `asia_ex_japan`,
`latin_america`, `middle_east_africa`, `emerging_markets`, `developed_markets`,
`frontier_markets`, `world_ex_us`.

**The country reference table is seeded with ISO-3166 codes and names only.** `region` and
`msci_class` are left NULL on purpose. MSCI's developed/emerging/frontier classification is
proprietary and inventing it would be exactly the derived number rule #0 forbids. There is a
clean way to obtain it from real data and it arrives with holdings: **the constituents of
MSCI's own index ETFs state which countries MSCI puts in which bucket.** Until that runs, the
column stays honest and empty.

## 4. Role

Fixed by the schema's CHECK, four values: `pure_play`, `picks_and_shovels`, `diversified`,
`not_applicable`. This is the axis the FM named as the interesting one, and it is the hardest
to do from names alone — deciding whether a semiconductor-equipment fund is a pure play on
chips or the picks-and-shovels of AI is a holdings question, and a judgement. It is therefore
an LLM field with human confirmation, never a rules field, and `not_applicable` is the honest
answer for every fund that is not an equity sector or theme bet.

## Open for the FM

1. **Is `dividend_income` a strategy or a factor?** It is 308 funds, which is too many to
   bury inside `factor`, so it is its own value here. Say if you disagree.
2. **`size_style` merges size and style.** A "large cap growth" fund is one fund, not two
   labels, and the schema has one strategy column. If you want them separated, that is a new
   column rather than more strategy values.
3. **Themes below the peer-group minimum.** Seed them anyway for browsing and filtering, or
   only seed the seven with enough funds to score? Recommendation: seed all sixteen, and let
   the scorer fall back to the parent sector, so the board can still show a theme page.
4. **The 150-label eval set.** Still yours to produce, and it is what gates automatic
   confirmation. Stratify by strategy using the table in section 1 rather than by issuer.
5. **Is a plain US equity fund `broad_market` or `country`?** The classifier says
   `broad_market` (or `size_style`), for the reason in section 1. If you want US treated as a
   country like any other, say so — it is a one-line change, and it moves roughly a third of
   the universe.
