// ── THE SIGNATURE COMPONENT (§1.1) ──
// "score → sub-components → the actual numbers" as one designed, glanceable block.
// Reused across stock / sector / ETF / fund via thin adapters (stockToLadder, …).
// Presentation-only + server-safe (native <details>). Each lens row = decile
// meter + decile figure + raw score; expand reveals THE ACTUAL NUMBERS first
// (the hero), then the 0–100 sub-component breakdown, then the evidence.
import type { ReactNode } from 'react'
import { DecileMeter } from './DecileMeter'
import { decileColor } from './decile'

export type LadderNumber = { label: string; value: string; tone?: 'pos' | 'neg' | 'neutral' }
export type LadderLens = {
  key: string
  label: string
  decile: number | null
  score: number | null
  numbers?: LadderNumber[]
  subs?: { label: string; v: number }[]
  evidence?: string[]
  pointer?: string
}
export type DecileLadderProps = {
  lenses: LadderLens[]
  strength?: number | null
  leadership?: { n: number; of: number }
  cohortLabel?: string
  note?: ReactNode
  defaultOpenKey?: string
}

const numTone = (t?: LadderNumber['tone']) =>
  t === 'pos' ? 'text-sig-pos' : t === 'neg' ? 'text-sig-neg' : 'text-txt-1'

function LadderRow({ lens, open }: { lens: LadderLens; open: boolean }) {
  const { decile, score } = lens
  // §1.1: the 0–100 sub-component scores do NOT reconcile with the decile/raw headline
  // (e.g. D10/80 over ~20 sub-bars — different scales). Per FM, we DROP them and let the
  // real numbers carry the breakdown. `subs` stays on the type but is no longer rendered.
  const numbers = lens.numbers ?? []
  const evidence = lens.evidence ?? []

  return (
    <details open={open} className="group/row border-b border-edge-hair last:border-0">
      <summary className="-mx-2 flex cursor-pointer list-none select-none items-center gap-3 rounded-tile px-2 py-2.5 transition-colors hover:bg-surface-raised/50">
        <span className="w-[112px] shrink-0 font-sans text-[13px] text-txt-2">{lens.label}</span>
        <span className="flex-1"><DecileMeter decile={decile} /></span>
        <span className="w-[40px] shrink-0 text-right font-display text-[15px] font-semibold tabular-nums" style={{ color: decileColor(decile) }}>
          {decile != null ? `D${decile}` : '—'}
        </span>
        <span className="w-[42px] shrink-0 text-right font-num text-[12px] tabular-nums text-txt-2">
          {score != null ? score.toFixed(0) : '—'}
        </span>
        <span className="w-[14px] shrink-0 text-right font-num text-[12px] text-txt-3 transition-transform group-open/row:rotate-90">›</span>
      </summary>

      <div className="space-y-3.5 pb-4 pl-[124px] pr-2 pt-1">
        {numbers.length > 0 && (
          <div>
            <p className="mb-2 font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">The actual numbers</p>
            <div className="grid grid-cols-2 gap-x-7 gap-y-1.5 sm:grid-cols-3">
              {numbers.map((n) => (
                <div key={n.label} className="flex items-baseline justify-between gap-2 border-b border-edge-hair py-1">
                  <span className="font-sans text-[11px] text-txt-3">{n.label}</span>
                  <span className={`font-num text-[13px] tabular-nums ${numTone(n.tone)}`}>{n.value}</span>
                </div>
              ))}
            </div>
          </div>
        )}
        {lens.pointer && <p className="font-sans text-[11px] italic text-txt-3">{lens.pointer}</p>}
        {evidence.length > 0 && (
          <div className="border-l-2 border-brand/60 pl-3">
            <p className="mb-1 font-num text-[9px] uppercase tracking-[0.14em] text-brand">Evidence</p>
            {evidence.map((line, i) => (
              <p key={i} className="font-sans text-[12px] leading-[1.5] text-txt-2">{line}</p>
            ))}
          </div>
        )}
      </div>
    </details>
  )
}

export function DecileLadder({ lenses, strength, leadership, cohortLabel, note, defaultOpenKey }: DecileLadderProps) {
  return (
    <div>
      {(strength != null || leadership || note) && (
        <div className="mb-4 flex flex-wrap items-stretch gap-3">
          {strength != null && (
            <div className="rounded-tile border border-edge-hair bg-surface-raised px-4 py-2.5">
              <div className="font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">Strength</div>
              <div className="mt-0.5 font-display text-[22px] font-semibold leading-none tabular-nums" style={{ color: decileColor(Math.round(strength)) }}>
                {strength.toFixed(1)}
              </div>
              <div className="mt-0.5 font-sans text-[10px] text-txt-3">avg conviction decile</div>
            </div>
          )}
          {leadership && (
            <div className="rounded-tile border border-edge-hair bg-surface-raised px-4 py-2.5">
              <div className="font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">Leadership</div>
              <div
                className="mt-0.5 font-display text-[22px] font-semibold leading-none tabular-nums"
                style={{ color: leadership.n >= 2 ? 'var(--color-sig-pos)' : leadership.n === 1 ? 'var(--color-sig-warn)' : 'var(--color-txt-3)' }}
              >
                {leadership.n}/{leadership.of}
              </div>
              <div className="mt-0.5 font-sans text-[10px] text-txt-3">lenses top-decile</div>
            </div>
          )}
          {note && <div className="min-w-[200px] flex-1 self-center font-sans text-[12px] leading-[1.5] text-txt-2">{note}</div>}
        </div>
      )}

      <div className="flex items-center gap-3 border-b border-edge-rule pb-2">
        <span className="w-[112px] shrink-0 font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">Lens</span>
        <span className="flex-1 font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">
          {cohortLabel ? `Decile · ${cohortLabel} cohort` : 'Decile within cohort'}
        </span>
        <span className="w-[40px] shrink-0 text-right font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">D</span>
        <span className="w-[42px] shrink-0 text-right font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">Raw</span>
        <span className="w-[14px] shrink-0" />
      </div>

      <div>
        {lenses.map((l) => (
          <LadderRow key={l.key} lens={l} open={l.key === defaultOpenKey} />
        ))}
      </div>
    </div>
  )
}
