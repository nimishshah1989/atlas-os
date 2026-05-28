// frontend/src/lib/queries/symbol-aliases.ts
//
// Looks up NSE symbol renames + demergers from atlas.atlas_symbol_aliases
// so dead bookmarks (e.g. /stocks/TATAMOTORS, /stocks/ZOMATO) redirect to
// the current symbol (TMPV, ETERNAL) instead of 404-ing.
//
// Used by frontend/src/app/stocks/[symbol]/page.tsx as a fallback after
// getStockBySymbol returns null.

import 'server-only'
import sql from '@/lib/db'

/**
 * Look up the current symbol for an old (renamed/demerged) NSE symbol.
 * Returns the new_symbol string if a mapping exists, else null.
 */
export async function lookupSymbolAlias(oldSymbol: string): Promise<string | null> {
  const rows = await sql<Array<{ new_symbol: string }>>`
    SELECT new_symbol
    FROM atlas.atlas_symbol_aliases
    WHERE old_symbol = ${oldSymbol.toUpperCase()}
    LIMIT 1
  `
  return rows[0]?.new_symbol ?? null
}
