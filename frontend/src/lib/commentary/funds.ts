import type { CommentaryResult } from './stocks'
import type { FundMasterRow, FundLensRow } from '@/lib/queries/funds'

// Context for universe-level commentary (/funds page)
export interface FundCommentaryContext {
  total: number
  n_recommended: number
  pct_recommended: number
  n_leader_nav: number
  pct_leader_nav: number
  pct_aligned_composition: number
  pct_weak_holdings: number
  // pct_suspended counts nav_state = 'DISLOCATION_SUSPENDED' (NOT recommendation)
  pct_suspended: number
  top_category: string | null
  top_category_rs_pctile: number   // 0–100 scale (already multiplied)
}

type FundCondition = {
  test: (ctx: FundCommentaryContext) => boolean
  generate: (ctx: FundCommentaryContext) => string
}

const FUND_CONDITIONS: FundCondition[] = [
  {
    test: ctx => ctx.pct_recommended > 0.15,
    generate: ctx =>
      `Momentum is broad: ${ctx.n_recommended} of ${ctx.total} funds are Recommended (${(ctx.pct_recommended * 100).toFixed(0)}%). Selective entry conditions are met across multiple categories.`,
  },
  {
    test: ctx => ctx.pct_recommended === 0,
    generate: () =>
      'No funds currently carry a Recommended rating — market-wide caution. Hold existing positions; avoid new entries.',
  },
  {
    test: ctx => ctx.pct_leader_nav > 0.4,
    generate: ctx =>
      `NAV quality is broadly strong: ${ctx.n_leader_nav} funds (${(ctx.pct_leader_nav * 100).toFixed(0)}%) are Leader NAV — outperforming their category on NAV momentum.`,
  },
  {
    test: ctx => ctx.top_category !== null && ctx.top_category_rs_pctile > 70,
    generate: ctx =>
      `${ctx.top_category} funds lead on RS — mean RS pctile ${ctx.top_category_rs_pctile.toFixed(0)}th. Sector rotation visible at the fund level; overweight this category.`,
  },
  {
    test: ctx => ctx.pct_aligned_composition > 0.5,
    generate: ctx =>
      `${(ctx.pct_aligned_composition * 100).toFixed(0)}% of funds are composition-aligned — holdings match the current recommended sector tilts. Macro alignment supports active strategies.`,
  },
  {
    test: ctx => ctx.pct_weak_holdings > 0.6,
    generate: ctx =>
      `Holdings quality is a headwind: ${(ctx.pct_weak_holdings * 100).toFixed(0)}% of funds carry predominantly weak stocks. Bottom-up pressure on NAV is elevated.`,
  },
  {
    test: ctx => ctx.pct_suspended > 0.3,
    generate: ctx =>
      `${(ctx.pct_suspended * 100).toFixed(0)}% of funds are in DISLOCATION_SUSPENDED — recommendations are paused during current market stress.`,
  },
  {
    // Fallback — always fires
    test: () => true,
    generate: ctx =>
      `${ctx.total} funds computed. NAV quality and composition signals are mixed — no dominant directional signal. Review individual fund lenses before acting.`,
  },
]

export function buildFundCommentary(ctx: FundCommentaryContext): CommentaryResult {
  const condition = FUND_CONDITIONS.find(c => c.test(ctx))!
  const narrative = condition.generate(ctx)
  const contextCards = [
    { label: 'Recommended', value: `${ctx.n_recommended}` },
    { label: 'Leader NAV',  value: `${ctx.n_leader_nav}` },
    { label: 'Aligned Comp', value: `${(ctx.pct_aligned_composition * 100).toFixed(0)}%` },
    { label: 'Suspended',   value: `${(ctx.pct_suspended * 100).toFixed(0)}%`,
      deltaPositive: ctx.pct_suspended === 0 },
  ]
  return { narrative, contextCards }
}

// Single-fund commentary for the deep dive page (/funds/[mstar_id])
// Uses gate status and triggers — NOT universe-level percentages
export function buildSingleFundCommentary(
  master: FundMasterRow,
  _lens: FundLensRow | null,
): CommentaryResult {
  const gateCount = [
    master.performance_gate,
    master.sectors_gate,
    master.stocks_gate,
    master.market_gate,
  ].filter(Boolean).length

  const triggerFlags = [
    master.entry_trigger && 'entry',
    master.exit_trigger && 'exit',
    master.reduce_trigger && 'reduce',
  ].filter((x): x is string => typeof x === 'string')

  const weeks = master.weeks_in_current_state ? parseInt(master.weeks_in_current_state, 10) : null
  const weeksStr = weeks != null
    ? (weeks > 260 ? '52+ weeks' : `${weeks} weeks`)
    : null

  let narrative: string
  if (master.nav_state === 'DISLOCATION_SUSPENDED') {
    narrative = `${master.scheme_name} is in DISLOCATION_SUSPENDED state — recommendations are paused during market dislocation. No entry or exit action until the state clears.`
  } else if (master.recommendation === 'Recommended') {
    narrative = [
      `${master.scheme_name} is Recommended with all 4 gates passing.`,
      weeksStr ? `In current state for ${weeksStr}.` : null,
      triggerFlags.length ? `Active triggers: ${triggerFlags.join(', ')}.` : null,
    ].filter(Boolean).join(' ')
  } else if (master.recommendation === 'Reduce' || master.recommendation === 'Exit') {
    const failedGates = [
      !master.performance_gate && 'Performance',
      !master.sectors_gate && 'Sectors',
      !master.stocks_gate && 'Holdings',
      !master.market_gate && 'Market',
    ].filter((x): x is string => typeof x === 'string').join(', ')
    narrative = [
      `${master.scheme_name} is ${master.recommendation}.`,
      `Gate failures: ${failedGates || 'none'}.`,
      weeksStr ? `In current state for ${weeksStr}.` : null,
    ].filter(Boolean).join(' ')
  } else {
    narrative = [
      `${master.scheme_name} is on Hold — ${gateCount}/4 gates passing.`,
      'Monitor for gate improvement before accumulating.',
      weeksStr ? `In current state for ${weeksStr}.` : null,
    ].filter(Boolean).join(' ')
  }

  const contextCards = [
    { label: 'Recommendation', value: master.recommendation ?? '—' },
    { label: 'Gates Passing', value: `${gateCount}/4`, deltaPositive: gateCount === 4 },
    { label: 'NAV State', value: master.nav_state?.replace(/ NAV$/, '') ?? '—' },
    { label: 'In State', value: weeksStr ?? '—' },
  ]
  return { narrative, contextCards }
}
