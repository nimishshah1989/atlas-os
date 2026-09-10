// Unscored — why the funds under a node carry no score, in one sentence.
//
// The FM, looking at the sector page: "within healthcare, we have just 4 out of 12, and within IT
// we have 42 out of 94 — for the funds which are not scored, what is the issue? Why can't we score
// all the funds?"
//
// He had to ask, which means the board was withholding it. The answer is never "the scorer failed":
// score_etfs.py grades exactly what universe_snapshot admits (it joins ON u.in_universe), so an
// unscored fund is an EXCLUDED fund, and every exclusion is one of three things — two of them the
// FM's own rules. Measured across the live board on 2026-09-10: 2,975 below the floor, 714
// geared, 43 inverse, 184 too young. Not one is a defect.
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
  const missing = node.n_funds - node.n_scored
  if (missing <= 0) return null
  const reasons = unscoredReasons(node)
  return (
    <p className="mt-2 max-w-(--measure) text-meta text-ink-3">
      {formatNum(missing)} of the {formatNum(node.n_funds)} funds here carry no score
      {reasons.length > 0 ? <>: {reasons.join(', ')}.</> : '.'}{' '}
      <InfoTip title="Not scored is not a gap">
        The scorer grades every fund the universe admits, so an unscored fund is an excluded one.
        Two of the three reasons are your own rules — the liquidity floor, and no geared or inverse
        funds. The third is a fund without enough trading history to measure yet. Lower the floor
        on the admin panel and more of these get scored.
      </InfoTip>
    </p>
  )
}
