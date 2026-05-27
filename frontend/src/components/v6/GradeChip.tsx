'use client'

// frontend/src/components/v6/GradeChip.tsx
// Grade chip: AAA / AA / A / BBB / BB / B / failed-gate
// Design: DESIGN.md grade-chips — uppercase, 0.14em letter-spacing, 3px 7px padding, 2px radius
// Colors: signal-* palette from globals.css. failed-gate uses paper-deep + ink-tertiary text.

export type Grade = 'AAA' | 'AA' | 'A' | 'BBB' | 'BB' | 'B' | 'failed-gate'

export interface GradeChipProps {
  grade: Grade
  size?: 'sm' | 'md'
  className?: string
}

// Maps each grade to Tailwind classes using tokens from globals.css.
// AAA/AA/A use signal-pos tints (strongest → weakest).
// BBB uses signal-warn.
// BB/B use signal-neg tints (weakest → strongest).
// failed-gate uses paper-deep (--color-paper-deep: #F1ECDF) + text-ink-tertiary.
const GRADE_CLASSES: Record<Grade, string> = {
  AAA:          'bg-signal-pos text-paper',
  AA:           'bg-signal-pos/70 text-paper',
  A:            'bg-signal-pos/45 text-signal-pos',
  BBB:          'bg-signal-warn/20 text-signal-warn',
  BB:           'bg-signal-neg/30 text-signal-neg',
  B:            'bg-signal-neg text-paper',
  'failed-gate': 'bg-paper-deep text-ink-tertiary',
}

const SIZE_CLASSES: Record<NonNullable<GradeChipProps['size']>, string> = {
  sm: 'text-[10px]',
  md: 'text-[11px]',
}

export function GradeChip({ grade, size = 'md', className = '' }: GradeChipProps) {
  const colorClass = GRADE_CLASSES[grade]
  const sizeClass = SIZE_CLASSES[size]

  // Display text: failed-gate shows "NO SIGNAL", others show the grade label uppercase.
  const displayText = grade === 'failed-gate' ? 'NO SIGNAL' : grade

  return (
    <span
      role="img"
      aria-label={`Atlas grade ${grade}`}
      className={[
        'inline-flex items-center font-sans font-semibold uppercase rounded-[2px]',
        'px-[7px] py-[3px]',
        colorClass,
        sizeClass,
        className,
      ]
        .filter(Boolean)
        .join(' ')}
      style={{ letterSpacing: '0.14em' }}
    >
      {displayText}
    </span>
  )
}

export default GradeChip
