// src/components/pulse/PulseView.tsx — what the market is doing, counted rather than indexed.
//
// THE ONE IDEA. The S&P 500 is capitalisation-weighted: seven companies can carry it while four
// hundred fall. So this page never prints an index level. It prints how many members are above
// their 200-day average, how many are beating SPY, how many sit at a 52-week high — the readings
// that say whether a move is broad or narrow, which is the only version of "what is the market
// doing" an FM can act on.
//
// EVERY SHARE IS OVER WHAT WAS MEASURED, never over what was listed. See BreadthBar.
import Link from 'next/link'
import { BreadthBar } from '@/components/pulse/BreadthBar'
import { Section } from '@/components/ui/Section'
import { formatIsoDate, formatNum, formatPct } from '@/lib/format'
import { BEATING, breadthHref, POS52, POS52_KEY, RS12_KEY, RS3_KEY, TREND, TREND_KEY } from '@/lib/breadth'
import type { Pulse } from '@/lib/queries/pulse'
import { shareTint } from '@/lib/tone'

const POPULATION: Record<string, { title: string; note: string; market: '/etfs' | '/sp500' }> = {
  stock: { title: 'The S&P 500', note: 'current members, from the SSGA holdings file', market: '/sp500' },
  etf: { title: 'The board’s ETFs', note: 'above the liquidity floor, neither leveraged nor inverse', market: '/etfs' },
}

function Pct({ value, decimals = 1 }: { value: string | null; decimals?: number }) {
  return value == null ? <span className="text-ink-3">—</span> : <span className="num">{formatPct(value, decimals)}</span>
}

export function PulseView({ pulse }: { pulse: Pulse }) {
  const { breadth, sectors, macro } = pulse

  if (breadth.length === 0) {
    return (
      <p
        className="panel px-4 py-3 text-body text-ink-2"
        title="Counting one without the other would count over the wrong population, so nothing is counted."
      >
        Breadth needs the universe snapshot and the nightly technicals for the same session; one of
        them has not run for {pulse.eod ? formatIsoDate(pulse.eod) : 'this session'}.
      </p>
    )
  }

  return (
    <>
      {macro && (
        <Section title="The backdrop" note={`FRED, ${formatIsoDate(macro.date)}`}>
          <dl className="facts">
            <div className="fact">
              <dt className="text-meta text-ink-3">Volatility index</dt>
              <dd className="text-body text-ink">
                {macro.vixcls == null ? <span className="text-ink-3">—</span> : <span className="num text-section">{Number(macro.vixcls).toFixed(2)}</span>}
              </dd>
              <dd className="fact-src text-meta text-ink-3">CBOE VIX close</dd>
            </div>
            <div className="fact">
              <dt className="text-meta text-ink-3">10-year Treasury</dt>
              <dd className="text-body text-ink">
                {macro.dgs10 == null ? <span className="text-ink-3">—</span> : <span className="num text-section">{Number(macro.dgs10).toFixed(2)}</span>}
              </dd>
              <dd className="fact-src text-meta text-ink-3">percent a year, constant maturity</dd>
            </div>
            <div className="fact">
              <dt className="text-meta text-ink-3">3-month bill</dt>
              <dd className="text-body text-ink">
                {macro.dtb3 == null ? <span className="text-ink-3">—</span> : <span className="num text-section">{Number(macro.dtb3).toFixed(2)}</span>}
              </dd>
              <dd className="fact-src text-meta text-ink-3">the risk-free rate every Sharpe here uses</dd>
            </div>
            <div className="fact">
              <dt className="text-meta text-ink-3">Dollar</dt>
              <dd className="text-body text-ink">
                {macro.dtwexbgs == null ? <span className="text-ink-3">—</span> : <span className="num text-section">{Number(macro.dtwexbgs).toFixed(1)}</span>}
              </dd>
              <dd className="fact-src text-meta text-ink-3">broad trade-weighted index</dd>
            </div>
          </dl>
        </Section>
      )}

      {breadth.map((b) => {
        const p = POPULATION[b.asset_class]
        if (!p) return null
        // EVERY ROW IS A DOOR. The bar's count and the board's filtered count are the same query
        // shape over the same column (src/lib/breadth.ts), so what is counted here is what opens.
        const door = (key: string, value: string) => breadthHref(p.market, key, value)
        return (
          <Section key={b.asset_class} title={p.title} href={p.market} note={`${formatNum(b.members)} members — ${p.note}`}>
            <div className="panel space-y-2 px-4 py-3">
              <BreadthBar label="Above the 200-day" href={door(TREND_KEY, TREND.above200)} count={b.above_ema200} measured={b.measured_ema200} note="An instrument with fewer than 200 sessions has no 200-day average and is not counted either way." />
              <BreadthBar label="Above the 50-day" href={door(TREND_KEY, TREND.above50)} count={b.above_ema50} measured={b.measured_ema50} />
              <BreadthBar label="Averages stacked up" href={door(TREND_KEY, TREND.stacked)} count={b.stacked_up} measured={b.measured_stack} note="21-day over 50-day over 200-day — the full uptrend shape." />
              <BreadthBar label="Beating SPY, 3 months" href={door(RS3_KEY, BEATING)} count={b.beating_3m} measured={b.measured_rs_3m} />
              <BreadthBar label="Beating SPY, 12 months" href={door(RS12_KEY, BEATING)} count={b.beating_12m} measured={b.measured_rs_12m} />
              <BreadthBar label="At a 52-week high" href={door(POS52_KEY, POS52.high)} count={b.near_high} measured={b.measured_52w} note="Within 2 percent of the top of its own 52-week range." />
              <BreadthBar label="At a 52-week low" href={door(POS52_KEY, POS52.low)} count={b.near_low} measured={b.measured_52w} note="Within 2 percent of the bottom of its own 52-week range." />
            </div>
            <p
              className="mt-1 text-meta text-ink-3"
              title="The median, not the average — one runaway does not move it."
            >
              Median member, 3-month total return: <Pct value={b.median_ret_3m} />
            </p>
          </Section>
        )
      })}

      {sectors.length > 0 && (
        <Section title="By sector" note="S&P 500 members, GICS level 1">
          <div className="panel overflow-x-auto">
            <table className="tbl">
              <thead>
                <tr>
                  <th>Sector</th>
                  <th className="text-right">Members</th>
                  <th className="text-right">Above the 200-day</th>
                  <th className="text-right">Beating SPY, 3m</th>
                  <th className="text-right">Median 3m</th>
                  <th className="text-right">Mean composite</th>
                </tr>
              </thead>
              <tbody>
                {[...sectors]
                  .sort((a, b) => share(b.above_ema200, b.measured_ema200) - share(a.above_ema200, a.measured_ema200))
                  .map((s) => (
                    <tr key={s.sector} className="hover:bg-raised">
                      <td className="text-ink">
                        {/* Into the drill-down, where the sector opens onto its themes and their
                            funds. The pulse names a sector; the sector board says what is in it. */}
                        {s.sector_id ? (
                          <Link href={`/sectors/${encodeURIComponent(s.sector_id)}`} className="hover:underline">
                            {s.sector}
                          </Link>
                        ) : (
                          s.sector
                        )}
                      </td>
                      <td className="num text-right text-ink-2">
                        <Link href={`/sp500?sector=${encodeURIComponent(s.sector)}`} className="hover:underline" title="Open the sector's members on the board">
                          {formatNum(s.members)}
                        </Link>
                      </td>
                      <td className="num text-right">
                        <Link href={breadthHref('/sp500', TREND_KEY, TREND.above200, { sector: s.sector })} className="hover:underline" title="Open exactly these members">
                          {fraction(s.above_ema200, s.measured_ema200)}
                        </Link>
                      </td>
                      <td className="num text-right">
                        <Link href={breadthHref('/sp500', RS3_KEY, BEATING, { sector: s.sector })} className="hover:underline" title="Open exactly these members">
                          {fraction(s.beating_3m, s.measured_rs_3m)}
                        </Link>
                      </td>
                      <td className="num text-right">
                        <Pct value={s.median_ret_3m} />
                      </td>
                      <td className="num text-right text-ink">
                        {s.mean_composite == null ? <span className="text-ink-3">—</span> : Number(s.mean_composite).toFixed(1)}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}
    </>
  )
}

const share = (count: number, measured: number) => (measured === 0 ? -1 : count / measured)

/** A share with HALF as its baseline: green when more of the population is doing the thing than
 *  is not, red when it is the other way. The count and its denominator are printed either way, so
 *  the colour is the second channel and never the only one (scores.ts rule 3). */
function fraction(count: number, measured: number) {
  if (measured === 0) return <span className="text-ink-3">—</span>
  const share = count / measured
  return (
    <span className="rounded-tile px-1 py-px text-ink" style={{ background: shareTint(share) }}>
      {(share * 100).toFixed(0)}%<span className="ml-1 text-ink-3">{count}/{measured}</span>
    </span>
  )
}
