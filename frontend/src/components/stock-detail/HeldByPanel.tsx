// "Held by" panel for the stock detail page — closes the navigation loop:
// stock → the funds & ETFs that hold it (reverse of the holdings drill).
// Pure server component. Real data only (atlas_foundation); empty = "not held".
import Link from 'next/link'
import type { FundHolding } from '@/lib/queries/funds_holding_stock'
import type { EtfHolding } from '@/lib/queries/etfs_holding_stock'
import { TermInfo } from '@/components/shared/TermInfo'

const SECTION = 'px-8 py-8 border-b border-edge-hair'

function gradeTone(g: string): string {
  if (g.startsWith('AAA') || g.startsWith('AA')) return 'text-sig-pos'
  if (g === 'A' || g.startsWith('BBB')) return 'text-txt-1'
  if (g === '—') return 'text-txt-3'
  return 'text-sig-warn'
}

export function HeldByPanel({ funds, etfs, symbol }: {
  funds: FundHolding[]
  etfs: EtfHolding[]
  symbol: string
}) {
  if (funds.length === 0 && etfs.length === 0) return null
  return (
    <section className={SECTION}>
      <div className="mb-4">
        <p className="font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">Ownership</p>
        <h2 className="font-display text-[22px] font-medium tracking-tight text-txt-1">Who holds {symbol}</h2>
      </div>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Funds */}
        <div>
          <p className="mb-2 font-num text-[10px] uppercase tracking-wider text-txt-3">
            Mutual funds holding {symbol} <span className="text-txt-2">({funds.length})</span>
          </p>
          {funds.length === 0 ? (
            <p className="font-sans text-[12px] italic text-txt-3">No tracked fund holds {symbol} ≥0.5%.</p>
          ) : (
            <table className="tbl-centered w-full font-num text-[12px]">
              <thead>
                <tr className="border-b border-edge-rule text-left text-[10px] uppercase tracking-wider text-txt-3">
                  <th className="py-1.5 font-semibold">Fund</th>
                  <th className="py-1.5 text-right font-semibold">Weight<TermInfo term="holding_weight" /></th>
                  <th className="py-1.5 text-right font-semibold">AUM ₹cr<TermInfo term="aum" /></th>
                  <th className="py-1.5 text-right font-semibold">Grade<TermInfo term="atlas_grade" /></th>
                </tr>
              </thead>
              <tbody>
                {funds.map((f) => (
                  <tr key={f.fund_code} className="border-b border-edge-hair/60">
                    <td className="py-1.5 pr-2">
                      <Link href={`/funds/${encodeURIComponent(f.fund_code)}`} className="text-brand hover:underline">{f.fund_name}</Link>
                    </td>
                    <td className="py-1.5 text-right tabular-nums text-txt-1">{Number(f.weight_pct).toFixed(2)}%</td>
                    <td className="py-1.5 text-right tabular-nums text-txt-2">{Number(f.aum_cr).toLocaleString('en-IN', { maximumFractionDigits: 0 })}</td>
                    <td className={`py-1.5 text-right font-semibold ${gradeTone(f.atlas_grade)}`}>{f.atlas_grade}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        {/* ETFs */}
        <div>
          <p className="mb-2 font-num text-[10px] uppercase tracking-wider text-txt-3">
            ETFs holding {symbol} <span className="text-txt-2">({etfs.length})</span>
          </p>
          {etfs.length === 0 ? (
            <p className="font-sans text-[12px] italic text-txt-3">No tracked ETF holds {symbol} ≥0.5%.</p>
          ) : (
            <table className="tbl-centered w-full font-num text-[12px]">
              <thead>
                <tr className="border-b border-edge-rule text-left text-[10px] uppercase tracking-wider text-txt-3">
                  <th className="py-1.5 font-semibold">ETF</th>
                  <th className="py-1.5 text-right font-semibold">Weight<TermInfo term="holding_weight" /></th>
                  <th className="py-1.5 text-right font-semibold">Grade<TermInfo term="atlas_grade" /></th>
                </tr>
              </thead>
              <tbody>
                {etfs.map((e) => (
                  <tr key={e.ticker} className="border-b border-edge-hair/60">
                    <td className="py-1.5 pr-2">
                      <Link href={`/etfs/${encodeURIComponent(e.ticker)}`} className="text-brand hover:underline">{e.etf_name}</Link>
                    </td>
                    <td className="py-1.5 text-right tabular-nums text-txt-1">{Number(e.weight_pct).toFixed(2)}%</td>
                    <td className={`py-1.5 text-right font-semibold ${gradeTone(e.atlas_grade)}`}>{e.atlas_grade}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </section>
  )
}
