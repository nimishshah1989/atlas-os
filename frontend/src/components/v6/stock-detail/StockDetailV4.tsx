// allow-large: v4 stock detail page assembles the price/VWAP snapshot, the lens card (real
// numbers behind every score), RS matrix, the two native Lightweight EMA charts, the 8-quarter
// financials table, and corporate announcements into one ordered page. Single-line renders.
// StockDetailV4 — the v4 stock detail page (behind LENS_V4). Lens-first and FULLY native
// foundation_staging (no atlas.* / public.de_* reads — fs-only for the legacy retirement).
// Drops the trader-view verdict header, the TV Advanced chart + TV Financials/News widgets
// (TV's embed refuses NSE symbols / the data was unhelpful), and the Weinstein lifecycle panel
// (its only inputs were legacy atlas metrics; the Technical lens now shows the real trend numbers).
import Link from 'next/link'
import { notFound } from 'next/navigation'

import { getStockDecile, getStockRSMatrix, getStockChartSeries, getStockEvidence, getStockFundamentals, getStockAnnouncements, getStockHeader } from '@/lib/queries/v6/stock_lens'
import { StockFundamentalsTable } from './StockFundamentalsTable'
import { StockAnnouncementsPanel } from './StockAnnouncementsPanel'

import { StockLensCardV4 } from './StockLensCardV4'
import { StockRSMatrix } from './StockRSMatrix'
import { StockPriceEMAChart } from './StockPriceEMAChart'
import { StockRSChart } from './StockRSChart'
import { TVTechnicalAnalysis, TVCompanyProfile } from './TVWidgets'

const CAP_LABEL: Record<string, string> = { large: 'Large-cap', mid: 'Mid-cap', small: 'Small-cap', micro: 'Micro-cap' }

export async function StockDetailV4({ symbol }: { symbol: string }) {
  // Batch 1 — instrument header (fs) + lens + RS matrix (Supabase session pooler caps clients at 15).
  const [stock, decile, rsMatrix] = await Promise.all([
    getStockHeader(symbol),
    getStockDecile(symbol).catch(() => null),
    getStockRSMatrix(symbol).catch(() => null),
  ])
  if (!stock) notFound()

  // Batch 2 — chart series + the REAL numbers behind the scores: evidence (technicals/flow/
  // valuation/VWAP), the 8-quarter financials, and corporate announcements. All native fs.
  const [chartRows, evidence, fundamentals, announcements] = await Promise.all([
    getStockChartSeries(symbol, 5).catch(() => []),
    getStockEvidence(symbol).catch(() => null),
    getStockFundamentals(symbol).catch(() => []),
    getStockAnnouncements(symbol).catch(() => []),
  ])

  const capLabel = decile?.cap ? (CAP_LABEL[decile.cap] ?? decile.cap) : null
  const sector = stock.sector ?? decile?.sector ?? null
  const name = stock.name ?? decile?.name ?? stock.symbol

  return (
    <div className="max-w-[1400px] mx-auto">
      {/* ── Header ── */}
      <section className="px-8 py-9 border-b border-paper-rule">
        <nav className="font-sans text-[12px] text-ink-tertiary mb-3" aria-label="Breadcrumb">
          <Link href="/" className="text-teal hover:underline no-underline">Atlas</Link> ›{' '}
          <Link href="/stocks" className="text-teal hover:underline no-underline">Stocks</Link> ›{' '}
          <span aria-current="page">{stock.symbol}</span>
        </nav>
        <div className="flex items-baseline gap-4 flex-wrap mb-1.5">
          <h1 className="font-serif text-[44px] font-normal tracking-[-0.011em] text-ink-primary leading-[1.05]">{stock.symbol}</h1>
          <span className="font-sans text-[18px] text-ink-secondary">{name}</span>
        </div>
        <div className="flex items-center gap-3 flex-wrap font-sans text-[13px] text-ink-tertiary">
          {capLabel && <span className="font-mono text-[11px] uppercase tracking-wider px-2 py-0.5 bg-paper-deep border border-paper-rule rounded-[2px]">{capLabel}</span>}
          {sector && (
            <Link href={`/sectors/${encodeURIComponent(sector)}`} className="text-teal hover:underline">{sector} ↗</Link>
          )}
          {decile && (
            <>
              <span className="text-paper-rule">·</span>
              <span>
                Strength <strong className="font-mono text-ink-primary">{decile.strength != null ? decile.strength.toFixed(1) : '—'}</strong>
              </span>
              <span className={`font-mono text-[11px] uppercase tracking-wider px-2 py-0.5 rounded-[2px] border ${
                decile.lead >= 2 ? 'text-signal-pos border-signal-pos/40 bg-signal-pos/10'
                : decile.lead === 1 ? 'text-signal-warn border-signal-warn/40 bg-signal-warn/10'
                : 'text-ink-tertiary border-paper-rule bg-paper-deep'}`}>
                Leadership {decile.lead}/4
              </span>
            </>
          )}
        </div>
        <p className="font-sans text-[15px] text-ink-secondary max-w-[880px] mt-3">
          What the six lenses say about {stock.symbol}, its relative strength vs the baselines, price &amp; RS trend,
          and the live TradingView instrument view.
        </p>
      </section>

      {/* ── Price & VWAP snapshot (real numbers at a glance) ── */}
      {evidence && (
        <section className="px-8 py-5 border-b border-paper-rule" aria-label="Price and VWAP snapshot">
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-px bg-paper-rule border border-paper-rule rounded-[2px] overflow-hidden">
            {[
              { label: 'Price', value: evidence.close == null ? '—' : `₹${evidence.close.toFixed(1)}`, foot: evidence.as_of ?? '', tone: 'neutral' as const },
              { label: 'VWAP · 1Y anchor', value: evidence.vwap_252 == null ? '—' : `₹${evidence.vwap_252.toFixed(0)}`,
                foot: evidence.vwap_dist == null ? '252-session' : `${evidence.vwap_dist >= 0 ? '+' : ''}${evidence.vwap_dist.toFixed(1)}% from VWAP`,
                tone: (evidence.vwap_dist == null ? 'neutral' : evidence.vwap_dist >= 0 ? 'pos' : 'neg') as 'pos' | 'neg' | 'neutral' },
              { label: 'P/E · TTM', value: evidence.pe_ttm == null ? '—' : `${evidence.pe_ttm.toFixed(1)}×`, foot: evidence.eps_ttm == null ? 'no TTM EPS' : `TTM EPS ₹${evidence.eps_ttm.toFixed(1)}`, tone: 'neutral' as const },
              { label: '52-week range', value: evidence.pos_52w == null ? '—' : `${evidence.pos_52w.toFixed(0)}%`, foot: 'position low→high', tone: 'neutral' as const },
              { label: 'RSI(14)', value: evidence.rsi == null ? '—' : evidence.rsi.toFixed(0), foot: 'momentum', tone: 'neutral' as const },
            ].map(t => (
              <div key={t.label} className="bg-paper px-4 py-3">
                <div className="font-sans text-[9px] uppercase tracking-[0.16em] text-ink-tertiary mb-1 font-semibold">{t.label}</div>
                <div className={`font-mono text-[20px] leading-none tabular-nums ${t.tone === 'pos' ? 'text-signal-pos' : t.tone === 'neg' ? 'text-signal-neg' : 'text-ink-primary'}`}>{t.value}</div>
                <div className="font-sans text-[10px] text-ink-tertiary mt-1">{t.foot}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Lens decile card (centerpiece) ── */}
      {decile ? (
        <StockLensCardV4 decile={decile} metrics={evidence} />
      ) : (
        <section className="px-8 py-9 border-b border-paper-rule">
          <p className="font-sans text-[13px] text-ink-tertiary italic">No lens scores recorded for {stock.symbol}.</p>
        </section>
      )}

      {/* ── RS matrix (always on) ── */}
      {rsMatrix && <StockRSMatrix matrix={rsMatrix} />}

      {/* ── Native EMA charts: price + RS ── */}
      {chartRows.length > 0 && (
        <>
          <StockPriceEMAChart rows={chartRows} symbol={stock.symbol} />
          <StockRSChart rows={chartRows} symbol={stock.symbol} />
        </>
      )}

      {/* ── TV Technical Analysis ── */}
      <section className="px-8 py-6 border-b border-paper-rule">
        <p className="font-mono text-[10px] uppercase tracking-wider text-ink-tertiary mb-3">
          TradingView Composite Technical Analysis — multi-timeframe consensus
        </p>
        <div className="border border-paper-rule rounded-[2px] overflow-hidden bg-paper">
          <TVTechnicalAnalysis symbol={stock.symbol} interval="1D" />
        </div>
      </section>

      {/* ── Quarterly financials (native XBRL — replaces the TV Financials widget) ── */}
      <StockFundamentalsTable quarters={fundamentals} />

      {/* ── Corporate announcements (native filings — replaces TV "Top Stories") ── */}
      <StockAnnouncementsPanel filings={announcements} />

      {/* ── TV Company profile (collapsed) ── */}
      <section className="px-8 py-6 border-b border-paper-rule">
        <details className="font-sans text-[12px] text-ink-tertiary border border-paper-rule rounded-[2px] p-3 bg-paper">
          <summary className="cursor-pointer text-teal font-medium select-none">
            Show company profile (about, sector, employees, IPO)
          </summary>
          <div className="pt-3">
            <TVCompanyProfile symbol={stock.symbol} />
          </div>
        </details>
      </section>

      <div className="px-8 py-6 font-sans text-[12px] text-ink-tertiary leading-[1.6]">
        Native from <strong className="text-ink-secondary">foundation_staging</strong> — lens journal, technical_daily, ohlcv_stock; TradingView for the live instrument view.{' '}
        {sector && <Link href={`/sectors/${encodeURIComponent(sector)}`} className="text-teal hover:underline">← Back to {sector}</Link>}
      </div>
    </div>
  )
}
