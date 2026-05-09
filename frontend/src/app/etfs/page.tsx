export const dynamic = 'force-dynamic'

import { getAllETFs } from '@/lib/queries/etfs'
import { ETFScreener } from '@/components/etfs/ETFScreener'

export default async function ETFsPage() {
  const etfs = await getAllETFs()

  if (etfs.length === 0) {
    return (
      <div className="p-8">
        <p className="font-sans text-sm text-ink-secondary">
          No ETF data available. Run the nightly pipeline first.
        </p>
      </div>
    )
  }

  const investableCount = etfs.filter(e => e.is_investable).length
  const leaderCount     = etfs.filter(e => e.rs_state === 'Leader' || e.rs_state === 'Strong').length

  return (
    <div className="max-w-[1400px] mx-auto">
      {/* Header band */}
      <div className="px-6 py-4 border-b border-paper-rule flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-6">
          <h1 className="font-sans text-sm font-semibold text-ink-primary uppercase tracking-wide">
            ETF Universe
          </h1>
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
              <span className="inline-block w-2 h-2 rounded-full bg-teal" />
              {investableCount} Investable
            </span>
            <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
              <span className="inline-block w-2 h-2 rounded-full bg-signal-pos" />
              {leaderCount} Leader/Strong
            </span>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="px-6 py-6">
        <ETFScreener etfs={etfs} />
      </div>
    </div>
  )
}
