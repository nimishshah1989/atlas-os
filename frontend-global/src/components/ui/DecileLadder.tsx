// ── THE SIGNATURE COMPONENT, PORTED FROM ATLAS INDIA ──
// frontend/src/components/ui/DecileLadder.tsx, adapted to this board's tokens and components.
// "score → lens rows, each a track + its figure + its weight → expand to reveal THE ACTUAL
// NUMBERS first (the hero), then the evidence." Presentation-only and server-safe: the
// disclosure is a native <details>, so no client bundle and no hydration.
//
// ONE DEPARTURE FROM INDIA, AND WHY. India's row carries a DECILE per lens, cut within cap
// cohort. atlas_global cuts a decile on the COMPOSITE only (src/lib/queries/scores.ts) — neither
// journal holds a per-lens rank — so a "D7" on a lens row here would be a number nobody computed
// (rule #0). The row therefore shows the lens's own 0–100 score on this board's LensBar track,
// and the one real decile, the composite's, goes in a header tile, where the caller puts Atlas's
// own DecileMeter beside it.
//
// A LENS WITH NO PRODUCER IS AN EMPTY TRACK AND THE WORDS BELOW, NEVER A ZERO (rule #0): an
// instrument is not bad at something nobody has looked at yet.
import type { ReactNode } from 'react'
import { formatNum } from '@/lib/format'
import { LensBar } from './LensBar'

/** This board's one phrase for an absent measurement. Everywhere, so it can be searched for. */
export const NOT_MEASURED = 'not yet measured'

/** One of "the actual numbers" behind a lens: what was measured, and what it came to — already
 *  formatted WITH ITS UNIT by the adapter, because only the adapter knows the units. A null value
 *  is the phrase above, never a zero. */
export type LadderNumber = { label: string; value: string | null }

export type LadderLens = {
  key: string
  label: string
  /** The lens score, 0–100; null when no producer has reached it. */
  score: number | null
  /** Its weight in the blend, as a fraction. 0 is a real answer — an overlay, not a gap. */
  weight: number
  numbers?: LadderNumber[]
  evidence?: string[]
  pointer?: string
}

/** A header stat: the facts that used to be a paragraph. Value is a node so the caller can hand
 *  over the board's own glyphs (CompositeNumeral, DecileMeter, LeaderMark) rather than a string. */
export type LadderTile = { label: string; value: ReactNode; sub?: ReactNode }

export type DecileLadderProps = {
  lenses: LadderLens[]
  tiles?: LadderTile[]
  /** The population the header's decile was cut in — named once, on the column head. */
  cohortLabel?: string
  note?: ReactNode
  defaultOpenKey?: string
}

const COL_LENS = 'w-[112px] shrink-0'
const COL_SCORE = 'w-[46px] shrink-0 text-right'
const COL_WEIGHT = 'w-[54px] shrink-0 text-right'
const HEAD = 'font-num text-[9px] uppercase tracking-[0.14em] text-txt-3'

function LadderRow({ lens, open }: { lens: LadderLens; open: boolean }) {
  const numbers = lens.numbers ?? []
  const evidence = lens.evidence ?? []
  const overlay = lens.weight === 0
  const measured = numbers.some((n) => n.value != null)

  return (
    <details open={open} className="group/row border-b border-edge-hair last:border-0">
      <summary className="-mx-2 flex cursor-pointer list-none select-none items-center gap-3 rounded-tile px-2 py-2.5 transition-colors hover:bg-surface-raised/50">
        <span className={`${COL_LENS} font-sans text-[13px] text-txt-2`}>{lens.label}</span>
        {/* The board's own bar, one segment: an inset track filled to the score, and an EMPTY
            track when the score is null. Its title carries the real weight and the real score. */}
        <span className="flex-1">
          <LensBar segments={[{ key: lens.key, label: lens.label, weight: lens.weight, score: lens.score }]} />
        </span>
        <span className={`${COL_SCORE} font-display text-[15px] font-semibold tabular-nums text-txt-1`}>
          {lens.score == null ? <span className="text-txt-3">—</span> : formatNum(lens.score, 1)}
        </span>
        <span
          className={`${COL_WEIGHT} font-num text-[12px] tabular-nums text-txt-2`}
          title={overlay ? 'Overlay: scored and shown, not blended into the composite.' : undefined}
        >
          {overlay ? <span className="text-txt-3">overlay</span> : `${formatNum(lens.weight * 100)}%`}
        </span>
        <span className="w-[14px] shrink-0 text-right font-num text-[12px] text-txt-3 transition-transform group-open/row:rotate-90">
          ›
        </span>
      </summary>

      <div className="space-y-3.5 pb-4 pl-[124px] pr-2 pt-1">
        {numbers.length > 0 ? (
          <div>
            <p className="mb-2 font-num text-[10px] uppercase tracking-[0.14em] text-txt-2">
              {measured ? 'The actual numbers' : `The actual numbers · ${NOT_MEASURED}`}
            </p>
            <div className="grid grid-cols-2 gap-x-7 gap-y-2 sm:grid-cols-3">
              {numbers.map((n) => (
                <div
                  key={n.label}
                  className="flex items-baseline justify-between gap-2 border-b border-edge-hair py-1.5"
                >
                  <span className="font-sans text-[12.5px] text-txt-2">{n.label}</span>
                  <span
                    className={
                      n.value == null
                        ? 'font-sans text-[11.5px] text-txt-3'
                        : 'font-num text-[15px] font-medium tabular-nums text-txt-1'
                    }
                  >
                    {n.value ?? NOT_MEASURED}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <p className="font-sans text-[12px] text-txt-3">
            {lens.score == null ? `${lens.label}: ${NOT_MEASURED}.` : 'No sub-scores in the journal for this lens.'}
          </p>
        )}
        {lens.pointer && <p className="font-sans text-[11px] italic text-txt-3">{lens.pointer}</p>}
        {evidence.length > 0 && (
          <div className="border-l-2 border-brand/60 pl-3">
            <p className="mb-1 font-num text-[10px] uppercase tracking-[0.14em] text-brand">Evidence</p>
            {evidence.map((line) => (
              <p key={line} className="font-sans text-[12.5px] leading-[1.55] text-txt-2">
                {line}
              </p>
            ))}
          </div>
        )}
      </div>
    </details>
  )
}

export function DecileLadder({ lenses, tiles, cohortLabel, note, defaultOpenKey }: DecileLadderProps) {
  return (
    <div data-decile-ladder="">
      {((tiles && tiles.length > 0) || note) && (
        <div className="mb-4 flex flex-wrap items-stretch gap-3">
          {tiles?.map((t) => (
            <div key={t.label} className="rounded-tile border border-edge-hair bg-surface-raised px-4 py-2.5">
              <div className={HEAD}>{t.label}</div>
              <div className="mt-0.5 flex items-baseline gap-2 font-display text-[22px] font-semibold leading-none tabular-nums text-txt-1">
                {t.value}
              </div>
              {t.sub && (
                <div className="mt-1 flex flex-wrap items-center gap-1.5 font-sans text-[10px] leading-[1.4] text-txt-3">
                  {t.sub}
                </div>
              )}
            </div>
          ))}
          {note && <div className="min-w-[200px] flex-1 self-center font-sans text-[12px] leading-[1.5] text-txt-2">{note}</div>}
        </div>
      )}

      <div className="flex items-center gap-3 border-b border-edge-rule pb-2">
        <span className={`${COL_LENS} ${HEAD}`}>Lens</span>
        <span className={`flex-1 ${HEAD}`}>{cohortLabel ? `Lens score · ${cohortLabel}` : 'Lens score'}</span>
        <span className={`${COL_SCORE} ${HEAD}`}>/100</span>
        <span className={`${COL_WEIGHT} ${HEAD}`}>Weight</span>
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
