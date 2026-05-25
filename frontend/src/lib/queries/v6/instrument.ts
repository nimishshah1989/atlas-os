// frontend/src/lib/queries/v6/instrument.ts
//
// Direct Supabase query for the v6 single-stock detail page.
// Resolves a stock by either UUID (instrument_id) or symbol — the page route
// is /v6/stocks/[iid] and accepts both.

import 'server-only'
import { getStocksForDate } from '@/lib/queries/v6/stocks'
import type { ScreenStock } from '@/lib/api/v1'
import { getLatestSnapshotDate } from '@/lib/queries/v6/snapshot'

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
