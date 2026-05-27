// frontend/src/lib/queries/v6/gold_availability.ts
//
// Server-only query: checks whether the GOLD series exists in de_index_prices.
// Memoized per server request via React.cache() so multiple server components
// in the same render tree call this at most once.
//
// Usage (server component or layout):
//   const goldAvailable = await isGoldAvailable()
//   // Pass as prop to <BenchmarkToggle goldAvailable={goldAvailable} />

import 'server-only'
import { cache } from 'react'
import sql from '@/lib/db'

type ExistsRow = { exists: boolean }

/**
 * Returns true when de_index_prices contains at least one row with
 * benchmark_code = 'GOLD'. Memoized per server request via React.cache().
 */
export const isGoldAvailable: () => Promise<boolean> = cache(async () => {
  const rows = await sql<ExistsRow[]>`
    SELECT EXISTS(
      SELECT 1
      FROM de_index_prices
      WHERE benchmark_code = 'GOLD'
      LIMIT 1
    ) AS exists
  `
  return rows[0]?.exists ?? false
})
