// frontend/src/components/v6/stock-detail/LifecyclePanel.tsx
interface LifecyclePanelProps {
  state: string | null
  dwellDays: number | null
  ema20Ratio: number | null
  volRatio63: number | null
  extensionPct: number | null
}

const DWELL_CONTEXT: Record<string, string> = {
  stage_1:      'Base formation — duration varies (weeks to years).',
  stage_2a:     'Typical Stage 2A breakout: 10–90 days.',
  stage_2b:     'Typical Stage 2B confirmed: 60–360 days.',
  stage_2c:     'Typical Stage 2C mature: 90–400 days. Watch for distribution.',
  stage_3:      'Distribution phase — typically short-lived (weeks to 3 months).',
  stage_4:      'Decline phase — can last 6–24 months.',
  uninvestable: 'Structurally impaired — no actionable signal.',
}

const STAGE_LABEL: Record<string, string> = {
  stage_1: 'Stage 1 Base', stage_2a: 'Stage 2A Breakout', stage_2b: 'Stage 2B Confirmed',
  stage_2c: 'Stage 2C Mature', stage_3: 'Stage 3 Distribution', stage_4: 'Stage 4 Decline', uninvestable: 'Uninvestable',
}

function volClass(v: number | null): { label: string; cls: string } {
  if (v == null) return { label: '— Unavailable', cls: 'text-ink-3' }
  if (v > 1.3) return { label: '↑ Expanding', cls: 'text-signal-pos' }
  if (v < 0.8) return { label: '↓ Fading', cls: 'text-signal-neg' }
  return { label: '→ Stable', cls: 'text-ink-3' }
}

function emaClass(r: number | null): { label: string; cls: string } {
  if (r == null) return { label: '— Unavailable', cls: 'text-ink-3' }
  const p = (r - 1) * 100
  if (p > 8) return { label: `⚠ Extended (+${p.toFixed(1)}% above EMA 20)`, cls: 'text-signal-warn' }
  if (p >= 0) return { label: `Not stretched (+${p.toFixed(1)}%)`, cls: 'text-signal-pos' }
  return { label: `Below EMA 20 (${p.toFixed(1)}%)`, cls: 'text-signal-neg' }
}

function synthesize(state: string | null, dwellDays: number | null, volRatio63: number | null, ema20Ratio: number | null): string {
  if (!state) return 'No lifecycle classification available.'
  const parts: string[] = []
  const ctx = DWELL_CONTEXT[state] ?? ''
  if (dwellDays !== null && ctx) {
    const early = dwellDays <= 30
    const late = (state === 'stage_2b' && dwellDays > 300) || (state === 'stage_2c' && dwellDays > 350) || (state === 'stage_4' && dwellDays > 365)
    if (early) parts.push(`Early in ${STAGE_LABEL[state] ?? state} (${dwellDays} days). ${ctx}`)
    else if (late) parts.push(`Deep into ${STAGE_LABEL[state] ?? state} (${dwellDays} days) — ${ctx}`)
    else parts.push(`${dwellDays} days into ${STAGE_LABEL[state] ?? state}. ${ctx}`)
  }
  if (volRatio63 !== null) {
    if (volRatio63 > 1.3) parts.push('Volume is expanding — institutional demand confirmed.')
    else if (volRatio63 < 0.8) parts.push('Volume is contracting — re-acceleration needed before adding.')
    else parts.push('Volume is steady — no distribution signal.')
  }
  if (ema20Ratio !== null) {
    const p = (ema20Ratio - 1) * 100
    if (p > 8) parts.push(`Running ${p.toFixed(1)}% above EMA 20 — not an ideal entry; prefer waiting for a pullback.`)
    else if (p < 0) parts.push('Trading below EMA 20 — needs to reclaim before entry is confirmed.')
  }
  return parts.join(' ') || 'Insufficient data for lifecycle synthesis.'
}

function MetricRow({ label, value, valueClass }: { label: string; value: string; valueClass: string }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-paper-rule last:border-0">
      <span className="font-sans text-[12px] text-ink-3">{label}</span>
      <span className={`font-mono text-[12px] font-medium ${valueClass}`}>{value}</span>
    </div>
  )
}

export function LifecyclePanel({ state, dwellDays, ema20Ratio, volRatio63, extensionPct }: LifecyclePanelProps) {
  const vol = volClass(volRatio63)
  const ema = emaClass(ema20Ratio)
  const ext = extensionPct != null
    ? { label: extensionPct >= 0 ? `+${(extensionPct * 100).toFixed(1)}% above 200D EMA` : `${(extensionPct * 100).toFixed(1)}% below 200D EMA`, cls: extensionPct >= 0 ? 'text-signal-pos' : 'text-signal-neg' }
    : { label: '—', cls: 'text-ink-3' }

  return (
    <section className="px-6 py-6 border-b border-paper-rule">
      <p className="font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-4">Lifecycle Position — Where in the stage?</p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-paper border border-paper-rule rounded p-4">
          <MetricRow label="Days in current stage" value={dwellDays !== null ? `${dwellDays} days` : '—'} valueClass="text-ink" />
          <MetricRow label="Volume trend" value={vol.label} valueClass={vol.cls} />
          <MetricRow label="EMA 20 position" value={ema.label} valueClass={ema.cls} />
          <MetricRow label="Extension from 200D EMA" value={ext.label} valueClass={ext.cls} />
          {state && DWELL_CONTEXT[state] && <p className="font-sans text-[11px] text-ink-3 mt-3 italic">{DWELL_CONTEXT[state]}</p>}
        </div>
        <div className="bg-paper-deep border border-paper-rule rounded p-4">
          <p className="font-mono text-[10px] text-teal uppercase tracking-wider mb-2">Lifecycle Reading</p>
          <p className="font-sans text-sm text-ink leading-relaxed">{synthesize(state, dwellDays, volRatio63, ema20Ratio)}</p>
        </div>
      </div>
    </section>
  )
}
