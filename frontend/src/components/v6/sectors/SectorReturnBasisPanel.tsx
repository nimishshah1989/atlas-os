'use client'
// frontend/src/components/v6/sectors/SectorReturnBasisPanel.tsx
//
// Sector returns across all windows under two bases, switchable via a toggle:
//   Index     — official cap-weighted NSE sector index
//   Bottom-up — free-float cap-weighted aggregate of Atlas's constituents
//
// Shows Return and RS (vs Nifty 500) for 1D / 1W / 1M / 3M / 6M / 12M.
// Replaces the old equal-weighted "absolute return" (which over-counted micro-caps).

import { useState } from 'react'
import {
  basisReturn, basisRs,
  type SectorReturnBases, type ReturnSet, type ReturnBasis, type ReturnWindow,
} from '@/lib/queries/v6/sector_return_bases_shared'

type Props = {
  data: SectorReturnBases | null
  nifty500: ReturnSet
}

const WINDOWS: { key: ReturnWindow; label: string }[] = [
  { key: '1d', label: '1D' },
  { key: '1w', label: '1W' },
  { key: '1m', label: '1M' },
  { key: '3m', label: '3M' },
  { key: '6m', label: '6M' },
  { key: '12m', label: '12M' },
]

const BASES: { key: ReturnBasis; label: string }[] = [
  { key: 'index', label: 'Index' },
  { key: 'bottomup', label: 'Bottom-up' },
]

// Heatmap tint on a decimal fraction (return) or pp (rs, already fraction here).
function tint(v: number | null): React.CSSProperties {
  if (v == null) return {}
  const pct = v * 100
  if (pct >= 10) return { background: 'rgba(47,107,67,0.40)', color: '#F8F4EC', fontWeight: 600 }
  if (pct >= 5) return { background: 'rgba(47,107,67,0.22)' }
  if (pct >= 2) return { background: 'rgba(47,107,67,0.10)' }
  if (pct >= -2) return {}
  if (pct >= -5) return { background: 'rgba(176,73,44,0.10)' }
  if (pct >= -10) return { background: 'rgba(176,73,44,0.22)' }
  return { background: 'rgba(176,73,44,0.40)', color: '#F8F4EC', fontWeight: 600 }
}

function Cell({ v, unit }: { v: number | null; unit: '%' | 'pp' }) {
  const text = v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}${unit}`
  return (
    <td style={{ padding: 0, textAlign: 'center', borderBottom: '1px solid #F1ECDF' }}>
      <div className="font-mono text-[12.5px]" style={{ padding: '9px 8px', ...tint(v) }}>{text}</div>
    </td>
  )
}

export function SectorReturnBasisPanel({ data, nifty500 }: Props) {
  // Default to Bottom-up — reliable for every sector. The Index basis is missing
  // for several NSE sector indices whose price series is too sparse (shows "—").
  const [basis, setBasis] = useState<ReturnBasis>('bottomup')

  if (!data) {
    return (
      <div className="bg-paper-soft border border-paper-rule rounded-[2px] p-4 text-center text-[12px] text-ink-tertiary">
        No return data mapped for this sector.
      </div>
    )
  }

  const basisLabel = BASES.find((b) => b.key === basis)!.label

  return (
    <div className="bg-paper border border-paper-rule rounded-[2px] overflow-hidden" data-testid="return-basis-panel">
      {/* Toggle header */}
      <div className="flex items-center justify-between flex-wrap gap-3 px-4 py-3 border-b border-paper-rule bg-paper-soft">
        <div className="flex items-center gap-2">
          <span className="text-[10px] uppercase tracking-[0.14em] text-ink-tertiary font-semibold">Return basis</span>
          <div className="flex gap-1">
            {BASES.map((b) => (
              <button
                key={b.key}
                onClick={() => setBasis(b.key)}
                aria-pressed={basis === b.key}
                className={`px-2.5 py-0.5 text-[11px] border rounded-sm font-medium transition-colors cursor-pointer ${
                  basis === b.key
                    ? 'bg-accent text-paper border-accent'
                    : 'bg-paper text-ink-tertiary border-paper-rule hover:text-ink-secondary'
                }`}
              >
                {b.label}
              </button>
            ))}
          </div>
        </div>
        <span className="font-mono text-[10px] text-ink-tertiary">
          {basis === 'index'
            ? `${data.index_code ?? 'NSE index'} · cap-weighted`
            : 'Atlas constituents · free-float cap-weighted'}
        </span>
      </div>

      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            <th className="text-left" style={{ padding: '9px 16px', fontFamily: 'Inter, sans-serif', fontSize: 9, letterSpacing: '0.16em', textTransform: 'uppercase', color: '#6B6157', fontWeight: 600, background: '#FBF8F1', borderBottom: '1px solid #DDD3BF' }}>Window</th>
            <th style={{ padding: '9px 8px', fontFamily: 'Inter, sans-serif', fontSize: 9, letterSpacing: '0.16em', textTransform: 'uppercase', color: '#6B6157', fontWeight: 600, background: '#FBF8F1', borderBottom: '1px solid #DDD3BF' }}>Return</th>
            <th style={{ padding: '9px 8px', fontFamily: 'Inter, sans-serif', fontSize: 9, letterSpacing: '0.16em', textTransform: 'uppercase', color: '#6B6157', fontWeight: 600, background: '#FBF8F1', borderBottom: '1px solid #DDD3BF' }}>RS vs Nifty 500</th>
          </tr>
        </thead>
        <tbody>
          {WINDOWS.map((w) => (
            <tr key={w.key}>
              <td className="text-left text-ink-primary font-medium text-[12.5px]" style={{ padding: '9px 16px', fontFamily: 'Inter, sans-serif', borderBottom: '1px solid #F1ECDF' }}>{w.label}</td>
              <Cell v={basisReturn(data, basis, w.key)} unit="%" />
              <Cell v={basisRs(data, nifty500, basis, w.key)} unit="pp" />
            </tr>
          ))}
        </tbody>
      </table>

      <div className="px-4 py-2 border-t border-paper-rule bg-paper-soft">
        <p className="font-sans text-[11px] text-ink-tertiary">
          {basisLabel} basis. <strong className="text-ink-secondary">Index</strong> = official cap-weighted NSE sector index;{' '}
          <strong className="text-ink-secondary">Bottom-up</strong> = free-float cap-weighted return of Atlas&apos;s tracked constituents.
          RS = return minus Nifty 500 over the same window.
        </p>
      </div>
    </div>
  )
}

export default SectorReturnBasisPanel
