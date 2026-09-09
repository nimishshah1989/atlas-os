// src/lib/queries/methodology.ts — the lens weights, read from the thresholds table.
// Reads ONLY atlas_global (the schema gate scans this directory).
//
// The /methodology page must never restate a weight: the FM re-tunes them from a table, and a
// page carrying its own copy would be wrong from the first edit. `has_producer` is the other
// honest half — a lens with a weight but no producer is not a lens that scored zero, it is a
// lens that has not been built, and the page says which.
import 'server-only'
import { eodCached } from '@/lib/cache'
import { db, dbAvailable } from '@/lib/db'

/** The five ETF lenses, in the order the board renders them (ddl/05_scores.sql). */
export const ETF_LENSES = [
  { lens: 'technical', label: 'Technical', reads: 'Trend, relative strength vs SPY and vs peers, EMA structure' },
  { lens: 'quality', label: 'Quality', reads: 'Look-through onto the scored stocks a fund actually holds' },
  { lens: 'cost_liquidity', label: 'Cost & liquidity', reads: 'Dollar volume, expense ratio, assets, concentration' },
  { lens: 'flow', label: 'Flow', reads: 'Change in shares outstanding — money arriving or leaving' },
  { lens: 'risk', label: 'Risk', reads: 'Volatility, drawdown, downside deviation, beta (an overlay)' },
] as const

/** Lenses whose producer exists today. The rest are absent, and the page says so. */
const WITH_PRODUCER = new Set(['technical', 'risk', 'cost_liquidity'])

export type LensWeight = {
  lens: string
  label: string
  reads: string
  weight: string
  has_producer: boolean
}

const inner = eodCached(async (): Promise<LensWeight[]> => {
  const rows = await db()<{ threshold_key: string; threshold_value: string }[]>`
    SELECT threshold_key, threshold_value::text AS threshold_value
    FROM atlas_global.atlas_thresholds
    WHERE is_active AND threshold_key LIKE 'etf_lens_weight_%'
  `
  const byKey = new Map(rows.map((r) => [r.threshold_key, r.threshold_value]))
  return ETF_LENSES.map((l) => ({
    lens: l.lens,
    label: l.label,
    reads: l.reads,
    weight: byKey.get(`etf_lens_weight_${l.lens}`) ?? '0',
    has_producer: WITH_PRODUCER.has(l.lens),
  }))
}, 'methodology')

export async function getLensWeights(): Promise<LensWeight[]> {
  if (!dbAvailable) {
    // No database: still show WHAT the lenses are and which are built. The weights are the
    // only thing that needs the table, and a zero here is visibly a no-database state, not a
    // methodology claim.
    return ETF_LENSES.map((l) => ({
      lens: l.lens,
      label: l.label,
      reads: l.reads,
      weight: '0',
      has_producer: WITH_PRODUCER.has(l.lens),
    }))
  }
  return inner()
}
