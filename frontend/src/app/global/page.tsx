export const dynamic = 'force-dynamic'

import { Suspense } from 'react'
import { getGlobalRegime, getGlobalRegimeHistory, getCountryRankings } from '@/lib/queries/global'
import { GlobalPulseShell } from '@/components/global/GlobalPulseShell'

export default async function GlobalPulsePage() {
  const [regime, history, countries] = await Promise.all([
    getGlobalRegime().catch(() => null),
    getGlobalRegimeHistory(365).catch(() => []),
    getCountryRankings().catch(() => []),
  ])

  return (
    <div className="max-w-[1600px] mx-auto">
      <Suspense>
        <GlobalPulseShell regime={regime} history={history} countries={countries} />
      </Suspense>
    </div>
  )
}
