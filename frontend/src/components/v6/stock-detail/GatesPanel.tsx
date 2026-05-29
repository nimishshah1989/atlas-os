// 5 Investability Gates per CONTEXT.md:
//   strength · direction · risk · sector · market
// Each gate has a pass/fail dot + the underlying value that triggers it.
// Per CONTEXT.md: if cell state = POSITIVE and any gate fails → verdict = WAIT.
// Pure server component.

interface GatesPanelProps {
  /** RS percentile 3M from atlas_stock_metrics_daily — 0..1 scale */
  rsPctile3m: number | null
  /** EMA20 momentum ratio (price/EMA20). >1 means rising. */
  ema20Ratio: number | null
  /** Extension from 200D EMA. Failure threshold 40% per CONTEXT WAIT example. */
  extensionPct: number | null
  /** Sector state from atlas_sector_states_daily ('Overweight'|'Neutral'|'Avoid') */
  sectorState: string | null
  /** Regime state from atlas_market_regime_daily ('Risk-On'|'Elevated'|'Below-Trend'|'Risk-Off') */
  regimeState: string | null
}

type GateStatus = 'PASS' | 'FAIL' | 'UNKNOWN'

interface GateResult {
  name: string
  status: GateStatus
  detail: string
}

function strengthGate(rsPctile: number | null): GateResult {
  if (rsPctile == null) return { name: 'Strength', status: 'UNKNOWN', detail: 'RS percentile unavailable' }
  if (rsPctile >= 0.5) return { name: 'Strength', status: 'PASS', detail: `RS percentile ${Math.round(rsPctile * 100)} ≥ 50` }
  return { name: 'Strength', status: 'FAIL', detail: `RS percentile ${Math.round(rsPctile * 100)} < 50 (below median)` }
}

function directionGate(ema20Ratio: number | null): GateResult {
  if (ema20Ratio == null) return { name: 'Direction', status: 'UNKNOWN', detail: 'EMA20 ratio unavailable' }
  if (ema20Ratio >= 1.0) return { name: 'Direction', status: 'PASS', detail: `Price ≥ EMA20 (ratio ${ema20Ratio.toFixed(3)})` }
  return { name: 'Direction', status: 'FAIL', detail: `Price below EMA20 (ratio ${ema20Ratio.toFixed(3)})` }
}

function riskGate(extensionPct: number | null): GateResult {
  if (extensionPct == null) return { name: 'Risk', status: 'UNKNOWN', detail: 'Extension unavailable' }
  const extPctDisplay = `${(extensionPct * 100).toFixed(1)}%`
  if (extensionPct > 0.40) return { name: 'Risk', status: 'FAIL', detail: `Extension ${extPctDisplay} > 40% threshold (over-extended)` }
  return { name: 'Risk', status: 'PASS', detail: `Extension ${extPctDisplay} ≤ 40%` }
}

function sectorGate(sectorState: string | null): GateResult {
  if (sectorState == null) return { name: 'Sector', status: 'UNKNOWN', detail: 'Sector state unavailable' }
  if (sectorState === 'Avoid') return { name: 'Sector', status: 'FAIL', detail: 'Sector state: Avoid' }
  return { name: 'Sector', status: 'PASS', detail: `Sector state: ${sectorState}` }
}

function marketGate(regimeState: string | null): GateResult {
  if (regimeState == null) return { name: 'Market', status: 'UNKNOWN', detail: 'Regime unavailable' }
  if (regimeState === 'Risk-Off') return { name: 'Market', status: 'FAIL', detail: 'Market regime: Risk-Off' }
  return { name: 'Market', status: 'PASS', detail: `Market regime: ${regimeState}` }
}

const STATUS_META: Record<GateStatus, { dot: string; label: string; cls: string }> = {
  PASS:    { dot: '●', label: 'PASS',    cls: 'text-signal-pos' },
  FAIL:    { dot: '●', label: 'FAIL',    cls: 'text-signal-neg' },
  UNKNOWN: { dot: '○', label: 'N/A',     cls: 'text-ink-4' },
}

export function GatesPanel({ rsPctile3m, ema20Ratio, extensionPct, sectorState, regimeState }: GatesPanelProps) {
  const gates = [
    strengthGate(rsPctile3m),
    directionGate(ema20Ratio),
    riskGate(extensionPct),
    sectorGate(sectorState),
    marketGate(regimeState),
  ]

  const fails = gates.filter(g => g.status === 'FAIL')
  const verdictDerived =
    fails.length === 0
      ? { label: 'CLEAR', cls: 'bg-signal-pos text-white', note: 'All 5 gates pass — POSITIVE signals are actionable.' }
      : { label: 'WAIT', cls: 'bg-signal-warn text-white', note: `${fails.length} gate fail: ${fails.map(f => f.name).join(', ')}. POSITIVE signals render as WAIT.` }

  return (
    <section className="border border-paper-rule rounded p-4 bg-paper">
      <div className="flex items-center justify-between mb-3">
        <p className="font-mono text-[10px] uppercase tracking-wider text-ink-3">
          Investability Gates — proof for the verdict
        </p>
        <span className={`inline-block px-2 py-0.5 rounded-[2px] font-mono text-[10px] font-semibold tracking-wider ${verdictDerived.cls}`}>
          {verdictDerived.label}
        </span>
      </div>

      <ul className="space-y-1.5 mb-3">
        {gates.map(gate => {
          const meta = STATUS_META[gate.status]
          return (
            <li key={gate.name} className="flex items-center gap-2 font-mono text-[12px]">
              <span className={`inline-block ${meta.cls} text-base leading-none`}>{meta.dot}</span>
              <span className="w-[80px] text-ink-3 uppercase text-[10px] tracking-wider">{gate.name}</span>
              <span className={`w-[50px] ${meta.cls} text-[10px] font-semibold`}>{meta.label}</span>
              <span className="flex-1 text-ink text-[11px]">{gate.detail}</span>
            </li>
          )
        })}
      </ul>

      <p className="font-sans text-[11px] text-ink-3 italic border-t border-paper-rule pt-2">
        {verdictDerived.note}
      </p>
    </section>
  )
}
