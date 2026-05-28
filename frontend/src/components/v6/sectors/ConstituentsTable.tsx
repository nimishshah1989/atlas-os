'use client'
// frontend/src/components/v6/sectors/ConstituentsTable.tsx
// Top-30 constituents table for Page 04a sector deep-dive.
// Source: mv_sector_deepdive.constituents_top30 JSONB array.
// Values are already percentages (ret_* columns multiplied by 100 in MV).

import { useState } from 'react'
import Link from 'next/link'
import type { ConstituentRow } from '@/lib/queries/v6/sectors'

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtPct(v: number | null): { text: string; cls: string } {
  // Values from MV are already percentages (e.g. 5.2 = +5.2%)
  if (v == null) return { text: '—', cls: 'text-ink-tertiary' }
  return {
    text: `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`,
    cls: v >= 0 ? 'text-signal-pos' : 'text-signal-neg',
  }
}

function fmtPp(v: number | null): { text: string; cls: string } {
  if (v == null) return { text: '—', cls: 'text-ink-tertiary' }
  return {
    text: `${v >= 0 ? '+' : ''}${v.toFixed(1)}pp`,
    cls: v >= 0 ? 'text-signal-pos' : 'text-signal-neg',
  }
}

// ── Action chip ───────────────────────────────────────────────────────────────

function ActionChip({ action }: { action: string | null }) {
  if (!action) return <span className="text-ink-tertiary text-[11px]">—</span>

  const cls =
    action === 'POSITIVE' ? 'bg-signal-pos text-paper'
    : action === 'NEGATIVE' ? 'bg-signal-neg text-paper'
    : 'bg-signal-warn/15 text-signal-warn border border-signal-warn/30'

  const label = action === 'POSITIVE' ? 'BUY' : action === 'NEGATIVE' ? 'AVOID' : 'WATCH'

  return (
    <span
      className={`inline-flex font-sans text-[9px] font-bold uppercase tracking-[0.12em] px-[6px] py-[2px] rounded-[2px] ${cls}`}
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
        const cls = active && p === 'H' ? 'bg-signal-pos'
          : active && p === 'M' ? 'bg-signal-warn'
          : active ? 'bg-ink-tertiary/60'
          : 'bg-paper-deep'
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
  if (!state) return <span className="text-ink-tertiary text-[10px]">—</span>

  const cls =
    ['Leader', 'Strong'].includes(state) ? 'text-signal-pos'
    : ['Weak', 'Laggard'].includes(state) ? 'text-signal-neg'
    : ['Emerging', 'Consolidating'].includes(state) ? 'text-signal-warn'
    : 'text-ink-tertiary'

  return <span className={`font-mono text-[10px] ${cls}`}>{state}</span>
}

// ── Sort types ────────────────────────────────────────────────────────────────

type SortKey = 'composite' | 'ret_1m' | 'ret_3m' | 'rs_3m'

// ── Main table ────────────────────────────────────────────────────────────────

export function ConstituentsTable({ constituents }: { constituents: ConstituentRow[] }) {
  const [sortKey, setSortKey] = useState<SortKey>('composite')
  const [sortDir, setSortDir] = useState<'desc' | 'asc'>('desc')

  if (constituents.length === 0) {
    return (
      <div className="py-8 text-center text-ink-tertiary font-sans text-sm" role="status">
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
    if (sortKey === 'composite') return r.composite_score ?? -Infinity
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

  function SortTh({ label, skey, unit }: { label: string; skey: SortKey; unit?: string }) {
    const active = sortKey === skey
    return (
      <th
        onClick={() => handleSort(skey)}
        style={{
          cursor: 'pointer',
          textAlign: 'center',
          padding: '9px 8px',
          fontFamily: 'Inter, sans-serif',
          fontSize: 9,
          letterSpacing: '0.13em',
          textTransform: 'uppercase',
          color: active ? 'var(--color-ink-primary, #1A1714)' : 'var(--color-ink-tertiary, #6B6157)',
          fontWeight: 600,
          background: 'var(--color-paper-soft, #FBF8F1)',
          borderBottom: '1px solid var(--color-ink-rule, #DDD3BF)',
          verticalAlign: 'bottom',
          userSelect: 'none',
        }}
        aria-sort={active ? (sortDir === 'desc' ? 'descending' : 'ascending') : 'none'}
      >
        {label}
        {active && <span style={{ marginLeft: 3 }}>{sortDir === 'desc' ? '↓' : '↑'}</span>}
        {unit && (
          <span style={{ display: 'block', fontSize: 8, color: 'var(--color-ink-4, #9A8F82)', fontFamily: "'JetBrains Mono', monospace", letterSpacing: '0.04em', textTransform: 'none', marginTop: 2, fontWeight: 400 }}>
            {unit}
          </span>
        )}
      </th>
    )
  }

  return (
    <div className="overflow-x-auto bg-paper border border-paper-rule rounded-[2px]" data-testid="constituents-table">
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }} aria-label="Top-30 constituents">
        <thead>
          <tr>
            <th
              style={{
                textAlign: 'left',
                paddingLeft: 14,
                paddingTop: 9,
                paddingBottom: 9,
                fontFamily: 'Inter, sans-serif',
                fontSize: 9,
                letterSpacing: '0.13em',
                textTransform: 'uppercase',
                color: 'var(--color-ink-tertiary, #6B6157)',
                fontWeight: 600,
                background: 'var(--color-paper-soft, #FBF8F1)',
                borderBottom: '1px solid var(--color-ink-rule, #DDD3BF)',
              }}
            >
              Stock
            </th>
            <th style={{ textAlign: 'left', paddingTop: 9, paddingBottom: 9, paddingLeft: 8, fontFamily: 'Inter, sans-serif', fontSize: 9, letterSpacing: '0.13em', textTransform: 'uppercase', color: 'var(--color-ink-tertiary, #6B6157)', fontWeight: 600, background: 'var(--color-paper-soft, #FBF8F1)', borderBottom: '1px solid var(--color-ink-rule, #DDD3BF)' }}>
              Tier
            </th>
            <th style={{ textAlign: 'center', padding: '9px 8px', fontFamily: 'Inter, sans-serif', fontSize: 9, letterSpacing: '0.13em', textTransform: 'uppercase', color: 'var(--color-ink-tertiary, #6B6157)', fontWeight: 600, background: 'var(--color-paper-soft, #FBF8F1)', borderBottom: '1px solid var(--color-ink-rule, #DDD3BF)' }}>
              RS State
            </th>
            <SortTh label="1M" skey="ret_1m" unit="abs" />
            <SortTh label="3M" skey="ret_3m" unit="abs" />
            <th style={{ textAlign: 'center', padding: '9px 8px', fontFamily: 'Inter, sans-serif', fontSize: 9, letterSpacing: '0.13em', textTransform: 'uppercase', color: 'var(--color-ink-tertiary, #6B6157)', fontWeight: 600, background: 'var(--color-paper-soft, #FBF8F1)', borderBottom: '1px solid var(--color-ink-rule, #DDD3BF)' }}>
              1W
              <span style={{ display: 'block', fontSize: 8, color: 'var(--color-ink-4, #9A8F82)', fontFamily: "'JetBrains Mono', monospace", letterSpacing: '0.04em', textTransform: 'none', marginTop: 2, fontWeight: 400 }}>abs</span>
            </th>
            <SortTh label="RS 3M" skey="rs_3m" unit="vs N500" />
            <th style={{ textAlign: 'center', padding: '9px 8px', fontFamily: 'Inter, sans-serif', fontSize: 9, letterSpacing: '0.13em', textTransform: 'uppercase', color: 'var(--color-ink-tertiary, #6B6157)', fontWeight: 600, background: 'var(--color-paper-soft, #FBF8F1)', borderBottom: '1px solid var(--color-ink-rule, #DDD3BF)' }}>
              Conf
            </th>
            <th style={{ textAlign: 'center', padding: '9px 8px', fontFamily: 'Inter, sans-serif', fontSize: 9, letterSpacing: '0.13em', textTransform: 'uppercase', color: 'var(--color-ink-tertiary, #6B6157)', fontWeight: 600, background: 'var(--color-paper-soft, #FBF8F1)', borderBottom: '1px solid var(--color-ink-rule, #DDD3BF)' }}>
              Action
            </th>
            <SortTh label="Score" skey="composite" unit="composite" />
          </tr>
        </thead>
        <tbody>
          {sorted.map((c, idx) => {
            const r1m = fmtPct(c.ret_1m)
            const r3m = fmtPct(c.ret_3m)
            const r1w = fmtPct(c.ret_1w)
            const rs3m = fmtPp(c.rs_3m_nifty500_pp)
            const score = c.composite_score != null
              ? { text: `${c.composite_score >= 0 ? '+' : ''}${c.composite_score.toFixed(1)}`, cls: c.composite_score >= 0 ? 'text-signal-pos' : 'text-signal-neg' }
              : { text: '—', cls: 'text-ink-tertiary' }

            return (
              <tr
                key={c.symbol}
                style={{ borderBottom: '1px solid var(--color-paper-deep, #F1ECDF)' }}
                className="hover:bg-paper-soft/60 transition-colors"
                data-testid={`constituent-row-${c.symbol}`}
                aria-rowindex={idx + 1}
              >
                {/* Symbol + name */}
                <td style={{ textAlign: 'left', padding: '7px 14px', fontFamily: 'Inter, sans-serif' }}>
                  <div>
                    <Link
                      href={`/stocks/${encodeURIComponent(c.symbol)}`}
                      className="font-mono text-[12px] font-semibold text-teal hover:underline"
                    >
                      {c.symbol}
                    </Link>
                    {c.company_name && (
                      <div className="text-[10px] text-ink-tertiary mt-[1px] truncate max-w-[150px]">
                        {c.company_name}
                      </div>
                    )}
                  </div>
                </td>
                <td style={{ padding: '7px 8px', textAlign: 'left', fontFamily: 'Inter, sans-serif', fontSize: 11, color: 'var(--color-ink-tertiary, #6B6157)' }}>
                  {c.tier ?? '—'}
                </td>
                <td style={{ padding: '7px 8px', textAlign: 'center' }}>
                  <RsStateBadge state={c.rs_state} />
                </td>
                <td style={{ padding: '7px 8px', textAlign: 'center', fontFamily: "'JetBrains Mono', monospace", fontSize: '11.5px', color: r1m.cls.includes('pos') ? 'var(--color-signal-pos, #2F6B43)' : r1m.cls.includes('neg') ? 'var(--color-signal-neg, #B0492C)' : 'var(--color-ink-4, #9A8F82)' }}>
                  {r1m.text}
                </td>
                <td style={{ padding: '7px 8px', textAlign: 'center', fontFamily: "'JetBrains Mono', monospace", fontSize: '11.5px', color: r3m.cls.includes('pos') ? 'var(--color-signal-pos, #2F6B43)' : r3m.cls.includes('neg') ? 'var(--color-signal-neg, #B0492C)' : 'var(--color-ink-4, #9A8F82)' }}>
                  {r3m.text}
                </td>
                <td style={{ padding: '7px 8px', textAlign: 'center', fontFamily: "'JetBrains Mono', monospace", fontSize: '11.5px', color: r1w.cls.includes('pos') ? 'var(--color-signal-pos, #2F6B43)' : r1w.cls.includes('neg') ? 'var(--color-signal-neg, #B0492C)' : 'var(--color-ink-4, #9A8F82)' }}>
                  {r1w.text}
                </td>
                <td style={{ padding: '7px 8px', textAlign: 'center', fontFamily: "'JetBrains Mono', monospace", fontSize: '11.5px', color: rs3m.cls.includes('pos') ? 'var(--color-signal-pos, #2F6B43)' : rs3m.cls.includes('neg') ? 'var(--color-signal-neg, #B0492C)' : 'var(--color-ink-4, #9A8F82)' }}>
                  {rs3m.text}
                </td>
                <td style={{ padding: '7px 8px', textAlign: 'center' }}>
                  <ConfPip band={c.confidence_band} />
                </td>
                <td style={{ padding: '7px 8px', textAlign: 'center' }}>
                  <ActionChip action={c.action} />
                </td>
                <td style={{ padding: '7px 8px', textAlign: 'center', fontFamily: "'JetBrains Mono', monospace", fontSize: '11.5px', color: score.cls.includes('pos') ? 'var(--color-signal-pos, #2F6B43)' : score.cls.includes('neg') ? 'var(--color-signal-neg, #B0492C)' : 'var(--color-ink-4, #9A8F82)', fontWeight: 600 }}>
                  {score.text}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
