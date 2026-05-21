import Link from 'next/link'
import type { ETFRow } from '@/lib/queries/etfs'
import { RSStateChip, MomentumChip, RiskChip, pct, pctColor } from '@/lib/stock-formatters'
import { ETFGatesPanel } from '@/components/etfs/ETFGatesPanel'
import { LinkedETF } from '@/components/ui/LinkedToken'

function MetricTile({ label, value, color, subtitle }: { label: string; value: string; color?: string; subtitle?: string }) {
  return (
    <div className="flex flex-col gap-1 px-4 py-3 border-r border-paper-rule last:border-0">
      <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">{label}</div>
      <div className={`font-mono text-sm font-semibold tabular-nums ${color ?? 'text-ink-primary'}`}>{value}</div>
      {subtitle && (
        <div className="font-sans text-[9px] text-ink-tertiary/60 leading-tight">{subtitle}</div>
      )}
    </div>
  )
}

function ETFCard({ etf }: { etf: ETFRow }) {
  const rsPctile = etf.rs_pctile_3m != null
    ? `${(parseFloat(etf.rs_pctile_3m) * 100).toFixed(0)}th`
    : '—'
  const rsPctileColor = etf.rs_pctile_3m != null
    ? parseFloat(etf.rs_pctile_3m) >= 0.7 ? 'text-signal-pos'
      : parseFloat(etf.rs_pctile_3m) >= 0.4 ? 'text-signal-warn'
      : 'text-signal-neg'
    : 'text-ink-tertiary'

  const extPct = etf.extension_pct != null
    ? `${(parseFloat(etf.extension_pct) * 100).toFixed(1)}%`
    : '—'

  return (
    <div className="border border-paper-rule rounded-sm bg-paper">
      {/* Header */}
      <div className="px-5 py-4 border-b border-paper-rule flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <LinkedETF
              ticker={etf.ticker}
              className="font-serif text-2xl font-semibold"
            />
            <span className={`font-sans text-[10px] font-semibold px-1.5 py-0.5 rounded ${
              etf.theme === 'Broad' ? 'bg-teal/10 text-teal'
              : etf.theme === 'Sectoral' ? 'bg-signal-pos/10 text-signal-pos'
              : 'bg-signal-warn/10 text-signal-warn'
            }`}>
              {etf.theme}
            </span>
          </div>
          <div className="font-sans text-xs text-ink-secondary">{etf.etf_name}</div>
          {etf.linked_index && (
            <div className="font-sans text-[11px] text-ink-tertiary mt-0.5">
              <span className="font-semibold">Tracks:</span> {etf.linked_index}
            </div>
          )}
        </div>
        <div className="shrink-0">
          {etf.is_investable ? (
            <span className="font-sans text-xs font-semibold text-signal-pos bg-signal-pos/10 px-2.5 py-1 rounded">
              ● Investable
            </span>
          ) : (
            <span className="font-sans text-xs font-semibold text-ink-tertiary bg-paper-rule/30 px-2.5 py-1 rounded">
              Not Investable
            </span>
          )}
        </div>
      </div>

      {/* Metrics strip */}
      <div className="grid grid-cols-3 sm:grid-cols-6 border-b border-paper-rule">
        <MetricTile label="RS Pctile" value={rsPctile} color={rsPctileColor} subtitle="3M vs peers" />
        <MetricTile label="1M Return" value={pct(etf.ret_1m)} color={pctColor(etf.ret_1m)} />
        <MetricTile label="3M Return" value={pct(etf.ret_3m)} color={pctColor(etf.ret_3m)} />
        <MetricTile label="6M Return" value={pct(etf.ret_6m)} color={pctColor(etf.ret_6m)} />
        <MetricTile
          label="Weinstein"
          value={etf.weinstein_gate_pass == null ? '—' : etf.weinstein_gate_pass ? 'Pass ✓' : 'Fail ✗'}
          color={etf.weinstein_gate_pass == null ? 'text-ink-tertiary' : etf.weinstein_gate_pass ? 'text-signal-pos' : 'text-signal-neg'}
          subtitle="Price > 30-week MA"
        />
        <MetricTile
          label="Extension"
          value={extPct}
          subtitle="vs 200-day MA"
        />
      </div>

      {/* States + gates */}
      <div className="p-5 grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div>
          <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-3">
            State Assessment
          </div>
          <div className="space-y-2">
            <div className="flex items-center gap-3">
              <span className="font-sans text-[11px] text-ink-tertiary w-20">RS State</span>
              <RSStateChip value={etf.rs_state} />
            </div>
            <div className="flex items-center gap-3">
              <span className="font-sans text-[11px] text-ink-tertiary w-20">Momentum</span>
              <MomentumChip value={etf.momentum_state} />
            </div>
            <div className="flex items-center gap-3">
              <span className="font-sans text-[11px] text-ink-tertiary w-20">Risk</span>
              <RiskChip value={etf.risk_state} />
            </div>
          </div>
          <div className="mt-4">
            <Link
              href={`/etfs/${encodeURIComponent(etf.ticker)}`}
              className="inline-flex items-center gap-1.5 font-sans text-xs text-teal hover:underline"
            >
              Full deep dive →
            </Link>
          </div>
        </div>
        <ETFGatesPanel etf={etf} />
      </div>
    </div>
  )
}

export function SectorETFTab({
  etfs,
  sectorName,
}: {
  etfs: ETFRow[]
  sectorName: string
}) {
  if (etfs.length === 0) {
    return (
      <div className="px-6 py-10 text-center">
        <p className="font-sans text-sm text-ink-tertiary">
          No ETF linked to the {sectorName} sector in the universe.
        </p>
      </div>
    )
  }

  return (
    <div className="px-6 py-6 space-y-4">
      <div className="font-sans text-xs text-ink-tertiary">
        {etfs.length === 1
          ? `1 ETF tracks the ${sectorName} sector.`
          : `${etfs.length} ETFs track the ${sectorName} sector.`
        }
      </div>
      {etfs.map(etf => (
        <ETFCard key={etf.ticker} etf={etf} />
      ))}
    </div>
  )
}
