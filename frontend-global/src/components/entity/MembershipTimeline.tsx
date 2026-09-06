// src/components/entity/MembershipTimeline.tsx — every index_membership interval for a stock,
// oldest first, the open one marked. Ends are EXCLUSIVE (the member is out on that date); an SSGA
// interval starts on the weekly observation date, so it can trail the true change by a week.
import { describeInterval, type MembershipInterval } from '@/lib/facts'
import { formatPct } from '@/lib/format'

export function MembershipTimeline({ intervals }: { intervals: MembershipInterval[] }) {
  if (intervals.length === 0) {
    return (
      <p className="max-w-[64ch] text-body text-ink-2">
        Not an S&amp;P 500 member in the archive or in SSGA&apos;s weekly holdings. Membership starts on the first date
        either source records it.
      </p>
    )
  }
  return (
    <>
      <ol className="timeline">
        {intervals.map((m) => {
          const t = describeInterval(m)
          return (
            <li key={`${m.effective_from}-${m.source}`} className="timeline-item">
              <span aria-hidden="true" className={`dot ${t.open ? 'bg-pos' : 'bg-ink-3'}`} />
              <div>
                <p className="text-body text-ink">{t.span}</p>
                <p className="text-meta text-ink-3">
                  {t.source}
                  {m.weight_frac != null && `, weight ${formatPct(m.weight_frac, 2)}`}
                </p>
              </div>
            </li>
          )
        })}
      </ol>
      <p className="mt-3 max-w-[64ch] text-meta text-ink-3">
        Ends are exclusive: the member is out on the date shown. SSGA intervals begin on the weekly observation date;
        the archive&apos;s intervals begin on its first date.
      </p>
    </>
  )
}
