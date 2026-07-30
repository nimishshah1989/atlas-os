# 0004 — Coverage universe widened to 750, and every ETF gets a sector

- **Status:** Accepted (2026-07-30)
- **Context chunk:** Monday confirmations (see `0003-monday-confirmations-book-state.md`)

## Context

Seeding the FM's three real model portfolios into the new Monday-confirmations tool
exposed two data gaps that made the desk's own book unrepresentable in Atlas.

**1. Two holdings were invisible.** `JSFB` (Jana Small Finance Bank) and `LLOYDSENGG`
(Lloyds Engineering Works) sit in the Multi Asset Alpha book at 8% each, but both had
`instrument_master.is_active = false`, so the instrument autocomplete would not offer
them. They were not stale rows — both had OHLCV bars through 2026-07-29. Per
`build_universe.py`, `is_active` for a stock means *"in Atlas coverage"*, and coverage
was the **Nifty 500** (FM decision, 2026-06-25). Both names are Nifty Microcap 250
constituents, i.e. correctly outside the 500 and correctly excluded by the old rule.

The rule itself was the problem: a coverage universe that cannot express the book the
desk actually runs is the wrong universe.

**2. No ETF had a sector.** All 318 active ETFs carried `sector IS NULL`, and
`de_etf_master` covered only 43. The Passive book is *entirely* ETFs, so its sector pie
would have rendered 100% "Unmapped"; Alpha's would have been 43% unmapped.

## Decision 1 — coverage is NIFTY 500 ∪ NIFTY MICROCAP250 = 750

Exactly NSE's Nifty Total Market construction. The two indices are disjoint (verified:
0 overlap), so the union is exactly 750; 747 of those have a `stock` row in
`instrument_master` (3 index constituents have no matching row — a pre-existing gap,
noted not fixed).

*Rejected:* adding a `scope=tradeable` parameter to `/api/instruments/search` so the
confirmations grid could bypass `is_active`. That treats the symptom — it would let the
FM buy a name that no lens scores, no sector card covers and no gate checks, producing a
book Atlas can display but not analyse. Widening coverage fixes it once, for every
surface.

Verified after the change: 747 active stocks, **0** missing a sector, **21** distinct
sectors, **0** non-canonical — both data-integrity gates still pass, because all 249
incoming names already carried canonical sectors. 242 of 249 have a `kite_token`; 220
have ≥300 bars, so a handful of the newest listings will produce NULL long-window lens
values until they have history. That is the normal new-listing path, not a regression.

## Decision 2 — ETF sector vocabulary is the canonical 21 plus exactly five asset classes

`scripts/foundation/etf_sector.py` derives a sector from the ETF's name, because the
underlying index is encoded there ("ICICI PRUDENTIAL NIFTY AUTO ETF"). An ETF tracking a
sector index gets one of the 21 canonical `atlas_sector_master` names, so it shares a pie
slice with stocks in that sector. The ~75% with no equity sector get one of exactly five
asset-class labels: **Gold, Silver, Debt, Broad Index, International** (FM, 2026-07-30).

Result over the 318: 17 canonical labels covering 81 ETFs (Banking 26, IT 10, FMCG 7,
Healthcare 6, Automobile 5, …) and 5 asset-class labels covering 237 (Broad Index 149,
Debt 36, Gold 27, Silver 19, International 6). Zero NULL.

*Rejected — force all 318 into the 21.* There is no truthful mapping: labelling a gold
ETF "Metal" implies equity beta it does not have, and labelling a Nifty 50 ETF by its
largest constituent misstates a diversified holding. In a document that allocates
capital, an honest asset-class label beats a forced sector.

*Rejected — use `de_etf_master.sector`.* It covers 42 of 318 and supplies synonyms for
names we already have canonically ("Banking & Financial" for Banking, "Consumption" for
FMCG) plus a useless "Sectoral" — precisely the inconsistency this removes. Comparing all
42 against the derivation showed 21 disagreements, 19 of which the derivation won. The
two it lost became rules: `NYSE FANG+` → International, and "NIFTY FINANCIAL SERVICES
EX-BANK" → Financial Services (the literal string "BANK" inside the name had been
hijacking it). So one vocabulary, derived, loses nothing.

The five asset-class labels are deliberately **not** added to `atlas_sector_master`: the
canonical-21 gate is scoped to `asset_class='stock'` (`assign_sectors.py`), so ETF labels
never widen the stock vocabulary. `backfill()` fails loudly if a label appears that is
neither canonical nor one of the five.

## Consequences

- The nightly `build_universe.py` now maintains the 750 set; the one-time flip was applied
  directly (498 → 747 active, 0 deactivated) because the coverage set derives purely from
  `de_index_constituents`, needing no Kite session.
- `etf_sector.backfill()` is idempotent and must re-run after any ETF listing sync,
  otherwise new ETFs sit at NULL. It is not yet wired into `atlas_daily.sh`.
- Lens/score surfaces now compute over 747 names rather than 498 — roughly a 50% larger
  scored universe, so expect the nightly compute window to lengthen.
- A fund-house name can collide with a sector pattern ("BAJAJ FINSERV NIFTY BANK ETF"
  tracks Nifty Bank, not financial services); `_AMC_NOISE` strips those before matching.
