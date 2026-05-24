export const dynamic = 'force-dynamic'

import { getAllStocks } from '@/lib/queries/stocks'
import { getCurrentRegime } from '@/lib/queries/regime'
import { getComponentValidations } from '@/lib/queries/component_validation'
import { getRSLeaders, getBreakoutCandidates, getDeteriorationWatch } from '@/lib/queries/leaders'
import { getEffectivePolicy } from '@/lib/queries/policy'
import { StocksClientShell } from '@/components/stocks/StocksClientShell'
import type { PolicyEntryParams } from '@/lib/policy-entry-filter'

export default async function StocksPage({
  searchParams,
}: {
  searchParams: Promise<{ sector?: string; index?: string; portfolio?: string }>
}) {
  const params = await searchParams
  const sectorFilter  = params.sector?.trim() || undefined
  const indexFilter   = params.index?.trim() || undefined
  const portfolioId   = params.portfolio?.trim() || undefined

  // Flow mode: active portfolio + sector filter → load effective policy for entry-rule filter.
  // If no portfolio param, policy stays undefined (engine view — no constraints applied).
  let policyEntryParams: PolicyEntryParams | undefined

  if (portfolioId && sectorFilter) {
    try {
      const policy = await getEffectivePolicy(portfolioId)
      if (policy !== null) {
        const buyStates = policy.buy_states.value as string[] | null
        policyEntryParams = {
          buy_states: buyStates ?? [],
          min_within_state_rank: parseFloat(
            (policy.min_within_state_rank.value as string | null) ?? '0'
          ),
          min_rs_rank: parseFloat(
            (policy.min_rs_rank.value as string | null) ?? '0'
          ),
        }
      }
    } catch {
      // Non-fatal: policy load failure degrades to unfiltered engine view.
    }
  }

  const [stocks, regime, validations, leaders, breakouts, deterioration] = await Promise.all([
    getAllStocks({ sectorFilter, indexFilter }),
    getCurrentRegime(),
    getComponentValidations(),
    getRSLeaders(null, 50),
    getBreakoutCandidates(),
    getDeteriorationWatch(),
  ])

  if (stocks.length === 0) {
    return (
      <div className="p-8">
        <p className="font-sans text-sm text-ink-secondary">
          No stock data available. Run the nightly pipeline first.
        </p>
      </div>
    )
  }

  const investableCount = stocks.filter(s => s.is_investable).length
  const leaderCount     = stocks.filter(s => s.rs_state === 'Leader' || s.rs_state === 'Strong').length
  const improvingCount  = stocks.filter(s => s.momentum_state === 'Improving' || s.momentum_state === 'Accelerating').length

  return (
    <div className="max-w-[1400px] mx-auto">
      <div className="px-6 py-4 border-b border-paper-rule flex items-center gap-6 flex-wrap">
        <h1 className="font-sans text-sm font-semibold text-ink-primary uppercase tracking-wide">
          Stock Universe
        </h1>
        <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
          <span className="inline-block w-2 h-2 rounded-full bg-teal" />
          {investableCount} Investable
          <span className="text-ink-tertiary">(of {stocks.length} total)</span>
        </span>
        <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
          <span className="inline-block w-2 h-2 rounded-full bg-signal-pos" />
          {leaderCount} Leader/Strong
        </span>
        <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
          <span className="inline-block w-2 h-2 rounded-full bg-signal-pos" />
          {improvingCount} Accel/Improving
        </span>
        {portfolioId && sectorFilter && policyEntryParams && (
          <span className="flex items-center gap-1.5 font-sans text-xs text-teal">
            <span className="inline-block w-2 h-2 rounded-full bg-teal" />
            Policy active
          </span>
        )}
      </div>

      <div className="px-6 py-6">
        <StocksClientShell
          stocks={stocks}
          regimeState={regime?.regime_state ?? 'Unknown'}
          deploymentMultiplier={Number(regime?.deployment_multiplier ?? '0')}
          validations={validations}
          leaders={leaders}
          breakouts={breakouts}
          deterioration={deterioration}
          initialSectorFilter={sectorFilter}
          initialIndexFilter={indexFilter}
          policyEntryParams={policyEntryParams}
        />
      </div>
    </div>
  )
}
