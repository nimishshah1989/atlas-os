'use client'
import { useState, useEffect } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import dynamic from 'next/dynamic'
import type { USSectorRow, USSectorRRGPoint } from '@/lib/queries/us-sectors'
import type { USStockRow } from '@/lib/queries/us-stocks'
import type { USETFRow } from '@/lib/queries/us-etfs'
import type { ETFRow } from '@/lib/queries/etfs'
import { USBreadthPanel } from '@/components/us/USBreadthPanel'
import { USSectorTable } from '@/components/us/USSectorTable'
import { USSectorHeatmap } from '@/components/us/USSectorHeatmap'
import { USStockScreener } from '@/components/us/USStockScreener'
import { USETFScreener } from '@/components/us/USETFScreener'
import { ETFMetricTiles } from '@/components/etfs/ETFMetricTiles'

// D3 charts loaded client-side only (no SSR)
const USSectorBubbleChart = dynamic(
  () => import('@/components/us/USSectorBubbleChart').then(m => m.USSectorBubbleChart),
  {
    ssr: false,
    loading: () => (
      <div className="h-64 flex items-center justify-center text-ink-tertiary font-sans text-sm">
        Loading chart...
      </div>
    ),
  },
)
const USRRGChart = dynamic(
  () => import('@/components/us/USRRGChart').then(m => m.USRRGChart),
  {
    ssr: false,
    loading: () => (
      <div className="h-64 flex items-center justify-center text-ink-tertiary font-sans text-sm">
        Loading chart...
      </div>
    ),
  },
)
const USStockBubbleChart = dynamic(
  () => import('@/components/us/USStockBubbleChart').then(m => m.USStockBubbleChart),
  {
    ssr: false,
    loading: () => (
      <div className="h-64 flex items-center justify-center text-ink-tertiary font-sans text-sm">
        Loading chart...
      </div>
    ),
  },
)
const ETFBubbleChart = dynamic(
  () => import('@/components/etfs/ETFBubbleChart').then(m => m.ETFBubbleChart),
  {
    ssr: false,
    loading: () => (
      <div className="h-64 flex items-center justify-center text-ink-tertiary font-sans text-sm">
        Loading chart...
      </div>
    ),
  },
)

// Adapt USETFRow → ETFRow shape for reuse of India ETFBubbleChart + ETFMetricTiles
function adaptUSETF(row: USETFRow): ETFRow {
  const isSector = row.etf_category?.toLowerCase().includes('sector') ?? false
  const isInvestable = (row.history_gate_pass ?? false) && (row.liquidity_gate_pass ?? false)
  return {
    ticker:              row.ticker,
    etf_name:            row.etf_name ?? row.ticker,
    theme:               isSector ? 'Sectoral' : 'Broad',
    linked_sector:       row.linked_sector,
    linked_index:        null,
    inception_date:      null,
    asset_class:         null,
    fund_house:          null,
    data_as_of:          row.data_as_of,
    ret_1w:              row.ret_1w,
    ret_1m:              row.ret_1m,
    ret_3m:              row.ret_3m,
    ret_6m:              row.ret_6m,
    ret_12m:             row.ret_12m,
    rs_pctile_3m:        row.rs_pctile_3m_vt,
    rs_3m_benchmark:     null,
    ema_10_ratio:        row.ema_10_ratio,
    extension_pct:       row.extension_pct,
    vol_63:              row.realized_vol_63,
    drawdown:            row.max_drawdown_252,
    volume_expansion:    row.volume_expansion,
    avg_volume_20:       row.avg_volume_20,
    effort_ratio_63:     row.effort_ratio_63,
    above_30w_ma:        row.above_30w_ma,
    ema_10_at_20d_high:  null,
    days_in_state:       null,
    rs_state:            row.rs_state,
    momentum_state:      row.momentum_state,
    risk_state:          row.risk_state,
    weinstein_gate_pass: row.weinstein_gate_pass,
    history_gate_pass:   row.history_gate_pass,
    liquidity_gate_pass: row.liquidity_gate_pass,
    is_investable:       isInvestable,
    strength_gate:       null,
    direction_gate:      null,
    risk_gate:           null,
    sector_gate:         null,
    market_gate:         null,
    position_size_pct:   null,
    breakout_trigger:    null,
    transition_trigger:  null,
    exit_market_riskoff:  null,
    exit_sector_avoid:   null,
    exit_rs_deteriorate: null,
    exit_momentum_collapse: null,
    exit_stop_loss:      null,
    // Stage badge not available for US ETFs
    engine_state:          null,
    // Phase 8: bubble chart axes — not available for US ETFs
    mean_rs_rank_12m:      null,
    mean_within_state_rank: null,
    pct_stage_2:           null,
    pct_stage_4:           null,
  }
}

type Tab = 'Sectors' | 'Stocks' | 'ETFs'
const TABS: Tab[] = ['Sectors', 'Stocks', 'ETFs']

type Props = {
  sectors: USSectorRow[]
  rrgHistory: USSectorRRGPoint[]
  stocks: USStockRow[]
  etfs: USETFRow[]
}


export function USPulseShell({ sectors, rrgHistory, stocks, etfs }: Props) {
  const router       = useRouter()
  const searchParams = useSearchParams()
  const rawTab       = searchParams.get('tab')
  const initialTab: Tab = TABS.includes(rawTab as Tab) ? (rawTab as Tab) : 'Sectors'
  const [activeTab, setActiveTab] = useState<Tab>(initialTab)

  // Keep URL in sync when tab changes
  useEffect(() => {
    const params = new URLSearchParams(searchParams.toString())
    params.set('tab', activeTab)
    router.replace(`?${params.toString()}`, { scroll: false })
  }, [activeTab, router, searchParams])

  return (
    <div>
      {/* Tab bar */}
      <div className="px-6 border-b border-paper-rule flex items-center gap-0">
        {TABS.map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={[
              'px-4 py-3 font-sans text-xs font-medium transition-colors border-b-2 -mb-px',
              activeTab === tab
                ? 'text-teal border-teal'
                : 'text-ink-secondary border-transparent hover:text-teal',
            ].join(' ')}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Sectors tab — mirrors India /sectors: breadth → bubble → RRG → heatmap → table */}
      {activeTab === 'Sectors' && (
        <div>
          <USBreadthPanel stocks={stocks} />
          <div className="px-6 py-6 border-b border-paper-rule">
            <USSectorBubbleChart sectors={sectors} />
          </div>
          <div className="px-6 py-6 border-b border-paper-rule">
            <USRRGChart sectors={sectors} rrgHistory={rrgHistory} />
          </div>
          <div className="px-6 py-6 border-b border-paper-rule">
            <USSectorHeatmap etfs={etfs} />
          </div>
          <div className="px-6 py-6">
            <USSectorTable sectors={sectors} />
          </div>
        </div>
      )}

      {/* Stocks tab — mirrors India /stocks: breadth → bubble → screener */}
      {activeTab === 'Stocks' && (
        <div>
          <USBreadthPanel stocks={stocks} />
          <div className="px-6 pt-4">
            <div className="border border-paper-rule rounded-sm p-4">
              <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-1">
                US Stock Risk/Return Map — Volatility vs Return
              </div>
              <p className="font-sans text-[11px] text-ink-tertiary mb-3">
                X = annualised volatility, Y = return. Color = RS state. Bubble size = avg volume 20D.
              </p>
              <USStockBubbleChart stocks={stocks} />
            </div>
          </div>
          <div className="px-6 py-4">
            <USStockScreener stocks={stocks} />
          </div>
        </div>
      )}

      {/* ETFs tab — mirrors India /etfs: metric tiles → bubble → screener */}
      {activeTab === 'ETFs' && (
        <div>
          <div className="px-6 pt-4">
            <ETFMetricTiles etfs={etfs.map(adaptUSETF)} />
          </div>
          <div className="px-6 pt-4">
            <div className="border border-paper-rule rounded-sm p-4">
              <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-1">
                US ETF Risk/Return Map — Volatility vs 3M Return
              </div>
              <p className="font-sans text-[11px] text-ink-tertiary mb-3">
                X = annualised volatility, Y = 3-month return. Color = RS state. Bubble size = avg volume 20D.
              </p>
              <ETFBubbleChart etfs={etfs.map(adaptUSETF)} />
            </div>
          </div>
          <div className="px-6 py-4">
            <USETFScreener etfs={etfs} />
          </div>
        </div>
      )}
    </div>
  )
}
