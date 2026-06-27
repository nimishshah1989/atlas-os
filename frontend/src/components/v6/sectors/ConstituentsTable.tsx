'use client'
// frontend/src/components/v6/sectors/ConstituentsTable.tsx
// Top-30 constituents table for Page 04a sector deep-dive.
// Source: mv_sector_deepdive.constituents_top30 JSONB array.
// Values are already percentages (ret_* columns multiplied by 100 in MV).
// Each row → /stocks/<symbol>. Sortable headers.

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import type { ConstituentRow } from '@/lib/queries/v6/sectors'
import { TermInfo } from '@/components/v6/shared/TermInfo'

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtPct(v: number | null): { text: string; cls: string } {
  // Values from MV are already percentages (e.g. 5.2 = +5.2%)
  if (v == null) return { text: '—', cls: 'text-txt-3' }
  return {
    text: `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`,
    cls: v >= 0 ? 'text-sig-pos' : 'text-sig-neg',
  }
}

function fmtPp(v: number | null): { text: string; cls: string } {
  if (v == null) return { text: '—', cls: 'text-txt-3' }
  return {
    text: `${v >= 0 ? '+' : ''}${v.toFixed(1)}pp`,
    cls: v >= 0 ? 'text-sig-pos' : 'text-sig-neg',
  }
}

// Resolve a fmt* cls token → concrete colour for inline-styled numeric cells.
function numColor(cls: string): string {
  return cls.includes('pos') ? 'var(--color-sig-pos)'
    : cls.includes('neg') ? 'var(--color-sig-neg)'
    : 'var(--color-txt-3)'
}

// ── Action chip ───────────────────────────────────────────────────────────────

function ActionChip({ action }: { action: string | null }) {
  if (!action) return <span className="text-txt-3 text-[11px]">—</span>

  const cls =
    action === 'POSITIVE' ? 'bg-sig-pos text-surface-base'
    : action === 'NEGATIVE' ? 'bg-sig-neg text-surface-base'
    : 'bg-sig-warn/15 text-sig-warn border border-sig-warn/30'

  const label = action === 'POSITIVE' ? 'BUY' : action === 'NEGATIVE' ? 'AVOID' : 'WATCH'

  return (
    <span
      className={`inline-flex font-num text-[9px] font-bold uppercase tracking-[0.12em] px-[6px] py-[2px] rounded-tile ${cls}`}
    >
      {label}
    </span>
  )
}

// ── Confidence pip ────────────────────────────────────────────────────────────

function ConfPip({ band }: { band: string | null }) {
  const pips = ['H', 'M', 'L']
  return (
    <div className="flex gap-[2px] items-center justify-center">
      {pips.map((p) => {
        const active = band === p
        const cls = active && p === 'H' ? 'bg-sig-pos'
          : active && p === 'M' ? 'bg-sig-warn'
          : active ? 'bg-txt-3/60'
          : 'bg-surface-inset'
        return (
          <span
            key={p}
            className={`w-[6px] h-[8px] rounded-[1px] ${cls}`}
            aria-label={active ? `${p} confidence` : ''}
          />
        )
      })}
    </div>
  )
}

// ── RS state badge ────────────────────────────────────────────────────────────

function RsStateBadge({ state }: { state: string | null }) {
  if (!state) return <span className="text-txt-3 text-[10px]">—</span>

  const cls =
    ['Leader', 'Strong'].includes(state) ? 'text-sig-pos'
    : ['Weak', 'Laggard'].includes(state) ? 'text-sig-neg'
    : ['Emerging', 'Consolidating'].includes(state) ? 'text-sig-warn'
    : 'text-txt-3'

  return <span className={`font-num text-[10px] ${cls}`}>{state}</span>
}

// ── Sort types ────────────────────────────────────────────────────────────────

// Action / composite-score / confidence columns removed (FM 2026-06-26): they came from
// the separate atlas conviction model, not the six-lens decile system, and read as an
// unexplained black box. The table now shows only fresh, explainable return + RS data.
type SortKey = 'ret_1m' | 'ret_3m' | 'rs_3m'

// Shared <th> style — tokenised header chrome.
const thStyle: React.CSSProperties = {
  padding: '9px 8px',
  fontFamily: 'var(--font-sans), Inter, sans-serif',
  fontSize: 9,
  letterSpacing: '0.13em',
  textTransform: 'uppercase',
  color: 'var(--color-txt-3)',
  fontWeight: 600,
  background: 'var(--color-surface-raised)',
  borderBottom: '1px solid var(--color-edge-rule)',
}

// ── Main table ────────────────────────────────────────────────────────────────

export function ConstituentsTable({ constituents }: { constituents: ConstituentRow[] }) {
  const router = useRouter()
  const [sortKey, setSortKey] = useState<SortKey>('ret_3m')
  const [sortDir, setSortDir] = useState<'desc' | 'asc'>('desc')

  if (constituents.length === 0) {
    return (
      <div className="py-8 text-center text-txt-3 font-sans text-sm" role="status">
        No constituent data available.
      </div>
    )
  }

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === 'desc' ? 'asc' : 'desc'))
    } else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  const getVal = (r: ConstituentRow): number => {
    if (sortKey === 'ret_1m') return r.ret_1m ?? -Infinity
    if (sortKey === 'ret_3m') return r.ret_3m ?? -Infinity
    if (sortKey === 'rs_3m') return r.rs_3m_nifty500_pp ?? -Infinity
    return -Infinity
  }

  // Defensive slice: MV promises top-30 but guard against oversized arrays
  const capped = constituents.slice(0, 30)

  const sorted = [...capped].sort((a, b) => {
    const diff = getVal(b) - getVal(a)
    return sortDir === 'desc' ? diff : -diff
  })

  function SortTh({ label, skey, unit, term }: { label: string; skey: SortKey; unit?: string; term?: string }) {
    const active = sortKey === skey
    return (
      <th
        onClick={() => handleSort(skey)}
        style={{
          ...thStyle,
          cursor: 'pointer',
          textAlign: 'center',
          color: active ? 'var(--color-txt-1)' : 'var(--color-txt-3)',
          verticalAlign: 'bottom',
          userSelect: 'none',
        }}
        aria-sort={active ? (sortDir === 'desc' ? 'descending' : 'ascending') : 'none'}
      >
        {label}
        {term && <TermInfo term={term} />}
        {active && <span style={{ marginLeft: 3 }}>{sortDir === 'desc' ? '↓' : '↑'}</span>}
        {unit && (
          <span style={{ display: 'block', fontSize: 8, color: 'var(--color-txt-3)', fontFamily: 'var(--font-num), monospace', letterSpacing: '0.04em', textTransform: 'none', marginTop: 2, fontWeight: 400 }}>
            {unit}
          </span>
        )}
      </th>
    )
  }

  return (
    <div className="overflow-x-auto bg-surface-panel border border-edge-hair rounded-panel shadow-panel" data-testid="constituents-table">
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }} aria-label="Top-30 constituents">
        <thead>
          <tr>
            <th style={{ ...thStyle, textAlign: 'left', paddingLeft: 14 }}>
              Stock
            </th>
            <th style={{ ...thStyle, textAlign: 'left' }}>
              Tier
            </th>
            <th style={{ ...thStyle, textAlign: 'center' }}>
              RS State<TermInfo term="rs_state" />
            </th>
            <SortTh label="1M" skey="ret_1m" unit="abs" />
            <SortTh label="3M" skey="ret_3m" unit="abs" />
            <th style={{ ...thStyle, textAlign: 'center' }}>
              1W
              <span style={{ display: 'block', fontSize: 8, color: 'var(--color-txt-3)', fontFamily: 'var(--font-num), monospace', letterSpacing: '0.04em', textTransform: 'none', marginTop: 2, fontWeight: 400 }}>abs</span>
            </th>
            <SortTh label="RS 3M" skey="rs_3m" unit="vs N500" term="rs" />
          </tr>
        </thead>
        <tbody>
          {sorted.map((c, idx) => {
            const r1m = fmtPct(c.ret_1m)
            const r3m = fmtPct(c.ret_3m)
            const r1w = fmtPct(c.ret_1w)
            const rs3m = fmtPp(c.rs_3m_nifty500_pp)

            return (
              <tr
                key={c.symbol}
                onClick={() => router.push(`/stocks/${encodeURIComponent(c.symbol)}`)}
                style={{ borderBottom: '1px solid var(--color-edge-hair)', cursor: 'pointer' }}
                className="hover:bg-surface-raised transition-colors"
                data-testid={`constituent-row-${c.symbol}`}
                aria-rowindex={idx + 1}
              >
                {/* Symbol + name */}
                <td style={{ textAlign: 'left', padding: '7px 14px', fontFamily: 'var(--font-sans), Inter, sans-serif' }}>
                  <div>
                    <span className="font-num text-[12px] font-semibold text-brand">
                      {c.symbol}
                    </span>
                    {c.company_name && (
                      <div className="text-[10px] text-txt-3 mt-[1px] truncate max-w-[150px]">
                        {c.company_name}
                      </div>
                    )}
                  </div>
                </td>
                <td style={{ padding: '7px 8px', textAlign: 'left', fontFamily: 'var(--font-sans), Inter, sans-serif', fontSize: 11, color: 'var(--color-txt-3)' }}>
                  {c.tier ?? '—'}
                </td>
                <td style={{ padding: '7px 8px', textAlign: 'center' }}>
                  <RsStateBadge state={c.rs_state} />
                </td>
                <td style={{ padding: '7px 8px', textAlign: 'center', fontFamily: 'var(--font-num), monospace', fontVariantNumeric: 'tabular-nums', fontSize: '11.5px', color: numColor(r1m.cls) }}>
                  {r1m.text}
                </td>
                <td style={{ padding: '7px 8px', textAlign: 'center', fontFamily: 'var(--font-num), monospace', fontVariantNumeric: 'tabular-nums', fontSize: '11.5px', color: numColor(r3m.cls) }}>
                  {r3m.text}
                </td>
                <td style={{ padding: '7px 8px', textAlign: 'center', fontFamily: 'var(--font-num), monospace', fontVariantNumeric: 'tabular-nums', fontSize: '11.5px', color: numColor(r1w.cls) }}>
                  {r1w.text}
                </td>
                <td style={{ padding: '7px 8px', textAlign: 'center', fontFamily: 'var(--font-num), monospace', fontVariantNumeric: 'tabular-nums', fontSize: '11.5px', color: numColor(rs3m.cls) }}>
                  {rs3m.text}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
