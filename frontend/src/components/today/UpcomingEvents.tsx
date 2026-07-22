'use client'
// STEP 3 — the forward calendar. "Who reports / acts in the days ahead", from
// lens_events (NSE event-calendar). A 7/15/30-day window toggle; events grouped
// by day, conviction-tagged so the names Atlas rates highly stand out. Client
// component for the toggle; the server passes the full 45-day horizon + a stable
// `today` so the default render matches on hydrate.
import { useMemo, useState } from 'react'
import Link from 'next/link'
import { Panel } from '../ui/Panel'
import type { UpcomingEvent } from '@/lib/queries/today'
// NB: this is a client component — do NOT import from server-only modules
// (@/lib/queries/*, @/lib/db). The `liked` flag is already computed server-side.

const WINDOWS = [7, 15, 30] as const
type Win = (typeof WINDOWS)[number]

const TYPE_META: Record<string, { label: string; cls: string }> = {
  earnings: { label: 'Earnings', cls: 'bg-brand/10 text-brand border-brand/30' },
  dividend: { label: 'Dividend', cls: 'bg-sig-pos/10 text-sig-pos border-sig-pos/30' },
  buyback: { label: 'Buyback', cls: 'bg-sig-warn/10 text-sig-warn border-sig-warn/30' },
  split: { label: 'Split', cls: 'bg-sig-warn/10 text-sig-warn border-sig-warn/30' },
  bonus: { label: 'Bonus', cls: 'bg-sig-warn/10 text-sig-warn border-sig-warn/30' },
  rights: { label: 'Rights', cls: 'bg-sig-warn/10 text-sig-warn border-sig-warn/30' },
  restructuring: { label: 'M&A', cls: 'bg-sig-warn/10 text-sig-warn border-sig-warn/30' },
  capital: { label: 'Capital', cls: 'bg-sig-warn/10 text-sig-warn border-sig-warn/30' },
  delisting: { label: 'Delisting', cls: 'bg-sig-neg/10 text-sig-neg border-sig-neg/30' },
  other: { label: 'Event', cls: 'text-txt-3 border-edge-hair' },
}
const typeMeta = (t: string) => TYPE_META[t] ?? TYPE_META.other

const DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
// 'YYYY-MM-DD' → parsed as a LOCAL date at noon (avoids tz/DST edge flips)
const asDate = (d: string) => new Date(`${d}T12:00:00`)
function dayLabel(d: string, todayISO: string | null): string {
  const dt = asDate(d)
  const head = `${DOW[dt.getDay()]} ${dt.getDate()} ${MON[dt.getMonth()]}`
  if (todayISO) {
    const diff = Math.round((asDate(d).getTime() - asDate(todayISO).getTime()) / 86_400_000)
    if (diff <= 0) return `Today · ${head}`
    if (diff === 1) return `Tomorrow · ${head}`
  }
  return head
}

export function UpcomingEvents({ events, today }: { events: UpcomingEvent[]; today: string | null }) {
  const [win, setWin] = useState<Win>(7)

  const { groups, count } = useMemo(() => {
    const cutoff = today ? asDate(today).getTime() + win * 86_400_000 : Infinity
    const inWin = events.filter((e) => asDate(e.date).getTime() <= cutoff)
    const byDay = new Map<string, UpcomingEvent[]>()
    for (const e of inWin) (byDay.get(e.date) ?? byDay.set(e.date, []).get(e.date)!).push(e)
    return { groups: [...byDay.entries()], count: inWin.length }
  }, [events, win, today])

  return (
    <Panel
      eyebrow="The week ahead · NSE"
      title="Upcoming events"
      info={{ title: 'Upcoming events', body: "Scheduled board meetings, results, dividends and corporate actions from NSE's event calendar. ★ marks names in Atlas's top 2 deciles." }}
      action={
        <div className="flex items-center gap-0.5 rounded-tile border border-edge-hair p-0.5">
          {WINDOWS.map((w) => (
            <button
              key={w}
              onClick={() => setWin(w)}
              className={`rounded-[5px] px-2 py-0.5 font-num text-[11px] tabular-nums transition-colors ${
                win === w ? 'bg-brand/15 text-brand' : 'text-txt-3 hover:text-txt-1'
              }`}
            >
              {w}d
            </button>
          ))}
        </div>
      }
    >
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <p className="font-num text-[11px] tabular-nums text-txt-3">
          {count} event{count === 1 ? '' : 's'} in the next {win} days
        </p>
        <span className="flex items-center gap-1 font-num text-[10px] text-txt-3">
          <span className="text-brand">★</span> Atlas top-decile conviction
        </span>
      </div>
      {groups.length === 0 ? (
        <p className="px-1 py-6 text-center font-sans text-[12px] text-txt-3">No scheduled events in this window.</p>
      ) : (
        <div className="grid max-h-[460px] grid-cols-1 gap-x-8 gap-y-4 overflow-y-auto pr-1 md:grid-cols-2 xl:grid-cols-3">
          {groups.map(([day, evs]) => (
            <div key={day}>
              <div className="mb-1.5 flex items-baseline justify-between border-b border-edge-hair pb-1">
                <h3 className="font-num text-[11px] font-medium text-txt-1">{dayLabel(day, today)}</h3>
                <span className="font-num text-[10px] tabular-nums text-txt-3">{evs.length}</span>
              </div>
              <ul>
                {evs.map((e, i) => {
                  const m = typeMeta(e.event_type)
                  return (
                    <li key={`${e.symbol}-${i}`}>
                      <Link
                        href={`/stocks/${e.symbol}`}
                        className="flex items-baseline gap-2 py-1 transition-colors hover:bg-surface-raised"
                      >
                        <span className="w-[92px] shrink-0 truncate font-num text-[12px] font-medium text-txt-1">
                          {e.symbol}
                          {e.liked && <span className="ml-1 text-brand" title="Atlas top deciles">★</span>}
                        </span>
                        <span className={`shrink-0 rounded-tile border px-1.5 py-0.5 font-num text-[9px] uppercase ${m.cls}`}>{m.label}</span>
                        <span className="min-w-0 flex-1 truncate font-sans text-[11px] text-txt-3">{e.name ?? ''}</span>
                      </Link>
                    </li>
                  )
                })}
              </ul>
            </div>
          ))}
        </div>
      )}
    </Panel>
  )
}
