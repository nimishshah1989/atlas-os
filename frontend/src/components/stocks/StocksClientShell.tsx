'use client'
import { useState } from 'react'
import type { StockRowWithSector } from '@/lib/queries/stocks'
import { StockBreadthPanel } from './StockBreadthPanel'
import { StockBubbleChart } from './StockBubbleChart'
import { StockIntelligencePanel } from './StockIntelligencePanel'
import { StockScreener } from './StockScreener'

type MaFilter = 'above_30w_ma' | 'above_50d_ma' | 'above_200d_ma' | null

export function StocksClientShell({
  stocks,
  regimeState,
  deploymentMultiplier,
}: {
  stocks: StockRowWithSector[]
  regimeState: string
  deploymentMultiplier: number
}) {
  const [maFilter, setMaFilter] = useState<MaFilter>(null)

  return (
    <div className="flex flex-col gap-6">
      <StockBreadthPanel
        stocks={stocks}
        activeMaFilter={maFilter}
        onMaFilter={setMaFilter}
      />
      <StockBubbleChart stocks={stocks} />
      <StockIntelligencePanel
        stocks={stocks}
        regimeState={regimeState}
        deploymentMultiplier={deploymentMultiplier}
      />
      <StockScreener
        stocks={stocks}
        maFilter={maFilter}
      />
    </div>
  )
}
