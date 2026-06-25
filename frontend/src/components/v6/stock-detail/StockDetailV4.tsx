// allow-large: v4 stock detail assembles header + price/VWAP StatCards + the six-lens
// DecileLadder (real numbers behind every score) + RS matrix + two theme-aware EMA charts
// + 8-quarter financials + corporate announcements + TV widgets into one ordered page.
// StockDetailV4 — lens-first, FULLY native foundation_staging (no atlas.* / public.de_* reads).
import Link from 'next/link'
import { notFound } from 'next/navigation'

import { getStockDecile, getStockRSMatrix, getStockChartSeries, getStockEvidence, getStockFundamentals, getStockAnnouncements, getStockHeader } from '@/lib/queries/v6/stock_lens'
import { StockFundamentalsTable } from './StockFundamentalsTable'
import { StockAnnouncementsPanel } from './StockAnnouncementsPanel'
import { StockRSMatrix } from './StockRSMatrix'
import { StockPriceEMAChart } from './StockPriceEMAChart'
import { StockRSChart } from './StockRSChart'
import { TVTechnicalAnalysis, TVCompanyProfile } from './TVWidgets'
import { DecileLadder } from '@/components/v4/ui/DecileLadder'
import { StatCard, type Tone } from '@/components/v4/ui/StatCard'
import { stockToLadder } from '@/components/v4/adapters/stockToLadder'

const CAP_LABEL: Record<string, string> = { large: 'Large-cap', mid: 'Mid-cap', small: 'Small-cap', micro: 'Micro-cap' }
const SECTION = 'px-8 py-8 border-b border-edge-hair'

export async function StockDetailV4({ symbol }: { symbol: string }) {
  // Batch 1 — instrument header + lens + RS matrix (session pooler caps clients at 15).
  const [stock, decile, rsMatrix] = await Promise.all([
    getStockHeader(symbol),
    getStockDecile(symbol).catch(() => null),
    getStockRSMatrix(symbol).catch(() => null),
  ])
  if (!stock) notFound()

  // Batch 2 — chart series + the REAL numbers (evidence), 8-quarter financials, announcements.
  const [chartRows, evidence, fundamentals, announcements] = await Promise.all([
    getStockChartSeries(symbol, 5).catch(() => []),
    getStockEvidence(symbol).catch(() => null),
    getStockFundamentals(symbol).catch(() => []),
    getStockAnnouncements(symbol).catch(() => []),
  ])

  const capLabel = decile?.cap ? (CAP_LABEL[decile.cap] ?? decile.cap) : null
  const sector = stock.sector ?? decile?.sector ?? null
  const name = stock.name ?? decile?.name ?? stock.symbol
  const ladder = decile ? stockToLadder(decile, evidence) : null

  // price/VWAP snapshot tiles (real numbers at a glance)
  const tiles: { label: string; value: string; sub?: string; tone?: Tone }[] = evidence
    ? [
        { label: 'Price', value: evidence.close == null ? '—' : `₹${evidence.close.toFixed(1)}`, sub: evidence.as_of ?? undefined },
        {
          label: 'VWAP · 1Y anchor', value: evidence.vwap_252 == null ? '—' : `₹${evidence.vwap_252.toFixed(0)}`,
          sub: evidence.vwap_dist == null ? '252-session' : `${evidence.vwap_dist >= 0 ? '+' : ''}${evidence.vwap_dist.toFixed(1)}% from VWAP`,
          tone: evidence.vwap_dist == null ? 'neutral' : evidence.vwap_dist >= 0 ? 'pos' : 'neg',
        },
        { label: 'P/E · TTM', value: evidence.pe_ttm == null ? '—' : `${evidence.pe_ttm.toFixed(1)}×`, sub: evidence.eps_ttm == null ? 'no TTM EPS' : `TTM EPS ₹${evidence.eps_ttm.toFixed(1)}` },
        { label: '52-week range', value: evidence.pos_52w == null ? '—' : `${evidence.pos_52w.toFixed(0)}%`, sub: 'position low→high' },
        { label: 'RSI(14)', value: evidence.rsi == null ? '—' : evidence.rsi.toFixed(0), sub: 'momentum' },
      ]
    : []

  return (
    <div className="mx-auto max-w-[1280px]">
      {/* ── Header ── */}
      <section className="border-b border-edge-hair px-8 py-8">
        <nav className="mb-3 font-num text-[11px] text-txt-3" aria-label="Breadcrumb">
          <Link href="/" className="text-brand hover:underline">Atlas</Link> ›{' '}
          <Link href="/stocks" className="text-brand hover:underline">Stocks</Link> ›{' '}
          <span aria-current="page">{stock.symbol}</span>
        </nav>
        <div className="mb-2 flex flex-wrap items-baseline gap-4">
          <h1 className="font-display text-[40px] font-bold leading-none tracking-tight text-txt-1">{stock.symbol}</h1>
          <span className="font-sans text-[17px] text-txt-2">{name}</span>
        </div>
        <div className="flex flex-wrap items-center gap-3 font-sans text-[13px] text-txt-3">
          {capLabel && <span className="rounded-tile border border-edge-rule bg-surface-raised px-2 py-0.5 font-num text-[11px] uppercase tracking-wider text-txt-2">{capLabel}</span>}
          {sector && <Link href={`/sectors/${encodeURIComponent(sector)}`} className="text-brand hover:underline">{sector} ↗</Link>}
        </div>
        <p className="mt-3 max-w-[880px] font-sans text-[14px] leading-[1.5] text-txt-2">
          What the six lenses say about {stock.symbol} — its relative strength vs the baselines, price &amp; RS trend, the 8-quarter financials, and live filings.
        </p>
      </section>

      {/* ── Price & VWAP snapshot ── */}
      {tiles.length > 0 && (
        <section className="border-b border-edge-hair px-8 py-6">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {tiles.map((t) => <StatCard key={t.label} label={t.label} value={t.value} sub={t.sub} tone={t.tone ?? 'neutral'} />)}
          </div>
        </section>
      )}

      {/* ── Six-lens DecileLadder (centerpiece) ── */}
      <section className={SECTION}>
        <div className="mb-4">
          <p className="font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">Six-lens read</p>
          <h2 className="font-display text-[22px] font-medium tracking-tight text-txt-1">What the six lenses say</h2>
        </div>
        {ladder ? (
          <DecileLadder
            lenses={ladder.lenses}
            strength={ladder.strength}
            leadership={ladder.leadership}
            cohortLabel={ladder.cohortLabel}
            defaultOpenKey={ladder.topLensKey ?? undefined}
            note={<>Each lens is a <strong className="text-txt-1">decile within its cap cohort</strong> (D10 = top 10%) — no black-box composite. Expand a lens for the real numbers behind it.</>}
          />
        ) : (
          <p className="font-sans text-[13px] italic text-txt-3">No lens scores recorded for {stock.symbol}.</p>
        )}
      </section>

      {/* ── RS matrix ── */}
      {rsMatrix && <StockRSMatrix matrix={rsMatrix} />}

      {/* ── Native EMA charts: price + RS ── */}
      {chartRows.length > 0 && (
        <>
          <section className={SECTION}><StockPriceEMAChart rows={chartRows} symbol={stock.symbol} /></section>
          <section className={SECTION}><StockRSChart rows={chartRows} symbol={stock.symbol} /></section>
        </>
      )}

      {/* ── TV Technical Analysis ── */}
      <section className="border-b border-edge-hair px-8 py-7">
        <p className="mb-3 font-num text-[10px] uppercase tracking-wider text-txt-3">TradingView composite technical analysis — multi-timeframe consensus</p>
        <div className="overflow-hidden rounded-tile border border-edge-hair bg-surface-panel">
          <TVTechnicalAnalysis symbol={stock.symbol} interval="1D" />
        </div>
      </section>

      {/* ── Quarterly financials + corporate announcements (native) ── */}
      <StockFundamentalsTable quarters={fundamentals} />
      <StockAnnouncementsPanel filings={announcements} />

      {/* ── TV Company profile (collapsed) ── */}
      <section className="border-b border-edge-hair px-8 py-6">
        <details className="rounded-tile border border-edge-hair bg-surface-panel p-3 font-sans text-[12px] text-txt-3">
          <summary className="cursor-pointer select-none font-medium text-brand">Show company profile (about, sector, employees, IPO)</summary>
          <div className="pt-3"><TVCompanyProfile symbol={stock.symbol} /></div>
        </details>
      </section>

      <div className="px-8 py-6 font-sans text-[12px] leading-[1.6] text-txt-3">
        Native from <strong className="text-txt-2">foundation_staging</strong> — lens journal, technical_daily, ohlcv_stock; TradingView for the live instrument view.{' '}
        {sector && <Link href={`/sectors/${encodeURIComponent(sector)}`} className="text-brand hover:underline">← Back to {sector}</Link>}
      </div>
    </div>
  )
}
