// Unscored — why the funds under a node are not ones the FM can buy, in one sentence.
//
// The FM, looking at the sector page: "within healthcare, we have just 4 out of 12, and within IT
// we have 42 out of 94 — for the funds which are not scored, what is the issue? Why can't we score
// all the funds?"
//
// He had to ask, which means the board was withholding it. Both halves of the answer have since
// changed: the scorer now grades nearly everything (his own instruction), so "not scored" stopped
// being the gap — and this panel counted `composite IS NULL`, which made it silently print
// nothing. The real gap is between MEASURED and OFFERED, and every one of it is one of three
// things, two of them his own rules. Measured across the live board on 2026-09-10: 2,975 below
// the floor, 711 geared, 40 inverse, 184 too young. Not one is a defect.
import { InfoTip } from '@/components/ui/InfoTip'
import { formatNum } from '@/lib/format'
import type { SectorNode } from '@/lib/sectors'

/** The three counts as clauses, longest first, omitting any that is zero. */
export function unscoredReasons(node: Pick<SectorNode, 'n_small' | 'n_geared' | 'n_young'>): string[] {
  const parts: [number, string][] = [
    [node.n_small, 'below the liquidity floor'],
    [node.n_geared, 'geared or inverse'],
    [node.n_young, 'too new to measure'],
  ]
  return parts
    .filter(([n]) => n > 0)
    .sort((a, b) => b[0] - a[0])
    .map(([n, why]) => `${formatNum(n)} ${why}`)
}

export function Unscored({ node }: { node: SectorNode }) {
  const missing = node.n_funds - node.n_offered
  if (missing <= 0) return null
  const reasons = unscoredReasons(node)
  return (
    <p className="mt-2 max-w-(--measure) text-meta text-ink-3">
      {formatNum(missing)} of the {formatNum(node.n_funds)} funds here are not ones you can buy
      {reasons.length > 0 ? <>: {reasons.join(', ')}.</> : '.'}{' '}
      <InfoTip title="Measured is not offered">
        The scorer grades nearly every fund, so almost all of these carry a composite and you can
        still open them. What they do not do is take part in a ranking, a median or a basket, and
        two of the three reasons are your own rules — the liquidity floor, and no geared or inverse
        funds. The third is a fund without enough trading history to measure yet. Lower the floor
        on the admin panel and more of these become buyable.
      </InfoTip>
    </p>
  )
}
