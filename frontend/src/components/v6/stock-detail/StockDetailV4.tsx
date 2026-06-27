// allow-large: v4 stock detail assembles header + price/VWAP StatCards + the six-lens
// DecileLadder (real numbers behind every score) + RS matrix + two theme-aware EMA charts
// + 8-quarter financials + corporate announcements + TV widgets into one ordered page.
// StockDetailV4 — lens-first, FULLY native foundation_staging (no atlas.* / public.de_* reads).
import Link from 'next/link'
import { notFound } from 'next/navigation'
import { unstable_cache } from 'next/cache'

import { getStockDecile, getStockRSMatrix, getStockChartSeries, getStockEvidence, getStockFundamentals, getStockAnnouncements, getStockHeader } from '@/lib/queries/v6/stock_lens'
import { getFundsHoldingStock } from '@/lib/queries/v6/funds_holding_stock'
import { getEtfsHoldingStock } from '@/lib/queries/v6/etfs_holding_stock'
import { getPolicyAlertsForStock } from '@/lib/queries/v6/policy_alerts'
import { getSectorCards } from '@/lib/queries/v6/sectors'
import { HeldByPanel } from './HeldByPanel'
import { PolicyAlertPanel } from './PolicyAlertPanel'
import { OwnSectorStrip } from './OwnSectorStrip'
import { StockFundamentalsTable } from './StockFundamentalsTable'
import { StockAnnouncementsPanel } from './StockAnnouncementsPanel'
import { StockRSMatrix } from './StockRSMatrix'
import { StockPriceEMAChart } from './StockPriceEMAChart'
import { StockRSChart } from './StockRSChart'
import { TVTechnicalAnalysis, TVCompanyProfile } from './TVWidgets'
import { DecileLadder } from '@/components/v4/ui/DecileLadder'
import { StatCard, type Tone } from '@/components/v4/ui/StatCard'
import { stockToLadder } from '@/components/v4/adapters/stockToLadder'
import { stockToDerivation } from '@/components/v4/adapters/stockToDerivation'
import { ScoreDerivationTree } from '@/components/v6/shared/ScoreDerivationTree'

const CAP_LABEL: Record<string, string> = { large: 'Large-cap', mid: 'Mid-cap', small: 'Small-cap', micro: 'Micro-cap' }
const SECTION = 'px-8 py-8 border-b border-edge-hair'

// The route reads searchParams (legacy path) → forced dynamic → not ISR-cached. So we
// cache each daily-stable query for 5 min: the DB is hit once per stock per 5 min, not
// on every request → the page renders in <2s. Key includes the symbol/iid.
function cached<T>(fn: () => Promise<T>, key: string): Promise<T> {
  return unstable_cache(fn, [key], { revalidate: 3600 })()
}

export async function StockDetailV4({ symbol }: { symbol: string }) {
  // Batch 1 — instrument header + lens + RS matrix (session pooler caps clients at 15).
  // Each fetch is independently caught so one transient DB/network failure degrades
  // to a clean 404 (header missing) or a missing section — never a 500 that takes
  // down the whole page. (S1: header had no .catch → a throw rejected Promise.all.)
  const [stock, decile, rsMatrix] = await Promise.all([
    cached(() => getStockHeader(symbol), `hdr:${symbol}`).catch(() => null),
    cached(() => getStockDecile(symbol), `dec:${symbol}`).catch(() => null),
    cached(() => getStockRSMatrix(symbol), `rsm:${symbol}`).catch(() => null),
  ])
  if (!stock) notFound()

  // Batch 2 — chart series + the REAL numbers (evidence), 8-quarter financials, announcements.
  const [chartRows, evidence, fundamentals, announcements, fundsHolding, etfsHolding, policyAlerts, sectorCards] = await Promise.all([
    cached(() => getStockChartSeries(symbol, 5), `chart:${symbol}`).catch(() => []),
    cached(() => getStockEvidence(symbol), `ev:${symbol}`).catch(() => null),
    cached(() => getStockFundamentals(symbol), `fnd:${symbol}`).catch(() => []),
    cached(() => getStockAnnouncements(symbol), `ann:${symbol}`).catch(() => []),
    cached(() => getFundsHoldingStock(stock.instrument_id), `fh:${stock.instrument_id}`).catch(() => []),
    cached(() => getEtfsHoldingStock(stock.instrument_id), `eh:${stock.instrument_id}`).catch(() => []),
    cached(() => getPolicyAlertsForStock(stock.sector ?? null), `pol:${stock.sector ?? 'none'}`).catch(() => []),
    cached(() => getSectorCards(), 'sectorcards').catch(() => []),
  ])
  // Own-sector index — the stock's own sector card (fresh mv_sector_cards), for context.
  const sectorCard = (stock.sector
    ? sectorCards.find((c) => c.sector_name === stock.sector)
    : null) ?? null

  const capLabel = decile?.cap ? (CAP_LABEL[decile.cap] ?? decile.cap) : null
  const sector = stock.sector ?? decile?.sector ?? null
  const name = stock.name ?? decile?.name ?? stock.symbol
  const ladder = decile ? stockToLadder(decile, evidence) : null
  const deriv = ladder ? stockToDerivation(stock.symbol, stock.name ?? null, ladder) : null
  // Glass-box: the exact conviction maths (FM 2026-06-26 — show the decile + composite
  // calculation, don't just print the result). Strength = mean of the 4 SCORED-lens
  // deciles (Technical / Fundamental / Catalyst / Flow); Valuation + Policy are shown
  // for context but not scored. `dOf` pulls each lens's real decile from the ladder.
  const dOf = (k: string) => ladder?.lenses.find((l) => l.key === k)?.decile ?? null
  const SCORED_LENSES: { k: string; label: string }[] = [
    { k: 'technical', label: 'Technical' }, { k: 'fundamental', label: 'Fundamental' },
    { k: 'catalyst', label: 'Catalyst' }, { k: 'flow', label: 'Flow' },
  ]
  const dStr = (k: string) => { const d = dOf(k); return d == null ? '—' : `D${d}` }

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

      {/* ── Own-sector index (context) ── */}
      <OwnSectorStrip card={sectorCard} symbol={stock.symbol} />

      {/* ── Six-lens DecileLadder (centerpiece) ── */}
      <section className={SECTION}>
        <div className="mb-4 flex items-end justify-between gap-4">
          <div>
            <p className="font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">Six-lens read</p>
            <h2 className="font-display text-[22px] font-medium tracking-tight text-txt-1">What the six lenses say</h2>
          </div>
          <Link href="/methodology" className="shrink-0 font-num text-[11px] text-brand hover:underline">How the lenses are scored ↗</Link>
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

        {/* ── How the decile & conviction are calculated (glass-box explainer) ── */}
        {ladder && (
          <details className="mt-5 rounded-tile border border-edge-hair bg-surface-panel px-4 py-3">
            <summary className="cursor-pointer select-none font-num text-[11px] font-semibold uppercase tracking-wider text-txt-2">
              How the decile &amp; conviction are calculated
            </summary>
            <div className="space-y-3 pt-3 font-sans text-[13px] leading-[1.55] text-txt-2">
              <p>
                <strong className="text-txt-1">Decile</strong> — each lens&rsquo;s 0&ndash;100 score is ranked against every{' '}
                <strong className="text-txt-1">{ladder.cohortLabel}</strong> stock in the universe. D10 = top 10% (strongest),
                D1 = bottom 10%. A decile is simply where this stock sits versus its size-peers on that lens &mdash; no weighting, no black box.
              </p>
              <p>
                <strong className="text-txt-1">Conviction</strong> — the average of the four <em>scored</em>-lens deciles:
              </p>
              <div className="rounded-tile border border-edge-hair bg-surface-inset px-3 py-2 font-num text-[14px] tabular-nums text-txt-1">
                ( {SCORED_LENSES.map((l) => dStr(l.k)).join(' + ')} ) ÷ 4 ={' '}
                <strong className="text-txt-1">{ladder.strength != null ? ladder.strength.toFixed(1) : '—'}</strong>
                <span className="ml-2 font-sans text-[11px] text-txt-3">
                  ({SCORED_LENSES.map((l) => l.label).join(' · ')})
                </span>
              </div>
              <p className="text-txt-3">
                <strong>Valuation</strong> and <strong>Policy</strong> are shown for context but are <strong>not</strong> scored into
                conviction (FM-locked methodology). Full detail on the{' '}
                <Link href="/methodology" className="text-brand hover:underline">methodology page ↗</Link>.
              </p>
            </div>
          </details>
        )}
      </section>

      {/* ── Score derivation tree (canonical glass-box: composite → lens → sub-component → variable) ── */}
      {deriv && (
        <section className={SECTION}>
          <div className="mb-4">
            <p className="font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">Glass box</p>
            <h2 className="font-display text-[22px] font-medium tracking-tight text-txt-1">How the score is built</h2>
            <p className="mt-1 max-w-[760px] font-sans text-[13px] text-txt-2">
              Click a lens to expand its sub-components, then drill to the actual values. The eye icon on any term explains it.
            </p>
          </div>
          <ScoreDerivationTree root={deriv} />
        </section>
      )}

      {/* ── Policy as a RAG sector-policy alert (NOT a score) ── */}
      <PolicyAlertPanel alerts={policyAlerts} sector={stock.sector ?? null} />

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

      {/* ── Ownership: which funds & ETFs hold this stock (closes the nav loop) ── */}
      <HeldByPanel funds={fundsHolding} etfs={etfsHolding} symbol={stock.symbol} />

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
