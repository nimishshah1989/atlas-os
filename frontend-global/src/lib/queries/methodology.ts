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

/** The five ETF lenses, in the order the board renders them (ddl/05_scores.sql), each with its
 *  producer's own account of what it can and cannot compute today
 *  (atlas/global_market/scoring/etf_lenses.py, scripts/global_market/score_etfs.py). */
export const ETF_LENSES = [
  {
    lens: 'technical',
    label: 'Technical',
    reads: 'Trend, relative strength vs SPY and vs peers, EMA structure',
    state: 'computed',
    note: 'Every sub-score, from technical_daily.',
  },
  {
    lens: 'quality',
    label: 'Quality',
    reads: 'Look-through onto the scored stocks a fund actually holds',
    state: 'absent',
    note: 'No producer yet: needs the holdings looked through onto lens_scores_daily. Holdings (N-PORT) and stock scores both exist; the join does not.',
  },
  {
    lens: 'cost_liquidity',
    label: 'Cost & liquidity',
    reads: 'Dollar volume, expense ratio, assets, concentration',
    state: 'partial',
    note: 'Three of four sub-scores: traded value, assets (from N-PORT) and top-ten concentration. The expense ratio waits on an issuer feed and its sub-score is left out of the mean, not scored zero.',
  },
  {
    lens: 'flow',
    label: 'Flow',
    reads: 'Change in shares outstanding — money arriving or leaving',
    state: 'absent',
    note: 'No producer yet: needs daily shares outstanding, which N-PORT does not carry.',
  },
  {
    lens: 'risk',
    label: 'Risk',
    reads: 'Volatility, drawdown, downside deviation, beta',
    state: 'overlay',
    note: 'Every sub-score is computed from technical_daily, and the blend carries it at weight 0 by the FM’s rule — shown beside the score, not inside it. It does not count towards “n of 5 lenses”.',
  },
] as const

export type LensState = (typeof ETF_LENSES)[number]['state']

export type LensWeight = {
  lens: string
  label: string
  reads: string
  weight: string
  /** computed · partial (some sub-scores) · overlay (computed, weight 0) · absent (no producer). */
  state: LensState
  note: string
  /** Blended into the composite: computed or partial, AND weight > 0. */
  has_producer: boolean
}

/** The tier ladder's cut points, read from the thresholds table (blend.py's `_TIER_KEYS`). */
export type TierRule = { tier: string; minScore: string | null; minLenses: string | null }
const TIERS: [string, string, string | null][] = [
  ['Highest', 'lens_conviction_highest_score', 'lens_conviction_highest_min_layers'],
  ['High', 'lens_conviction_high_score', 'lens_conviction_high_min_layers'],
  ['Medium', 'lens_conviction_medium_score', null],
  ['Watch', 'lens_conviction_watch_score', null],
]

const shape = (l: (typeof ETF_LENSES)[number], weight: string): LensWeight => ({
  lens: l.lens,
  label: l.label,
  reads: l.reads,
  weight,
  state: l.state,
  note: l.note,
  has_producer: (l.state === 'computed' || l.state === 'partial') && Number(weight) > 0,
})

const inner = eodCached(async (): Promise<{ lenses: LensWeight[]; tiers: TierRule[] }> => {
  const rows = await db()<{ threshold_key: string; threshold_value: string }[]>`
    SELECT threshold_key, threshold_value::text AS threshold_value
    FROM atlas_global.atlas_thresholds
    WHERE is_active AND (threshold_key LIKE 'etf_lens_weight_%' OR threshold_key LIKE 'lens_conviction_%')
  `
  const byKey = new Map(rows.map((r) => [r.threshold_key, r.threshold_value]))
  return {
    lenses: ETF_LENSES.map((l) => shape(l, byKey.get(`etf_lens_weight_${l.lens}`) ?? '0')),
    tiers: TIERS.map(([tier, score, layers]) => ({
      tier,
      minScore: byKey.get(score) ?? null,
      minLenses: layers ? (byKey.get(layers) ?? null) : null,
    })),
  }
}, 'methodology')

export async function getLensWeights(): Promise<LensWeight[]> {
  // No database: still show WHAT the lenses are and which are built. The weights are the only
  // thing that needs the table, and a zero here is visibly a no-database state, not a claim.
  if (!dbAvailable) return ETF_LENSES.map((l) => shape(l, '0'))
  return (await inner()).lenses
}

/** The tier ladder as the thresholds table holds it; nulls with no database or no seed row. */
export async function getTierRules(): Promise<TierRule[]> {
  if (!dbAvailable) return TIERS.map(([tier]) => ({ tier, minScore: null, minLenses: null }))
  return (await inner()).tiers
}
