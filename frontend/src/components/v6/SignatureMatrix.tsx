'use client'

// frontend/src/components/v6/SignatureMatrix.tsx
// Factor-exposure grid for fund + ETF list/detail pages.
// Each tile shows a factor name, exposure chip (POSITIVE/NEUTRAL/NEGATIVE/null),
// raw score, and rank. InfoTooltip explains each factor.
// Token discipline: signal-* + paper + ink only.

import { InfoTooltip } from '@/components/ui/InfoTooltip'
import { signedPct } from '@/lib/v6/decimal'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type SignatureExposure = 'POSITIVE' | 'NEUTRAL' | 'NEGATIVE' | null

export type SignatureCell = {
  factor: string
  exposure: SignatureExposure
  raw_score: string | null  // stringified Decimal from Postgres NUMERIC
  rank_in_category: number | null
}

export interface SignatureMatrixProps {
  cells: SignatureCell[]
  asset_label: string
  className?: string
}

// ---------------------------------------------------------------------------
// Static factor tooltip copy
// ---------------------------------------------------------------------------

const FACTOR_DESCRIPTIONS: Record<string, string> = {
  Value: 'Book/price, earnings yield and EV/EBITDA relative to the fund\'s peer category.',
  Momentum: '12-1 month price momentum of the fund\'s holdings vs the Nifty 500 universe.',
  Quality: 'ROE, debt/equity and earnings stability of the top-20 holdings.',
  Size: 'Weighted average market capitalisation of holdings — higher means large-cap tilt.',
  LowVol: '36-month realised volatility of the fund vs its category median.',
  ESG: 'Weighted ESG score of holdings using Atlas ESG dataset.',
  Growth: 'Revenue and earnings growth rate of holdings vs category median.',
  Yield: 'Dividend yield of the portfolio vs category benchmark.',
}

function factorTooltip(factor: string): string {
  return FACTOR_DESCRIPTIONS[factor] ?? `${factor}: exposure relative to category peers.`
}

// ---------------------------------------------------------------------------
// Exposure chip
// ---------------------------------------------------------------------------

const EXPOSURE_CLASSES: Record<NonNullable<SignatureExposure>, string> = {
  POSITIVE: 'bg-signal-pos text-paper',
  NEUTRAL:  'bg-signal-warn/20 text-ink-primary',
  NEGATIVE: 'bg-signal-neg text-paper',
}

function ExposureChip({ exposure }: { exposure: SignatureExposure }) {
  if (exposure === null) {
    return (
      <span className="inline-flex items-center bg-paper-deep text-ink-tertiary text-[10px] font-semibold uppercase rounded-[2px] px-[6px] py-[2px]" style={{ letterSpacing: '0.10em' }}>
        N/A
      </span>
    )
  }
  return (
    <span
      className={[
        'inline-flex items-center text-[10px] font-semibold uppercase rounded-[2px] px-[6px] py-[2px]',
        EXPOSURE_CLASSES[exposure],
      ].join(' ')}
      style={{ letterSpacing: '0.10em' }}
    >
      {exposure}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Single factor tile
// ---------------------------------------------------------------------------

function FactorTile({ cell }: { cell: SignatureCell }) {
  const { factor, exposure, raw_score, rank_in_category } = cell

  // Tile background
  const tileBg =
    exposure === null
      ? 'bg-paper-deep'
      : exposure === 'POSITIVE'
      ? 'bg-signal-pos/5 border-signal-pos/20'
      : exposure === 'NEGATIVE'
      ? 'bg-signal-neg/5 border-signal-neg/20'
      : 'bg-paper border-paper-rule'

  const scoreText = signedPct(raw_score)
  const rankLabel =
    rank_in_category !== null ? `Rank ${rank_in_category}` : null

  const ariaLabel = [
    `${factor}: ${exposure ?? 'no data'}`,
    raw_score !== null ? `score ${scoreText}` : null,
    rank_in_category !== null ? `rank ${rank_in_category}` : null,
  ]
    .filter(Boolean)
    .join(', ')

  return (
    <div
      role="listitem"
      aria-label={ariaLabel}
      className={[
        'flex flex-col gap-1.5 rounded-[3px] border p-3',
        tileBg,
      ].join(' ')}
    >
      {/* Factor name + info icon */}
      <div className="flex items-center gap-1">
        <span className="text-[11px] font-semibold text-ink-primary leading-tight">
          {factor}
        </span>
        <InfoTooltip content={factorTooltip(factor)} />
      </div>

      {/* Exposure chip */}
      <ExposureChip exposure={exposure} />

      {/* Score */}
      <span
        className={[
          'font-mono text-[11px]',
          exposure === null ? 'text-ink-tertiary' : 'text-ink-secondary',
        ].join(' ')}
      >
        {scoreText}
      </span>

      {/* Rank chip */}
      {rankLabel !== null && (
        <span className="text-[10px] text-ink-tertiary leading-none">
          {rankLabel}
        </span>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Public component
// ---------------------------------------------------------------------------

export function SignatureMatrix({ cells, asset_label, className = '' }: SignatureMatrixProps) {
  return (
    <section
      aria-label={`Factor exposure matrix for ${asset_label}`}
      className={['w-full', className].join(' ').trim()}
    >
      <div
        role="list"
        className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3"
      >
        {cells.map((cell) => (
          <FactorTile key={cell.factor} cell={cell} />
        ))}
      </div>
    </section>
  )
}

export default SignatureMatrix
