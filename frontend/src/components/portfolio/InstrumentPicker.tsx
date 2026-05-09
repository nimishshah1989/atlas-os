'use client'
// src/components/portfolio/InstrumentPicker.tsx
// Multi-asset instrument picker for the Static portfolio builder.
// Tabs: Stocks | ETFs | Mutual Funds. Per-tab filter chips + search.
// Selected instruments shown in a sticky right panel (handled by parent).
// allow-large: single cohesive picker component with 3 tabs, each with filter+list

import { useState, useMemo } from 'react'
import type { StockPickerRow, ETFPickerRow, FundPickerRow } from '@/lib/queries/instruments'

export type SelectedInstrument = {
  instrument_id: string
  instrument_type: 'stock' | 'etf' | 'fund'
  display_name: string
  meta: string
}

type Props = {
  stocks: StockPickerRow[]
  etfs: ETFPickerRow[]
  funds: FundPickerRow[]
  selectedIds: Set<string>
  onSelect: (instrument: SelectedInstrument) => void
}

type AssetTab = 'stocks' | 'etfs' | 'funds'

const TAB_LABELS: Record<AssetTab, string> = {
  stocks: 'Stocks',
  etfs: 'ETFs',
  funds: 'Mutual Funds',
}

const STOCK_TIERS = ['Large', 'Mid', 'Small', 'Micro']
const ETF_THEMES = ['Broad', 'Sectoral', 'Thematic']

function FilterChip({
  label,
  active,
  onClick,
}: {
  label: string
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`font-sans text-xs px-2.5 py-1 rounded-[2px] border transition-colors ${
        active
          ? 'bg-accent text-white border-accent'
          : 'bg-paper text-ink-secondary border-paper-rule hover:text-ink-primary'
      }`}
    >
      {label}
    </button>
  )
}

export function InstrumentPicker({ stocks, etfs, funds, selectedIds, onSelect }: Props) {
  const [activeTab, setActiveTab] = useState<AssetTab>('stocks')
  const [search, setSearch] = useState('')
  const [stockTier, setStockTier] = useState<string | null>(null)
  const [etfTheme, setEtfTheme] = useState<string | null>(null)
  const [fundCategory, setFundCategory] = useState<string | null>(null)

  // Derive unique sectors from stocks for filter chips
  const stockSectors = useMemo(
    () => [...new Set(stocks.map((s) => s.sector))].sort(),
    [stocks],
  )
  const [stockSector, setStockSector] = useState<string | null>(null)

  // Derive unique fund categories
  const fundCategories = useMemo(
    () => [...new Set(funds.map((f) => f.broad_category))].sort(),
    [funds],
  )

  // Reset search on tab change
  const handleTabChange = (tab: AssetTab) => {
    setActiveTab(tab)
    setSearch('')
  }

  // Filtered lists — client-side filtering of already-limited server data
  const filteredStocks = useMemo(() => {
    const q = search.toLowerCase()
    return stocks.filter((s) => {
      if (stockTier && s.tier !== stockTier) return false
      if (stockSector && s.sector !== stockSector) return false
      if (q && !s.symbol.toLowerCase().includes(q) && !(s.company_name?.toLowerCase().includes(q))) return false
      return true
    })
  }, [stocks, stockTier, stockSector, search])

  const filteredETFs = useMemo(() => {
    const q = search.toLowerCase()
    return etfs.filter((e) => {
      if (etfTheme && e.theme !== etfTheme) return false
      if (q && !e.ticker.toLowerCase().includes(q) && !(e.etf_name?.toLowerCase().includes(q))) return false
      return true
    })
  }, [etfs, etfTheme, search])

  const filteredFunds = useMemo(() => {
    const q = search.toLowerCase()
    return funds.filter((f) => {
      if (fundCategory && f.broad_category !== fundCategory) return false
      if (q && !f.scheme_name.toLowerCase().includes(q) && !(f.amc?.toLowerCase().includes(q))) return false
      return true
    })
  }, [funds, fundCategory, search])

  const tabCounts = {
    stocks: stocks.length,
    etfs: etfs.length,
    funds: funds.length,
  }

  return (
    <div className="border border-paper-rule rounded-[2px]">
      {/* Tab bar */}
      <div className="flex border-b border-paper-rule">
        {(['stocks', 'etfs', 'funds'] as AssetTab[]).map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => handleTabChange(tab)}
            className={`font-sans text-xs px-4 py-2.5 border-r border-paper-rule transition-colors ${
              activeTab === tab
                ? 'bg-accent/5 text-accent font-semibold border-b-2 border-b-accent -mb-px'
                : 'text-ink-secondary hover:text-ink-primary'
            }`}
          >
            {TAB_LABELS[tab]} ({tabCounts[tab]})
          </button>
        ))}
        <div className="flex-1" />
      </div>

      {/* Filters row */}
      <div className="p-3 border-b border-paper-rule bg-paper space-y-2">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={`Search ${TAB_LABELS[activeTab].toLowerCase()}…`}
          className="w-full font-mono text-xs px-2.5 py-1.5 border border-paper-rule rounded-[2px] bg-paper text-ink-primary placeholder:text-ink-tertiary focus:outline-none focus:border-accent"
        />

        {activeTab === 'stocks' && (
          <div className="flex flex-wrap gap-1.5">
            {STOCK_TIERS.map((t) => (
              <FilterChip
                key={t}
                label={t}
                active={stockTier === t}
                onClick={() => setStockTier(stockTier === t ? null : t)}
              />
            ))}
            <span className="border-l border-paper-rule mx-1" />
            {stockSectors.slice(0, 8).map((sec) => (
              <FilterChip
                key={sec}
                label={sec}
                active={stockSector === sec}
                onClick={() => setStockSector(stockSector === sec ? null : sec)}
              />
            ))}
          </div>
        )}

        {activeTab === 'etfs' && (
          <div className="flex flex-wrap gap-1.5">
            {ETF_THEMES.map((t) => (
              <FilterChip
                key={t}
                label={t}
                active={etfTheme === t}
                onClick={() => setEtfTheme(etfTheme === t ? null : t)}
              />
            ))}
          </div>
        )}

        {activeTab === 'funds' && (
          <div className="flex flex-wrap gap-1.5">
            {fundCategories.map((c) => (
              <FilterChip
                key={c}
                label={c}
                active={fundCategory === c}
                onClick={() => setFundCategory(fundCategory === c ? null : c)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Instrument list */}
      <div className="overflow-y-auto max-h-72">
        {activeTab === 'stocks' && (
          filteredStocks.length === 0 ? (
            <p className="font-sans text-xs text-ink-tertiary text-center py-6">No matches — try fewer filters</p>
          ) : (
            <table className="w-full text-left">
              <tbody>
                {filteredStocks.map((s) => {
                  const id = s.instrument_id
                  const isSelected = selectedIds.has(id)
                  return (
                    <tr
                      key={id}
                      onClick={() => !isSelected && onSelect({
                        instrument_id: id,
                        instrument_type: 'stock',
                        display_name: s.symbol,
                        meta: `${s.tier} · ${s.sector}`,
                      })}
                      className={`border-b border-paper-rule/50 cursor-pointer transition-colors ${
                        isSelected ? 'opacity-40 cursor-not-allowed' : 'hover:bg-accent/5'
                      }`}
                    >
                      <td className="py-2 px-3 font-mono text-xs text-ink-primary w-24">
                        {isSelected && <span className="mr-1 text-signal-pos">✓</span>}
                        {s.symbol}
                      </td>
                      <td className="py-2 px-3 font-sans text-xs text-ink-secondary truncate max-w-[160px]">
                        {s.company_name ?? '—'}
                      </td>
                      <td className="py-2 px-3 font-sans text-xs text-ink-tertiary">{s.tier}</td>
                      <td className="py-2 px-3 font-sans text-xs text-ink-tertiary truncate max-w-[100px]">{s.sector}</td>
                      <td className="py-2 px-3 font-sans text-xs text-ink-tertiary">{s.rs_state ?? '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )
        )}

        {activeTab === 'etfs' && (
          filteredETFs.length === 0 ? (
            <p className="font-sans text-xs text-ink-tertiary text-center py-6">No matches — try fewer filters</p>
          ) : (
            <table className="w-full text-left">
              <tbody>
                {filteredETFs.map((e) => {
                  const id = e.ticker
                  const isSelected = selectedIds.has(id)
                  return (
                    <tr
                      key={id}
                      onClick={() => !isSelected && onSelect({
                        instrument_id: id,
                        instrument_type: 'etf',
                        display_name: e.ticker,
                        meta: `${e.theme}${e.linked_sector ? ' · ' + e.linked_sector : ''}`,
                      })}
                      className={`border-b border-paper-rule/50 cursor-pointer transition-colors ${
                        isSelected ? 'opacity-40 cursor-not-allowed' : 'hover:bg-accent/5'
                      }`}
                    >
                      <td className="py-2 px-3 font-mono text-xs text-ink-primary w-24">
                        {isSelected && <span className="mr-1 text-signal-pos">✓</span>}
                        {e.ticker}
                      </td>
                      <td className="py-2 px-3 font-sans text-xs text-ink-secondary truncate max-w-[200px]">
                        {e.etf_name ?? '—'}
                      </td>
                      <td className="py-2 px-3 font-sans text-xs text-ink-tertiary">{e.theme}</td>
                      <td className="py-2 px-3 font-sans text-xs text-ink-tertiary">{e.linked_sector ?? '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )
        )}

        {activeTab === 'funds' && (
          filteredFunds.length === 0 ? (
            <p className="font-sans text-xs text-ink-tertiary text-center py-6">No matches — try fewer filters</p>
          ) : (
            <table className="w-full text-left">
              <tbody>
                {filteredFunds.map((f) => {
                  const id = f.mstar_id
                  const isSelected = selectedIds.has(id)
                  return (
                    <tr
                      key={id}
                      onClick={() => !isSelected && onSelect({
                        instrument_id: id,
                        instrument_type: 'fund',
                        display_name: f.scheme_name,
                        meta: `${f.broad_category} · ${f.category_name}`,
                      })}
                      className={`border-b border-paper-rule/50 cursor-pointer transition-colors ${
                        isSelected ? 'opacity-40 cursor-not-allowed' : 'hover:bg-accent/5'
                      }`}
                    >
                      <td className="py-2 px-3 font-sans text-xs text-ink-primary truncate max-w-[200px]">
                        {isSelected && <span className="mr-1 text-signal-pos">✓</span>}
                        {f.scheme_name}
                      </td>
                      <td className="py-2 px-3 font-sans text-xs text-ink-tertiary">{f.amc ?? '—'}</td>
                      <td className="py-2 px-3 font-sans text-xs text-ink-tertiary">{f.broad_category}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )
        )}
      </div>
    </div>
  )
}
