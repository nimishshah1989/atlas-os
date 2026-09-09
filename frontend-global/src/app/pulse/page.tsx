// src/app/pulse/page.tsx — breadth: how many instruments are doing the thing.
//
// This is deliberately NOT the front door: the FM's D1 of 2026-09-09 put Countries there, and
// that decision stands until they change it. `/` still redirects to /countries; moving it here
// is one line in src/app/page.tsx if they want it.
import { PulseView } from '@/components/pulse/PulseView'
import { EodStamp } from '@/components/ui/EodStamp'
import { InfoTip } from '@/components/ui/InfoTip'
import { PageHeader } from '@/components/ui/PageHeader'
import { QueryFailed } from '@/components/ui/Section'
import { requireUser } from '@/lib/auth'
import { getPulse } from '@/lib/queries/pulse'
import { attempt } from '@/lib/result'

export const metadata = { title: 'Pulse' }

export default async function PulsePage() {
  await requireUser()
  const pulse = await attempt(getPulse())
  return (
    <div className="page">
      <PageHeader
        title="Pulse"
        lead={
          <>
            How many instruments are doing the thing — not what the index did.{' '}
            <InfoTip title="Why counted, not indexed">
              The S&P 500 is weighted by size, so seven companies can carry it while four hundred
              fall. Every share here is over what was MEASURED, never over what was listed.
            </InfoTip>
          </>
        }
        aside={pulse.ok && pulse.value.eod ? <EodStamp eod={pulse.value.eod} asOf={pulse.value.as_of} /> : undefined}
      />
      {pulse.ok ? <PulseView pulse={pulse.value} /> : <QueryFailed error={pulse.error} />}
    </div>
  )
}
