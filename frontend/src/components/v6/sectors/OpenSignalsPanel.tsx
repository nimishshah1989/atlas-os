'use client'
// frontend/src/components/v6/sectors/OpenSignalsPanel.tsx
// Open signals panel for Page 04a sector deep-dive.
// Source: mv_sector_deepdive.open_signals JSONB array.

import Link from 'next/link'
import type { OpenSignalRow } from '@/lib/queries/v6/sectors'

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtDate(d: string): string {
  try {
    const dt = new Date(d)
    return dt.toLocaleDateString('en-IN', {
      day: '2-digit', month: 'short', year: 'numeric',
    }).replace(/ /g, '-')
  } catch {
    return d
  }
}

// ── Action chip ───────────────────────────────────────────────────────────────

function ActionChip({ action }: { action: string }) {
  const cls =
    action === 'POSITIVE' ? 'bg-signal-pos text-paper'
    : action === 'NEGATIVE' ? 'bg-signal-neg text-paper'
    : 'bg-signal-warn/15 text-signal-warn border border-signal-warn/30'
  const label = action === 'POSITIVE' ? 'BUY' : action === 'NEGATIVE' ? 'SELL' : action
  return (
    <span className={`font-sans text-[9px] font-bold uppercase tracking-[0.12em] px-[6px] py-[2px] rounded-[2px] ${cls}`}>
      {label}
    </span>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export function OpenSignalsPanel({ signals }: { signals: OpenSignalRow[] }) {
  if (signals.length === 0) {
    return (
      <div
        className="flex items-center justify-center h-20 bg-paper border border-paper-rule rounded-[2px] text-ink-tertiary font-sans text-sm"
        role="status"
        data-testid="open-signals-empty"
      >
        No open signals in this sector.
      </div>
    )
  }

  return (
    <div
      className="bg-paper border border-paper-rule rounded-[2px] overflow-hidden"
      data-testid="open-signals-panel"
      aria-label="Open signals in sector"
    >
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
        <thead>
          <tr>
            {['Stock', 'Action', 'Tenure', 'Tier', 'Confidence', 'Signal Date'].map((h) => (
              <th
                key={h}
                style={{
                  textAlign: h === 'Stock' ? 'left' : 'center',
                  padding: '8px 12px',
                  fontFamily: 'Inter, sans-serif',
                  fontSize: 9,
                  letterSpacing: '0.13em',
                  textTransform: 'uppercase',
                  color: '#6B6157',
                  fontWeight: 600,
                  background: '#FBF8F1',
                  borderBottom: '1px solid #DDD3BF',
                }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {signals.map((sig) => {
            const conf = sig.confidence_unconditional != null
              ? `${(sig.confidence_unconditional * 100).toFixed(0)}%`
              : '—'

            return (
              <tr
                key={`${sig.symbol}-${sig.signal_date}`}
                style={{ borderBottom: '1px solid #F1ECDF' }}
                className="hover:bg-paper-soft/60 transition-colors"
              >
                <td style={{ padding: '7px 12px', textAlign: 'left', fontFamily: 'Inter, sans-serif' }}>
                  <Link
                    href={`/stocks/${encodeURIComponent(sig.symbol)}`}
                    className="font-mono text-[12px] font-semibold text-teal hover:underline"
                  >
                    {sig.symbol}
                  </Link>
                  {sig.company_name && (
                    <div className="text-[10px] text-ink-tertiary truncate max-w-[140px]">
                      {sig.company_name}
                    </div>
                  )}
                </td>
                <td style={{ padding: '7px 12px', textAlign: 'center' }}>
                  <ActionChip action={sig.action} />
                </td>
                <td style={{ padding: '7px 12px', textAlign: 'center', fontFamily: 'Inter, sans-serif', fontSize: 11, color: '#6B6157' }}>
                  {sig.tenure ?? '—'}
                </td>
                <td style={{ padding: '7px 12px', textAlign: 'center', fontFamily: 'Inter, sans-serif', fontSize: 11, color: '#6B6157' }}>
                  {sig.cap_tier_at_trigger ?? '—'}
                </td>
                <td style={{ padding: '7px 12px', textAlign: 'center', fontFamily: "'JetBrains Mono', monospace", fontSize: 11.5, color: '#1A1714', fontWeight: 600 }}>
                  {conf}
                </td>
                <td style={{ padding: '7px 12px', textAlign: 'center', fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#6B6157' }}>
                  {fmtDate(sig.signal_date)}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
