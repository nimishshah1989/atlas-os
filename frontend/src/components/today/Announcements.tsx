'use client'
// STEP 2 (v2) — classified announcements the FM reads WITHOUT opening the PDF.
// Each filing: a tone dot (positive / watch / neutral, by action type), a plain-
// language one-liner (from category), and — on click — NSE's own summary_text précis
// (the 2-3 lines of substance). A 1/7/15/30-day window toggle, scoped to the scored
// universe. Client component for the toggle + expand.
// NB: type-only import from the server-only query module (erased at build); no value imports.
import { useMemo, useState } from 'react'
import Link from 'next/link'
import { Panel } from '../ui/Panel'
import type { TodayCatalyst } from '@/lib/queries/today'

const WINDOWS = [1, 7, 15, 30] as const
type Win = (typeof WINDOWS)[number]

type AnnTone = 'pos' | 'watch' | 'neutral'
const TONE_DOT: Record<AnnTone, string> = { pos: 'bg-sig-pos', watch: 'bg-sig-warn', neutral: 'bg-txt-3/40' }
const TONE_LABEL: Record<AnnTone, string> = { pos: 'Positive', watch: 'Watch', neutral: 'Neutral' }

const CATEGORY_INFO: Record<string, { line: string; tone: AnnTone }> = {
  'financial results': { line: 'Results declared', tone: 'neutral' },
  'outcome of board': { line: 'Board-meeting outcome', tone: 'neutral' },
  concall: { line: 'Earnings call', tone: 'neutral' },
  'analyst meet': { line: 'Analyst / investor meet', tone: 'neutral' },
  'investor presentation': { line: 'Investor presentation', tone: 'neutral' },
  'annual report': { line: 'Annual report', tone: 'neutral' },
  buyback: { line: 'Share buyback', tone: 'pos' },
  dividend: { line: 'Dividend declared', tone: 'pos' },
  bonus: { line: 'Bonus issue', tone: 'pos' },
  split: { line: 'Stock split', tone: 'neutral' },
  acquisition: { line: 'Acquisition', tone: 'pos' },
  amalgamation: { line: 'Amalgamation / scheme', tone: 'neutral' },
  merger: { line: 'Merger', tone: 'neutral' },
  'credit rating': { line: 'Credit-rating update', tone: 'neutral' },
  'press release': { line: 'Press release', tone: 'neutral' },
  takeover: { line: 'Takeover / SAST disclosure', tone: 'neutral' },
  appointment: { line: 'Board / KMP appointment', tone: 'neutral' },
  'change in director': { line: 'Change in directorate', tone: 'watch' },
  resignation: { line: 'Resignation — director / KMP', tone: 'watch' },
  cessation: { line: 'Cessation — director / KMP', tone: 'watch' },
  'change in auditor': { line: 'Auditor change', tone: 'watch' },
}
function annInfo(c: TodayCatalyst): { line: string; tone: AnnTone } {
  const hit = c.category ? CATEGORY_INFO[c.category.toLowerCase()] : undefined
  if (hit) return hit
  return { line: c.subject?.trim() || 'Exchange filing', tone: 'neutral' }
}

const ANN_BUCKETS: { key: string; label: string }[] = [
  { key: 'earnings', label: 'Earnings & results' },
  { key: 'capital', label: 'Capital actions' },
  { key: 'governance', label: 'Governance' },
]
const PRIO_RANK: Record<string, number> = { HIGH: 0, MEDIUM: 1, LOW: 2 }
const prio = (p: string | null) => PRIO_RANK[(p ?? 'LOW').toUpperCase()] ?? 2
const BUCKET_CAP = 12

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const asDate = (d: string) => new Date(`${d}T12:00:00`)
function shortDate(d: string): string {
  const [, m, day] = d.split('-')
  return `${day.replace(/^0/, '')} ${MON[Number(m) - 1] ?? m}`
}

function AnnRow({ c }: { c: TodayCatalyst }) {
  const { line, tone } = annInfo(c)
  const isHigh = (c.priority ?? '').toUpperCase() === 'HIGH'
  const hasDetail = !!(c.summary || c.url)
  const head = (
    <>
      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${TONE_DOT[tone]}`} title={TONE_LABEL[tone]} />
      {c.symbol ? (
        <Link href={`/stocks/${c.symbol}`} className="w-[84px] shrink-0 truncate font-num text-[12px] font-medium text-txt-1 hover:text-brand" onClick={(e) => e.stopPropagation()}>{c.symbol}</Link>
      ) : (
        <span className="w-[84px] shrink-0 font-num text-[12px] text-txt-3">—</span>
      )}
      {c.liked && <span className="shrink-0 font-num text-[10px] text-brand" title="Atlas top-2-decile conviction">★</span>}
      <span className={`min-w-0 flex-1 truncate font-sans text-[12px] ${isHigh ? 'font-medium text-txt-1' : 'text-txt-2'}`}>{line}</span>
      <span className="shrink-0 font-num text-[10px] tabular-nums text-txt-3">{shortDate(c.date)}</span>
    </>
  )
  if (!hasDetail) {
    return <li className="flex items-center gap-2 border-b border-edge-hair py-1.5 last:border-b-0">{head}</li>
  }
  return (
    <li className="border-b border-edge-hair last:border-b-0">
      <details className="group/r">
        <summary className="flex cursor-pointer list-none items-center gap-2 py-1.5 [&::-webkit-details-marker]:hidden">
          {head}
          <span className="shrink-0 font-num text-[10px] text-txt-3 transition-transform group-open/r:rotate-90">▸</span>
        </summary>
        <div className="pb-2.5 pl-[26px] pr-1 pt-0.5">
          {c.summary ? (
            <p className="font-sans text-[12px] leading-[1.55] text-txt-2">{c.summary}</p>
          ) : (
            <p className="font-sans text-[11px] text-txt-3">No exchange summary — open the filing for detail.</p>
          )}
          {c.url && (
            <a href={c.url} target="_blank" rel="noopener noreferrer" className="mt-1 inline-block font-num text-[10px] text-brand hover:underline">
              Full filing on NSE ↗
            </a>
          )}
        </div>
      </details>
    </li>
  )
}

function LegendDot({ cls, children }: { cls: string; children: React.ReactNode }) {
  return <span className="flex items-center gap-1"><span className={`h-1.5 w-1.5 rounded-full ${cls}`} />{children}</span>
}

export function Announcements({ catalysts, today }: { catalysts: TodayCatalyst[]; today: string | null }) {
  const [win, setWin] = useState<Win>(7)

  const { sections, count } = useMemo(() => {
    const cutoff = today ? asDate(today).getTime() - win * 86_400_000 : -Infinity
    const inWin = catalysts.filter((c) => asDate(c.date).getTime() >= cutoff)
    const byBucket = new Map<string, TodayCatalyst[]>()
    for (const c of inWin) {
      const k = (c.bucket ?? 'governance').toLowerCase()
      ;(byBucket.get(k) ?? byBucket.set(k, []).get(k)!).push(c)
    }
    const sections = ANN_BUCKETS.map((b) => ({
      ...b,
      items: (byBucket.get(b.key) ?? []).slice().sort((a, z) => prio(a.priority) - prio(z.priority)),
    })).filter((b) => b.items.length > 0)
    return { sections, count: inWin.length }
  }, [catalysts, win, today])

  return (
    <Panel
      eyebrow="Filings · classified"
      title="Announcements"
      info={{ title: 'Announcements', body: 'Recent NSE filings for your scored universe. Each has a plain-language one-liner and a tone dot — positive (shareholder-friendly), watch (governance/risk), neutral (informational) — the nature of the action type, not a read on the numbers. Click a row for NSE’s own summary of the filing. ★ = a name in Atlas’s top 2 deciles.' }}
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
      <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 font-num text-[10px] text-txt-3">
        <span className="tabular-nums">{count} in {win}d</span>
        <LegendDot cls="bg-sig-pos">Positive</LegendDot>
        <LegendDot cls="bg-sig-warn">Watch</LegendDot>
        <LegendDot cls="bg-txt-3/40">Neutral</LegendDot>
        <span className="ml-auto flex items-center gap-1"><span className="text-brand">★</span>Atlas top decile · click a row for detail</span>
      </div>
      {sections.length === 0 ? (
        <p className="px-1 py-6 text-center font-sans text-[12px] text-txt-3">No filings in this window.</p>
      ) : (
        <div className="flex flex-col gap-3">
          {sections.map((s) => {
            const high = s.items.filter((i) => (i.priority ?? '').toUpperCase() === 'HIGH').length
            const shown = s.items.slice(0, BUCKET_CAP)
            const more = s.items.length - shown.length
            return (
              <div key={s.key}>
                <div className="mb-0.5 flex items-center gap-2 border-b border-edge-hair pb-1">
                  <span className="font-display text-[13px] font-medium text-txt-1">{s.label}</span>
                  {high > 0 && <span className="rounded-tile bg-sig-pos/10 px-1.5 py-0.5 font-num text-[9px] text-sig-pos">{high} HIGH</span>}
                  <span className="ml-auto font-num text-[11px] tabular-nums text-txt-3">{s.items.length}</span>
                </div>
                <ul>{shown.map((c, i) => <AnnRow key={`${c.date}-${c.symbol}-${i}`} c={c} />)}</ul>
                {more > 0 && <p className="py-1 font-num text-[10px] text-txt-3">+{more} more — narrow the window to focus</p>}
              </div>
            )
          })}
        </div>
      )}
    </Panel>
  )
}
