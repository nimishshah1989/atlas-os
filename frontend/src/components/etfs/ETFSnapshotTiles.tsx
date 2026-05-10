import type { ReactNode } from 'react'
import type { ETFRow } from '@/lib/queries/etfs'
import { pct, pctColor, RSStateChip, MomentumChip, RiskChip } from '@/lib/stock-formatters'

function Tile({ label, value, color, subtitle }: { label: string; value: string; color?: string; subtitle?: string }) {
  return (
    <div className="flex flex-col gap-1 px-4 py-3 border-r border-paper-rule last:border-0">
      <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">
        {label}
      </div>
      <div className={`font-mono text-sm font-semibold tabular-nums ${color ?? 'text-ink-primary'}`}>
        {value}
      </div>
      {subtitle && (
        <div className="font-sans text-[9px] text-ink-tertiary/60 leading-tight">{subtitle}</div>
      )}
    </div>
  )
}

function ChipTile({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5 px-4 py-3 border-r border-paper-rule last:border-0">
      <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">
        {label}
      </div>
      <div className="flex items-center h-5">
        {children}
      </div>
    </div>
  )
}

export function ETFSnapshotTiles({ etf }: { etf: ETFRow }) {
  const rsPctile = etf.rs_pctile_3m != null
    ? (parseFloat(etf.rs_pctile_3m) * 100).toFixed(0)
    : '—'

  const rsPctileColor = etf.rs_pctile_3m != null
    ? parseFloat(etf.rs_pctile_3m) >= 0.7 ? 'text-signal-pos'
      : parseFloat(etf.rs_pctile_3m) >= 0.4 ? 'text-signal-warn'
      : 'text-signal-neg'
    : 'text-ink-tertiary'

  const extPct = etf.extension_pct != null
    ? `${(parseFloat(etf.extension_pct) * 100).toFixed(1)}%`
    : '—'

  const extColor = etf.extension_pct != null
    ? parseFloat(etf.extension_pct) >= 0.4 ? 'text-signal-neg'
      : parseFloat(etf.extension_pct) < 0 ? 'text-signal-warn'
      : 'text-ink-primary'
    : 'text-ink-tertiary'

  const emaQualityValue = etf.ema_10_at_20d_high == null
    ? '—'
    : etf.ema_10_at_20d_high
    ? 'At 20D High ✓'
    : 'Below 20D High'

  const emaQualityColor = etf.ema_10_at_20d_high == null
    ? 'text-ink-tertiary'
    : etf.ema_10_at_20d_high
    ? 'text-signal-pos'
    : 'text-ink-secondary'

  return (
    <div className="px-6 py-3 border-b border-paper-rule grid grid-cols-2 sm:grid-cols-5 xl:grid-cols-10">
      <Tile label="RS Pctile" value={rsPctile} color={rsPctileColor} subtitle={etf.rs_3m_benchmark ? `vs ${etf.rs_3m_benchmark}` : '3-month vs peers'} />
      <Tile label="3M Return" value={pct(etf.ret_3m)} color={pctColor(etf.ret_3m)} />
      <Tile label="12M Return" value={pct(etf.ret_12m)} color={pctColor(etf.ret_12m)} />
      <Tile label="6M Return" value={pct(etf.ret_6m)} color={pctColor(etf.ret_6m)} />
      <Tile label="1M Return" value={pct(etf.ret_1m)} color={pctColor(etf.ret_1m)} />
      <Tile
        label="Weinstein"
        value={etf.weinstein_gate_pass == null ? '—' : etf.weinstein_gate_pass ? 'Pass ✓' : 'Fail ✗'}
        color={etf.weinstein_gate_pass == null ? 'text-ink-tertiary' : etf.weinstein_gate_pass ? 'text-signal-pos' : 'text-signal-neg'}
        subtitle="Price above 30-week MA (Stage 2 uptrend)"
      />
      <Tile
        label="Extension"
        value={extPct}
        color={extColor}
        subtitle="% above/below 200-day MA"
      />
      <Tile
        label="EMA Quality"
        value={emaQualityValue}
        color={emaQualityColor}
        subtitle="EMA10 at 20-day high"
      />
      <ChipTile label="RS State">
        <RSStateChip value={etf.rs_state} />
      </ChipTile>
      <ChipTile label="Momentum">
        <MomentumChip value={etf.momentum_state} />
      </ChipTile>
    </div>
  )
}
