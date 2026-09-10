// src/app/sectors/page.tsx — the drill-down: GICS sector → theme → fund, in one table, expanded
// in place. The board's answer to "which parts of the world's economy are working, and what would
// I buy for the part that is".
import Link from 'next/link'
import { SectorHeatmap } from '@/components/sectors/SectorHeatmap'
import { EodStamp } from '@/components/ui/EodStamp'
import { InfoTip } from '@/components/ui/InfoTip'
import { PageHeader } from '@/components/ui/PageHeader'
import { QueryFailed } from '@/components/ui/Section'
import { requireUser } from '@/lib/auth'
import { getSectorTree } from '@/lib/queries/sectors'
import { attempt } from '@/lib/result'
import { formatNum } from '@/lib/format'

export const metadata = { title: 'Sectors' }

export default async function SectorsPage() {
  await requireUser()
  const tree = await attempt(getSectorTree())
  return (
    <div className="page">
      <PageHeader
        title="Sectors"
        lead={
          <>
            Open a sector to see its themes; open a theme to see its funds. Same columns all the
            way down.{' '}
            <InfoTip title="Two levels, not three">
              The taxonomy seeds sectors, sub-sectors and themes, but every theme hangs directly
              off a GICS sector and nothing writes a sub-sector onto a fund — so the mapping that
              exists is sector → theme → fund, and that is what this shows.
            </InfoTip>
          </>
        }
        aside={tree.ok && tree.value.date ? <EodStamp eod={tree.value.date} asOf={tree.value.date} /> : undefined}
      />
      {tree.ok ? <SectorHeatmap tree={tree.value} /> : <QueryFailed error={tree.error} />}
      {tree.ok && tree.value.n_unthemed > 0 && (
        <p className="mt-4 max-w-(--measure) text-meta text-ink-3">
          {formatNum(tree.value.n_unthemed)} classified funds state no theme in their name and sit
          under no sector here — a broad-market fund is a bet on nothing narrower than the market.
          They are all on <Link className="underline" href="/etfs">the fund board</Link>.
        </p>
      )}
    </div>
  )
}
