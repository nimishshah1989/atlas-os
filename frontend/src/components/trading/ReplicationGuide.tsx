'use client'

import type { LeaderboardRow, GenomePositionRow, PortfolioConfigRow } from '@/lib/queries/strategy_lab'
import { TaxHarvestingAlert } from './TaxHarvestingAlert'

type Props = {
  strategy: LeaderboardRow
  positions: GenomePositionRow[]
  config: PortfolioConfigRow | null
}

type Section = 'hold' | 'watch' | 'buy' | 'sell' | 'liquidbees'

function classifyPosition(pos: GenomePositionRow): Section {
  if (pos.position_type === 'liquidbees') return 'liquidbees'
  const signals = (pos.entry_signals as Record<string, unknown>) ?? {}
  if (signals.exit_triggered) return 'sell'
  if (signals.softening) return 'watch'
  if (Number(pos.unrealized_pnl) > 0) return 'hold'
  return 'watch'
}

const SECTION_META: Record<Section, { label: string; cls: string }> = {
  hold:       { label: 'Hold',       cls: 'text-teal-700 bg-teal-50 border-teal-200' },
  watch:      { label: 'Watch',      cls: 'text-amber-700 bg-amber-50 border-amber-200' },
  buy:        { label: 'Buy Today',  cls: 'text-blue-700 bg-blue-50 border-blue-200' },
  sell:       { label: 'Sell Today', cls: 'text-red-700 bg-red-50 border-red-200' },
  liquidbees: { label: 'LiquidBees', cls: 'text-gray-700 bg-gray-50 border-gray-200' },
}

function PositionRow({ pos, stcgRate, ltcgRate }: { pos: GenomePositionRow; stcgRate: number; ltcgRate: number }) {
  const pnl = Number(pos.unrealized_pnl)
  return (
    <div className="py-3 border-b border-paper-rule last:border-0">
      <div className="flex justify-between items-start">
        <div>
          <span className="font-mono text-sm font-semibold text-ink-primary">{pos.ticker}</span>
          {pos.company_name && <span className="font-sans text-xs text-ink-tertiary ml-2">{pos.company_name}</span>}
          <div className="flex gap-3 mt-1">
            <span className="font-sans text-xs text-ink-tertiary">Entry ₹{Number(pos.entry_price).toFixed(2)}</span>
            <span className="font-sans text-xs text-ink-tertiary">{pos.holding_days}d held</span>
            <span className={`font-sans text-xs px-1.5 py-0.5 rounded-[2px] ${pos.tax_status === 'ltcg_eligible' ? 'bg-green-100 text-green-700' : 'bg-orange-100 text-orange-700'}`}>
              {pos.tax_status === 'ltcg_eligible' ? 'LTCG' : 'STCG'}
            </span>
          </div>
        </div>
        <div className="text-right">
          <p className="font-mono text-sm font-semibold text-ink-primary">₹{Number(pos.current_value).toLocaleString('en-IN')}</p>
          <p className={`font-mono text-xs ${pnl >= 0 ? 'text-teal-600' : 'text-red-600'}`}>
            {pnl >= 0 ? '+' : ''}₹{Math.abs(pnl).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
          </p>
        </div>
      </div>
      {pos.tax_status === 'stcg' && pnl > 5000 && 365 - pos.holding_days < 60 && (
        <TaxHarvestingAlert ticker={pos.ticker} grossPnl={pnl} holdingDays={pos.holding_days}
          stcgRate={stcgRate} ltcgRate={ltcgRate} signalStrength={0.4} />
      )}
    </div>
  )
}

export function ReplicationGuide({ strategy, positions, config }: Props) {
  const cfg = config?.config_json as Record<string, string> | undefined
  const stcgRate = Number(cfg?.stcg_rate ?? '0.20')
  const ltcgRate = Number(cfg?.ltcg_rate ?? '0.125')

  const grouped = positions.reduce<Record<Section, GenomePositionRow[]>>(
    (acc, pos) => { acc[classifyPosition(pos)].push(pos); return acc },
    { hold: [], watch: [], buy: [], sell: [], liquidbees: [] }
  )
  const equityVal = positions.filter(p => p.position_type === 'equity').reduce((s, p) => s + Number(p.current_value), 0)
  const totalVal = positions.reduce((s, p) => s + Number(p.current_value), 0)
  const heat = totalVal > 0 ? (equityVal / totalVal * 100).toFixed(1) : '0.0'

  return (
    <div className="space-y-5">
      <div className="border border-paper-rule rounded-[2px] p-4">
        <div className="flex justify-between">
          <div>
            <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide">Replication Guide</p>
            <h2 className="font-serif text-lg text-ink-primary mt-1">{strategy.strategy_name}</h2>
          </div>
          <div className="text-right">
            <p className="font-sans text-xs text-ink-tertiary">Portfolio Heat</p>
            <p className="font-mono text-lg font-semibold text-ink-primary">{heat}%</p>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3 mt-3">
          <div><p className="font-sans text-xs text-ink-tertiary">Sortino OOS</p>
            <p className="font-mono text-sm font-semibold text-ink-primary">{Number(strategy.sortino_oos ?? 0).toFixed(2)}</p></div>
          <div><p className="font-sans text-xs text-ink-tertiary">Calmar OOS</p>
            <p className="font-mono text-sm font-semibold text-ink-primary">{Number(strategy.calmar_oos ?? 0).toFixed(2)}</p></div>
          <div><p className="font-sans text-xs text-ink-tertiary">Positions</p>
            <p className="font-mono text-sm font-semibold text-ink-primary">{positions.filter(p => p.position_type === 'equity').length}</p></div>
        </div>
      </div>
      {(['sell', 'buy', 'watch', 'hold', 'liquidbees'] as Section[]).map((section) => {
        const items = grouped[section]
        if (!items.length) return null
        const { label, cls } = SECTION_META[section]
        return (
          <div key={section} className={`border rounded-[2px] ${cls}`}>
            <div className={`px-4 py-2 border-b ${cls}`}>
              <p className="font-sans text-xs font-semibold uppercase tracking-wide">{label} ({items.length})</p>
            </div>
            <div className="px-4">
              {items.map((pos) => (
                <PositionRow key={`${pos.ticker}-${String(pos.date)}`} pos={pos} stcgRate={stcgRate} ltcgRate={ltcgRate} />
              ))}
            </div>
          </div>
        )
      })}
      {positions.length === 0 && (
        <p className="font-sans text-sm text-ink-tertiary">No positions yet. Strategy is in early optimization.</p>
      )}
    </div>
  )
}
