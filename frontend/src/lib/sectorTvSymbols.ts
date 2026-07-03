// frontend/src/lib/sectorTvSymbols.ts
//
// Sector → TradingView RATIO symbol (sector index / Nifty 50) for the RS ratio
// charts on the sector detail page.
//
// Base is bare "NIFTY" (TradingView's Nifty 50), matching the fund manager's
// "Ratio charts" watchlist. Ratio form: "<numerator>/NIFTY".
//
// Numerators below come from that watchlist where available (marked ✓). The
// remaining sectors are derived from atlas_sector_master.primary_nse_index using
// TradingView's underscore convention (NIFTY <NAME> → NIFTY_<NAME>) and are
// marked (derived) — these should be confirmed against TradingView; an
// unresolved symbol shows TradingView's own "Invalid symbol" state.
//
// Keys are EXACT sector_name strings from atlas_sector_master.

export const NIFTY_TV = 'NIFTY'

// Per-sector TradingView index symbol (numerator of the ratio).
const SECTOR_TV_INDEX: Record<string, string> = {
  // ── From the fund manager's watchlist (authoritative) ──
  Automobile: 'CNXAUTO',                 // ✓
  Banking: 'BANKNIFTY',                  // ✓
  'Capital Goods': 'NIFTY_INDIA_MFG',    // ✓
  Chemicals: 'NIFTY_CHEMICALS',          // ✓
  Defence: 'NIFTY_IND_DEFENCE',          // ✓
  Energy: 'CNXENERGY',                   // ✓
  FMCG: 'CNXFMCG',                       // ✓
  Infrastructure: 'CNXINFRA',            // ✓
  Media: 'CNXMEDIA',                     // ✓
  Metal: 'CNXMETAL',                     // ✓
  'Oil & Gas': 'NIFTY_OIL_AND_GAS',      // ✓
  Pharma: 'CNXPHARMA',                   // ✓
  Realty: 'CNXREALTY',                   // ✓

  // ── Standard TradingView classic symbol (not in watchlist, high confidence) ──
  IT: 'CNXIT',

  // ── Derived from primary_nse_index (verify against TradingView) ──
  // All verified to resolve via TradingView symbol search (NSE).
  'Capital Markets': 'NIFTY_CAPITAL_MKT',
  'Consumer Durables': 'NIFTY_CONSR_DURBL',
  Consumption: 'CNXCONSUMPTION',
  Digital: 'NIFTY_IND_DIGITAL',
  'EV & Auto': 'NIFTY_EV',
  'Financial Services': 'CNXFINANCE',
  Healthcare: 'NIFTY_HEALTHCARE',
  Housing: 'NIFTY_HOUSING',
  Logistics: 'NIFTY_TRANS_LOGIS',
  MNC: 'CNXMNC',
  Power: 'CNXENERGY',                         // Power maps to NIFTY ENERGY
  Rural: 'NIFTY_RURAL',
  Services: 'CNXSERVICE',
  Telecom: 'NIFTY_MS_IT_TELCM',
  Tourism: 'NIFTY_IND_TOURISM',
  // Diversified intentionally omitted — it benchmarks to Nifty 500, no single
  // sector index makes sense as a ratio numerator.
}

/**
 * Full TradingView ratio symbol for a sector (sector index / Nifty 50), or null
 * when the sector has no mapped TradingView index symbol.
 */
export function sectorRatioSymbol(sectorName: string): string | null {
  const idx = SECTOR_TV_INDEX[sectorName]
  return idx ? `${idx}/${NIFTY_TV}` : null
}
