// frontend/src/components/sectors/SectorRiskWatch.tsx
'use client'
import { useState } from 'react'
import Link from 'next/link'
import { AlertTriangle, Users, Ban, Sparkles, ChevronDown, ChevronUp, HelpCircle } from 'lucide-react'
import type { SectorSnapshot } from '@/lib/queries/sectors'
import type { SectorDecision } from '@/lib/sectors-decision'

type SectorWithDecision = SectorSnapshot & { decision: SectorDecision }

const HIGH_CONCENTRATION_THRESHOLD = 0.6

type Tone = 'pos' | 'warn' | 'neg'
type CardSpec = {
  id: string
  Icon: React.ComponentType<{ className?: string }>
  title: string
  meaning: string
  action: string
  methodology: string
  tone: Tone
}

const TONE_STYLES: Record<Tone, { card: string; icon: string; count: string; pillBg: string; pillText: string }> = {
  pos:  { card: 'border-signal-pos/30 bg-signal-pos/5',   icon: 'text-signal-pos',   count: 'text-signal-pos',   pillBg: 'bg-signal-pos/10',  pillText: 'text-signal-pos' },
  warn: { card: 'border-signal-warn/30 bg-signal-warn/5', icon: 'text-signal-warn',  count: 'text-signal-warn',  pillBg: 'bg-signal-warn/10', pillText: 'text-signal-warn' },
  neg:  { card: 'border-signal-neg/30 bg-signal-neg/5',   icon: 'text-signal-neg',   count: 'text-signal-neg',   pillBg: 'bg-signal-neg/10',  pillText: 'text-signal-neg' },
}

function WatchCard({ spec, sectors }: { spec: CardSpec; sectors: SectorWithDecision[] }) {
  const [expanded, setExpanded] = useState(false)
  const [methodOpen, setMethodOpen] = useState(false)
  const styles = TONE_STYLES[spec.tone]
  const count = sectors.length

  return (
    <div className={`relative flex-1 px-4 py-3.5 border rounded-sm ${styles.card}`}>
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2">
          <spec.Icon className={`w-4 h-4 ${styles.icon}`} />
          <span className="font-sans text-xs font-semibold text-ink-primary uppercase tracking-wider">
            {spec.title}
          </span>
        </div>
        <button
          onClick={() => setMethodOpen(o => !o)}
          className="text-ink-tertiary hover:text-ink-primary transition-colors"
          aria-label={`How ${spec.title} is computed`}
          title="How this is computed"
        >
          <HelpCircle className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className={`font-mono text-2xl font-bold tabular-nums leading-none mb-2 ${styles.count}`}>
        {count}
      </div>

      <p className="font-sans text-[12px] text-ink-secondary leading-relaxed mb-1.5">
        {spec.meaning}
      </p>
      <p className="font-sans text-[12px] text-ink-primary leading-relaxed font-medium">
        <span className="text-ink-tertiary font-normal">Action → </span>
        {spec.action}
      </p>

      {methodOpen && (
        <div className="mt-2 px-3 py-2 bg-paper border border-paper-rule rounded-sm">
          <div className="flex items-baseline justify-between mb-1">
            <span className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">How it&apos;s computed</span>
            <button
              onClick={() => setMethodOpen(false)}
              className="font-sans text-[14px] text-ink-tertiary hover:text-ink-primary leading-none"
              aria-label="Close methodology"
            >
              ×
            </button>
          </div>
          <p className="font-sans text-[11px] text-ink-secondary leading-snug">
            {spec.methodology}
          </p>
        </div>
      )}

      <div className="mt-2.5 pt-2.5 border-t border-paper-rule/60">
        {count === 0 ? (
          <span className="font-sans text-[11px] text-ink-tertiary italic">No sectors match today.</span>
        ) : (
          <>
            <div className="flex flex-wrap gap-1">
              {(expanded ? sectors : sectors.slice(0, 3)).map(s => (
                <Link
                  key={s.sector_name}
                  href={`/sectors/${encodeURIComponent(s.sector_name)}`}
                  className={`inline-flex px-1.5 py-0.5 rounded-[2px] font-sans text-[11px] hover:underline ${styles.pillBg} ${styles.pillText}`}
                >
                  {s.sector_name}
                </Link>
              ))}
            </div>
            {count > 3 && (
              <button
                onClick={() => setExpanded(e => !e)}
                className="mt-1.5 inline-flex items-center gap-1 font-sans text-[10px] text-ink-tertiary hover:text-ink-primary transition-colors"
                aria-expanded={expanded}
              >
                {expanded ? (
                  <><ChevronUp className="w-3 h-3" /> show less</>
                ) : (
                  <><ChevronDown className="w-3 h-3" /> show all {count}</>
                )}
              </button>
            )}
          </>
        )}
      </div>
    </div>
  )
}

export function SectorRiskWatch({ sectors }: { sectors: SectorWithDecision[] }) {
  const enterCandidates = sectors.filter(s => s.decision === 'ENTER' || s.decision === 'ROTATE IN')
  const divergent       = sectors.filter(s => s.divergence_flag)
  const concentrated    = sectors.filter(s => {
    const v = s.leadership_concentration
    return v != null && parseFloat(v) >= HIGH_CONCENTRATION_THRESHOLD
  })
  const avoids = sectors.filter(s => s.sector_state === 'Avoid' || s.decision === 'EXIT')

  const cards: { spec: CardSpec; sectors: SectorWithDecision[] }[] = [
    {
      spec: {
        id: 'actionable',
        Icon: Sparkles,
        title: 'Actionable',
        meaning: 'Sectors flagged ENTER or ROTATE IN — bottom-up signals confirm a buy setup right now.',
        action: 'Open the sector and review its top picks; size positions per market × sector × stock multipliers.',
        methodology: 'Decision = ENTER when state=Overweight + momentum=Improving. ROTATE IN when state=Neutral + RS=Overweight + momentum=Improving. Both indicate fresh setups confirmed by constituent breadth, not just index strength.',
        tone: 'pos',
      },
      sectors: enterCandidates,
    },
    {
      spec: {
        id: 'divergent',
        Icon: AlertTriangle,
        title: 'Divergent',
        meaning: 'Sector index says one thing, constituent stocks say another. The signal is contradictory.',
        action: 'Wait for confirmation. Do not act on either reading alone — the model lacks conviction here.',
        methodology: 'Set when divergence_flag = true in atlas_sector_states_daily — typically when bottom-up state (derived from constituents\' RS, breadth, momentum) disagrees with top-down state (derived from the NSE sector index trend). Resolution comes when one side flips.',
        tone: 'warn',
      },
      sectors: divergent,
    },
    {
      spec: {
        id: 'narrow',
        Icon: Users,
        title: 'Narrow Leadership',
        meaning: `Concentration ≥ ${(HIGH_CONCENTRATION_THRESHOLD * 100).toFixed(0)}% — 1 or 2 names carrying the sector. Trend is fragile.`,
        action: 'Size smaller. If those leaders crack, the sector cracks. Broad participation is what makes trends persist.',
        methodology: `Concentration = share of the sector's total positive RS attributable to the top stocks. ≥ ${(HIGH_CONCENTRATION_THRESHOLD * 100).toFixed(0)}% means a few names dominate the aggregate; the rest of the sector isn't participating.`,
        tone: 'warn',
      },
      sectors: concentrated,
    },
    {
      spec: {
        id: 'exit',
        Icon: Ban,
        title: 'Exit / Avoid',
        meaning: 'Sectors flagged Avoid (state) or EXIT (decision). Capital preservation priority.',
        action: 'Close existing positions. Do not initiate new exposure here, even on bounces.',
        methodology: 'Avoid state triggers when bottom-up RS is deeply negative AND breadth collapses below floor. EXIT decision applies whenever state ∈ {Underweight, Avoid} — the floor for being in the sector at all has broken.',
        tone: 'neg',
      },
      sectors: avoids,
    },
  ]

  return (
    <div className="px-6 py-4 border-b border-paper-rule bg-paper-rule/5">
      <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-3">
        Watchlist — Today
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {cards.map(c => (
          <WatchCard key={c.spec.id} spec={c.spec} sectors={c.sectors} />
        ))}
      </div>
    </div>
  )
}
