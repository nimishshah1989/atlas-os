export type SectorCommentaryContext = {
  sectorName: string
  sectorState: string
  divergence_flag: boolean
  bottomup_momentum_state: string | null
  constituent_count: number
  leadingRRGCount: number
  recentlyUpgraded: boolean
}

export type SectorCommentaryResult = {
  narrative: string
  contextCards: { label: string; value: string }[]
}

type Condition = {
  test: (ctx: SectorCommentaryContext) => boolean
  generate: (ctx: SectorCommentaryContext) => string
}

const CONDITIONS: Condition[] = [
  {
    test: ctx => ctx.divergence_flag,
    generate: ctx =>
      `${ctx.sectorName} has a top-down vs bottom-up signal conflict. ` +
      `Top-down and bottom-up signals conflict; await alignment before acting.`,
  },
  {
    test: ctx => ctx.sectorState === 'Overweight' && ctx.recentlyUpgraded,
    generate: ctx =>
      `Rotation signal detected — ${ctx.sectorName} upgraded to Overweight. ` +
      `New positions can be sized within your regime-gated deployment limit.`,
  },
  {
    test: ctx => ctx.leadingRRGCount >= 3,
    generate: ctx =>
      `Broad leadership: ${ctx.leadingRRGCount} sectors are in the Leading RRG quadrant. ` +
      `Offensive allocation supported — breadth is healthy.`,
  },
  {
    test: ctx =>
      ctx.bottomup_momentum_state === 'Deteriorating' && ctx.sectorState === 'Overweight',
    generate: ctx =>
      `${ctx.sectorName} is Overweight but momentum is Deteriorating. ` +
      `Consider reducing exposure before a formal state downgrade.`,
  },
  {
    test: ctx => ctx.constituent_count < 10,
    generate: ctx =>
      `Small-sample sector (N=${ctx.constituent_count}). ` +
      `Signal reliability is lower — treat classification as indicative only.`,
  },
  {
    test: () => true,
    generate: ctx =>
      `${ctx.sectorName} is classified ${ctx.sectorState} ` +
      `with ${ctx.constituent_count} constituents. ` +
      `Monitor rotation signals in the RRG tab for timing cues.`,
  },
]

export function buildSectorCommentary(ctx: SectorCommentaryContext): SectorCommentaryResult {
  const condition = CONDITIONS.find(c => c.test(ctx))!
  const narrative = condition.generate(ctx)

  const contextCards = [
    { label: 'State',        value: ctx.sectorState },
    { label: 'Constituents', value: String(ctx.constituent_count) },
    { label: 'RRG Leaders',  value: `${ctx.leadingRRGCount} sectors` },
  ]

  return { narrative, contextCards }
}
