// src/app/page.tsx — Today. A placeholder until the nightly pipeline has written a session:
// the shell, the title, what will appear here, and the freshness stamp. No numbers.
import { FreshnessStamp } from '@/components/ui/FreshnessStamp'
import { requireUser } from '@/lib/auth'

export default async function TodayPage() {
  await requireUser()
  return (
    <div className="page">
      <h1 className="font-serif text-title text-ink">Today</h1>
      <p className="mt-4 max-w-[64ch] text-lead text-ink-2">
        Once the nightly pipeline has scored its first session, this page shows where the US market closed and what
        moved, by classification: the benchmark strip (SPY, QQQ, IWM, VXUS, AGG, GLD), breadth by peer group, and the
        day’s top and bottom movers with their Lens bars. Every figure will be dated and traceable to a real row;
        nothing appears before it has been computed.
      </p>
      <div className="mt-6">
        <FreshnessStamp size="lg" />
      </div>
    </div>
  )
}
