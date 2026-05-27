'use client'

// frontend/src/components/v6/SwitchProposalsBanner.tsx
// D.5 — Banner at top of /v6/funds when held funds have SWITCH proposals.
// Silent (renders nothing) when proposals.length === 0 — FM-critic §1.6 gap #2.
// v6.0: renders nothing because atlas_paper_portfolio is empty at launch.

import { useState } from 'react'
import type { SwitchProposal } from '@/lib/queries/v6/switch_proposals'

export interface SwitchProposalsBannerProps {
  proposals: SwitchProposal[]
  className?: string
}

function QuartileChip({ quartile }: { quartile: string | null }) {
  if (!quartile) return <span className="font-mono text-xs text-ink-tertiary">—</span>
  const cls =
    quartile === 'Q1' || quartile === 'Q2'
      ? 'bg-signal-pos/15 text-signal-pos'
      : 'bg-signal-neg/15 text-signal-neg'
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded-[2px] font-mono text-[10px] font-semibold ${cls}`} aria-label={`Quartile ${quartile}`}>
      {quartile}
    </span>
  )
}

function FundCol({ label, name, quartile }: { label: string; name: string | null; quartile: string | null }) {
  return (
    <div className="flex flex-col gap-0.5 min-w-[160px]">
      <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">{label}</span>
      <span className="text-sm font-medium text-ink-primary leading-snug">{name ?? '—'}</span>
      {quartile && (
        <div className="flex items-center gap-1.5 mt-0.5">
          <QuartileChip quartile={quartile} />
          <span className="text-[11px] text-ink-secondary">peer rank</span>
        </div>
      )}
    </div>
  )
}

function ProposalRow({ proposal, index }: { proposal: SwitchProposal; index: number }) {
  return (
    <div className={`flex flex-wrap items-start gap-x-6 gap-y-1.5 py-3 ${index > 0 ? 'border-t border-signal-warn/20' : ''}`}>
      <FundCol label="Current holding" name={proposal.source_name} quartile={proposal.source_peer_quartile} />
      <div className="flex items-center pt-4">
        <span className="text-ink-tertiary text-sm font-mono">→</span>
      </div>
      {proposal.target_name ? (
        <FundCol label="Suggested switch" name={proposal.target_name} quartile={proposal.target_peer_quartile} />
      ) : (
        <div className="flex flex-col gap-0.5 min-w-[160px]">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">Suggested switch</span>
          <span className="text-sm text-ink-tertiary italic">No qualifying fund found in {proposal.category}</span>
        </div>
      )}
      <div className="flex flex-col gap-0.5">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">Category</span>
        <span className="text-[11px] text-ink-secondary leading-snug max-w-[160px]">{proposal.category}</span>
      </div>
    </div>
  )
}

export function SwitchProposalsBanner({ proposals, className = '' }: SwitchProposalsBannerProps): React.ReactElement | null {
  const [expanded, setExpanded] = useState(false)

  if (proposals.length === 0) return null

  const count = proposals.length
  const summaryText = count === 1
    ? '1 of your fund holdings should switch'
    : `${count} of your fund holdings should switch`

  return (
    <div
      className={['rounded-[4px] border border-signal-warn/40 bg-signal-warn/5', className].join(' ')}
      role="region"
      aria-label="SWITCH proposals"
    >
      <button
        type="button"
        onClick={() => setExpanded(v => !v)}
        aria-expanded={expanded}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left rounded-[4px] hover:bg-signal-warn/10 transition-colors"
      >
        <div className="flex items-center gap-2">
          <svg aria-hidden="true" width="15" height="15" viewBox="0 0 15 15" fill="none" className="shrink-0 text-signal-warn">
            <path d="M7.5 1L14 13H1L7.5 1Z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
            <line x1="7.5" y1="6" x2="7.5" y2="9.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
            <circle cx="7.5" cy="11.5" r="0.75" fill="currentColor" />
          </svg>
          <span className="text-sm font-medium text-ink-primary">{summaryText}</span>
          <span className="text-xs text-ink-tertiary">— click for proposals</span>
        </div>
        <svg
          aria-hidden="true" width="14" height="14" viewBox="0 0 14 14" fill="none"
          stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"
          className={`transition-transform duration-200 ${expanded ? 'rotate-180' : ''}`}
        >
          <path d="M2 4l5 5 5-5" />
        </svg>
      </button>

      {expanded && (
        <div className="border-t border-signal-warn/20 px-4 pb-3">
          {proposals.map((p, i) => (
            <ProposalRow key={p.source_iid} proposal={p} index={i} />
          ))}
          <p className="mt-3 text-[10px] text-ink-tertiary leading-relaxed">
            SWITCH criteria: same-category only; current fund at Q3/Q4 peer
            quartile + qualifying Q1/Q2 alternative with ≥6 months consistency.
            Tie-break: lowest expense ratio.
          </p>
        </div>
      )}
    </div>
  )
}

export default SwitchProposalsBanner
