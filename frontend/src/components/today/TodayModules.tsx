// Presentational modules for the /today Pulse change-feed. Pure server components —
// all data is fetched in TodayBoard and passed in. Every row links back to the name's
// deep-dive so "what changed" is one click from "why".
import Link from 'next/link'
import { Panel } from '../ui/Panel'
import type { ConvictionMove, ConvictionMoves, Mover, TodayCatalyst } from '@/lib/queries/today'
import { LEAD_DECILE } from '@/lib/queries/stock_lens'

// ── formatting ────────────────────────────────────────────────────────────────
const fmtDelta = (n: number | null) => (n == null ? '—' : `${n >= 0 ? '+' : ''}${n.toFixed(1)}`)
const fmtPct = (n: number | null) => (n == null ? '—' : `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`)
const fmtClose = (n: number | null) => (n == null ? '—' : n.toLocaleString('en-IN', { maximumFractionDigits: 2 }))
const posNeg = (n: number | null | undefined) => (n == null ? 'text-txt-2' : n >= 0 ? 'text-sig-pos' : 'text-sig-neg')
// 'YYYY-MM-DD' → "21 Jul" (field-parsed, no Date()/tz drift)
const MON = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
function shortDate(d: string): string {
  const [, m, day] = d.split('-')
  return `${day.replace(/^0/, '')} ${MON[Number(m)] ?? m}`
}

function EmptyRow({ children }: { children: React.ReactNode }) {
  return <p className="px-1 py-6 text-center font-sans text-[12px] text-txt-3">{children}</p>
}

// ── 1. Conviction moves ─────────────────────────────────────────────────────
function MoveRow({ m, mode }: { m: ConvictionMove; mode: 'decile' | 'delta' }) {
  return (
    <Link
      href={`/stocks/${m.symbol}`}
      className="flex items-baseline gap-2 border-b border-edge-hair px-1 py-2 last:border-b-0 transition-colors hover:bg-surface-raised"
    >
      <span className="w-[86px] shrink-0 truncate font-num text-[12px] font-medium text-txt-1">{m.symbol}</span>
      <span className="min-w-0 flex-1 truncate font-sans text-[11px] text-txt-3">{m.name ?? ''}</span>
      {mode === 'decile' ? (
        <span className="shrink-0 font-num text-[11px] tabular-nums text-txt-2">
          D{m.dec_prev ?? '·'}<span className="text-txt-3"> → </span>D{m.dec_now ?? '·'}
        </span>
      ) : (
        <span className={`shrink-0 font-num text-[12px] tabular-nums ${posNeg(m.delta)}`}>{fmtDelta(m.delta)}</span>
      )}
    </Link>
  )
}

function MoveColumn({ title, tint, moves, mode, empty }: {
  title: string; tint: string; moves: ConvictionMove[]; mode: 'decile' | 'delta'; empty: string
}) {
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between">
        <h3 className="font-num text-[10px] uppercase tracking-[0.12em]" style={{ color: tint }}>{title}</h3>
        {moves.length > 0 && <span className="font-num text-[10px] tabular-nums text-txt-3">{moves.length}</span>}
      </div>
      {moves.length === 0 ? <EmptyRow>{empty}</EmptyRow> : moves.map(m => <MoveRow key={m.symbol} m={m} mode={mode} />)}
    </div>
  )
}

export function ConvictionMovesPanel({ data }: { data: ConvictionMoves }) {
  const none = data.entered.length + data.fellOut.length + data.jumps.length === 0
  return (
    <Panel
      eyebrow="Conviction · overnight"
      title="What Atlas re-rated"
      info={{
        title: 'Conviction moves',
        body: `Composite score moves between the last two trading sessions${data.prevOf ? ` (${shortDate(data.prevOf)} → ${data.asOf ? shortDate(data.asOf) : ''})` : ''}. "Leadership" = top ${11 - LEAD_DECILE} deciles (D${LEAD_DECILE}+) of a name's cap cohort.`,
      }}
    >
      {none ? (
        <EmptyRow>No scored changes yet — the baseline is still building.</EmptyRow>
      ) : (
        <div className="grid grid-cols-1 gap-x-6 gap-y-4 md:grid-cols-3">
          <MoveColumn title="Entered leadership" tint="var(--color-sig-pos)" moves={data.entered} mode="decile" empty="None today" />
          <MoveColumn title="Fell out" tint="var(--color-sig-neg)" moves={data.fellOut} mode="decile" empty="None today" />
          <MoveColumn title="Biggest score swings" tint="var(--color-brand)" moves={data.jumps} mode="delta" empty="None today" />
        </div>
      )}
    </Panel>
  )
}

// ── 2. Movers ────────────────────────────────────────────────────────────────
function MoverRow({ m }: { m: Mover }) {
  return (
    <Link
      href={`/stocks/${m.symbol}`}
      className="flex items-baseline gap-2 border-b border-edge-hair px-1 py-2 last:border-b-0 transition-colors hover:bg-surface-raised"
    >
      <span className="w-[86px] shrink-0 truncate font-num text-[12px] font-medium text-txt-1">{m.symbol}</span>
      <span className="min-w-0 flex-1 truncate font-sans text-[11px] text-txt-3">{m.name ?? ''}</span>
      <span className="shrink-0 font-num text-[11px] tabular-nums text-txt-3">₹{fmtClose(m.close)}</span>
      <span className={`w-[62px] shrink-0 text-right font-num text-[12px] tabular-nums ${posNeg(m.pct)}`}>{fmtPct(m.pct)}</span>
    </Link>
  )
}

export function MoversPanel({ gainers, losers }: { gainers: Mover[]; losers: Mover[] }) {
  return (
    <Panel
      eyebrow="Price · last session"
      title="Movers"
      info={{ title: 'Movers', body: 'Biggest EOD price moves over the last two trading sessions, within the scored Nifty 500 universe (liquid by construction).' }}
    >
      <div className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2">
        <div>
          <h3 className="mb-1.5 font-num text-[10px] uppercase tracking-[0.12em] text-sig-pos">Gainers</h3>
          {gainers.length === 0 ? <EmptyRow>No price data.</EmptyRow> : gainers.map(m => <MoverRow key={m.symbol} m={m} />)}
        </div>
        <div>
          <h3 className="mb-1.5 font-num text-[10px] uppercase tracking-[0.12em] text-sig-neg">Losers</h3>
          {losers.length === 0 ? <EmptyRow>No price data.</EmptyRow> : losers.map(m => <MoverRow key={m.symbol} m={m} />)}
        </div>
      </div>
    </Panel>
  )
}

// ── 3. Announcements ─────────────────────────────────────────────────────────
// Each filing gets a plain-language ONE-LINER (from its category — "Outcome of
// Board Meeting" alone tells you nothing) plus a TONE dot. Tone reflects the
// NATURE of the action type — a buyback is structurally shareholder-positive, a
// director/auditor exit is a governance watch — NOT a read on the specific
// numbers (we don't parse the filing body; the NSE link carries the detail).
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
  return { line: c.subject?.trim() || 'Exchange filing', tone: 'neutral' } // 'other' → raw subject
}

function AnnRow({ c }: { c: TodayCatalyst }) {
  const { line, tone } = annInfo(c)
  const isHigh = (c.priority ?? '').toUpperCase() === 'HIGH'
  return (
    <li className="flex items-center gap-2 border-b border-edge-hair py-1.5 last:border-b-0">
      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${TONE_DOT[tone]}`} title={TONE_LABEL[tone]} />
      {c.symbol ? (
        <Link href={`/stocks/${c.symbol}`} className="w-[84px] shrink-0 truncate font-num text-[12px] font-medium text-txt-1 hover:text-brand">{c.symbol}</Link>
      ) : (
        <span className="w-[84px] shrink-0 font-num text-[12px] text-txt-3">—</span>
      )}
      {c.liked && <span className="shrink-0 font-num text-[10px] text-brand" title="Atlas top-2-decile conviction">★</span>}
      <span
        className={`min-w-0 flex-1 truncate font-sans text-[12px] ${isHigh ? 'font-medium text-txt-1' : 'text-txt-2'}`}
        title={c.subject ?? undefined}
      >
        {line}
      </span>
      <span className="shrink-0 font-num text-[10px] tabular-nums text-txt-3">{shortDate(c.date)}</span>
      {c.url && (
        <a href={c.url} target="_blank" rel="noopener noreferrer" className="shrink-0 font-num text-[10px] text-txt-3 hover:text-brand">NSE ↗</a>
      )}
    </li>
  )
}

// Three catalyst buckets, most material first (HIGH before MEDIUM/LOW). Each is a
// native <details> dropdown — earnings + capital open, governance collapsed.
const ANN_BUCKETS: { key: string; label: string; open: boolean }[] = [
  { key: 'earnings', label: 'Earnings & results', open: true },
  { key: 'capital', label: 'Capital actions', open: true },
  { key: 'governance', label: 'Governance', open: false },
]
const PRIO_RANK: Record<string, number> = { HIGH: 0, MEDIUM: 1, LOW: 2 }
const prio = (p: string | null) => PRIO_RANK[(p ?? 'LOW').toUpperCase()] ?? 2
const BUCKET_CAP = 10 // keep each group short; HIGH-first sort means the cap keeps the material ones

function LegendDot({ cls, children }: { cls: string; children: React.ReactNode }) {
  return (
    <span className="flex items-center gap-1">
      <span className={`h-1.5 w-1.5 rounded-full ${cls}`} />
      {children}
    </span>
  )
}

export function AnnouncementsPanel({ catalysts, total }: { catalysts: TodayCatalyst[]; total: number }) {
  const byBucket = new Map<string, TodayCatalyst[]>()
  for (const c of catalysts) {
    const k = (c.bucket ?? 'governance').toLowerCase()
    ;(byBucket.get(k) ?? byBucket.set(k, []).get(k)!).push(c)
  }
  const sections = ANN_BUCKETS.map((b) => ({
    ...b,
    items: (byBucket.get(b.key) ?? []).slice().sort((a, z) => prio(a.priority) - prio(z.priority)),
  })).filter((b) => b.items.length > 0)

  return (
    <Panel
      eyebrow="Filings · classified"
      title="Announcements"
      info={{ title: 'Announcements', body: 'Recent NSE filings (trailing 60 days), grouped by type and most-material-first. Each carries a plain-language one-liner and a tone dot — positive (shareholder-friendly action), watch (governance/risk), neutral (informational). The dot is the nature of the action type, not a read on the numbers. ★ = a name in Atlas’s top 2 deciles. Open the NSE link for the full filing.' }}
      action={<span className="font-num text-[10px] text-txt-3">{catalysts.length} of {total}</span>}
    >
      {sections.length === 0 ? (
        <EmptyRow>No recent filings.</EmptyRow>
      ) : (
        <>
          <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 font-num text-[10px] text-txt-3">
            <LegendDot cls="bg-sig-pos">Positive</LegendDot>
            <LegendDot cls="bg-sig-warn">Watch</LegendDot>
            <LegendDot cls="bg-txt-3/40">Neutral</LegendDot>
            <span className="ml-auto flex items-center gap-1"><span className="text-brand">★</span>Atlas top decile</span>
          </div>
          <div className="flex flex-col gap-2">
            {sections.map((s) => {
              const high = s.items.filter((i) => (i.priority ?? '').toUpperCase() === 'HIGH').length
              const shown = s.items.slice(0, BUCKET_CAP)
              const more = s.items.length - shown.length
              return (
                <details key={s.key} open={s.open} className="group/ann rounded-tile border border-edge-hair">
                  <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 [&::-webkit-details-marker]:hidden">
                    <span className="font-num text-[10px] text-txt-3 transition-transform group-open/ann:rotate-90">▸</span>
                    <span className="font-display text-[13px] font-medium text-txt-1">{s.label}</span>
                    {high > 0 && <span className="rounded-tile bg-sig-pos/10 px-1.5 py-0.5 font-num text-[9px] text-sig-pos">{high} HIGH</span>}
                    <span className="ml-auto font-num text-[11px] tabular-nums text-txt-3">{s.items.length}</span>
                  </summary>
                  <ul className="border-t border-edge-hair px-3 pb-1">
                    {shown.map((c, i) => <AnnRow key={`${c.date}-${c.symbol}-${i}`} c={c} />)}
                  </ul>
                  {more > 0 && (
                    <p className="px-3 py-1.5 font-num text-[10px] text-txt-3">+{more} more this week</p>
                  )}
                </details>
              )
            })}
          </div>
        </>
      )}
    </Panel>
  )
}
