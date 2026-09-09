// src/components/entity/HoldingsSection.tsx — what the fund holds, from its own SEC filing.
//
// EVERY FIGURE CARRIES THE SNAPSHOT'S DATE, ONCE, AT THE TOP. Form N-PORT-P is public about
// sixty days after the third month of a filer's fiscal quarter, so nothing here is today's and
// the page must not let a reader assume it is.
//
// A MULTI-CLASS SERIES GETS NO AUM. The filing's net assets are the SERIES' — VOO is one of four
// share classes of a fund whose filed assets are the whole thing — so the ingest leaves aum_usd
// null there and the card says which fund the figure belongs to instead of printing a number
// that is not this one's.
import type { ReactNode } from 'react'
import { Section } from '@/components/ui/Section'
import { formatDecimal, formatIsoDate, formatPct, formatUsd } from '@/lib/format'
import type { FundHoldings, Weighted } from '@/lib/queries/holdings'
import { TOP_HOLDINGS } from '@/lib/queries/holdings'
import { FactList, type Fact } from './FactList'

/** N-PORT's own words for the buckets exposures sorts holdings into. */
const ASSET_LABEL: Record<string, string> = {
  equity: 'Equity',
  fixed_income: 'Fixed income',
  cash: 'Cash and short-term',
  derivative: 'Derivatives (marked)',
}

const SECTOR_LABEL: Record<string, string> = {
  energy: 'Energy',
  materials: 'Materials',
  industrials: 'Industrials',
  consumer_discretionary: 'Consumer Discretionary',
  consumer_staples: 'Consumer Staples',
  health_care: 'Health Care',
  financials: 'Financials',
  information_technology: 'Information Technology',
  communication_services: 'Communication Services',
  utilities: 'Utilities',
  real_estate: 'Real Estate',
}

function num(value: string | null | undefined, decimals = 2): ReactNode {
  return value == null ? <span className="text-ink-3">—</span> : <span className="num">{formatPct(value, decimals)}</span>
}

/** A weight vector as labelled bars, heaviest first. Shows what is attributed, never a total
 *  scaled to 100: a fund 97 per cent in one country and 3 per cent in cash reads 97. */
function WeightBars({ rows, label, empty }: { rows: Weighted[]; label: (k: string) => string; empty: string }) {
  if (rows.length === 0) return <p className="text-body text-ink-2">{empty}</p>
  const widest = Math.max(...rows.map((r) => Math.abs(Number(r.weight))), 0.0001)
  return (
    <ul className="mt-1 space-y-1.5">
      {rows.slice(0, 8).map((r) => (
        <li key={r.key} className="grid grid-cols-[9rem_1fr_4rem] items-center gap-2">
          <span className="truncate text-meta text-ink-2">{label(r.key)}</span>
          <span className="h-2 rounded-sm bg-rule/40">
            <span
              className="block h-2 rounded-sm bg-accent/70"
              style={{ width: `${Math.min(100, (Math.abs(Number(r.weight)) / widest) * 100)}%` }}
            />
          </span>
          <span className="num text-right text-meta text-ink">{formatPct(r.weight, 1)}</span>
        </li>
      ))}
      {rows.length > 8 && <li className="text-meta text-ink-3">and {rows.length - 8} more</li>}
    </ul>
  )
}

export function HoldingsSection({ data, symbol }: { data: FundHoldings; symbol: string }) {
  const { meta, exposure, holdings } = data
  if (!meta && !exposure) {
    return (
      <Section title="What it holds" note="SEC Form N-PORT-P">
        <p className="panel px-4 py-3 text-body text-ink-2">
          No filing has been read for {symbol} yet. Holdings arrive from the fund&rsquo;s own N-PORT-P,
          which the SEC publishes about sixty days after the third month of each filer&rsquo;s fiscal
          quarter — and a unit investment trust (SPY among them) never files one at all.
        </p>
      </Section>
    )
  }

  const asOf = exposure ? formatIsoDate(exposure.as_of_date) : meta?.aum_as_of ? formatIsoDate(meta.aum_as_of) : null
  const filedSource = asOf ? `N-PORT-P, holdings as of ${asOf}` : 'N-PORT-P'
  const multiClass = (meta?.series_class_count ?? 1) > 1

  const facts: Fact[] = []
  if (meta) {
    facts.push({
      label: 'Net assets',
      value: meta.aum_usd ? (
        <span className="num">{formatUsd(meta.aum_usd, 0)}</span>
      ) : (
        <span className="text-ink-2">not this share class&rsquo;s to report</span>
      ),
      source: meta.aum_usd ? filedSource : `the series has ${meta.series_class_count} share classes`,
    })
    if (multiClass && meta.series_net_assets_usd) {
      facts.push({
        label: 'Whole fund',
        value: <span className="num">{formatUsd(meta.series_net_assets_usd, 0)}</span>,
        source: `every share class of the series, ${filedSource}`,
      })
    }
    facts.push({
      label: 'In derivatives',
      value: num(meta.derivatives_share, 2),
      source: 'share of net assets, at the mark',
    })
    facts.push({
      label: 'Derivative notional',
      value: num(meta.derivative_notional_share, 2),
      source: 'what the derivatives control ÷ net assets — the gearing evidence',
    })
  }
  if (exposure) {
    facts.push({ label: 'Holdings', value: <span className="num">{formatDecimal(String(exposure.n_holdings), 0)}</span>, source: filedSource })
    facts.push({ label: 'Top ten', value: num(exposure.top10_w, 1), source: 'share of the fund in its ten largest positions' })
    facts.push({ label: 'Weights sum to', value: num(exposure.sum_abs_weight, 2), source: 'a plain fund reads near 100 percent' })
    facts.push({
      label: 'Look-through',
      value: num(exposure.lookthrough_scored_w, 1),
      source: 'the share held in stocks Atlas itself scores',
    })
  }

  return (
    <Section title="What it holds" note={asOf ? `SEC Form N-PORT-P, as of ${asOf}` : 'SEC Form N-PORT-P'}>
      <FactList facts={facts} />

      {exposure && (
        <div className="mt-5 grid gap-5 sm:grid-cols-2">
          <div>
            <p className="text-meta text-ink-3">By asset class</p>
            <WeightBars
              rows={exposure.asset}
              label={(k) => ASSET_LABEL[k] ?? k}
              empty="The filing gave no asset category."
            />
          </div>
          <div>
            <p className="text-meta text-ink-3">By country of the holding</p>
            <WeightBars
              rows={exposure.country}
              label={(k) => k}
              empty="No holding named a country."
            />
          </div>
          <div className="sm:col-span-2">
            <p className="text-meta text-ink-3">
              By sector, through the holdings Atlas scores
              {exposure.sector.length === 0 && ' — none of them, here'}
            </p>
            <WeightBars
              rows={exposure.sector}
              label={(k) => SECTOR_LABEL[k] ?? k}
              empty="No holding resolved to a scored S&P 500 stock, so this fund has no sector read. That is the look-through's honest bound, not a gap in the filing."
            />
          </div>
        </div>
      )}

      {holdings.length > 0 && (
        <div className="mt-6 overflow-x-auto">
          <p className="text-meta text-ink-3">
            The {holdings.length} largest positions of {exposure?.n_holdings ?? holdings.length}
            {(exposure?.n_holdings ?? 0) > TOP_HOLDINGS && ` — the rest are in the filing, not on this page`}
          </p>
          <table className="mt-2 w-full text-body">
            <thead>
              <tr className="text-meta text-ink-3">
                <th className="py-1 text-left font-normal">Holding</th>
                <th className="py-1 text-left font-normal">Ticker</th>
                <th className="py-1 text-left font-normal">Country</th>
                <th className="py-1 text-left font-normal">Kind</th>
                <th className="py-1 text-right font-normal">Weight</th>
                <th className="py-1 text-right font-normal">Value</th>
              </tr>
            </thead>
            <tbody>
              {holdings.map((h) => (
                <tr key={h.holding_key} className="border-t border-rule/60">
                  <td className="max-w-[22rem] truncate py-1.5 pr-3 text-ink">{h.name ?? h.holding_key}</td>
                  <td className="py-1.5 pr-3 text-ink-2">{h.held_symbol ?? h.ticker ?? '—'}</td>
                  <td className="py-1.5 pr-3 text-ink-2">{h.country_iso2 ?? '—'}</td>
                  <td className="py-1.5 pr-3 text-ink-2">
                    {h.derivative_category ?? h.asset_category ?? '—'}
                  </td>
                  <td className="num py-1.5 pr-3 text-right text-ink">{formatPct(h.weight_frac, 2)}</td>
                  <td className="num py-1.5 text-right text-ink-2">{formatUsd(h.market_value_usd, 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  )
}
