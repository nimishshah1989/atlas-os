'use client'
// frontend/src/components/v6/sectors/SectorHeatmapTable.tsx
// Multi-window return heatmap table — Page 04 Sectors.
// Source: mv_sector_cards (ret_1w/1m/3m/6m/12m + rs_1m/3m/6m + pct_above_ema20 + breadth).

import Link from 'next/link'
import type { SectorCardRow } from '@/lib/queries/v6/sectors'

// ── Color intensity mapping ───────────────────────────────────────────────────

function hmClass(value: number | null, thresholds = [0.10, 0.05, 0.02, -0.02, -0.05, -0.10]): string {
  if (value == null) return ''
  const [t1, t2, t3, t4, t5, t6] = thresholds
  if (value >= t1)  return 'hm-pos-strong'
  if (value >= t2)  return 'hm-pos'
  if (value >= t3)  return 'hm-pos-weak'
  if (value >= t4)  return 'hm-flat'
  if (value >= t5)  return 'hm-neg-weak'
  if (value >= t6)  return 'hm-neg'
  return 'hm-neg-strong'
}

// Tailwind inline styles for heatmap cells (cannot use dynamic class names in Tailwind)
const HM_STYLES: Record<string, React.CSSProperties> = {
  'hm-pos-strong': { background: 'rgba(47,107,67,0.40)', color: 'var(--color-paper, #F8F4EC)', fontWeight: 600 },
  'hm-pos':        { background: 'rgba(47,107,67,0.22)' },
  'hm-pos-weak':   { background: 'rgba(47,107,67,0.10)' },
  'hm-flat':       { background: 'var(--color-paper-soft, #FBF8F1)' },
  'hm-neg-weak':   { background: 'rgba(176,73,44,0.10)' },
  'hm-neg':        { background: 'rgba(176,73,44,0.22)' },
  'hm-neg-strong': { background: 'rgba(176,73,44,0.40)', color: 'var(--color-paper, #F8F4EC)', fontWeight: 600 },
  '':              { background: 'transparent', color: 'var(--color-ink-4, #9A8F82)' },
}

// ── Cell components ───────────────────────────────────────────────────────────

function HmCell({ value, multiplier = 100, unit }: { value: number | null; multiplier?: number; unit?: 'pp' | '%' }) {
  const cls = hmClass(value)
  const style = HM_STYLES[cls] ?? {}
  const resolvedUnit = unit ?? (multiplier === 100 ? '%' : 'pp')
  const display = value != null
    ? `${(value * multiplier) >= 0 ? '+' : ''}${(value * multiplier).toFixed(1)}${resolvedUnit}`
    : '—'

  return (
    <td style={{ padding: 0, textAlign: 'center', borderBottom: '1px solid var(--color-paper-deep, #F1ECDF)' }}>
      <div
        style={{
          padding: '7px 4px',
          cursor: 'pointer',
          fontFamily: "'JetBrains Mono', Consolas, monospace",
          fontSize: '11.5px',
          ...style,
        }}
        aria-label={display}
      >
        {display}
      </div>
    </td>
  )
}

// Confidence bar — H/M/L pips
function ConfBar({ H, M, L }: { H: number; M: number; L: number }) {
  const total = H + M + L
  if (total === 0) return <span className="text-ink-tertiary font-mono text-[11px]">—</span>

  const pips = [
    ...Array(H).fill('fill-high'),
    ...Array(M).fill('fill-med'),
    ...Array(L).fill('fill-low'),
  ].slice(0, 5)

  return (
    <div className="flex items-center justify-center gap-[2px]">
      {pips.map((cls, i) => (
        <span
          key={i}
          className={`w-[10px] h-[8px] rounded-[1px] ${
            cls === 'fill-high' ? 'bg-signal-pos'
            : cls === 'fill-med' ? 'bg-signal-warn'
            : 'bg-ink-tertiary/40'
          }`}
        />
      ))}
      <span className="font-mono text-[10px] text-ink-tertiary ml-1">{total}</span>
    </div>
  )
}

// ── Main table ────────────────────────────────────────────────────────────────

export function SectorHeatmapTable({ cards }: { cards: SectorCardRow[] }) {
  if (cards.length === 0) {
    return (
      <div className="text-ink-tertiary text-sm text-center py-8">No heatmap data available.</div>
    )
  }

  // Sort by rs_3m descending for heatmap
  const sorted = [...cards].sort((a, b) => (b.rs_3m ?? -Infinity) - (a.rs_3m ?? -Infinity))

  return (
    <div className="overflow-x-auto bg-paper border border-paper-rule rounded-[2px]">
      <table
        style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}
        aria-label="Sector return heatmap"
        data-testid="sector-heatmap-table"
      >
        <thead>
          <tr>
            <th
              style={{
                textAlign: 'left',
                paddingLeft: 14,
                paddingRight: 8,
                paddingTop: 8,
                paddingBottom: 8,
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
              Sector
            </th>

            {/* Returns */}
            {['1W', '1M', '3M', '6M', '12M'].map((w) => (
              <th
                key={w}
                style={{
                  textAlign: 'center',
                  padding: '8px 4px',
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
                {w}
                <span style={{ display: 'block', fontSize: 8, color: 'var(--color-ink-4, #9A8F82)', fontFamily: "'JetBrains Mono', monospace", letterSpacing: '0.04em', textTransform: 'none', marginTop: 2 }}>abs</span>
              </th>
            ))}

            {/* RS columns */}
            {['1M', '3M', '6M'].map((w) => (
              <th
                key={`rs-${w}`}
                style={{
                  textAlign: 'center',
                  padding: '8px 4px',
                  fontFamily: 'Inter, sans-serif',
                  fontSize: 9,
                  letterSpacing: '0.13em',
                  textTransform: 'uppercase',
                  color: 'var(--color-ink-tertiary, #6B6157)',
                  fontWeight: 600,
                  background: 'var(--color-paper-soft, #FBF8F1)',
                  borderBottom: '1px solid var(--color-ink-rule, #DDD3BF)',
                  borderLeft: '1px solid var(--color-ink-rule, #DDD3BF)',
                }}
              >
                RS {w}
                <span style={{ display: 'block', fontSize: 8, color: 'var(--color-ink-4, #9A8F82)', fontFamily: "'JetBrains Mono', monospace", letterSpacing: '0.04em', textTransform: 'none', marginTop: 2 }}>pp vs N500</span>
              </th>
            ))}

            {/* Signal count */}
            <th
              style={{
                textAlign: 'center',
                padding: '8px 4px',
                fontFamily: 'Inter, sans-serif',
                fontSize: 9,
                letterSpacing: '0.13em',
                textTransform: 'uppercase',
                color: 'var(--color-ink-tertiary, #6B6157)',
                fontWeight: 600,
                background: 'var(--color-paper-soft, #FBF8F1)',
                borderBottom: '1px solid var(--color-ink-rule, #DDD3BF)',
                borderLeft: '1px solid var(--color-ink-rule, #DDD3BF)',
              }}
            >
              Signals
              <span style={{ display: 'block', fontSize: 8, color: 'var(--color-ink-4, #9A8F82)', fontFamily: "'JetBrains Mono', monospace", letterSpacing: '0.04em', textTransform: 'none', marginTop: 2 }}>H/M/L</span>
            </th>

            <th
              style={{
                textAlign: 'center',
                padding: '8px 4px',
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
              Verdict
            </th>
          </tr>
        </thead>

        <tbody>
          {sorted.map((card) => (
            <tr
              key={card.sector_name}
              style={{ borderBottom: '1px solid var(--color-paper-deep, #F1ECDF)' }}
              className="hover:bg-paper-soft/60 transition-colors"
            >
              {/* Sector name */}
              <td style={{ textAlign: 'left', padding: '7px 14px', fontFamily: 'Inter, sans-serif' }}>
                <div className="flex items-center gap-2">
                  <Link
                    href={`/sectors/${encodeURIComponent(card.sector_name)}`}
                    className="font-medium text-ink-primary text-[12.5px] hover:text-teal transition-colors"
                  >
                    {card.sector_name}
                  </Link>
                  <span
                    className="font-mono text-[9px] text-ink-tertiary bg-paper-deep px-[5px] py-[1px] rounded-[2px]"
                    aria-label={`${card.constituent_count} stocks`}
                  >
                    {card.constituent_count}
                  </span>
                </div>
              </td>

              {/* Absolute returns */}
              <HmCell value={card.ret_1w} />
              <HmCell value={card.ret_1m} />
              <HmCell value={card.ret_3m} />
              <HmCell value={card.ret_6m} />
              <HmCell value={card.ret_12m} />

              {/* RS vs Nifty 500 — unit is pp (percentage point), not % */}
              <HmCell value={card.rs_1m} unit="pp" />
              <HmCell value={card.rs_3m} unit="pp" />
              <HmCell value={card.rs_6m} unit="pp" />

              {/* Signal count */}
              <td
                style={{
                  textAlign: 'center',
                  borderBottom: '1px solid var(--color-paper-deep, #F1ECDF)',
                  padding: '4px 8px',
                  borderLeft: '1px solid var(--color-paper-deep, #F1ECDF)',
                }}
              >
                <ConfBar
                  H={card.confidence_distribution?.H ?? 0}
                  M={card.confidence_distribution?.M ?? 0}
                  L={card.confidence_distribution?.L ?? 0}
                />
              </td>

              {/* Verdict */}
              <td style={{ textAlign: 'center', padding: '7px 8px', borderBottom: '1px solid var(--color-paper-deep, #F1ECDF)' }}>
                {card.verdict_abbr && (
                  <span
                    className={`inline-flex items-center font-mono text-[9px] font-bold uppercase tracking-[0.12em] px-[5px] py-[2px] rounded-[2px] ${
                      card.verdict_abbr === 'OW' ? 'bg-signal-pos text-paper'
                      : card.verdict_abbr === 'UW' ? 'bg-signal-neg text-paper'
                      : 'bg-signal-warn/15 text-signal-warn border border-signal-warn/30'
                    }`}
                  >
                    {card.verdict_abbr}
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
