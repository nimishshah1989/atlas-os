// frontend/src/lib/queries/v6/instrument.ts
//
// Direct Supabase query for the v6 single-stock detail page.
// Resolves a stock by either UUID (instrument_id) or symbol — the page route
// is /v6/stocks/[iid] and accepts both.
//
// Also exports lightweight metadata accessors (getInstrumentMeta,
// resolveSymbolToIid) that hit atlas_universe_stocks directly — used by
// components that need just name/sector/tier without the full scorecard join.

import 'server-only'
import { cache } from 'react'
import sql from '@/lib/db'
import { getStocksForDate } from '@/lib/queries/v6/stocks'
import type { ScreenStock } from '@/lib/api/v1'
import { getLatestSnapshotDate } from '@/lib/queries/v6/snapshot'

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export type InstrumentMeta = {
  instrument_id: string
  symbol: string
  name: string
  sector: string
  cap_tier: 'Small' | 'Mid' | 'Large'
  market_cap_cr: string | null  // always null — column not yet in schema
}

// ---------------------------------------------------------------------------
// Internal row type
// ---------------------------------------------------------------------------

type UniverseRow = {
  instrument_id: string
  symbol: string
  company_name: string | null
  sector: string
  tier: string
}

function rowToMeta(r: UniverseRow): InstrumentMeta {
  return {
    instrument_id: r.instrument_id,
    symbol: r.symbol,
    name: r.company_name ?? r.symbol,
    sector: r.sector,
    cap_tier: toCapTier(r.tier),
    market_cap_cr: null,
  }
}

function toCapTier(t: string): 'Small' | 'Mid' | 'Large' {
  if (t === 'Small' || t === 'Mid' || t === 'Large') return t
  return 'Large'
}

// ---------------------------------------------------------------------------
// Lightweight metadata accessors (memoized per server request)
// ---------------------------------------------------------------------------

/**
 * Return static metadata for a single instrument by UUID.
 * Returns null if the iid is not found in atlas_universe_stocks.
 * Memoized per server request via React.cache().
 */
export const getInstrumentMeta: (iid: string) => Promise<InstrumentMeta | null> = cache(
  async (iid: string): Promise<InstrumentMeta | null> => {
    const rows = await sql<UniverseRow[]>`
      SELECT
        instrument_id::text  AS instrument_id,
        symbol,
        company_name,
        sector,
        tier
      FROM atlas.atlas_universe_stocks
      WHERE instrument_id = ${iid}::uuid
        AND effective_to IS NULL
      LIMIT 1
    `
    return rows[0] != null ? rowToMeta(rows[0]) : null
  },
)

/**
 * Resolve an uppercase ticker symbol to its instrument_id UUID.
 * Returns null if the symbol is not in atlas_universe_stocks.
 * Memoized per server request via React.cache().
 */
export const resolveSymbolToIid: (symbol: string) => Promise<string | null> = cache(
  async (symbol: string): Promise<string | null> => {
    const rows = await sql<{ instrument_id: string }[]>`
      SELECT instrument_id::text AS instrument_id
      FROM atlas.atlas_universe_stocks
      WHERE symbol = ${symbol}
        AND effective_to IS NULL
      LIMIT 1
    `
    return rows[0]?.instrument_id ?? null
  },
)

// ---------------------------------------------------------------------------
// Full detail resolver (used by stock detail page)
// ---------------------------------------------------------------------------

/**
 * Resolve a single stock by iid (UUID) OR symbol. Returns null if missing.
 *
 * Implementation note: we fetch ALL stocks for the date and search in-memory.
 * That's ~750 rows — well under any pagination concern, and lets us reuse
 * exactly the same shape the table-row queries build (conviction tape, etc.).
 */
export async function getInstrumentDetail(
  iidOrSymbol: string,
  snapshotDate?: string,
): Promise<ScreenStock | null> {
  const asOf = snapshotDate ?? (await getLatestSnapshotDate())
  const stocks = await getStocksForDate(asOf)

  // UUID iids are 36-char hyphenated; symbols are uppercase tickers — keep the
  // match permissive: exact iid first, then exact symbol.
  return (
    stocks.find(s => s.iid === iidOrSymbol) ??
    stocks.find(s => s.symbol === iidOrSymbol) ??
    null
  )
}
