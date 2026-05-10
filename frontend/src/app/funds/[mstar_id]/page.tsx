export const dynamic = 'force-dynamic'

import { notFound } from 'next/navigation'
import {
  getFundMaster,
  getFundMetricHistory,
  getFundLens,
  getFundDecisionHistory,
  getFundHoldings,
  getFundNavHistory,
  getFundLensHistory,
} from '@/lib/queries/funds'
import { buildSingleFundCommentary } from '@/lib/commentary/funds'
import { CommentaryBlock } from '@/components/ui/CommentaryBlock'
import { FundDeepDiveHeader } from '@/components/funds/FundDeepDiveHeader'
import { FundLens1 } from '@/components/funds/FundLens1'
import { FundLens2 } from '@/components/funds/FundLens2'
import { FundLens3 } from '@/components/funds/FundLens3'
import { FundDecisionHistory } from '@/components/funds/FundDecisionHistory'
import { FundHoldingsTab } from '@/components/funds/FundHoldingsTab'
import { FundNavChart } from '@/components/funds/FundNavChart'
import { FundRiskPanel } from '@/components/funds/FundRiskPanel'
import { FundLensHistory } from '@/components/funds/FundLensHistory'

export default async function FundDeepDivePage({
  params,
}: {
  params: Promise<{ mstar_id: string }>
}) {
  const { mstar_id } = await params

  const [master, metricHistory, lens, decisionHistory, holdings, navHistory, lensHistory] =
    await Promise.all([
      getFundMaster(mstar_id),
      getFundMetricHistory(mstar_id, 180),
      getFundLens(mstar_id),
      getFundDecisionHistory(mstar_id),
      getFundHoldings(mstar_id, 20),
      getFundNavHistory(mstar_id, 1825),   // up to 5Y of NAV price
      getFundLensHistory(mstar_id),         // all disclosure periods
    ])

  if (!master) notFound()

  const commentary = buildSingleFundCommentary(master, lens)

  return (
    <div className="max-w-[1200px] mx-auto">
      <FundDeepDiveHeader master={master} />
      <div className="px-6 py-4 border-b border-paper-rule">
        <CommentaryBlock narrative={commentary.narrative} contextCards={commentary.contextCards} />
      </div>

      {/* NAV Price Chart — full width, uses de_mf_nav_daily (previously 0% coverage) */}
      <div className="px-6 py-5 border-b border-paper-rule">
        <FundNavChart navHistory={navHistory} />
      </div>

      {/* Three lens panels — RS pctile trend, Composition, Holdings */}
      <div className="px-6 py-6 grid grid-cols-3 gap-6 border-b border-paper-rule">
        <FundLens1 metricHistory={metricHistory} categoryName={master.category_name} />
        <FundLens2
          lens={lens}
          performanceGate={master.performance_gate}
          sectorsGate={master.sectors_gate}
        />
        <FundLens3
          lens={lens}
          stocksGate={master.stocks_gate}
          marketGate={master.market_gate}
        />
      </div>

      {/* Risk & Return panel — vol, drawdown, trailing return trends */}
      <div className="px-6 py-5 border-b border-paper-rule">
        <FundRiskPanel metricHistory={metricHistory} />
      </div>

      {/* Lens disclosure history — stacked area over all disclosure periods */}
      <div className="px-6 py-5 border-b border-paper-rule">
        <FundLensHistory lensHistory={lensHistory} />
      </div>

      {/* Holdings — individual stock states */}
      <div className="px-6 py-6 border-b border-paper-rule">
        <div className="border border-paper-rule rounded-sm">
          <div className="px-4 py-3 border-b border-paper-rule flex items-center justify-between">
            <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">
              Portfolio Holdings — Individual Stock States
            </div>
            {holdings.length > 0 && (
              <span className="font-sans text-xs text-ink-tertiary">Top {holdings.length}</span>
            )}
          </div>
          <div className="px-4 py-4">
            <FundHoldingsTab holdings={holdings} />
          </div>
        </div>
      </div>

      <div className="px-6 py-6">
        <h2 className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-4">
          Decision History
        </h2>
        <FundDecisionHistory decisions={decisionHistory} />
      </div>
    </div>
  )
}
