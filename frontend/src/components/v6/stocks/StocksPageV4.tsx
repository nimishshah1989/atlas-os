// StocksPageV4 — lens-first /stocks (behind LENS_V4). All data native foundation_staging.
// The list is a FUNNEL into the stock-detail atom. Order per the stocks-pages plan §B:
//   1. leadership strip + a few "top doing great" cards
//   2. one strong 2×2 (Strength × Leadership, size=liquidity, colour=leadership)
//   3. filter + smart-screen bar
//   4. decile table (5 lens deciles · strength · leadership · compact RS · liquidity)
// (2)–(4) are the interactive client screener; this server shell owns the fetch + headline.
import { getStocksDecileList, getLensAsOf, type StockListRow } from '@/lib/queries/v6/stock_lens'
import { DataSourceBanner } from '@/components/v6/DataSourceBanner'
import { StocksScreenerV4 } from './StocksScreenerV4'

const CAP_LABEL: Record<string, string> = { large: 'large', mid: 'mid', small: 'small', micro: 'micro' }
const leadColor = (lead: number) =>
  lead >= 3 ? 'text-signal-pos' : lead === 2 ? 'text-teal' : lead === 1 ? 'text-signal-warn' : 'text-ink-tertiary'

// A compact decile pip used inside the "top doing great" cards.
function Pip({ label, d }: { label: string; d: number | null }) {
  const c = d == null ? 'text-ink-tertiary' : d >= 8 ? 'text-signal-pos' : d >= 5 ? 'text-ink-secondary' : 'text-signal-neg'
  return (
    <div className="flex flex-col items-center">
      <span className="font-sans text-[8px] uppercase tracking-wider text-ink-tertiary">{label}</span>
      <span className={`font-mono text-[13px] font-medium ${c}`}>{d ?? '—'}</span>
    </div>
  )
}

function TopCard({ s }: { s: StockListRow }) {
  const rs = s.rs_3m
  return (
    <a href={`/stocks/${s.symbol}`}
       className="block bg-paper border border-paper-rule rounded-sm p-3 no-underline hover:border-ink-tertiary transition-colors">
      <div className="flex items-baseline justify-between gap-2 mb-0.5">
        <span className="font-mono text-[14px] font-semibold text-ink-primary truncate">{s.symbol}</span>
        <span className={`font-mono text-[11px] font-semibold ${leadColor(s.lead)}`}>{s.lead}/4</span>
      </div>
      <div className="font-sans text-[11px] text-ink-tertiary truncate mb-2">{s.name ?? s.sector ?? '—'}</div>
      <div className="flex items-center justify-between gap-1">
        <Pip label="Tch" d={s.d_tech} /><Pip label="Fnd" d={s.d_fund} /><Pip label="Cat" d={s.d_cat} />
        <Pip label="Flw" d={s.d_flow} /><Pip label="Val" d={s.d_val} />
      </div>
      <div className="mt-2 pt-2 border-t border-paper-rule/60 flex items-center justify-between">
        <span className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">{CAP_LABEL[s.cap] ?? s.cap}</span>
        <span className={`font-mono text-[11px] ${rs == null ? 'text-ink-tertiary' : rs >= 0 ? 'text-signal-pos' : 'text-signal-neg'}`}>
          {rs == null ? '—' : `${rs >= 0 ? '+' : ''}${(rs * 100).toFixed(1)}% RS·3M`}
        </span>
      </div>
    </a>
  )
}

export async function StocksPageV4() {
  const [stocks, asOf] = await Promise.all([getStocksDecileList(), getLensAsOf()])

  const leaders = stocks.filter(s => s.lead >= 3)
  const capCount = (c: string) => leaders.filter(s => s.cap === c).length
  const top = [...leaders].sort((a, b) => (b.strength ?? 0) - (a.strength ?? 0)).slice(0, 6)
  const universeCount = stocks.length

  const strip = [
    { label: 'Multi-factor leaders', value: String(leaders.length), cls: 'text-signal-pos',
      foot: `Top-decile in ≥3 of 4 conviction lenses · ${universeCount} scored` },
    { label: 'Large', value: String(capCount('large')), cls: 'text-ink-primary', foot: 'NIFTY 100 cohort' },
    { label: 'Mid', value: String(capCount('mid')), cls: 'text-ink-primary', foot: 'Midcap 150 cohort' },
    { label: 'Small', value: String(capCount('small')), cls: 'text-ink-primary', foot: 'Smallcap 250 cohort' },
    { label: 'Micro', value: String(capCount('micro')), cls: 'text-ink-primary', foot: 'Outside the broad indices' },
    { label: 'Data as of', value: asOf
        ? new Date(asOf + 'T12:00:00Z').toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
        : '—', cls: 'text-ink-primary font-mono text-[14px]', foot: 'Last session · nightly lens journal' },
  ]

  return (
    <div className="max-w-[1400px] mx-auto">
      {/* Header + leadership strip */}
      <section className="px-8 py-8 border-b border-paper-rule">
        <div className="font-sans text-[12px] text-ink-tertiary mb-3">
          <a href="/" className="text-teal no-underline hover:underline">Atlas</a> › Stocks
        </div>
        <div className="flex items-baseline gap-4 flex-wrap mb-2">
          <h1 className="font-serif text-[44px] font-normal tracking-[-0.011em] text-ink-primary leading-[1.1]">Stocks</h1>
          <span className="font-mono text-[12px] text-ink-tertiary">{universeCount} instruments · deciles within cap cohort</span>
        </div>
        <p className="font-sans text-[15px] text-ink-secondary max-w-[860px]">
          The universe as a funnel into each name. Every lens is a <strong>decile within its cap cohort</strong>;
          leadership counts how many of the four conviction lenses (technical · fundamental · catalyst · flow)
          a stock leads. Screen, then click through to the stock&apos;s evidence.
        </p>

        <div className="mt-6 bg-paper-soft border border-paper-rule rounded-sm overflow-hidden grid"
             style={{ gridTemplateColumns: 'repeat(6, 1fr)' }}>
          {strip.map((t, i) => (
            <div key={t.label} className={`px-[18px] py-[14px] ${i < 5 ? 'border-r border-paper-rule' : ''}`}>
              <div className="font-sans text-[9px] tracking-[0.18em] uppercase text-ink-tertiary font-semibold mb-1">{t.label}</div>
              <div className={`font-mono text-[22px] font-medium leading-none ${t.cls}`}>{t.value}</div>
              <div className="font-sans text-[11px] text-ink-tertiary mt-1 leading-snug">{t.foot}</div>
            </div>
          ))}
        </div>
      </section>

      {asOf && <DataSourceBanner source="live" asOf={asOf} />}

      {/* Top doing great */}
      {top.length > 0 && (
        <section className="px-8 py-9 border-b border-paper-rule" aria-label="Top multi-factor leaders">
          <div className="mb-4">
            <h2 className="font-serif text-[22px] font-normal tracking-tight text-ink-primary">Doing great right now</h2>
            <p className="font-sans text-[13px] text-ink-tertiary mt-1">
              The strongest multi-factor leaders — highest average conviction decile. Click any for the full lens read.
            </p>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            {top.map(s => <TopCard key={s.symbol} s={s} />)}
          </div>
        </section>
      )}

      {/* Interactive screener: 2×2 + filter/smart-screen bar + decile table */}
      <StocksScreenerV4 stocks={stocks} />

      <div className="px-8 py-6 font-sans text-[12px] text-ink-tertiary leading-[1.6]">
        Native from <strong className="text-ink-secondary">foundation_staging</strong> — the lens journal, technical_daily RS, and a 20-session turnover proxy.
      </div>
    </div>
  )
}
