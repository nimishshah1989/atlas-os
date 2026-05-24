// src/lib/queries/instruments.ts
// Read-only SELECT helpers for the InstrumentPicker component.
// Returns limited result sets suitable for the picker UI.
// NUMERIC columns kept as string — parse at display time.
import 'server-only'
import sql from '@/lib/db'

export type StockPickerRow = {
  instrument_id: string
  symbol: string
  company_name: string | null
  tier: string
  sector: string
  // Latest state from atlas_stock_metrics_daily (may be null if no metrics)
  rs_state: string | null
  effective_to: Date | null
}

export type ETFPickerRow = {
  ticker: string
  etf_name: string | null
  fund_house: string | null
  theme: string
  linked_sector: string | null
  asset_class: string | null
  effective_to: Date | null
}

export type FundPickerRow = {
  mstar_id: string
  scheme_name: string
  amc: string | null
  broad_category: string
  category_name: string
  effective_to: Date | null
}

export type StockFilters = {
  tier?: string | null
  sector?: string | null
  rs_state?: string | null
  search?: string | null
}

export type ETFFilters = {
  theme?: string | null
  linked_sector?: string | null
  search?: string | null
}

export type FundFilters = {
  category_name?: string | null
  broad_category?: string | null
  search?: string | null
}

/**
 * Stocks for the InstrumentPicker — current universe only (effective_to IS NULL).
 * Joined with latest daily metrics for rs_state.
 * Default: all current stocks, limited to 100 rows.
 * Filters: tier, sector, rs_state, search (ILIKE on symbol or company_name).
 */
export async function getStocksForPicker(
  filters: StockFilters = {},
): Promise<StockPickerRow[]> {
  const tier = filters.tier ?? null
  const sector = filters.sector ?? null
  const rsState = filters.rs_state ?? null
  const search = filters.search ? `%${filters.search}%` : null

  return sql<StockPickerRow[]>`
    -- Phase 7: rs_state from atlas_stock_signal_unified instead of atlas_stock_states_daily.
    SELECT
      s.instrument_id,
      s.symbol,
      s.company_name,
      s.tier,
      s.sector,
      st.rs_state,
      s.effective_to
    FROM atlas.atlas_universe_stocks s
    LEFT JOIN LATERAL (
      SELECT rs_state
      FROM atlas.atlas_stock_signal_unified
      WHERE instrument_id = s.instrument_id
      ORDER BY date DESC
      LIMIT 1
    ) st ON TRUE
    WHERE s.effective_to IS NULL
      AND (${tier}::text IS NULL OR s.tier = ${tier}::text)
      AND (${sector}::text IS NULL OR s.sector = ${sector}::text)
      AND (${rsState}::text IS NULL OR st.rs_state = ${rsState}::text)
      AND (
        ${search}::text IS NULL
        OR s.symbol ILIKE ${search}::text
        OR s.company_name ILIKE ${search}::text
      )
    ORDER BY s.tier, s.symbol
    LIMIT 100
  `
}

/**
 * ETFs for the InstrumentPicker — current universe only (effective_to IS NULL).
 * Filters: theme, linked_sector, search (ILIKE on ticker or etf_name).
 */
export async function getETFsForPicker(
  filters: ETFFilters = {},
): Promise<ETFPickerRow[]> {
  const theme = filters.theme ?? null
  const linkedSector = filters.linked_sector ?? null
  const search = filters.search ? `%${filters.search}%` : null

  return sql<ETFPickerRow[]>`
    SELECT
      ticker,
      etf_name,
      fund_house,
      theme,
      linked_sector,
      asset_class,
      effective_to
    FROM atlas.atlas_universe_etfs
    WHERE effective_to IS NULL
      AND (${theme}::text IS NULL OR theme = ${theme}::text)
      AND (${linkedSector}::text IS NULL OR linked_sector = ${linkedSector}::text)
      AND (
        ${search}::text IS NULL
        OR ticker ILIKE ${search}::text
        OR etf_name ILIKE ${search}::text
      )
    ORDER BY theme, ticker
    LIMIT 100
  `
}

/**
 * Mutual Funds for the InstrumentPicker — current universe only (effective_to IS NULL).
 * Filters: category_name, broad_category, search (ILIKE on scheme_name or amc).
 */
export async function getMutualFundsForPicker(
  filters: FundFilters = {},
): Promise<FundPickerRow[]> {
  const categoryName = filters.category_name ?? null
  const broadCategory = filters.broad_category ?? null
  const search = filters.search ? `%${filters.search}%` : null

  return sql<FundPickerRow[]>`
    SELECT
      mstar_id,
      scheme_name,
      amc,
      broad_category,
      category_name,
      effective_to
    FROM atlas.atlas_universe_funds
    WHERE effective_to IS NULL
      AND (${categoryName}::text IS NULL OR category_name = ${categoryName}::text)
      AND (${broadCategory}::text IS NULL OR broad_category = ${broadCategory}::text)
      AND (
        ${search}::text IS NULL
        OR scheme_name ILIKE ${search}::text
        OR amc ILIKE ${search}::text
      )
    ORDER BY broad_category, scheme_name
    LIMIT 100
  `
}
