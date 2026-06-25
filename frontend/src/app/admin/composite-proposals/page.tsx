// SP04 Stage 4a — admin review queue for auto-generated weight proposals.
export const dynamic = 'force-dynamic'

import { getPendingProposals } from '@/lib/queries/proposals'
import { getRecentReverts } from '@/lib/queries/weight_performance'
import { ProposalDiffTable } from '@/components/admin/ProposalDiffTable'
import { ProposalActionBar } from '@/components/admin/ProposalActionBar'
import { RevertBanner } from '@/components/admin/RevertBanner'

const TIER_LABELS: Record<string, string> = {
  tier_1_megacap: 'Tier 1 (mega-cap)',
  tier_2_largecap: 'Tier 2 (large-cap)',
  tier_3_uppermid: 'Tier 3 (upper mid-cap)',
  tier_4_lowermid: 'Tier 4 (lower mid-cap)',
  tier_5_smallcap: 'Tier 5 (small-cap)',
}

function fmtDate(d: Date | string): string {
  const date = typeof d === 'string' ? new Date(d) : d
  return date.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Kolkata',
  })
}

export default async function CompositeProposalsPage() {
  const [proposals, reverts] = await Promise.all([
    getPendingProposals(),
    getRecentReverts(),
  ])

  return (
    <main className="min-h-screen bg-surface-panel px-8 py-6 max-w-7xl mx-auto">
      <header className="mb-6">
        <div className="font-sans text-[10px] text-txt-3 uppercase tracking-wider">
          Atlas · Admin · Composite
        </div>
        <h1 className="font-display text-2xl text-txt-1 mt-1">
          Conviction Weight Proposals
        </h1>
        <p className="font-sans text-xs text-txt-2 mt-1">
          Stage 4a auto-optimization loop. Candidates re-weight per-tier signals
          using rolling out-of-sample IC. Approval applies a 15% Bayesian blend
          toward the candidate; the existing weight set is bookended with
          effective_to=today and the new set takes effect tomorrow.
        </p>
        <p className="font-sans text-[11px] text-txt-3 mt-2">
          {proposals.length} pending proposal{proposals.length === 1 ? '' : 's'}
        </p>
      </header>

      <RevertBanner reverts={reverts} />

      {proposals.length === 0 ? (
        <div className="border border-edge-hair rounded-panel bg-surface-panel p-6">
          <p className="font-sans text-sm text-txt-2">
            No pending proposals. The nightly generator only emits a candidate
            when the rolling IC re-weight differs materially (|Δ| ≥ 0.05) from
            the active weights.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {proposals.map((p) => {
            const tierLabel = TIER_LABELS[p.tier] ?? p.tier
            const ic = p.proposed_holdout_ic
              ? parseFloat(p.proposed_holdout_ic).toFixed(4)
              : '—'
            const currentIc = p.current_holdout_ic
              ? parseFloat(p.current_holdout_ic).toFixed(4)
              : '—'
            const delta = p.ic_delta ? parseFloat(p.ic_delta) : null
            const deltaSign = delta !== null && delta >= 0 ? '+' : ''
            const deltaColor =
              delta !== null && delta > 0
                ? 'text-sig-pos'
                : delta !== null && delta < 0
                  ? 'text-sig-neg'
                  : 'text-txt-3'

            return (
              <div
                key={p.id}
                className="border border-edge-hair rounded-panel bg-surface-panel p-5"
              >
                <div className="flex items-baseline justify-between mb-2 flex-wrap gap-2">
                  <div>
                    <h2 className="font-display text-lg text-txt-1">
                      {tierLabel}
                    </h2>
                    <div className="font-sans text-[11px] text-txt-3 mt-0.5">
                      Generated {fmtDate(p.created_at)} ·{' '}
                      <code className="font-num">{p.generator_version}</code>
                    </div>
                  </div>
                  <div className="flex items-baseline gap-3 font-num text-xs tabular-nums">
                    <span className="text-txt-2">
                      Current IC{' '}
                      <span className="text-txt-1">{currentIc}</span>
                    </span>
                    <span className="text-txt-2">
                      Proposed IC{' '}
                      <span className="text-txt-1">{ic}</span>
                    </span>
                    <span className={deltaColor}>
                      Δ {deltaSign}
                      {delta !== null ? delta.toFixed(4) : '—'}
                    </span>
                  </div>
                </div>
                {p.rationale && (
                  <p className="font-sans text-xs text-txt-2 mb-3 italic">
                    {p.rationale}
                  </p>
                )}
                <ProposalDiffTable
                  current={p.current_weights}
                  proposed={p.proposed_weights}
                />
                <ProposalActionBar proposalId={p.id} />
              </div>
            )
          })}
        </div>
      )}
    </main>
  )
}
