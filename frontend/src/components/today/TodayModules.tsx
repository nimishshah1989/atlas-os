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

// ── 3. Catalysts ─────────────────────────────────────────────────────────────
// Priority chip styling mirrors StockAnnouncementsPanel (kept local — 3 lines of Tailwind).
function priorityChip(priority: string | null): string {
  switch ((priority ?? '').toUpperCase()) {
    case 'HIGH': return 'bg-sig-pos/10 text-sig-pos border-sig-pos/30'
    case 'MEDIUM': return 'bg-sig-warn/10 text-sig-warn border-sig-warn/30'
    default: return 'text-txt-3 border-edge-hair'
  }
}

function CatalystRow({ c }: { c: TodayCatalyst }) {
  return (
    <li className="flex flex-col gap-1 border-b border-edge-hair px-1 py-2.5 last:border-b-0 sm:flex-row sm:items-baseline sm:gap-3">
      <span className="w-[52px] shrink-0 font-num text-[10px] tabular-nums text-txt-3">{shortDate(c.date)}</span>
      <span className={`shrink-0 rounded-tile border px-1.5 py-0.5 font-num text-[9px] uppercase ${priorityChip(c.priority)}`}>
        {(c.priority ?? 'LOW').toUpperCase()}
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <div className="flex items-center gap-1.5">
          {c.symbol ? (
            <Link href={`/stocks/${c.symbol}`} className="font-num text-[12px] font-medium text-txt-1 hover:text-brand">{c.symbol}</Link>
          ) : (
            <span className="font-num text-[12px] text-txt-2">—</span>
          )}
          {c.liked && <span className="font-num text-[10px] text-brand" title={`Atlas conviction: top ${11 - LEAD_DECILE} deciles`}>★</span>}
          {c.bucket && <span className="font-num text-[9px] uppercase tracking-wider text-txt-3">{c.bucket}</span>}
        </div>
        <span className="truncate font-sans text-[12px] text-txt-2">{c.subject ?? '—'}</span>
      </div>
      {c.url && (
        <a href={c.url} target="_blank" rel="noopener noreferrer" className="shrink-0 self-start font-num text-[10px] text-txt-3 hover:text-brand sm:self-center">
          NSE ↗
        </a>
      )}
    </li>
  )
}

export function CatalystsPanel({ catalysts, total }: { catalysts: TodayCatalyst[]; total: number }) {
  return (
    <Panel
      eyebrow="Filings · recent"
      title="Catalysts"
      info={{ title: 'Catalysts', body: 'The most recent exchange filings (trailing 60 days), newest first. ★ marks names Atlas already rates highly. The feed runs sparse — a quiet stretch is real, not a bug.' }}
      action={total > catalysts.length ? <span className="font-num text-[10px] text-txt-3">{catalysts.length} of {total}</span> : undefined}
    >
      {catalysts.length === 0 ? (
        <EmptyRow>No recent filings.</EmptyRow>
      ) : (
        <ul>{catalysts.map((c, i) => <CatalystRow key={`${c.date}-${c.symbol}-${i}`} c={c} />)}</ul>
      )}
    </Panel>
  )
}
