// frontend/src/components/v6/TVMetricsBadge.tsx
//
// TV-05: Inline badge for the stock hero right side — always visible
// regardless of active tab. Shows TradingView screener recommendation,
// RSI, MACD, and a direct link to TradingView.
//
// Renders null when tvRecommendLabel is null.
// Shows amber STALE label when fetched_at > 2 days.
// isLoading=true renders 3 animated skeleton pills.

import type { TVMetricsRow } from '@/lib/api/v1'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TVMetricsBadgeProps {
  symbol: string
  tvRecommendLabel: string | null   // "STRONG_BUY" | "BUY" | "NEUTRAL" | "SELL" | "STRONG_SELL"
  recommendAll: number | null
  rsi14: number | null
  macdMacd: number | null
  fetchedAt: string | null          // ISO string — drives stale detection
  isLoading?: boolean
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const STALE_MS = 2 * 24 * 60 * 60 * 1000

function isStale(fetchedAt: string | null): { stale: boolean; label: string } {
  if (!fetchedAt) return { stale: false, label: '' }
  const age = Date.now() - new Date(fetchedAt).getTime()
  if (age <= STALE_MS) return { stale: false, label: '' }
  const d = new Date(fetchedAt)
  const day = String(d.getDate()).padStart(2, '0')
  const mon = d.toLocaleString('en-IN', { month: 'short' })
  return { stale: true, label: `STALE ${day}-${mon}` }
}

function recommendPillClasses(label: string | null): string {
  if (!label) return 'bg-paper-deep text-ink-tertiary'
  if (label === 'STRONG_BUY' || label === 'BUY') return 'bg-signal-pos text-white'
  if (label === 'SELL' || label === 'STRONG_SELL') return 'bg-signal-neg text-white'
  return 'bg-signal-warn text-white' // NEUTRAL
}


function recommendDisplay(label: string | null): string {
  if (!label) return '—'
  return label.replace('_', ' ')
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Badge built from a TVMetricsRow. All numeric values must already be parsed
 * from Decimal strings before being passed (caller is responsible).
 */
export function TVMetricsBadge({
  symbol,
  tvRecommendLabel,
  rsi14,
  macdMacd,
  fetchedAt,
  isLoading = false,
}: TVMetricsBadgeProps) {
  // Loading state: show skeleton pills
  if (isLoading) {
    return (
      <div
        className="flex flex-wrap items-center gap-3 font-sans text-[11px] text-ink-secondary"
        aria-label="TradingView signal loading"
        data-testid="tv-metrics-badge-loading"
      >
        <span className="text-ink-tertiary uppercase tracking-wider font-medium">TV Signal</span>
        <span className="text-paper-rule">|</span>
        <div className="w-16 h-4 rounded-sm bg-paper-rule animate-pulse" />
        <div className="w-10 h-4 rounded-sm bg-paper-rule animate-pulse" />
        <div className="w-14 h-4 rounded-sm bg-paper-rule animate-pulse" />
      </div>
    )
  }

  // No data: hide badge entirely
  if (tvRecommendLabel === null) return null

  const staleInfo = isStale(fetchedAt)
  const pillClasses = recommendPillClasses(tvRecommendLabel)
  const tvUrl = `https://www.tradingview.com/symbols/NSE-${symbol}/`

  return (
    <div
      className="flex flex-wrap items-center gap-3 font-sans text-[11px] text-ink-secondary"
      aria-label="TradingView signal summary"
      data-testid="tv-metrics-badge"
    >
      {/* Label */}
      <span className="text-ink-tertiary uppercase tracking-wider font-medium">
        TV Signal
      </span>

      <span className="text-paper-rule">|</span>

      {/* Recommendation pill — bg-signal-pos/neg/warn text-white per spec */}
      <span
        className={`inline-flex items-center px-[7px] py-[3px] rounded-sm font-semibold uppercase ${pillClasses}`}
        style={{ letterSpacing: '0.1em' }}
        data-testid="tv-recommend-pill"
      >
        {recommendDisplay(tvRecommendLabel)}
      </span>

      <span className="text-paper-rule">|</span>

      {/* RSI */}
      <span className="font-mono tabular-nums">
        RSI{' '}
        <span className="text-ink-primary font-medium">
          {rsi14 != null ? rsi14.toFixed(1) : '—'}
        </span>
      </span>

      {/* MACD */}
      <span className="font-mono tabular-nums">
        MACD{' '}
        <span
          className={
            macdMacd != null
              ? macdMacd >= 0
                ? 'text-signal-pos font-medium'
                : 'text-signal-neg font-medium'
              : 'text-ink-tertiary'
          }
        >
          {macdMacd != null
            ? `${macdMacd >= 0 ? '+' : ''}${macdMacd.toFixed(2)}`
            : '—'}
        </span>
      </span>

      <span className="text-paper-rule">|</span>

      {/* TradingView link */}
      <a
        href={tvUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="text-accent hover:underline"
      >
        TradingView ↗
      </a>

      {/* Stale label */}
      {staleInfo.stale && (
        <span className="text-signal-warn font-medium" data-testid="tv-stale-label">
          {staleInfo.label}
        </span>
      )}
    </div>
  )
}

/**
 * Convenience wrapper that accepts a TVMetricsRow and extracts the
 * required props, converting Decimal strings to numbers at the boundary.
 */
export function TVMetricsBadgeFromRow({
  symbol,
  row,
}: {
  symbol: string
  row: TVMetricsRow | null
}) {
  if (!row) return null

  const rsi14 = row.rsi_14 != null ? parseFloat(row.rsi_14) : null
  const macdMacd = row.macd_macd != null ? parseFloat(row.macd_macd) : null

  return (
    <TVMetricsBadge
      symbol={symbol}
      tvRecommendLabel={row.tv_recommend_label}
      recommendAll={row.recommend_all != null ? parseFloat(row.recommend_all) : null}
      rsi14={Number.isFinite(rsi14) ? rsi14 : null}
      macdMacd={Number.isFinite(macdMacd) ? macdMacd : null}
      fetchedAt={row.fetched_at}
    />
  )
}

export default TVMetricsBadge
