// src/components/ui/EodStamp.tsx — which session a facts surface is anchored to: the latest SPY
// session (design principle 5, "dated everywhere"). With no SPY bar there is no price session and
// the stamp says which calendar date membership was read as of instead.
import { formatIsoDate } from '@/lib/format'

export function EodStamp({ eod, asOf }: { eod: string | null; asOf: string }) {
  return (
    <p className="text-body text-ink-2" data-eod={eod ?? ''}>
      {eod ? (
        <>
          At EOD <span className="text-ink">{formatIsoDate(eod)}</span>, the latest SPY session
        </>
      ) : asOf ? (
        <>No price session yet; membership as of {formatIsoDate(asOf)}</>
      ) : null}
    </p>
  )
}
