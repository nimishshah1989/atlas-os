// Trader-view since-call line — first-called date + days held + realized excess.

import { formatIST } from '@/lib/format-date'
import { fmtSignedPct } from '@/lib/format-number'

interface SinceCallLineProps {
  firstCalledAt: string | null   // ISO date string
  verdict: string                // BUY / AVOID / etc.
  sinceCallReturn: number | null
}

function daysBetween(d: string | null): number | null {
  if (!d) return null
  const then = new Date(d)
  const now = new Date()
  if (isNaN(then.getTime())) return null
  return Math.floor((now.getTime() - then.getTime()) / (1000 * 60 * 60 * 24))
}

export function SinceCallLine({ firstCalledAt, verdict, sinceCallReturn }: SinceCallLineProps) {
  if (!firstCalledAt) {
    return (
      <div className="text-[12px] text-ink-tertiary">
        No tracked call yet — this verdict is composite-derived; no entry-stamped signal_call open.
      </div>
    )
  }

  const days = daysBetween(firstCalledAt)
  const retCls = sinceCallReturn == null
    ? 'text-ink-tertiary'
    : sinceCallReturn >= 0 ? 'text-signal-pos font-semibold' : 'text-signal-neg font-semibold'

  return (
    <div className="text-[12px] text-ink-tertiary">
      First called <strong className="text-ink-secondary">{verdict}</strong> on{' '}
      <span className="font-mono">{formatIST(firstCalledAt)}</span>
      {days != null && days >= 0 && (
        <>
          {' · '}
          <span className="font-mono">{days}</span> day{days === 1 ? '' : 's'} held
        </>
      )}
      {sinceCallReturn != null && (
        <>
          {' · since-call return '}
          <span className={retCls}>{fmtSignedPct(sinceCallReturn)}</span>
        </>
      )}
    </div>
  )
}
