// frontend/src/components/regime/RegimeVerdict.tsx
// One-line verdict sentence derived from regime state + deployment % + leading sectors.
// Pure presentational: no DB, no async. Called from page.tsx (server component).
import { LinkedSector } from '@/components/ui/LinkedToken'

type Props = {
  regimeState: string
  deploymentPct: number
  leadingSectors: string[]
}

function buildVerdictPrefix(regimeState: string, deploymentPct: number): string {
  switch (regimeState) {
    case 'Risk-On':
      return `Risk-On — deploy ${deploymentPct}%. Add Leader/Strong names broadly across the market.`
    case 'Constructive':
      return `Constructive — deploy ${deploymentPct}%. Add Stage 2a/2b breakouts; prefer leading sectors.`
    case 'Cautious':
      return `Cautious — deploy ${deploymentPct}%. Add Leader/Strong names in leading sectors only. Trim Stage 3→4 holdings.`
    case 'Risk-Off':
      return `Risk-Off — deploy ${deploymentPct}%. Preserve capital. Hold only highest-conviction Stage 2 positions.`
    default:
      return `${regimeState} — deploy ${deploymentPct}%.`
  }
}

export function RegimeVerdict({ regimeState, deploymentPct, leadingSectors }: Props) {
  const prefix = buildVerdictPrefix(regimeState, deploymentPct)
  const topSectors = leadingSectors.slice(0, 3)

  const accentColor =
    regimeState === 'Risk-On'      ? 'text-signal-pos' :
    regimeState === 'Constructive' ? 'text-teal' :
    regimeState === 'Cautious'     ? 'text-signal-warn' :
    regimeState === 'Risk-Off'     ? 'text-signal-neg' :
    'text-ink-secondary'

  return (
    <div className="px-6 py-4 border-b border-paper-rule bg-paper">
      <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-1">
        Decision
      </div>
      <p
        className={`font-serif text-base leading-snug ${accentColor}`}
        data-testid="regime-verdict"
      >
        {prefix}
        {topSectors.length > 0 && (
          <span>
            {' '}Focus on leading sectors:{' '}
            {topSectors.map((sector, i) => (
              <span key={sector}>
                <LinkedSector sector={sector} className="font-serif" />
                {i < topSectors.length - 1 ? ', ' : '.'}
              </span>
            ))}
          </span>
        )}
      </p>
    </div>
  )
}
