'use client'
// TEMP design mockup — two graphical "score derivation tree" variants for sign-off.
// A = top-down branching tree (root → lens branches → sub-components → values).
// B = left→right flow tree (root left, branches flow rightward; pick a lens to drill).
// Both render the SAME real lens data; only the spatial model differs.
import { useState } from 'react'
import { decileColor } from '@/components/v4/ui/decile'

type Num = { label: string; value: string; tone?: 'pos' | 'neg' | 'neutral' }
type Lens = {
  key: string; label: string
  decile: number | null; score: number | null
  subs: { label: string; v: number }[]
  numbers: Num[]
}
type Props = {
  symbol: string; name: string | null
  strength: number | null; leadership: { n: number; of: number }
  lenses: Lens[]
}

const scoreColor = (v: number) => (v >= 60 ? 'var(--color-sig-pos)' : v >= 45 ? 'var(--color-sig-warn)' : 'var(--color-sig-neg)')
const numTone = (t?: Num['tone']) => (t === 'pos' ? 'text-sig-pos' : t === 'neg' ? 'text-sig-neg' : 'text-txt-1')

function DChip({ d, score }: { d: number | null; score: number | null }) {
  const c = d != null ? decileColor(d) : 'var(--color-txt-3)'
  return (
    <span className="inline-flex items-baseline gap-1 font-num tabular-nums">
      <span className="rounded px-1.5 py-0.5 text-[11px] font-semibold" style={{ background: `color-mix(in srgb, ${c} 20%, transparent)`, color: c }}>
        {d != null ? `D${d}` : '—'}
      </span>
      <span className="text-[12px] text-txt-2">{score != null ? score.toFixed(0) : '—'}<span className="text-[9px] text-txt-3">/100</span></span>
    </span>
  )
}

function Bar({ v }: { v: number }) {
  return (
    <span className="block h-[5px] w-full overflow-hidden rounded-full bg-surface-inset">
      <span className="block h-full rounded-full" style={{ width: `${Math.min(100, Math.max(0, v))}%`, background: scoreColor(v) }} />
    </span>
  )
}

// ── Variant A — top-down branching tree ──────────────────────────────────────
function VariantA({ strength, leadership, lenses }: Props) {
  return (
    <div className="overflow-x-auto pb-4">
      <div className="mx-auto flex min-w-[920px] flex-col items-center">
        {/* root */}
        <div className="rounded-tile border border-edge-rule bg-surface-raised px-5 py-3 text-center shadow-panel">
          <div className="font-num text-[9px] uppercase tracking-[0.16em] text-txt-3">Conviction</div>
          <div className="font-display text-[30px] font-semibold leading-none tabular-nums" style={{ color: strength != null ? decileColor(Math.round(strength)) : 'var(--color-txt-3)' }}>
            {strength != null ? strength.toFixed(1) : '—'}<span className="text-[14px] text-txt-3">/10</span>
          </div>
          <div className="mt-1 font-sans text-[10px] text-txt-3">avg decile · {leadership.n}/{leadership.of} lenses lead</div>
        </div>
        {/* trunk + rail */}
        <div className="h-5 w-px bg-edge-rule" />
        <div className="h-px bg-edge-rule" style={{ width: `${(lenses.length - 1) * 188 + 2}px` }} />
        {/* branches */}
        <div className="flex items-start gap-6">
          {lenses.map((l) => (
            <div key={l.key} className="flex w-[164px] flex-col items-center">
              <div className="h-5 w-px bg-edge-rule" />
              {/* lens node */}
              <div className="w-full rounded-tile border border-edge-hair bg-surface-panel px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-sans text-[12.5px] font-medium text-txt-1">{l.label}</span>
                </div>
                <div className="mt-1 flex items-center justify-between"><DChip d={l.decile} score={l.score} /></div>
                {l.score != null && <div className="mt-1.5"><Bar v={l.score} /></div>}
              </div>
              {/* sub-components */}
              {l.subs.length > 0 && (
                <>
                  <div className="h-4 w-px bg-edge-hair" />
                  <div className="w-full space-y-1.5 rounded-tile border border-edge-hair/70 bg-surface-inset/40 px-2.5 py-2">
                    {l.subs.map((s) => (
                      <div key={s.label}>
                        <div className="flex items-center justify-between gap-1">
                          <span className="font-sans text-[10.5px] text-txt-2">{s.label}</span>
                          <span className="font-num text-[10.5px] tabular-nums text-txt-1">{s.v.toFixed(0)}</span>
                        </div>
                        <Bar v={s.v} />
                      </div>
                    ))}
                  </div>
                </>
              )}
              {/* actual values (leaves) */}
              {l.numbers.length > 0 && (
                <>
                  <div className="h-4 w-px bg-edge-hair" />
                  <div className="w-full rounded-tile border border-dashed border-edge-hair px-2.5 py-2">
                    <div className="mb-1 font-num text-[8px] uppercase tracking-[0.14em] text-txt-3">actual values</div>
                    <div className="space-y-1">
                      {l.numbers.slice(0, 6).map((nm) => (
                        <div key={nm.label} className="flex items-baseline justify-between gap-1.5">
                          <span className="font-sans text-[10px] leading-tight text-txt-3">{nm.label}</span>
                          <span className={`shrink-0 font-num text-[10.5px] tabular-nums ${numTone(nm.tone)}`}>{nm.value}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Variant B — left→right flow tree (pick a lens to drill) ───────────────────
function VariantB({ strength, leadership, lenses }: Props) {
  const [sel, setSel] = useState(lenses[0]?.key ?? '')
  const active = lenses.find((l) => l.key === sel) ?? lenses[0]
  return (
    <div className="flex items-stretch gap-0 overflow-x-auto pb-4">
      {/* root (left) */}
      <div className="flex shrink-0 items-center">
        <div className="rounded-tile border border-edge-rule bg-surface-raised px-4 py-3 text-center shadow-panel">
          <div className="font-num text-[9px] uppercase tracking-[0.16em] text-txt-3">Conviction</div>
          <div className="font-display text-[26px] font-semibold leading-none tabular-nums" style={{ color: strength != null ? decileColor(Math.round(strength)) : 'var(--color-txt-3)' }}>
            {strength != null ? strength.toFixed(1) : '—'}<span className="text-[12px] text-txt-3">/10</span>
          </div>
          <div className="mt-1 font-sans text-[10px] text-txt-3">{leadership.n}/{leadership.of} lead</div>
        </div>
        <div className="h-px w-6 bg-edge-rule" />
      </div>
      {/* lens column */}
      <div className="flex shrink-0 flex-col justify-center gap-1.5 border-l border-edge-rule pl-4">
        {lenses.map((l) => {
          const on = l.key === active?.key
          return (
            <button key={l.key} type="button" onClick={() => setSel(l.key)}
              className={`flex w-[210px] items-center justify-between gap-2 rounded-tile border px-3 py-2 text-left transition-colors ${on ? 'border-brand bg-surface-raised' : 'border-edge-hair bg-surface-panel hover:bg-surface-raised/60'}`}>
              <span className="font-sans text-[12.5px] font-medium text-txt-1">{l.label}</span>
              <DChip d={l.decile} score={l.score} />
            </button>
          )
        })}
      </div>
      {/* selected lens branch (right) */}
      {active && (
        <div className="flex shrink-0 items-center">
          <div className="h-px w-6 bg-brand/50" />
          <div className="min-w-[280px] rounded-tile border border-brand/40 bg-surface-inset/40 p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="font-display text-[15px] text-txt-1">{active.label}</span>
              <DChip d={active.decile} score={active.score} />
            </div>
            {active.subs.length > 0 && (
              <div className="mb-3 space-y-1.5">
                <div className="font-num text-[8px] uppercase tracking-[0.14em] text-txt-3">sub-components (0–100)</div>
                {active.subs.map((s) => (
                  <div key={s.label}>
                    <div className="flex items-center justify-between gap-1">
                      <span className="font-sans text-[11px] text-txt-2">{s.label}</span>
                      <span className="font-num text-[11px] tabular-nums text-txt-1">{s.v.toFixed(0)}</span>
                    </div>
                    <Bar v={s.v} />
                  </div>
                ))}
              </div>
            )}
            {active.numbers.length > 0 && (
              <div>
                <div className="mb-1 font-num text-[8px] uppercase tracking-[0.14em] text-txt-3">actual values</div>
                <div className="grid grid-cols-1 gap-y-1">
                  {active.numbers.map((nm) => (
                    <div key={nm.label} className="flex items-baseline justify-between gap-2 border-b border-edge-hair/50 py-0.5">
                      <span className="font-sans text-[11px] text-txt-3">{nm.label}</span>
                      <span className={`font-num text-[12px] tabular-nums ${numTone(nm.tone)}`}>{nm.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export function ScoreTreeMock(props: Props) {
  const [variant, setVariant] = useState<'A' | 'B'>('A')
  return (
    <div className="mx-auto max-w-[1280px] px-6 py-8">
      <div className="mb-1 font-num text-[11px] uppercase tracking-[0.14em] text-txt-3">Mockup · score derivation tree</div>
      <h1 className="font-display text-[30px] font-medium tracking-[-0.01em] text-txt-1">{props.symbol}{props.name ? ` · ${props.name}` : ''}</h1>
      <p className="mb-5 mt-1 max-w-[760px] font-sans text-[13px] text-txt-2">
        Same real data, two graphical trees. Pick the one that reads better — it becomes the standard
        derivation view across stock / sector / ETF / fund (aggregates branch into constituents instead of variables).
      </p>
      <div className="mb-6 inline-flex rounded-tile border border-edge-rule bg-surface-inset p-0.5">
        {(['A', 'B'] as const).map((v) => (
          <button key={v} type="button" onClick={() => setVariant(v)}
            className={`font-num text-[12px] px-3 py-1 rounded-tile transition-colors ${variant === v ? 'bg-surface-raised text-txt-1 font-semibold' : 'text-txt-3 hover:text-txt-1'}`}>
            {v === 'A' ? 'A · Top-down tree' : 'B · Left→right flow'}
          </button>
        ))}
      </div>
      {variant === 'A' ? <VariantA {...props} /> : <VariantB {...props} />}
    </div>
  )
}
