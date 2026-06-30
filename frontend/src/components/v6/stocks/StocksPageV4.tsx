// StocksPageV4 — lens-first /stocks (behind LENS_V4). All data native foundation_staging.
// The list is a FUNNEL into the stock-detail atom. Order per the stocks-pages plan §B:
//   1. leadership strip + a few "top doing great" cards
//   2. one strong 2×2 (Strength × Leadership, size=liquidity, colour=leadership)
//   3. filter + smart-screen bar
//   4. decile table (5 lens deciles · strength · leadership · compact RS · liquidity)
// (2)–(4) are the interactive client screener; this server shell owns the fetch + headline.
import { getStocksDecileList, getLensAsOf, type StockListRow } from '@/lib/queries/v6/stock_lens'
import { StocksScreenerV4 } from './StocksScreenerV4'
import { Panel } from '@/components/v4/ui/Panel'
import { StatCard, type Tone } from '@/components/v4/ui/StatCard'
import { DecileMeter } from '@/components/v4/ui/DecileMeter'
import { decileColor } from '@/components/v4/ui/decile'

const CAP_LABEL: Record<string, string> = { large: 'large', mid: 'mid', small: 'small', micro: 'micro' }
const leadColor = (lead: number) =>
  lead >= 1 ? 'text-sig-pos' : 'text-txt-3'  // leader = top-decile composite (0/1)

// A compact decile pip used inside the "top doing great" cards. The figure takes
// the shared perceptual ramp (decileColor); null falls back to the tertiary token.
function Pip({ label, d }: { label: string; d: number | null }) {
  return (
    <div className="flex flex-col items-center">
      <span className="font-sans text-[8px] uppercase tracking-wider text-txt-3">{label}</span>
      <span
        className="font-num text-[13px] font-medium tabular-nums"
        style={{ color: d == null ? 'var(--color-txt-3)' : decileColor(d) }}
      >
        {d ?? '—'}
      </span>
    </div>
  )
}

function TopCard({ s }: { s: StockListRow }) {
  const rs = s.rs_3m
  return (
    <a href={`/stocks/${s.symbol}`}
       className="block rounded-tile border border-edge-hair bg-surface-panel p-3.5 shadow-tile no-underline hover:border-edge-strong transition-colors">
      <div className="flex items-baseline justify-between gap-2 mb-0.5">
        <span className="font-num text-[14px] font-semibold tabular-nums text-txt-1 truncate">{s.symbol}</span>
        <span className={`font-num text-[11px] font-semibold tabular-nums ${leadColor(s.lead)}`}>{s.lead >= 1 ? 'Leader' : '—'}</span>
      </div>
      <div className="font-sans text-[11px] text-txt-3 truncate mb-2">{s.name ?? s.sector ?? '—'}</div>
      <div className="mb-2"><DecileMeter decile={Math.round(s.strength ?? 0)} size="sm" /></div>
      <div className="flex items-center justify-between gap-1">
        <Pip label="Tch" d={s.d_tech} /><Pip label="Fnd" d={s.d_fund} /><Pip label="Cat" d={s.d_cat} />
        <Pip label="Flw" d={s.d_flow} /><Pip label="Val" d={s.d_val} />
      </div>
      <div className="mt-2 pt-2 border-t border-edge-hair flex items-center justify-between">
        <span className="font-sans text-[10px] text-txt-3 uppercase tracking-wider">{CAP_LABEL[s.cap] ?? s.cap}</span>
        <span className={`font-num text-[11px] tabular-nums ${rs == null ? 'text-txt-3' : rs >= 0 ? 'text-sig-pos' : 'text-sig-neg'}`}>
          {rs == null ? '—' : `${rs >= 0 ? '+' : ''}${(rs * 100).toFixed(1)}% RS·3M`}
        </span>
      </div>
    </a>
  )
}

export async function StocksPageV4() {
  const [stocks, asOf] = await Promise.all([getStocksDecileList(), getLensAsOf()])

  const leaders = stocks.filter(s => s.lead >= 1)
  const capCount = (c: string) => leaders.filter(s => s.cap === c).length
  const top = [...leaders].sort((a, b) => (b.strength ?? 0) - (a.strength ?? 0)).slice(0, 6)
  const universeCount = stocks.length

  const strip: { label: string; value: string; tone: Tone; sub: string }[] = [
    { label: 'Leaders', value: String(leaders.length), tone: 'pos',
      sub: `D9/D10 in both active lenses (Technical & Flow) · ${universeCount} scored` },
    { label: 'Large', value: String(capCount('large')), tone: 'neutral', sub: 'NIFTY 100 cohort' },
    { label: 'Mid', value: String(capCount('mid')), tone: 'neutral', sub: 'Midcap 150 cohort' },
    { label: 'Small', value: String(capCount('small')), tone: 'neutral', sub: 'Smallcap 250 cohort' },
    { label: 'Micro', value: String(capCount('micro')), tone: 'neutral', sub: 'Outside the broad indices' },
    { label: 'Data as of', value: asOf
        ? new Date(asOf + 'T12:00:00Z').toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
        : '—', tone: 'neutral', sub: 'Last session · nightly lens journal' },
  ]

  return (
    <div className="mx-auto max-w-[1680px] px-6 py-7">
      {/* Header + leadership strip */}
      <header className="mb-6">
        <div className="font-sans text-[12px] text-txt-3 mb-3">
          <a href="/" className="text-brand no-underline hover:underline">Atlas</a> › Stocks
        </div>
        <div className="flex items-baseline gap-4 flex-wrap mb-2">
          <h1 className="font-display text-[32px] font-bold tracking-tight text-txt-1">Stocks</h1>
          <span className="font-num text-[12px] tabular-nums text-txt-3">{universeCount} instruments · deciles within cap cohort</span>
        </div>
        <p className="font-sans text-[15px] text-txt-2 max-w-[860px]">
          The universe as a funnel into each name. Every lens is a <strong>decile within its cap cohort</strong>;
          leadership counts how many of the two active conviction lenses (technical · flow) a stock leads at
          D9/D10. Screen, then click through to the stock&apos;s evidence.
        </p>

        <div className="mt-6 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {strip.map(t => (
            <StatCard key={t.label} label={t.label} value={t.value} sub={t.sub} tone={t.tone} />
          ))}
        </div>
      </header>

      {/* Top doing great */}
      {top.length > 0 && (
        <div className="mb-6">
          <Panel
            eyebrow="Leaders"
            title="Doing great right now"
            info={{
              title: 'Doing great right now',
              body: 'The strongest multi-factor leaders — highest average conviction decile. Click any for the full lens read.',
            }}
          >
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
              {top.map(s => <TopCard key={s.symbol} s={s} />)}
            </div>
          </Panel>
        </div>
      )}

      {/* Interactive screener: 2×2 + filter/smart-screen bar + decile table */}
      <StocksScreenerV4 stocks={stocks} />

      <div className="mt-6 font-sans text-[12px] text-txt-3 leading-[1.6]">
        Native from <strong className="text-txt-2">foundation_staging</strong> — the lens journal, technical_daily RS, and a 20-session turnover proxy.
      </div>
    </div>
  )
}
