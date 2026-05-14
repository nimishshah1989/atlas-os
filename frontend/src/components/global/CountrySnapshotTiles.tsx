import type { CountryDetailRow } from '@/lib/queries/global'

function Tile({
  label,
  value,
  color,
  subtitle,
}: {
  label: string
  value: string
  color?: string
  subtitle?: string
}) {
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

function pct(v: string | null, digits = 1): string {
  if (v == null) return '—'
  const n = parseFloat(v) * 100
  return `${n >= 0 ? '+' : ''}${n.toFixed(digits)}%`
}

function pctColor(v: string | null): string {
  if (v == null) return 'text-ink-tertiary'
  const n = parseFloat(v)
  return n >= 0 ? 'text-signal-pos' : 'text-signal-neg'
}

export function CountrySnapshotTiles({ country }: { country: CountryDetailRow }) {
  const pctileVT = country.pctile_3m_vt != null
    ? (parseFloat(country.pctile_3m_vt) * 100).toFixed(0)
    : '—'
  const pctileColor = country.pctile_3m_vt != null
    ? parseFloat(country.pctile_3m_vt) >= 0.7 ? 'text-signal-pos'
      : parseFloat(country.pctile_3m_vt) >= 0.4 ? 'text-signal-warn'
      : 'text-signal-neg'
    : 'text-ink-tertiary'

  const vol = country.realized_vol_63 != null
    ? `${(parseFloat(country.realized_vol_63) * 100).toFixed(1)}%`
    : '—'

  const ext = country.extension_pct != null
    ? `${(parseFloat(country.extension_pct) * 100).toFixed(1)}%`
    : '—'

  const extColor = country.extension_pct != null
    ? parseFloat(country.extension_pct) >= 0.4 ? 'text-signal-neg'
      : parseFloat(country.extension_pct) < 0 ? 'text-signal-warn'
      : 'text-ink-primary'
    : 'text-ink-tertiary'

  const dd = country.max_drawdown_252 != null
    ? `${(parseFloat(country.max_drawdown_252) * 100).toFixed(1)}%`
    : '—'

  const ddColor = country.max_drawdown_252 != null
    ? parseFloat(country.max_drawdown_252) < -0.20 ? 'text-signal-neg'
      : parseFloat(country.max_drawdown_252) < -0.10 ? 'text-signal-warn'
      : 'text-ink-primary'
    : 'text-ink-tertiary'

  const consensus = country.rs_consensus_bullish != null
    ? `${country.rs_consensus_bullish}/20`
    : '—'
  const consensusColor = country.rs_consensus_bullish != null
    ? country.rs_consensus_bullish >= 14 ? 'text-signal-pos'
      : country.rs_consensus_bullish >= 10 ? 'text-signal-warn'
      : country.rs_consensus_bullish <= 4 ? 'text-signal-neg'
      : 'text-ink-primary'
    : 'text-ink-tertiary'

  return (
    <div className="px-6 py-3 border-b border-paper-rule grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-8">
      <Tile
        label="RS Pctile 3M"
        value={pctileVT}
        color={pctileColor}
        subtitle="vs VT benchmark"
      />
      <Tile label="3M Return" value={pct(country.ret_3m)} color={pctColor(country.ret_3m)} />
      <Tile label="12M Return" value={pct(country.ret_12m)} color={pctColor(country.ret_12m)} />
      <Tile label="1M Return" value={pct(country.ret_1m)} color={pctColor(country.ret_1m)} />
      <Tile
        label="30W MA"
        value={country.above_30w_ma == null ? '—' : country.above_30w_ma ? 'Above ✓' : 'Below ✗'}
        color={country.above_30w_ma == null ? 'text-ink-tertiary' : country.above_30w_ma ? 'text-signal-pos' : 'text-signal-neg'}
        subtitle="Weinstein Stage 2 gate"
      />
      <Tile label="Extension" value={ext} color={extColor} subtitle="vs 200-day MA" />
      <Tile label="Vol 63D" value={vol} color="text-ink-primary" subtitle="Annualised realised vol" />
      <Tile label="Consensus" value={consensus} color={consensusColor} subtitle="Bullish signals (0-20)" />
    </div>
  )
}
