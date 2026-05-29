// ETF investability gates.
// Five ETF-specific gates that mirror the stock GatesPanel pattern but use
// ETF-relevant signals. Each gate has PASS/FAIL/N/A + the trigger value.
// Derived verdict: CLEAR if all pass; WAIT if any fails (with reasons listed).
// Pure server component.

interface ETFGatesPanelProps {
  /** ADV (avg daily value) in INR. Liquidity gate threshold: 3 crore (3e7). */
  adv20dInr: number | null
  /** Tracking error in basis points (compared against category baseline). */
  trackingErrorBps: number | null
  /** ETF category — used to set category-aware TE thresholds. */
  etfCategory: string | null
  /** Premium/discount to NAV in basis points. ±25 bps boundary per
   * Atlas NAV-fair-value classification. */
  premiumBps: number | null
  /** Composite score 0-100 (mirrors stock RS strength gate at 50 cutoff). */
  compositeScore: number | null
  /** Sector index momentum state ('Overweight'|'Neutral'|'Avoid') from sector strip. */
  sectorState: string | null
  /** Market regime ('Risk-On'|'Elevated'|'Below-Trend'|'Risk-Off'). */
  regimeState: string | null
}

type GateStatus = 'PASS' | 'FAIL' | 'UNKNOWN'

interface GateResult {
  name: string
  status: GateStatus
  detail: string
}

// Per Atlas methodology: tracking error thresholds vary by category.
const TE_LIMITS_BPS: Record<string, number> = {
  'Index':       40,
  'Sector':      80,
  'Smart-beta':  100,
  'Commodity':   200,
  'International': 200,
}

function liquidityGate(advInr: number | null): GateResult {
  if (advInr == null) return { name: 'Liquidity', status: 'UNKNOWN', detail: 'ADV unavailable' }
  const advCr = advInr / 1e7
  if (advCr >= 3) return { name: 'Liquidity', status: 'PASS', detail: `ADV ₹${advCr.toFixed(1)} cr ≥ ₹3 cr` }
  return { name: 'Liquidity', status: 'FAIL', detail: `ADV ₹${advCr.toFixed(1)} cr < ₹3 cr (thin trading)` }
}

function trackingGate(teBps: number | null, category: string | null): GateResult {
  if (teBps == null) return { name: 'Tracking', status: 'UNKNOWN', detail: 'TE unavailable' }
  const limit = TE_LIMITS_BPS[category ?? ''] ?? 50
  if (teBps <= limit) return { name: 'Tracking', status: 'PASS', detail: `TE ${teBps.toFixed(0)} bps ≤ ${limit} bps (${category ?? 'category'} baseline)` }
  return { name: 'Tracking', status: 'FAIL', detail: `TE ${teBps.toFixed(0)} bps > ${limit} bps (poor tracking)` }
}

function navPremiumGate(premiumBps: number | null): GateResult {
  if (premiumBps == null) return { name: 'NAV Premium', status: 'UNKNOWN', detail: 'iNAV unavailable' }
  const absBps = Math.abs(premiumBps)
  if (absBps <= 25) return { name: 'NAV Premium', status: 'PASS', detail: `${premiumBps >= 0 ? '+' : ''}${premiumBps.toFixed(0)} bps to NAV (within ±25)` }
  return { name: 'NAV Premium', status: 'FAIL', detail: `${premiumBps >= 0 ? '+' : ''}${premiumBps.toFixed(0)} bps to NAV (>±25 bps, AP-friction)` }
}

function compositeGate(score: number | null): GateResult {
  if (score == null) return { name: 'Strength', status: 'UNKNOWN', detail: 'Composite score unavailable' }
  if (score >= 50) return { name: 'Strength', status: 'PASS', detail: `Composite ${Math.round(score)}/100 ≥ 50` }
  return { name: 'Strength', status: 'FAIL', detail: `Composite ${Math.round(score)}/100 < 50 (below median in category)` }
}

function sectorGate(state: string | null): GateResult {
  if (state == null) return { name: 'Sector/Category', status: 'UNKNOWN', detail: 'Sector state unavailable' }
  if (state === 'Avoid') return { name: 'Sector/Category', status: 'FAIL', detail: 'Sector state: Avoid' }
  return { name: 'Sector/Category', status: 'PASS', detail: `Sector state: ${state}` }
}

function marketGate(regime: string | null): GateResult {
  if (regime == null) return { name: 'Market', status: 'UNKNOWN', detail: 'Regime unavailable' }
  if (regime === 'Risk-Off') return { name: 'Market', status: 'FAIL', detail: 'Market regime: Risk-Off' }
  return { name: 'Market', status: 'PASS', detail: `Market regime: ${regime}` }
}

const STATUS_META: Record<GateStatus, { dot: string; label: string; cls: string }> = {
  PASS:    { dot: '●', label: 'PASS', cls: 'text-signal-pos' },
  FAIL:    { dot: '●', label: 'FAIL', cls: 'text-signal-neg' },
  UNKNOWN: { dot: '○', label: 'N/A',  cls: 'text-ink-4' },
}

export function ETFGatesPanel({
  adv20dInr,
  trackingErrorBps,
  etfCategory,
  premiumBps,
  compositeScore,
  sectorState,
  regimeState,
}: ETFGatesPanelProps) {
  const gates: GateResult[] = [
    liquidityGate(adv20dInr),
    trackingGate(trackingErrorBps, etfCategory),
    navPremiumGate(premiumBps),
    compositeGate(compositeScore),
    sectorGate(sectorState),
    marketGate(regimeState),
  ]

  const fails = gates.filter(g => g.status === 'FAIL')
  const verdict =
    fails.length === 0
      ? { label: 'CLEAR', cls: 'bg-signal-pos text-white', note: 'All 6 gates pass — buy/accumulate signals are actionable.' }
      : { label: 'WAIT', cls: 'bg-signal-warn text-white', note: `${fails.length} gate fail: ${fails.map(f => f.name).join(', ')}. Signals render as WAIT.` }

  return (
    <section className="border border-paper-rule rounded p-4 bg-paper">
      <div className="flex items-center justify-between mb-3">
        <p className="font-mono text-[10px] uppercase tracking-wider text-ink-3">
          ETF Investability Gates — proof for the verdict
        </p>
        <span className={`inline-block px-2 py-0.5 rounded-[2px] font-mono text-[10px] font-semibold tracking-wider ${verdict.cls}`}>
          {verdict.label}
        </span>
      </div>

      <ul className="space-y-1.5 mb-3">
        {gates.map(gate => {
          const meta = STATUS_META[gate.status]
          return (
            <li key={gate.name} className="flex items-center gap-2 font-mono text-[12px]">
              <span className={`inline-block ${meta.cls} text-base leading-none`}>{meta.dot}</span>
              <span className="w-[110px] text-ink-3 uppercase text-[10px] tracking-wider">{gate.name}</span>
              <span className={`w-[50px] ${meta.cls} text-[10px] font-semibold`}>{meta.label}</span>
              <span className="flex-1 text-ink text-[11px]">{gate.detail}</span>
            </li>
          )
        })}
      </ul>

      <p className="font-sans text-[11px] text-ink-3 italic border-t border-paper-rule pt-2">
        {verdict.note}
      </p>
    </section>
  )
}
