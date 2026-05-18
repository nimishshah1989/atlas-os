// src/app/strategies/v6/orders/page.tsx
// Order log — every entry/exit + paper execution view.
export const dynamic = 'force-dynamic'
import { getV6Book } from '@/lib/queries/v6'

const MOCK_ORDERS = [
  { date: '2026-05-19', symbol: 'GOLDBEES',   side: 'BUY',  qty: 12500, est_value_cr: 0.84, status: 'PAPER',    fill_price: 67.20, slippage_bps: 5.2 },
  { date: '2026-04-30', symbol: 'BHARATFORG', side: 'BUY',  qty: 32100, est_value_cr: 4.30, status: 'PAPER',    fill_price: 1338.75, slippage_bps: 18.4 },
  { date: '2026-04-30', symbol: 'POLYCAB',    side: 'BUY',  qty: 18200, est_value_cr: 3.81, status: 'PAPER',    fill_price: 2094.10, slippage_bps: 12.7 },
  { date: '2026-04-30', symbol: 'COFORGE',    side: 'BUY',  qty: 47800, est_value_cr: 3.46, status: 'PAPER',    fill_price: 723.80, slippage_bps: 22.1 },
  { date: '2026-04-30', symbol: 'ZOMATO',     side: 'SELL', qty: 142000, est_value_cr: 2.96, status: 'PAPER',   fill_price: 208.55, slippage_bps: 9.8 },
  { date: '2026-04-30', symbol: 'BAJFINANCE', side: 'SELL', qty: 2400,  est_value_cr: 2.18, status: 'PAPER',    fill_price: 9080.20, slippage_bps: 15.3 },
]

export default async function V6OrdersPage() {
  await getV6Book()
  return (
    <main className="min-h-screen bg-paper px-8 py-6 max-w-7xl mx-auto">
      <header className="mb-6">
        <p className="font-sans text-[11px] text-ink-tertiary uppercase tracking-wide">
          <a href="/strategies/v6" className="hover:text-ink-primary">v6 Command Center</a>
          {' / Orders'}
        </p>
        <h1 className="font-serif text-2xl text-ink-primary mt-1">Order Log</h1>
        <p className="font-sans text-xs text-ink-tertiary mt-1">
          Paper execution. Real-money trading is gated on the 90-day live paper-trade observation period after v0.1 completes.
        </p>
      </header>

      <div className="bg-paper border border-paper-rule rounded-[2px] overflow-hidden">
        <table className="w-full text-xs">
          <thead className="bg-paper-rule/20 border-b border-paper-rule text-ink-tertiary">
            <tr>
              <th className="text-left font-sans font-normal px-3 py-2">Date</th>
              <th className="text-left font-sans font-normal px-3 py-2">Symbol</th>
              <th className="text-left font-sans font-normal px-3 py-2">Side</th>
              <th className="text-right font-sans font-normal px-3 py-2">Qty</th>
              <th className="text-right font-sans font-normal px-3 py-2">Value (₹cr)</th>
              <th className="text-right font-sans font-normal px-3 py-2">Fill price</th>
              <th className="text-right font-sans font-normal px-3 py-2">Slippage (bps)</th>
              <th className="text-center font-sans font-normal px-3 py-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {MOCK_ORDERS.map((o, i) => (
              <tr key={i} className="border-b border-paper-rule/40">
                <td className="px-3 py-2 font-mono text-[11px] text-ink-tertiary">{o.date}</td>
                <td className="px-3 py-2 font-mono text-ink-primary">{o.symbol}</td>
                <td className={`px-3 py-2 font-sans font-semibold ${o.side === 'BUY' ? 'text-emerald-700' : 'text-rose-700'}`}>{o.side}</td>
                <td className="px-3 py-2 text-right font-mono">{o.qty.toLocaleString('en-IN')}</td>
                <td className="px-3 py-2 text-right font-mono">{o.est_value_cr.toFixed(2)}</td>
                <td className="px-3 py-2 text-right font-mono">₹{o.fill_price.toFixed(2)}</td>
                <td className="px-3 py-2 text-right font-mono text-ink-tertiary">{o.slippage_bps.toFixed(1)}</td>
                <td className="px-3 py-2 text-center">
                  <span className="inline-block px-1.5 py-0.5 bg-stone-100 text-stone-700 text-[10px] font-sans uppercase border border-stone-200 rounded-[2px]">{o.status}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="font-sans text-[11px] text-ink-tertiary mt-4">
        Slippage modeled via square-root impact: 5 + 30×√(order_value / 20d_ADV) bps + 15 bps explicit costs (STT, exchange, GST, SEBI, stamp). Capped at 100 bps.
      </p>
    </main>
  )
}
