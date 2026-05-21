import { Sparkles } from 'lucide-react'
import type { StockRowWithSector } from '@/lib/queries/stocks'
import { pct, pctColor, PosSizeBar, RSPctileBar } from '@/lib/stock-formatters'
import { SectorBadge } from './SectorBadge'
import { LinkedTicker } from '@/components/ui/LinkedToken'

export function StockTopPicks({ picks }: { picks: StockRowWithSector[] }) {
  if (picks.length === 0) {
    return (
      <div className="px-4 py-3 border border-paper-rule bg-paper-rule/10 rounded-sm">
        <div className="flex items-center gap-2 mb-1">
          <Sparkles className="w-3.5 h-3.5 text-ink-tertiary" />
          <span className="font-sans text-xs font-semibold text-ink-secondary uppercase tracking-wider">Top Picks</span>
        </div>
        <p className="font-sans text-xs text-ink-tertiary">
          No investable stocks with Overweight RS today. Market breadth is unfavorable —
          reduce position sizing across the portfolio.
        </p>
      </div>
    )
  }

  return (
    <div className="px-4 py-3 border border-signal-pos/30 bg-signal-pos/5 rounded-sm">
      <div className="flex items-center gap-2 mb-3">
        <Sparkles className="w-3.5 h-3.5 text-signal-pos" />
        <span className="font-sans text-xs font-semibold text-signal-pos uppercase tracking-wider">
          Top Picks
        </span>
        <span className="font-sans text-[11px] text-ink-tertiary">
          investable · Overweight RS · ranked by 3M RS Pctile
        </span>
        <span className="ml-auto font-sans text-[11px] text-ink-tertiary">
          {picks.length} picks
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-paper-rule">
              <th className="pb-1.5 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary w-8">#</th>
              <th className="pb-1.5 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">Symbol</th>
              <th className="pb-1.5 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">Sector</th>
              <th className="pb-1.5 text-right font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">RS Pctile</th>
              <th className="pb-1.5 text-right font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">3M Ret</th>
              <th className="pb-1.5 text-right font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">Pos Size</th>
            </tr>
          </thead>
          <tbody>
            {picks.map((p, i) => (
              <tr
                key={p.instrument_id}
                className="border-b border-paper-rule last:border-0 hover:bg-paper-rule/10"
              >
                <td className="py-2 font-mono text-xs text-ink-tertiary tabular-nums">{i + 1}</td>
                <td className="py-2 pr-3">
                  <LinkedTicker symbol={p.symbol} className="font-semibold" />
                  <div className="font-sans text-[10px] text-ink-tertiary truncate max-w-[160px]">{p.company_name}</div>
                </td>
                <td className="py-2 pr-3">
                  <SectorBadge sector={p.sector} />
                </td>
                <td className="py-2 text-right">
                  <RSPctileBar value={p.rs_pctile_3m} />
                </td>
                <td className={`py-2 text-right font-mono text-xs tabular-nums ${pctColor(p.ret_3m)}`}>
                  {pct(p.ret_3m)}
                </td>
                <td className="py-2 text-right">
                  <div className="flex justify-end">
                    <PosSizeBar value={p.position_size_pct} />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
