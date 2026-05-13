'use client'
import { useState, useEffect } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import dynamic from 'next/dynamic'
import type { USSectorRow, USSectorRRGPoint } from '@/lib/queries/us-sectors'
import type { USStockRow } from '@/lib/queries/us-stocks'
import type { USETFRow } from '@/lib/queries/us-etfs'
import { USBreadthPanel } from '@/components/us/USBreadthPanel'
import { USSectorTable } from '@/components/us/USSectorTable'
import { USStockScreener } from '@/components/us/USStockScreener'
import { USETFScreener } from '@/components/us/USETFScreener'

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

type Tab = 'Sectors' | 'Stocks' | 'ETFs'
const TABS: Tab[] = ['Sectors', 'Stocks', 'ETFs']

type Props = {
  sectors: USSectorRow[]
  rrgHistory: USSectorRRGPoint[]
  stocks: USStockRow[]
  etfs: USETFRow[]
}

function StockQuickStats({ stocks }: { stocks: USStockRow[] }) {
  const live        = stocks.filter(s => s.history_gate_pass && s.liquidity_gate_pass)
  const leaderStrong = live.filter(s => s.rs_state === 'Leader' || s.rs_state === 'Strong')
  const above30w    = live.filter(s => s.above_30w_ma === true)
  const accel       = live.filter(s => s.momentum_state === 'Accelerating' || s.momentum_state === 'Improving')

  return (
    <div className="px-6 py-3 border-b border-paper-rule flex flex-wrap gap-4 font-sans text-xs text-ink-secondary">
      <span>Total: <strong className="text-ink-primary">{stocks.length}</strong></span>
      <span>Live: <strong className="text-ink-primary">{live.length}</strong></span>
      <span>Leader/Strong: <strong className="text-teal">{leaderStrong.length}</strong></span>
      <span>Above 30W: <strong className="text-ink-primary">{above30w.length}</strong></span>
      <span>Accel/Improving: <strong className="text-signal-pos">{accel.length}</strong></span>
    </div>
  )
}

function ETFQuickStats({ etfs }: { etfs: USETFRow[] }) {
  const leaderStrong  = etfs.filter(e => e.rs_state === 'Leader' || e.rs_state === 'Strong')
  const sectorETFs    = etfs.filter(e => e.etf_category?.toLowerCase().includes('sector'))

  return (
    <div className="px-6 py-3 border-b border-paper-rule flex flex-wrap gap-4 font-sans text-xs text-ink-secondary">
      <span>Total ETFs: <strong className="text-ink-primary">{etfs.length}</strong></span>
      <span>Sector ETFs: <strong className="text-ink-primary">{sectorETFs.length}</strong></span>
      <span>Leader/Strong: <strong className="text-teal">{leaderStrong.length}</strong></span>
    </div>
  )
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

      {/* Sectors tab */}
      {activeTab === 'Sectors' && (
        <div>
          <USBreadthPanel stocks={stocks} />
          <div className="px-6 py-6 border-b border-paper-rule">
            <USSectorBubbleChart sectors={sectors} />
          </div>
          <div className="px-6 py-6 border-b border-paper-rule">
            <USRRGChart sectors={sectors} rrgHistory={rrgHistory} />
          </div>
          <div className="px-6 py-6">
            <USSectorTable sectors={sectors} />
          </div>
        </div>
      )}

      {/* Stocks tab */}
      {activeTab === 'Stocks' && (
        <div>
          <StockQuickStats stocks={stocks} />
          <div className="px-6 py-4">
            <USStockScreener stocks={stocks} />
          </div>
        </div>
      )}

      {/* ETFs tab */}
      {activeTab === 'ETFs' && (
        <div>
          <ETFQuickStats etfs={etfs} />
          <div className="px-6 py-4">
            <USETFScreener etfs={etfs} />
          </div>
        </div>
      )}
    </div>
  )
}
