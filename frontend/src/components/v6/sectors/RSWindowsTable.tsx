'use client'
// frontend/src/components/v6/sectors/RSWindowsTable.tsx
// RS windows table for Page 04a sector deep-dive.
// Source: mv_sector_deepdive.rs_windows JSONB {rs_1w, rs_1m, rs_3m, rs_6m, rs_12m}.
// Values are already pp differences vs Nifty 500.
// Note: MV only includes Nifty 500 baseline. Multi-baseline (Nifty 50, Gold, S&P 500)
// is marked as DEFERRED — requires separate macro query layer.

import type { SectorDeepdiveRow } from '@/lib/queries/v6/sectors'

// ── Color intensity mapping ───────────────────────────────────────────────────

const HM_STYLES: Record<string, React.CSSProperties> = {
  'pos-strong': { background: 'rgba(47,107,67,0.45)', color: '#F8F4EC', fontWeight: 600 },
  'pos':        { background: 'rgba(47,107,67,0.25)' },
  'pos-weak':   { background: 'rgba(47,107,67,0.10)' },
  'flat':       { background: '#FBF8F1' },
  'neg-weak':   { background: 'rgba(176,73,44,0.10)' },
  'neg':        { background: 'rgba(176,73,44,0.25)' },
  'neg-strong': { background: 'rgba(176,73,44,0.45)', color: '#F8F4EC', fontWeight: 600 },
}

function hmCls(pp: number | null): string {
  if (pp == null) return 'flat'
  if (pp >= 10)  return 'pos-strong'
  if (pp >= 5)   return 'pos'
  if (pp >= 2)   return 'pos-weak'
  if (pp >= -2)  return 'flat'
  if (pp >= -5)  return 'neg-weak'
  if (pp >= -10) return 'neg'
  return 'neg-strong'
}

// ── Cells ─────────────────────────────────────────────────────────────────────

function RSCell({ value }: { value: number | null }) {
  const cls = hmCls(value)
  const style = HM_STYLES[cls] ?? {}
  const text = value != null
    ? `${value >= 0 ? '+' : ''}${value.toFixed(1)}pp`
    : '—'

  return (
    <td style={{ padding: 0, textAlign: 'center', borderBottom: '1px solid #F1ECDF' }}>
      <div
        style={{
          padding: '12px 8px',
          cursor: 'pointer',
          fontFamily: "'JetBrains Mono', Consolas, monospace",
          fontSize: '13px',
          fontWeight: 500,
          color: '#1A1714',
          ...style,
        }}
        aria-label={text}
      >
        {text}
      </div>
    </td>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export function RSWindowsTable({ sector }: { sector: SectorDeepdiveRow }) {
  const rs = sector.rs_windows

  const thStyle: React.CSSProperties = {
    textAlign: 'center',
    padding: '11px 14px',
    fontFamily: 'Inter, sans-serif',
    fontSize: 9,
    letterSpacing: '0.18em',
    textTransform: 'uppercase',
    color: '#6B6157',
    fontWeight: 600,
    background: '#FBF8F1',
    borderBottom: '1px solid #DDD3BF',
  }

  return (
    <div
      className="bg-paper border border-paper-rule rounded-[2px] overflow-hidden"
      data-testid="rs-windows-table"
      aria-label="RS vs baselines across time windows"
    >
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            <th style={{ ...thStyle, textAlign: 'left', width: '28%', paddingLeft: 16 }}>Baseline</th>
            <th style={thStyle}>1 week</th>
            <th style={thStyle}>1 month</th>
            <th style={thStyle}>3 months</th>
            <th style={thStyle}>6 months</th>
            <th style={thStyle}>12 months</th>
          </tr>
        </thead>
        <tbody>
          {/* Nifty 500 row — live data */}
          <tr>
            <td style={{ padding: '14px 16px', textAlign: 'left', fontFamily: 'Inter, sans-serif', borderBottom: '1px solid #F1ECDF' }}>
              <div className="flex items-center gap-3">
                <div
                  className="w-7 h-5 rounded-[2px] flex items-center justify-center text-sm bg-paper-deep border border-paper-rule"
                  aria-hidden="true"
                >
                  🇮🇳
                </div>
                <div>
                  <div className="font-medium text-ink-primary text-[13px]">Nifty 500</div>
                  <div className="text-[10px] text-ink-tertiary mt-[1px]">Broad-market baseline</div>
                </div>
              </div>
            </td>
            <RSCell value={rs?.rs_1w ?? null} />
            <RSCell value={rs?.rs_1m ?? null} />
            <RSCell value={rs?.rs_3m ?? null} />
            <RSCell value={rs?.rs_6m ?? null} />
            <RSCell value={rs?.rs_12m ?? null} />
          </tr>

          {/* Deferred baselines — shown as placeholder rows */}
          {[
            { flag: '🇮🇳', name: 'Nifty 50', sub: 'Large-cap anchor' },
            { flag: '●',   name: 'Gold (₹/g, Mumbai)', sub: 'Safe-haven anchor' },
            { flag: '🇺🇸', name: 'S&P 500', sub: 'US large-cap · USD-INR adj' },
          ].map((row) => (
            <tr key={row.name} style={{ opacity: 0.45 }}>
              <td style={{ padding: '14px 16px', textAlign: 'left', fontFamily: 'Inter, sans-serif', borderBottom: '1px solid #F1ECDF' }}>
                <div className="flex items-center gap-3">
                  <div className="w-7 h-5 rounded-[2px] flex items-center justify-center text-sm bg-paper-deep border border-paper-rule" aria-hidden="true">
                    {row.flag}
                  </div>
                  <div>
                    <div className="font-medium text-ink-primary text-[13px]">{row.name}</div>
                    <div className="text-[10px] text-ink-tertiary mt-[1px]">{row.sub}</div>
                  </div>
                </div>
              </td>
              {[1,2,3,4,5].map((i) => (
                <td key={i} style={{ padding: '12px 8px', textAlign: 'center', borderBottom: '1px solid #F1ECDF' }}>
                  <span className="font-mono text-[11px] text-ink-tertiary">—</span>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>

      <div className="px-4 py-2 border-t border-paper-rule bg-paper-soft">
        <p className="font-sans text-[11px] text-ink-tertiary">
          Multi-baseline RS (Nifty 50, Gold, S&P 500) is planned — currently showing Nifty 500 only from the sector MV.
        </p>
      </div>
    </div>
  )
}
