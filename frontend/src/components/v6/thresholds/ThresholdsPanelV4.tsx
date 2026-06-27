'use client'
// ThresholdsPanelV4 — the FM's methodology control panel. Every knob in
// foundation_staging.atlas_thresholds, visible + editable within its own min/max, grouped by
// category. Lens weights are the hero (with a live "sums to 1.00" check). Save persists; Preview
// shows how the composite would shift (no write); Commit re-blends the live scores in seconds.
// The math is the canonical scorer (via the recompute engine) — this panel only edits inputs.
import { useMemo, useState } from 'react'
import type { ThresholdRow } from '@/lib/queries/v6/thresholds'

const CONV_LENSES = ['technical', 'fundamental', 'flow', 'catalyst'] as const // weights that drive the composite

const CATEGORY_ORDER = [
  'lens_weight', 'lens_convergence', 'lens_conviction', 'lens_valuation',
  'rs', 'sector', 'momentum', 'volume', 'flow', 'fundamental', 'risk', 'gate',
  'regime', 'etf', 'etf_rank', 'fund', 'funds', 'mf_rank', 'mf_holdings', 'decision',
]
const CATEGORY_LABEL: Record<string, string> = {
  lens_weight: 'Lens weights (composite blend)',
  lens_convergence: 'Convergence multipliers',
  lens_conviction: 'Conviction tier cut-offs',
  lens_valuation: 'Valuation lens',
  rs: 'Relative strength', sector: 'Sector', momentum: 'Momentum', volume: 'Volume',
  flow: 'Flow', fundamental: 'Fundamental', risk: 'Risk', gate: 'Universe gates', regime: 'Regime',
  etf: 'ETF', etf_rank: 'ETF ranking', fund: 'Fund', funds: 'Funds', mf_rank: 'MF ranking',
  mf_holdings: 'MF holdings', decision: 'Decision',
}

const fmtNum = (v: number) => (Number.isInteger(v) ? String(v) : v.toFixed(v < 1 && v > -1 ? 3 : 2))

type Status = { kind: 'idle' | 'busy' | 'ok' | 'err'; msg: string }

export function ThresholdsPanelV4({ rows }: { rows: ThresholdRow[] }) {
  const base = useMemo(() => Object.fromEntries(rows.map((r) => [r.key, r.value])), [rows])
  const [draft, setDraft] = useState<Record<string, number>>(base)
  const [status, setStatus] = useState<Status>({ kind: 'idle', msg: '' })
  const [savedSinceEdit, setSavedSinceEdit] = useState(true)

  const byKey = useMemo(() => Object.fromEntries(rows.map((r) => [r.key, r])), [rows])
  const dirtyKeys = rows.filter((r) => draft[r.key] !== base[r.key]).map((r) => r.key)
  const dirty = dirtyKeys.length > 0

  const grouped = useMemo(() => {
    const m = new Map<string, ThresholdRow[]>()
    for (const r of rows) (m.get(r.category) ?? m.set(r.category, []).get(r.category)!).push(r)
    const cats = [...m.keys()].sort((a, b) => {
      const ia = CATEGORY_ORDER.indexOf(a), ib = CATEGORY_ORDER.indexOf(b)
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a.localeCompare(b)
    })
    return cats.map((c) => [c, m.get(c)!] as const)
  }, [rows])

  // lens-weight sum check (the 4 conviction weights that form the composite)
  const weightSum = CONV_LENSES.reduce((a, l) => a + (draft[`lens_weight_${l}`] ?? 0), 0)
  const weightsOff = Math.abs(weightSum - 1) > 0.001

  const setVal = (key: string, raw: number) => {
    setDraft((d) => ({ ...d, [key]: raw }))
    setSavedSinceEdit(false)
  }
  const resetKey = (key: string) => setVal(key, byKey[key].default ?? base[key])
  const revertAll = () => { setDraft(base); setSavedSinceEdit(true); setStatus({ kind: 'idle', msg: '' }) }

  async function save() {
    setStatus({ kind: 'busy', msg: 'Saving…' })
    const edits = dirtyKeys.map((k) => ({ key: k, value: draft[k] }))
    const res = await fetch('/api/thresholds/save', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ edits }),
    }).then((r) => r.json()).catch((e) => ({ error_code: 'network', message: String(e) }))
    if (res.error_code) { setStatus({ kind: 'err', msg: res.message }); return }
    const { updated, rejected } = res.data
    setSavedSinceEdit(true)
    setStatus({
      kind: rejected.length ? 'err' : 'ok',
      msg: `Saved ${updated.length} change${updated.length === 1 ? '' : 's'}` +
        (rejected.length ? ` · ${rejected.length} rejected: ${rejected.map((x: { key: string; reason: string }) => `${x.key} (${x.reason})`).join(', ')}` : ''),
    })
  }

  async function recompute(apply: boolean) {
    setStatus({ kind: 'busy', msg: apply ? 'Recalculating live scores…' : 'Previewing impact…' })
    const res = await fetch('/api/thresholds/recompute', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ apply }),
    }).then((r) => r.json()).catch((e) => ({ error_code: 'network', message: String(e) }))
    if (res.error_code) { setStatus({ kind: 'err', msg: res.message }); return }
    const d = res.data
    setStatus({
      kind: 'ok',
      msg: apply
        ? `Recalculated — ${d.rows_updated} rows updated (${d.scope}). Scores are live.`
        : `Preview: ${d.composite_changed} of ${d.n} composites shift · ${d.tier_changed} change tier · max Δ ${d.max_abs_delta}. Save, then Commit to write.`,
    })
  }

  const statusColor = status.kind === 'err' ? 'text-sig-neg' : status.kind === 'ok' ? 'text-sig-pos' : 'text-txt-2'

  return (
    <div className="space-y-5">
      {/* action bar */}
      <div className="sticky top-0 z-20 -mx-6 border-b border-edge-hair bg-surface-base/95 px-6 py-3 backdrop-blur">
        <div className="flex flex-wrap items-center gap-3">
          <span className="font-num text-[11px] uppercase tracking-[0.14em] text-txt-3">
            {dirty ? `${dirtyKeys.length} unsaved` : 'no changes'}
          </span>
          <button type="button" onClick={save} disabled={!dirty || status.kind === 'busy'}
            className="rounded-tile bg-brand px-3 py-1.5 font-num text-[12px] font-semibold text-surface-base disabled:opacity-40">
            Save changes
          </button>
          <button type="button" onClick={() => recompute(false)} disabled={status.kind === 'busy'}
            className="rounded-tile border border-edge-rule px-3 py-1.5 font-num text-[12px] text-txt-1 hover:bg-surface-raised disabled:opacity-40">
            Preview impact
          </button>
          <button type="button" onClick={() => recompute(true)} disabled={status.kind === 'busy' || !savedSinceEdit || dirty}
            title={dirty || !savedSinceEdit ? 'Save your edits first' : 'Re-blend the live scores'}
            className="rounded-tile border border-sig-pos/50 bg-sig-pos/10 px-3 py-1.5 font-num text-[12px] font-semibold text-sig-pos hover:bg-sig-pos/20 disabled:opacity-40">
            Commit &amp; recalculate
          </button>
          {dirty && (
            <button type="button" onClick={revertAll} className="font-num text-[11px] text-txt-3 hover:text-txt-1">
              revert all
            </button>
          )}
          {status.msg && <span className={`font-sans text-[12px] ${statusColor}`}>{status.msg}</span>}
        </div>
      </div>

      {grouped.map(([cat, items]) => (
        <section key={cat} className="rounded-panel border border-edge-hair bg-surface-panel">
          <div className="flex items-center justify-between border-b border-edge-hair px-4 py-2.5">
            <h2 className="font-display text-[15px] font-medium text-txt-1">{CATEGORY_LABEL[cat] ?? cat}</h2>
            {cat === 'lens_weight' && (
              <span className={`font-num text-[12px] tabular-nums ${weightsOff ? 'text-sig-neg' : 'text-sig-pos'}`}>
                composite weights sum = {weightSum.toFixed(2)} {weightsOff ? '(should be 1.00)' : '✓'}
              </span>
            )}
          </div>
          <div className="divide-y divide-edge-hair/60">
            {items.map((r) => (
              <ThresholdControl key={r.key} row={r} value={draft[r.key]} dirty={draft[r.key] !== base[r.key]}
                onChange={(v) => setVal(r.key, v)} onReset={() => resetKey(r.key)} />
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}

function ThresholdControl({
  row, value, dirty, onChange, onReset,
}: { row: ThresholdRow; value: number; dirty: boolean; onChange: (v: number) => void; onReset: () => void }) {
  const { min, max } = row
  const step = max != null && min != null && max - min <= 2 ? 0.01 : max != null && max <= 100 ? 0.1 : 1
  const clamped = (v: number) => (min != null && v < min ? min : max != null && v > max ? max : v)
  const out = value != null && ((min != null && value < min) || (max != null && value > max))

  return (
    <div className="flex items-center gap-4 px-4 py-2.5">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-num text-[12px] text-txt-1">{row.key}</span>
          {row.units && <span className="font-num text-[9px] uppercase tracking-wider text-txt-3">{row.units}</span>}
          {dirty && <span className="h-1.5 w-1.5 rounded-full bg-brand" title="unsaved" />}
        </div>
        {row.description && <p className="mt-0.5 truncate font-sans text-[11px] text-txt-3">{row.description}</p>}
      </div>
      {/* slider when bounded, always a number input */}
      {min != null && max != null && (
        <input type="range" min={min} max={max} step={step} value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="h-1 w-[160px] shrink-0 cursor-pointer accent-brand" />
      )}
      <input type="number" value={value} step={step} min={min ?? undefined} max={max ?? undefined}
        onChange={(e) => onChange(e.target.value === '' ? value : clamped(Number(e.target.value)))}
        className={`w-[92px] shrink-0 rounded-tile border bg-surface-inset px-2 py-1 text-right font-num text-[12px] tabular-nums ${out ? 'border-sig-neg text-sig-neg' : 'border-edge-rule text-txt-1'}`} />
      <div className="w-[120px] shrink-0 text-right font-num text-[9.5px] tabular-nums text-txt-3">
        {min != null && max != null ? <>range {fmtNum(min)}–{fmtNum(max)}<br /></> : null}
        <button type="button" onClick={onReset} className="hover:text-brand">
          default {row.default != null ? fmtNum(row.default) : '—'} ↺
        </button>
      </div>
    </div>
  )
}
