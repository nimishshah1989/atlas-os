// src/components/entity/InstrumentDetailView.tsx — one instrument, two columns (7/5). The score
// leads, because it is what the reader came for and what the board's ranking is asserting: the
// composite, where it puts the instrument in its peer group, and the derivation down to the
// sub-scores. Then identity on the left (facts, SEC ids, vendor spellings, index membership for a
// stock) and, on the right, what ohlcv_daily actually holds. No series, no placeholder numbers.
import { Section } from '@/components/ui/Section'
import { SEC_KIND_LABEL, secIdentityKind } from '@/lib/facts'
import { formatAsOf, formatIsoDate, formatPct } from '@/lib/format'
import type { FundHoldings } from '@/lib/queries/holdings'
import type { InstrumentDetail, SymbolAlias } from '@/lib/queries/instruments'
import type { Classification, ScoreDetail } from '@/lib/queries/scores'
import { BarsProvenance } from './BarsProvenance'
import { ClassificationCard } from './ClassificationCard'
import { EntityHeader } from './EntityHeader'
import { FactList, type Fact } from './FactList'
import { HoldingsSection } from './HoldingsSection'
import { MembershipTimeline } from './MembershipTimeline'
import { ScoreSection } from './ScoreSection'

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

// What each price instrument will show and what it is built from. They arrive with the price
// spine (labelled bars + the nightly technicals); nothing is drawn from unlabelled bars.
const SLOTS = [
  { title: 'Price chart', text: 'Adjusted and total-return closes with SPY as the overlay, from the spine’s labelled bars.' },
  { title: 'Relative strength', text: 'Strength against SPY over 1 week to 12 months, from the nightly technicals on total-return closes.' },
  { title: 'Return calculator', text: 'Two dates in; the total return, the price return and SPY’s over the same window out, from total-return closes.' },
]

export function InstrumentDetailView({
  d,
  score,
  classification,
  holdings,
}: {
  d: InstrumentDetail
  score: ScoreDetail | null
  classification: Classification | null
  holdings: FundHoldings
}) {
  const f = d.facts
  const stock = f.asset_class === 'stock'
  const identitySource = `${IDENTITY_SOURCE[f.source] ?? f.source}, as of ${formatAsOf(new Date(f.updated_at))}`
  const anchor = d.eod ? `EOD ${formatIsoDate(d.eod)}` : `${formatIsoDate(d.as_of)} (no price session yet)`
  const exchange = f.exchange ?? 'exchange not recorded'

  const facts: Fact[] = [
    { label: 'Listed', value: f.listing_date ? formatIsoDate(f.listing_date) : 'not recorded', source: identitySource },
    { label: 'Exchange', value: exchange, source: identitySource },
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
    { label: 'CIK', value: f.cik ?? 'none', source: identitySource },
  ]
  if (kind === 'series_class') {
    secFacts.push({ label: 'Series', value: f.series_id ?? 'none', source: identitySource })
    secFacts.push({ label: 'Class', value: f.class_id ?? 'none', source: identitySource })
  }

  return (
    <div className="page">
      <EntityHeader
        name={f.name ?? f.symbol}
        line={
          <>
            <span className="font-medium text-ink">{f.symbol}</span> on {exchange}, {stock ? 'a stock' : 'an ETF'}
            {f.listing_date && ` listed ${formatIsoDate(f.listing_date)}`}
          </>
        }
        facts={facts}
      />

      <ScoreSection assetClass={f.asset_class} symbol={f.symbol} score={score} eod={d.eod} />

      <div className="detail">
        <div>
          <Section title="Identity" note="as the SEC and the vendors spell it">
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
          <Section title="Prices" note="arrive with the price spine">
            <ul className="slots">
              {SLOTS.map((s) => (
                <li key={s.title} className="slot">
                  <p className="font-medium text-body text-ink">{s.title}</p>
                  <p className="mt-1 text-body text-ink-2">{s.text}</p>
                </li>
              ))}
            </ul>
          </Section>
          <Section title="Bars" note="what ohlcv_daily holds">
            <BarsProvenance bars={d.bars} symbol={f.symbol} />
          </Section>
        </div>
      </div>
    </div>
  )
}
