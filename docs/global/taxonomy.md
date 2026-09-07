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
| fixed income | 873 | 15.4% |
| defined outcome and buffer | 543 | 9.6% |
| region | 515 | 9.1% |
| size and style | 405 | 7.2% |
| single stock (geared) | 394 | 7.0% |
| sector | 352 | 6.2% |
| dividend and income | 308 | 5.4% |
| options income | 188 | 3.3% |
| thematic | 187 | 3.3% |
| country | 164 | 2.9% |
| factor | 159 | 2.8% |
| commodity | 159 | 2.8% |
| crypto | 114 | 2.0% |
| broad market | 94 | 1.7% |
| multi-asset | 87 | 1.5% |
| alternative | 82 | 1.4% |
| currency | 20 | 0.4% |
| **unmatched, and therefore the LLM's job** | **1,012** | **17.9%** |

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

**Rules alone reach 82.1%.** The remaining 17.9% go to the LLM layer with a `review` status
and a human confirmation step. That split is the design working, not a shortfall: the rules
layer exists for precision, not recall.

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
