// src/components/entity/InstrumentDetailView.tsx — one instrument, two columns (7/5). The score
// leads, because it is what the reader came for and what the board's ranking is asserting: Atlas's
// DecileLadder, composite and decile in its header tiles and one collapsible row per lens down to
// the sub-scores. Then identity on the left (facts, SEC ids, vendor spellings, index membership
// for a stock) and, on the right, what ohlcv_daily actually holds. No series, no placeholder
// numbers, and every fact's source said ONCE rather than on every row.
import { Section } from '@/components/ui/Section'
import { SEC_KIND_LABEL, secIdentityKind } from '@/lib/facts'
import { formatAsOf, formatIsoDate, formatPct } from '@/lib/format'
import type { FundHoldings } from '@/lib/queries/holdings'
import type { InstrumentDetail, SymbolAlias } from '@/lib/queries/instruments'
import type { Classification, ScoreDetail } from '@/lib/queries/scores'
import type { InstrumentSeries } from '@/lib/queries/series'
import { BarsProvenance } from './BarsProvenance'
import { ClassificationCard } from './ClassificationCard'
import { EntityHeader } from './EntityHeader'
import { FactList, type Fact } from './FactList'
import { HoldingsSection } from './HoldingsSection'
import { MembershipTimeline } from './MembershipTimeline'
import { PriceSection } from './PriceSection'
import { ReturnCalculator } from './ReturnCalculator'
import { ScoreSection } from './ScoreSection'
import { StrengthSection } from './StrengthSection'

const IDENTITY_SOURCE: Record<string, string> = { nasdaq_trader: 'Nasdaq Trader directory', stooq: 'Stooq archive', alpaca: 'Alpaca', manual: 'Manual' }
const ALIAS_SOURCE: Record<string, string> = {
  nasdaq_symbol: 'Nasdaq symbol directory', cqs: 'CQS symbol directory', sec: 'SEC', stooq: 'Stooq', tiingo: 'Tiingo', alpaca: 'Alpaca', manual: 'Manual',
}

function AliasTable({ aliases }: { aliases: SymbolAlias[] }) {
  if (aliases.length === 0) return <p className="text-body text-ink-2">No vendor spelling recorded in symbol_alias.</p>
  const noted = aliases.some((a) => a.note)
  return (
    <div className="panel overflow-x-auto">
      <table className="tbl">
        <thead>
          <tr>
            <th>Source</th>
            <th>Spelling</th>
            <th>Valid from</th>
            <th>Valid to</th>
            {noted && <th>Note</th>}
          </tr>
        </thead>
        <tbody>
          {aliases.map((a) => (
            <tr key={`${a.source}-${a.source_symbol}-${a.valid_from}`}>
              <td>{ALIAS_SOURCE[a.source] ?? a.source}</td>
              <td className="font-medium text-ink">{a.source_symbol}</td>
              <td className="num">{formatIsoDate(a.valid_from)}</td>
              <td className="num">{a.valid_to ? formatIsoDate(a.valid_to) : 'current'}</td>
              {noted && <td className="text-ink-2">{a.note ?? ''}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function InstrumentDetailView({
  d,
  score,
  classification,
  holdings,
  series,
}: {
  d: InstrumentDetail
  score: ScoreDetail | null
  classification: Classification | null
  holdings: FundHoldings
  series: InstrumentSeries
}) {
  const f = d.facts
  const stock = f.asset_class === 'stock'
  const identitySource = `${IDENTITY_SOURCE[f.source] ?? f.source}, as of ${formatAsOf(new Date(f.updated_at))}`
  const anchor = d.eod ? `EOD ${formatIsoDate(d.eod)}` : `${formatIsoDate(d.as_of)} (no price session yet)`
  const exchange = f.exchange ?? 'exchange not recorded'

  // `identitySource` used to sit on EVERY row of both lists — the same 45 characters, five times
  // down one column. It is a fact and it stays, but it is said ONCE: on the identity line here and
  // in the Identity section's note below. A row keeps a source only where its source DIFFERS.
  const facts: Fact[] = [
    { label: 'Listed', value: f.listing_date ? formatIsoDate(f.listing_date) : 'not recorded' },
    { label: 'Exchange', value: exchange },
  ]
  if (stock) {
    facts.push({ label: 'S&P 500', value: f.sp500 ? 'Member' : 'Not a member', source: `index_membership at ${anchor}` })
    if (f.sp500) {
      facts.push({
        label: 'SPY weight',
        value: f.spy_weight != null ? <span className="num">{formatPct(f.spy_weight, 2)}</span> : 'not in the current SSGA row',
        source: 'SSGA weekly holdings, current row',
      })
    }
    if (f.sector_gics) facts.push({ label: 'GICS sector', value: f.sector_gics, source: 'Select Sector SPDR membership' })
  }

  const kind = secIdentityKind(f)
  const secFacts: Fact[] = [
    { label: 'SEC identity', value: SEC_KIND_LABEL[kind], source: 'derived from the ids below' },
    { label: 'CIK', value: f.cik ?? 'none' },
  ]
  if (kind === 'series_class') {
    secFacts.push({ label: 'Series', value: f.series_id ?? 'none' })
    secFacts.push({ label: 'Class', value: f.class_id ?? 'none' })
  }

  return (
    <div className="page">
      <EntityHeader
        name={f.name ?? f.symbol}
        line={
          <span title={identitySource}>
            <span className="font-medium text-ink">{f.symbol}</span> on {exchange}, {stock ? 'a stock' : 'an ETF'}
            {f.listing_date && ` listed ${formatIsoDate(f.listing_date)}`}
          </span>
        }
        facts={facts}
      />

      <ScoreSection assetClass={f.asset_class} symbol={f.symbol} score={score} eod={d.eod} />

      <PriceSection series={series} symbol={f.symbol} />
      <StrengthSection technical={series.technical} symbol={f.symbol} />
      <ReturnCalculator series={series} symbol={f.symbol} />

      <div className="detail">
        <div>
          <Section title="Identity" note={identitySource}>
            <FactList facts={secFacts} />
            <div className="mt-4">
              <AliasTable aliases={d.aliases} />
            </div>
          </Section>
          {stock ? (
            <Section title="S&P 500 membership" note="every recorded interval">
              <MembershipTimeline intervals={d.membership} />
            </Section>
          ) : (
            <>
              <ClassificationCard c={classification} />
              <HoldingsSection data={holdings} symbol={f.symbol} />
            </>
          )}
        </div>

        <div>
          <Section title="Bars" note="what ohlcv_daily holds">
            <BarsProvenance bars={d.bars} symbol={f.symbol} />
          </Section>
        </div>
      </div>
    </div>
  )
}
