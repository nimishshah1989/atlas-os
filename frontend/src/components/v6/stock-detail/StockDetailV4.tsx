// allow-large: v4 stock detail page assembles the lens card, RS matrix, the two native
// EMA charts, and the kept TV widgets + Weinstein lifecycle into one ordered page. Each
// section is a single-line render; splitting into sub-shells would obscure the page contract.
// StockDetailV4 — the v4 stock detail page (behind LENS_V4). Lens-first, native
// foundation_staging. Drops the trader-view verdict header, conviction decomposition,
// and gates/confidence cruft. Keeps the TV Advanced chart, TV technical/financials/
// news/profile widgets, and the Weinstein lifecycle panel from the old detail page.
import Link from 'next/link'
import { notFound } from 'next/navigation'

import { getStockBySymbol, getStockMetricHistory } from '@/lib/queries/stocks'
import { getStockState } from '@/lib/queries/states'
import { toNumber } from '@/lib/v6/decimal'
import { getStockDecile, getStockRSMatrix, getStockChartSeries } from '@/lib/queries/v6/stock_lens'

import { StockLensCardV4 } from './StockLensCardV4'
import { StockRSMatrix } from './StockRSMatrix'
import { StockPriceEMAChart } from './StockPriceEMAChart'
import { StockRSChart } from './StockRSChart'
import { LifecyclePanel } from './LifecyclePanel'
import { TVTechnicalAnalysis, TVFinancials, TVCompanyProfile, TVNews } from './TVWidgets'

const CAP_LABEL: Record<string, string> = { large: 'Large-cap', mid: 'Mid-cap', small: 'Small-cap', micro: 'Micro-cap' }

export async function StockDetailV4({ symbol }: { symbol: string }) {
  // Batch 1 — core stock + lens + RS matrix (Supabase session pooler caps clients at 15).
  const [stock, decile, rsMatrix] = await Promise.all([
    getStockBySymbol(symbol),
    getStockDecile(symbol).catch(() => null),
    getStockRSMatrix(symbol).catch(() => null),
  ])
  if (!stock) notFound()

  // Batch 2 — chart series + Weinstein inputs (released batch-1 connections first).
  const [chartRows, stockState, metricHistory] = await Promise.all([
    getStockChartSeries(symbol, 5).catch(() => []),
    getStockState(stock.instrument_id).catch(() => null),
    getStockMetricHistory(stock.instrument_id, 365).catch(() => []),
  ])

  const latest = metricHistory.length > 0 ? metricHistory[metricHistory.length - 1] : null

  const capLabel = decile?.cap ? (CAP_LABEL[decile.cap] ?? decile.cap) : null
  const sector = stock.sector ?? decile?.sector ?? null
  const name = stock.company_name ?? decile?.name ?? stock.symbol

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

      {/* ── Lens decile card (centerpiece) ── */}
      {decile ? (
        <StockLensCardV4 decile={decile} />
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

      {/* ── Weinstein lifecycle ── */}
      <LifecyclePanel
        state={stockState?.state ?? null}
        dwellDays={stockState?.dwell_days ?? null}
        ema20Ratio={toNumber(latest?.ema_20_ratio)}
        volRatio63={toNumber(latest?.vol_ratio_63)}
        extensionPct={toNumber(latest?.extension_pct)}
      />

      {/* ── TV Technical Analysis ── */}
      <section className="px-8 py-6 border-b border-paper-rule">
        <p className="font-mono text-[10px] uppercase tracking-wider text-ink-tertiary mb-3">
          TradingView Composite Technical Analysis — multi-timeframe consensus
        </p>
        <div className="border border-paper-rule rounded-[2px] overflow-hidden bg-paper">
          <TVTechnicalAnalysis symbol={stock.symbol} interval="1D" />
        </div>
      </section>

      {/* ── TV Financials ── */}
      <section className="px-8 py-6 border-b border-paper-rule">
        <p className="font-mono text-[10px] uppercase tracking-wider text-ink-tertiary mb-3">
          Financial Statements — revenue, EBITDA, EPS over time
        </p>
        <div className="border border-paper-rule rounded-[2px] overflow-hidden bg-paper">
          <TVFinancials symbol={stock.symbol} />
        </div>
      </section>

      {/* ── TV News ── */}
      <section className="px-8 py-6 border-b border-paper-rule">
        <p className="font-mono text-[10px] uppercase tracking-wider text-ink-tertiary mb-3">
          Latest News — auto-updated from TradingView
        </p>
        <div className="border border-paper-rule rounded-[2px] overflow-hidden bg-paper">
          <TVNews symbol={stock.symbol} />
        </div>
      </section>

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
