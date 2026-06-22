# ATLAS v4 — DATA CATALOG (one environment: `foundation_staging`; raw/derived/ref/cfg)

**FM directives D22/D22a/D22b:** every table Atlas v4 needs lives in ONE environment
(`foundation_staging`); no reads from other environments (legacy `public.de_*` is cleared after);
classify + name tables by role — **raw feeds = `raw_*`** (mandatory), derived/ref/cfg naming optional
but recommended. This catalog is the source of truth. NEW + brought-in tables follow it immediately;
existing tables rename via backward-compat VIEWS in a sequenced pass AFTER the atom is locked (the
immutable `validate_lenses.py` + ~hundreds of refs point at current names — don't break the green atom).

**Scope note:** the v4 build uses ~30 real tables. The `atlas` schema also holds ~125 OTHER tables
(old/v6/strategy platform — mostly empty); `public` holds the `de_*` legacy + dozens of empty yearly
partitions. Those are OUT of v4 scope and are part of the environment-clearing, not this build.

## RAW — external feeds, ingested as-is (`raw_*`, mandatory)

| current | schema | ~rows | → proposed |
|---|---|---|---|
| ohlcv_stock | foundation_staging | 5.9M | raw_equity_ohlcv (incl. delivery_pct after loopD) |
| ohlcv_etf | foundation_staging | 319K | raw_etf_ohlcv |
| index_prices | foundation_staging | 603K | raw_index_prices |
| financials_quarterly | foundation_staging | 73K | raw_financials_quarterly |
| financials_annual | foundation_staging | 17K | raw_financials_annual |
| lens_filings | foundation_staging | 930K | raw_filings |
| lens_insider | foundation_staging | 39K | raw_insider |
| lens_shareholding | foundation_staging | 96K | raw_shareholding |
| lens_bulk_deals | foundation_staging | 156 | raw_bulk_deals |
| corp_action / corp_action_event | foundation_staging | 297 | raw_corp_actions |
| **de_mf_nav_daily** | public → bring in | ~2.6M | raw_mf_nav_daily |
| **de_mf_holdings** | public → bring in | 243K | raw_mf_holdings |
| **de_mf_master** | public → bring in | 1.4K | raw_mf_master |
| **de_etf_holdings** | public → bring in | 12K | raw_etf_holdings |
| **de_etf_ohlcv** | public → bring in | 441K | raw_etf_ohlcv (reconcile w/ foundation ohlcv_etf — keep one) |
| **de_etf_master** | public → bring in | 443 | raw_etf_master |
| **de_index_constituents** | public → bring in | 2.9K | raw_index_constituents |
| **de_index_master** | public → bring in | 135 | raw_index_master |
| **de_corporate_actions** | public → bring in | 11.5K | merge → raw_corp_actions |

## REF — masters / mappings (`ref_*`)

| current | schema | ~rows | → proposed |
|---|---|---|---|
| instrument_master | foundation_staging | 2.8K | ref_instrument_master |
| atlas_sector_master | atlas → bring in | 31 | ref_sector_master |
| de_sector_mapping | public (verify vs above) | 31 | (fold into ref_sector_master) |

## DERIVED — computed from raw (`derived_*`, optional naming)

| current | schema | ~rows | → proposed |
|---|---|---|---|
| technical_daily | foundation_staging | 7.0M | derived_technical_daily (ATR/BB/RS/vol/52w + delivery trend) |
| technical_stock | foundation_staging | 57K | derived_technical_stock |
| atlas_lens_scores_daily (THE ATOM) | atlas → bring in | 3.9M | derived_lens_scores_daily |
| atlas_signal_weights | atlas → bring in | 82 | derived_signal_weights |
| atlas_signal_ic | atlas → bring in | 30 | derived_signal_ic |
| (roll-ups, to build) | — | — | derived_sector_lens_daily, derived_etf_lens_daily, derived_index_lens_daily, derived_fund_lens_daily |
| (composite/conviction) | ON-READ (D19) — NOT a table | — | — |

## CFG — config / parameters (`cfg_*`)

| current | schema | ~rows | → proposed |
|---|---|---|---|
| atlas_thresholds (weights, lags, breakpoints) | atlas → bring in | 112 | cfg_thresholds |
| policy_registry | atlas → bring in | — | cfg_policy_registry |

## OPS — internal pipeline state (`ops_*`, optional)

backfill_state, compute_state, xbrl_state, screener_state, lens_*_state, ingest_run → `ops_*_state`.

## Migration method (non-breaking)

1. **Bring-in** (public.de_* / atlas.* → foundation_staging): `CREATE TABLE foundation_staging.<raw_name>
   AS SELECT * FROM <source>` (+ PKs/indexes), validate row-parity, repoint code.
2. **Rename existing in place**: `ALTER TABLE … RENAME TO <new>` + `CREATE VIEW <old> AS SELECT * FROM
   <new>` so old refs keep working; repoint code incrementally; drop the view when no refs remain.
3. **Immutable gate**: when `atlas_lens_scores_daily` is renamed/moved, update `validate_lenses.py`'s
   table constant in the SAME commit (a table move is not a logic change) + re-run --check A green.
4. Order: bring-in feeds first (free) → lock atom → sequenced renames → drop legacy `public.de_*` + the
   out-of-scope `atlas.*` sprawl (FM-approved, destructive, gated).
