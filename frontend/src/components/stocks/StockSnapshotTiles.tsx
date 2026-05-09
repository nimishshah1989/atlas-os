import type { StockRowWithSector } from '@/lib/queries/stocks'
import { pct, pctColor } from '@/lib/stock-formatters'

function Tile({
  label,
  value,
  color,
}: {
  label: string
  value: string
  color?: string
}) {
  return (
    <div className="flex flex-col gap-1 px-4 py-3 border-r border-paper-rule last:border-0">
      <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">
        {label}
      </div>
      <div className={`font-mono text-sm font-semibold tabular-nums ${color ?? 'text-ink-primary'}`}>
        {value}
      </div>
    </div>
  )
}

export function StockSnapshotTiles({ stock }: { stock: StockRowWithSector }) {
  const rsPctile = stock.rs_pctile_3m != null
    ? (parseFloat(stock.rs_pctile_3m) * 100).toFixed(0)
    : '—'

  const rsPctileColor = stock.rs_pctile_3m != null
    ? parseFloat(stock.rs_pctile_3m) >= 0.7 ? 'text-signal-pos'
      : parseFloat(stock.rs_pctile_3m) >= 0.4 ? 'text-signal-warn'
      : 'text-signal-neg'
    : 'text-ink-tertiary'

  return (
    <div className="px-6 py-3 border-b border-paper-rule grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6">
      <Tile
        label="RS Pctile"
        value={rsPctile}
        color={rsPctileColor}
      />
      <Tile
        label="3M Return"
        value={pct(stock.ret_3m)}
        color={pctColor(stock.ret_3m)}
      />
      <Tile
        label="6M Return"
        value={pct(stock.ret_6m)}
        color={pctColor(stock.ret_6m)}
      />
      <Tile
        label="RS 3M"
        value={pct(stock.rs_3m_nifty500)}
        color={pctColor(stock.rs_3m_nifty500)}
      />
      <Tile
        label="Weinstein"
        value={stock.weinstein_gate_pass == null ? '—' : stock.weinstein_gate_pass ? 'Pass ✓' : 'Fail ✗'}
        color={stock.weinstein_gate_pass == null ? 'text-ink-tertiary' : stock.weinstein_gate_pass ? 'text-signal-pos' : 'text-signal-neg'}
      />
      <Tile
        label="EMA 20D High"
        value={stock.ema_10_at_20d_high == null ? '—' : stock.ema_10_at_20d_high ? 'Yes' : 'No'}
        color={stock.ema_10_at_20d_high == null ? 'text-ink-tertiary' : stock.ema_10_at_20d_high ? 'text-signal-pos' : 'text-ink-tertiary'}
      />
    </div>
  )
}
