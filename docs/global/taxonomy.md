# Global Atlas — taxonomy v1

**Status: DRAFT for FM review. Strategy and sector 2026-09-07; the theme layer rebuilt
2026-09-09 against the FM's brief — see section 2, "Level 3 is theme".** Seeded into `atlas_global.taxonomy_sector`,
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
| fixed income | 937 | 16.6% |
| defined outcome and buffer | 545 | 9.6% |
| region | 535 | 9.5% |
| single stock (geared) | 461 | 8.2% |
| size and style | 458 | 8.1% |
| sector | 371 | 6.6% |
| thematic | 272 | 4.8% |
| options income | 257 | 4.5% |
| factor | 171 | 3.0% |
| country | 150 | 2.7% |
| crypto | 133 | 2.4% |
| commodity | 131 | 2.3% |
| dividend and income | 129 | 2.3% |
| broad market | 71 | 1.3% |
| alternative | 58 | 1.0% |
| multi-asset | 28 | 0.5% |
| currency | 20 | 0.4% |
| **unmatched, and therefore the LLM's job** | **929** | **16.4%** |

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

**Rules alone reach 83.6%** (4,727 of the 5,656 real ETF names), measured 2026-09-09 by
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

A second pass took it to 83.6%, and its two REJECTED terms are the more useful record.
"Hedged equity" reads as an options overlay at Fidelity and as CURRENCY hedging at WisdomTree,
so adding it filed seven well-known hedged country funds as options income; the term is out,
and the currency case stays where it already was, on `is_currency_hedged`. "High yield" alone
is a junk-bond fund, but "High Yield Equity Dividend Achievers" is not, so the term refuses to
match before equity, dividend or stock. Both are regression tests
(`test_the_terms_that_were_tried_and_rejected_stay_out`), because both look obviously right
until they are run over all 5,656 names.

The remaining 16.4% go to the LLM layer with a `review` status and a human confirmation step.
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

**Level 3 is theme**, and this is the layer the FM sent back. v1 seeded sixteen theme rows
and nothing assigned one: `strategy.py` marked 272 funds `thematic` and stopped, so an AI
fund, a uranium fund and a water fund all sat in one undifferentiated bucket. The FM's words:

> "If there is something like an ETF which is focused on AI, then creating that artificial
> intelligence… it's not just energy, it's energy sources… We want to create funds around,
> let's just say, gold and silver miners. We want to create funds around water and food
> security. That's the kind of categorization I was looking for."

**There is now a rule table that assigns one.** `atlas/global_market/classify/themes.py` is an
ordered first-match table over the fund's name, run beside the strategy table rather than
under it: a gold-bullion trust is `commodity` by strategy and `precious_metals` by theme; a
uranium fund is `thematic` by strategy and `nuclear_uranium` by theme. `classify_etfs.py`
writes the verdict into `etf_classification.theme_ids` with the rule and the matched words in
`evidence`, so every label is explainable and reviewable.

**32 themes, and the counts are the classifier's own first-claim output** over the 5,655 real
listed ETF names in the committed 2026-09-04 directory snapshot — a fund is counted once,
under the first rule that reads it, so "VanEck Gold Miners" is one `gold_silver_miners` fund
and not a gold fund as well:

| theme | funds | | theme | funds | | theme | funds |
|---|---:|---|---|---:|---|---|---:|
| `precious_metals` | 53 | | `nuclear_uranium` | 16 | | `cloud` | 6 |
| `ai` | 43 | | `space` | 14 | | `genomics` | 6 |
| `infrastructure` | 37 | | `copper` | 12 | | `water` | 6 |
| `semiconductors` | 28 | | `clean_energy` | 12 | | `cannabis` | 5 |
| `gold_silver_miners` | 27 | | `critical_minerals` | 12 | | `fintech` | 5 |
| `defence` | 24 | | `gaming_esports` | 11 | | `lithium` | 5 |
| `reits` | 22 | | `cybersecurity` | 10 | | `shipping` | 4 |
| `robotics` | 16 | | `food_agriculture` | 10 | | `homebuilders` | 3 |
| | | | `blockchain` | 9 | | `data_centres` | 2 |
| | | | `ev_battery` | 7 | | `longevity` | 2 |
| | | | `grid_electrification` | 7 | | `timber_forestry` | 2 |
| | | | `quantum` | 7 | | `solar` | 1 |

**424 of the 5,655 names (7.5%) settle a theme from their words.** That is the whole point of
the layer being rules-first: the 7.5% are decided tonight, for free and auditably, and the
LLM's job shrinks to the funds the words do not settle. A fund with no theme is NOT sent to
review — an empty `theme_ids` is an answer, not a gap, and a Treasury ladder is not an
unclassified theme.

**What the ordering decides.** 56 names match two or more rules, and one principle sets the
order: **the input beats the trend.** A fund that names a physical thing it holds — a metal, a
fuel, a machine — is a fund about that thing; the trend it is sold on is the story, and the
stories are the widest rules at the bottom. So:

| fund | theme | over | because |
|---|---|---|---|
| VanEck Gold Miners | `gold_silver_miners` | `precious_metals` | miners are equity levered to the metal, not the metal — the FM's own example |
| Global X Lithium & Battery Tech | `lithium` | `ev_battery` | the metal is what it is priced off |
| Clean Edge Smart Grid Infrastructure | `grid_electrification` | `clean_energy`, `infrastructure` | the grid is what it holds |
| Global X AI Semiconductor & Quantum | `semiconductors` | `ai`, `quantum` | it is a chip fund |
| Global X Robotics & AI | `robotics` | `ai` | robots are the physical thing |
| ARK Space & Defense Innovation | `space` | `defence` | the narrower mandate, and ARKX is the market's space fund |
| Nicholas Defense and Rare Earth Income | `critical_minerals` | `defence` | **the case where the order costs something** — both labels are true; say the word and it moves |

`ai` is deliberately LAST in the technology group. Half of these funds name AI in passing, and
a theme that absorbs every fund saying "AI" is the undifferentiated bucket you rejected.

**Six phrases in this market mean something else**, each measured over all 5,655 names after
producing a wrong answer: "Blue Chip" is not a semiconductor (6 funds); "Infrastructure
Capital" (4), "CYBER HORNET" (4) and "Ai Funds" (1) are ISSUERS, not assets — one of the
InfraCap funds is a bond fund; "Grayscale Bitcoin **Mini** Trust" is not a bitcoin miner;
"LifeX … Longevity Income" is an annuity ladder, not a bet on ageing (8 funds, against only
two real ageing funds); and "AI Enhanced / Managed / Powered" is AI as the METHOD (11 funds).
Every one is a regression test in `tests/unit/global_market/test_themes.py`.

**Twenty-one plausible terms were written and then deleted** because no issuer uses them —
`photovoltaic`, `atomic`, `military`, `homeland security`, `marijuana`, `maritime`,
`fertilizer`, `gene editing`, `financial technology` and twelve more. Vocabulary that matches
nothing cannot be reviewed or tested, and it hides how small the theme it was meant to widen
really is. `test_no_rule_is_dead` holds the line.

**Themes are small, and `peer_group_min_members` is 8.** Fifteen of the 32 cannot form their
own peer group, so a fund scored within its theme would be ranked against too few competitors
to mean anything and the scorer falls back to the parent sector. That is the correct behaviour
and it is worth knowing before anyone reads a theme decile as a real ranking. `solar` is the
extreme case — **the market has listed exactly one solar ETF** (Invesco's TAN) — and it is
seeded anyway because you named solar as an energy source: a theme page reading "1 fund" is a
truer answer than folding it into `clean_energy` and losing the question.

**What changed from v1.** Fifteen of the sixteen v1 theme ids survive. `space_defence` is the
one that does not: it is split into `space` (14) and `defence` (24), two mandates that share a
supply chain and each clear the peer-group minimum alone. Seventeen themes are new, and they are
mostly your brief made executable — the five metals (`precious_metals`, `gold_silver_miners`,
`copper`, `lithium`, `critical_minerals`), the two energy sources v1 lacked (`solar`,
`grid_electrification`), `food_agriculture`, and the rest read off the market
(`blockchain`, `reits`, `shipping`, `homebuilders`, `timber_forestry`, `data_centres`,
`longevity`). The taxonomy version stays 1: v1 was never FM-reviewed, so this replaces it
rather than succeeding it.

**Three known gaps, stated rather than patched.** (1) Eight MLP and energy-pipeline funds land
in `infrastructure` because "Energy Infrastructure" is what their names say; a
`midstream_pipelines` theme is the obvious next row if you want them separated. (2) Four
generic metals-and-mining funds (XME, PICK, METL, DBB) reach no theme, because "Metals &
Mining" is the `materials` sector rather than a theme. (3) `reits`, `homebuilders`
and `shipping` overlap sub-sectors that already exist at level 2; they are themes today only
because the rules layer fills `theme_ids` and not `sub_sector_id`, and they should fold into
the sub-sector when the LLM layer starts filling it. See open question 6.

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
   only seed the seventeen with enough funds to score? Recommendation: seed all 32, and let
   the scorer fall back to the parent sector, so the board can still show a theme page — a
   `solar` page reading "1 fund" answers your question honestly; deleting the theme does not.
4. **The 150-label eval set.** Still yours to produce, and it is what gates automatic
   confirmation. Stratify by strategy using the table in section 1 rather than by issuer.
5. **Is a plain US equity fund `broad_market` or `country`?** The classifier says
   `broad_market` (or `size_style`), for the reason in section 1. If you want US treated as a
   country like any other, say so — it is a one-line change, and it moves roughly a third of
   the universe.
6. **`reits` (22), `homebuilders` (3) and `shipping` (4) are themes that repeat a level-2
   sub-sector.** They are here because the rules layer fills `theme_ids` and nothing yet fills
   `sub_sector_id`, so today the theme is the only grouping those funds get. Fold them into
   the sub-sector once the LLM layer runs, or keep them as themes so the board's theme filter
   covers them? Recommendation: keep for now, revisit at the LLM cut-over.
7. **One theme per fund, or up to three?** The column takes three; an ordered first-match rule
   table produces exactly one, because a second would have to be guessed rather than read.
   `Nicholas Defense and Rare Earth Income` is the fund that shows the cost — it is genuinely
   both. If you want multi-theme funds, that is an LLM field, not a rules field.
