// allow-large: single-table screener with inline sort/filter logic; all cohesive
'use client'

import { useState, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import { ChevronUp, ChevronDown } from 'lucide-react'
import type { CountryRow } from '@/lib/queries/global'
import { RSStateChip, MomentumChip, RiskChip } from '@/lib/stock-formatters'

type SortKey = 'country' | 'pctile_3m_vt' | 'ret_3m' | 'ret_12m' | 'rs_consensus_bullish'
type FilterChip = 'all' | 'dm' | 'em' | 'leader' | 'strong' | 'improving'

const REGIONS = ['All Regions', 'Americas', 'Europe Developed', 'Asia-Pacific DM', 'Asia Emerging', 'Other Emerging']

const CHIPS: { key: FilterChip; label: string }[] = [
  { key: 'all',       label: 'All' },
  { key: 'dm',        label: 'DM Only' },
  { key: 'em',        label: 'EM Only' },
  { key: 'leader',    label: 'Leader' },
  { key: 'strong',    label: 'Leader/Strong' },
  { key: 'improving', label: 'Improving' },
]

function fmtPct(v: string | null): string {
  if (v == null) return '—'
  const n = parseFloat(v) * 100
  return `${n >= 0 ? '+' : ''}${n.toFixed(1)}%`
}

function pctColor(v: string | null): string {
  if (v == null) return 'text-ink-tertiary'
  const n = parseFloat(v) * 100
  if (n >= 10) return 'text-signal-pos font-semibold'
  if (n >= 3)  return 'text-signal-pos/80'
  if (n <= -10) return 'text-signal-neg font-semibold'
  if (n <= -3)  return 'text-signal-neg/80'
  return 'text-ink-tertiary'
}

export function GlobalCountryScreener({ countries }: { countries: CountryRow[] }) {
  const router = useRouter()
  const [sortKey, setSortKey] = useState<SortKey>('pctile_3m_vt')
  const [asc, setAsc]         = useState(false)
  const [chip, setChip]       = useState<FilterChip>('all')
  const [region, setRegion]   = useState('All Regions')
  const [search, setSearch]   = useState('')

  function handleSort(key: SortKey) {
    if (sortKey === key) setAsc(a => !a)
    else { setSortKey(key); setAsc(false) }
  }

  const filtered = useMemo(() => {
    let r = [...countries]

    if (chip === 'dm')        r = r.filter(c => c.is_developed_market)
    else if (chip === 'em')   r = r.filter(c => !c.is_developed_market)
    else if (chip === 'leader')  r = r.filter(c => c.rs_state === 'Leader')
    else if (chip === 'strong')  r = r.filter(c => c.rs_state === 'Leader' || c.rs_state === 'Strong')
    else if (chip === 'improving') r = r.filter(c => c.momentum_state === 'Improving' || c.momentum_state === 'Accelerating')

    if (region !== 'All Regions') r = r.filter(c => c.region === region)

    if (search) {
      const q = search.toLowerCase()
      r = r.filter(c => c.country.toLowerCase().includes(q) || c.ticker.toLowerCase().includes(q))
    }

    return [...r].sort((a, b) => {
      let av: number | string | null = null
      let bv: number | string | null = null

      if (sortKey === 'country') {
        av = a.country; bv = b.country
      } else if (sortKey === 'pctile_3m_vt') {
        av = a.pctile_3m_vt ? parseFloat(a.pctile_3m_vt) : null
        bv = b.pctile_3m_vt ? parseFloat(b.pctile_3m_vt) : null
      } else if (sortKey === 'ret_3m') {
        av = a.ret_3m ? parseFloat(a.ret_3m) : null
        bv = b.ret_3m ? parseFloat(b.ret_3m) : null
      } else if (sortKey === 'ret_12m') {
        av = a.ret_12m ? parseFloat(a.ret_12m) : null
        bv = b.ret_12m ? parseFloat(b.ret_12m) : null
      } else if (sortKey === 'rs_consensus_bullish') {
        av = a.rs_consensus_bullish; bv = b.rs_consensus_bullish
      }

      if (av == null && bv == null) return 0
      if (av == null) return 1
      if (bv == null) return -1
      if (typeof av === 'string' && typeof bv === 'string')
        return asc ? av.localeCompare(bv) : bv.localeCompare(av)
      return asc ? (av as number) - (bv as number) : (bv as number) - (av as number)
    })
  }, [countries, chip, region, search, sortKey, asc])

  function SortIcon({ k }: { k: SortKey }) {
    if (sortKey !== k) return <ChevronUp className="w-3 h-3 opacity-20" />
    return asc
      ? <ChevronUp className="w-3 h-3 text-teal" />
      : <ChevronDown className="w-3 h-3 text-teal" />
  }

  function SortTh({ k, label, right }: { k: SortKey; label: string; right?: boolean }) {
    return (
      <th
        className={`px-2 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider cursor-pointer select-none hover:text-ink-primary ${right ? 'text-right' : 'text-left'}`}
        onClick={() => handleSort(k)}
      >
        <span className={`inline-flex items-center gap-0.5 ${right ? 'justify-end w-full' : ''}`}>
          {label}
          <SortIcon k={k} />
        </span>
      </th>
    )
  }

  return (
    <div>
      {/* Filter bar */}
      <div className="flex items-center gap-2 flex-wrap mb-4">
        {CHIPS.map(c => (
          <button
            key={c.key}
            onClick={() => setChip(c.key)}
            className={[
              'px-2.5 py-1 rounded font-sans text-[10px] font-medium border transition-colors',
              chip === c.key
                ? 'bg-teal text-white border-teal'
                : 'text-ink-secondary border-paper-rule hover:border-teal hover:text-teal',
            ].join(' ')}
          >
            {c.label}
          </button>
        ))}

        <select
          value={region}
          onChange={e => setRegion(e.target.value)}
          className="ml-1 font-sans text-xs text-ink-secondary bg-paper border border-paper-rule rounded px-2 py-1 focus:outline-none focus:border-teal"
        >
          {REGIONS.map(r => <option key={r} value={r}>{r}</option>)}
        </select>

        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search…"
          className="font-mono text-xs text-ink-primary bg-paper border border-paper-rule rounded px-2 py-1 w-28 focus:outline-none focus:border-teal placeholder:text-ink-tertiary"
        />

        <span className="ml-auto font-sans text-[10px] text-ink-tertiary">{filtered.length} countries</span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-paper-rule">
              <SortTh k="country" label="Country" />
              <th className="px-2 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">Region</th>
              <th className="px-2 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">Seg</th>
              <th className="px-2 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">RS State</th>
              <th className="px-2 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">Momentum</th>
              <th className="px-2 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">Risk</th>
              <SortTh k="pctile_3m_vt" label="RS Pctile" right />
              <SortTh k="ret_3m" label="3M Ret" right />
              <SortTh k="ret_12m" label="1Y Ret" right />
              <th className="px-2 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider text-center">30W</th>
              <SortTh k="rs_consensus_bullish" label="Score" right />
            </tr>
          </thead>
          <tbody>
            {filtered.map((c, i) => (
              <tr
                key={c.ticker}
                className={`border-b border-paper-rule/50 hover:bg-paper/40 transition-colors cursor-pointer ${i % 2 !== 0 ? 'bg-paper/50' : ''}`}
                onClick={() => router.push(`/global/country/${c.ticker}`)}
              >
                <td className="px-2 py-2">
                  <div className="font-sans text-[12px] text-ink-primary hover:text-teal">{c.country}</div>
                  <div className="font-mono text-[10px] text-ink-tertiary uppercase">{c.ticker}</div>
                </td>
                <td className="px-2 py-2 font-sans text-[11px] text-ink-secondary whitespace-nowrap">{c.region}</td>
                <td className="px-2 py-2">
                  <span className={`font-mono text-[9px] px-1 py-0.5 rounded ${c.is_developed_market ? 'bg-teal/10 text-teal' : 'bg-amber-500/10 text-amber-600'}`}>
                    {c.is_developed_market ? 'DM' : 'EM'}
                  </span>
                </td>
                <td className="px-2 py-2"><RSStateChip value={c.rs_state} /></td>
                <td className="px-2 py-2"><MomentumChip value={c.momentum_state} /></td>
                <td className="px-2 py-2"><RiskChip value={c.risk_state} /></td>
                <td className="px-2 py-2 text-right">
                  {c.pctile_3m_vt != null
                    ? <span className="font-mono text-[11px] text-ink-secondary">{(parseFloat(c.pctile_3m_vt) * 100).toFixed(0)}</span>
                    : <span className="text-ink-tertiary">—</span>}
                </td>
                <td className={`px-2 py-2 text-right font-mono text-[11px] ${pctColor(c.ret_3m)}`}>{fmtPct(c.ret_3m)}</td>
                <td className={`px-2 py-2 text-right font-mono text-[11px] ${pctColor(c.ret_12m)}`}>{fmtPct(c.ret_12m)}</td>
                <td className="px-2 py-2 text-center">
                  {c.above_30w_ma == null
                    ? <span className="text-ink-tertiary">—</span>
                    : <span className={`w-2 h-2 rounded-full inline-block ${c.above_30w_ma ? 'bg-signal-pos' : 'bg-signal-neg'}`} />}
                </td>
                <td className="px-2 py-2 text-right font-mono text-[11px] text-ink-secondary">
                  {c.rs_consensus_bullish != null ? `${c.rs_consensus_bullish}/20` : '—'}
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={11} className="px-4 py-8 text-center font-sans text-sm text-ink-secondary">
                  No countries match the current filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
