// frontend/src/components/v6/TVChartPanel.tsx
//
// TV-05: Chart tab panel — 36/64 split.
// Left 36%: TV signals summary (recommendation, MA, RSI, MACD, EMAs).
//           Labeled "TV Signals" — only fields present in tv_metrics table.
// Right 64%: TradingView chart iframe with dark theme.
//            Error fallback: "Chart unavailable · Open in TradingView ↗"
//
// Mobile (<768px): stacks vertically.
// Decimal fields arrive as strings — parseFloat only for display.

'use client'

import { useState } from 'react'
import type { TVMetricsRow } from '@/lib/api/v1'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TVChartPanelProps {
  symbol: string              // NSE symbol, e.g. "RELIANCE"
  tvMetrics: TVMetricsRow | null
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtNum(s: string | null | undefined, decimals = 2): string {
  if (s == null) return '—'
  const n = parseFloat(s)
  return Number.isFinite(n) ? n.toFixed(decimals) : '—'
}

function fmtPrice(s: string | null | undefined): string {
  if (s == null) return '—'
  const n = parseFloat(s)
  if (!Number.isFinite(n)) return '—'
  return `₹${n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function recommendColor(label: string | null): string {
  if (!label) return 'text-ink-tertiary'
  if (label === 'STRONG_BUY' || label === 'BUY') return 'text-signal-pos'
  if (label === 'SELL' || label === 'STRONG_SELL') return 'text-signal-neg'
  return 'text-signal-warn'
}

function recommendDisplay(label: string | null): string {
  if (!label) return '—'
  return label.replace('_', ' ')
}

function macdColor(s: string | null): string {
  if (s == null) return 'text-ink-tertiary'
  const n = parseFloat(s)
  if (!Number.isFinite(n)) return 'text-ink-tertiary'
  return n >= 0 ? 'text-signal-pos' : 'text-signal-neg'
}

function formatFetchedDate(fetchedAt: string | null): string {
  if (!fetchedAt) return 'unknown'
  const d = new Date(fetchedAt)
  const day = String(d.getDate()).padStart(2, '0')
  const mon = d.toLocaleString('en-IN', { month: 'short' })
  const yr = d.getFullYear()
  return `${day}-${mon}-${yr}`
}

// ---------------------------------------------------------------------------
// Left panel: TV Signals
// ---------------------------------------------------------------------------

interface SignalRowProps {
  label: string
  value: string
  valueClass?: string
}

function SignalRow({ label, value, valueClass = 'text-ink-primary' }: SignalRowProps) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-paper-rule last:border-0">
      <span className="font-sans text-[11px] text-ink-tertiary uppercase tracking-wide">{label}</span>
      <span className={`font-mono text-[12px] font-semibold tabular-nums ${valueClass}`}>
        {value}
      </span>
    </div>
  )
}

function TVSignalsPanel({ tvMetrics }: { tvMetrics: TVMetricsRow | null }) {
  const dateLabel = tvMetrics?.fetched_at ? formatFetchedDate(tvMetrics.fetched_at) : null

  return (
    <div className="bg-paper-deep p-5 h-full flex flex-col" data-testid="tv-signals-panel">
      <h3 className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-4">
        TV Signals
        {dateLabel && (
          <span className="ml-2 font-normal normal-case text-ink-tertiary">
            · as of {dateLabel}
          </span>
        )}
      </h3>

      {!tvMetrics ? (
        <p className="font-sans text-sm text-ink-tertiary">
          No TradingView data available for this symbol.
        </p>
      ) : (
        <div className="flex flex-col gap-0">
          {/* Recommendation */}
          <div className="flex items-center justify-between py-1.5 border-b border-paper-rule">
            <span className="font-sans text-[11px] text-ink-tertiary uppercase tracking-wide">
              Recommendation
            </span>
            <span
              className={`inline-flex items-center px-[7px] py-[2px] rounded-sm font-sans text-[11px] font-semibold uppercase bg-paper ${recommendColor(tvMetrics.tv_recommend_label)}`}
              style={{ letterSpacing: '0.1em' }}
            >
              {recommendDisplay(tvMetrics.tv_recommend_label)}
            </span>
          </div>

          {/* MA signal */}
          <div className="flex items-center justify-between py-1.5 border-b border-paper-rule">
            <span className="font-sans text-[11px] text-ink-tertiary uppercase tracking-wide">
              MA Signal
            </span>
            <span
              className={`inline-flex items-center px-[7px] py-[2px] rounded-sm font-sans text-[11px] font-semibold uppercase bg-paper ${recommendColor(tvMetrics.recommend_ma)}`}
              style={{ letterSpacing: '0.1em' }}
            >
              {recommendDisplay(tvMetrics.recommend_ma)}
            </span>
          </div>

          {/* RSI */}
          <SignalRow
            label="RSI (14)"
            value={fmtNum(tvMetrics.rsi_14, 1)}
            valueClass={
              tvMetrics.rsi_14 != null && parseFloat(tvMetrics.rsi_14) > 70
                ? 'text-signal-neg'
                : tvMetrics.rsi_14 != null && parseFloat(tvMetrics.rsi_14) < 30
                  ? 'text-signal-pos'
                  : 'text-ink-primary'
            }
          />

          {/* MACD */}
          <SignalRow
            label="MACD"
            value={
              tvMetrics.macd_macd != null
                ? `${parseFloat(tvMetrics.macd_macd) >= 0 ? '+' : ''}${fmtNum(tvMetrics.macd_macd, 2)}`
                : '—'
            }
            valueClass={macdColor(tvMetrics.macd_macd)}
          />

          {/* EMA 20 */}
          <SignalRow
            label="EMA 20"
            value={fmtPrice(tvMetrics.ema_20)}
          />

          {/* EMA 200 */}
          <SignalRow
            label="EMA 200"
            value={fmtPrice(tvMetrics.ema_200)}
          />

          <div className="mt-3 pt-3 border-t border-paper-rule">
            <h4 className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-2">
              Price Levels
            </h4>
            <SignalRow
              label="Price"
              value={fmtPrice(tvMetrics.price)}
            />
            <SignalRow
              label="52W High"
              value={fmtPrice(tvMetrics.high_52w)}
            />
            <SignalRow
              label="52W Low"
              value={fmtPrice(tvMetrics.low_52w)}
            />
            <SignalRow
              label="ATR (14)"
              value={fmtNum(tvMetrics.atr_14, 2)}
            />
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Right panel: TradingView iframe
// ---------------------------------------------------------------------------

function TVIframePanel({ symbol }: { symbol: string }) {
  const [iframeError, setIframeError] = useState(false)

  const tvUrl = `https://www.tradingview.com/widgetembed/?symbol=NSE:${encodeURIComponent(symbol)}&interval=D&theme=dark&style=1&locale=en`
  const tvOpenUrl = `https://www.tradingview.com/symbols/NSE-${encodeURIComponent(symbol)}/`

  return (
    <div
      className="flex flex-col h-full min-h-[480px]"
      style={{ backgroundColor: '#161a25' }}
      data-testid="tv-iframe-panel"
    >
      {/* Header bar */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#2a2e3a]">
        <span className="font-mono text-[13px] font-semibold text-white">
          NSE:{symbol}
        </span>
        <a
          href={tvOpenUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="font-sans text-[11px] text-[#7b8196] hover:text-white transition-colors"
        >
          Open in TradingView ↗
        </a>
      </div>

      {/* Chart body */}
      <div className="flex-1 relative">
        {iframeError ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3">
            <span className="font-sans text-[13px] text-[#7b8196]">
              Chart unavailable
            </span>
            <a
              href={tvOpenUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="font-sans text-[12px] text-[#a0b4c8] hover:text-white transition-colors underline"
            >
              Open in TradingView ↗
            </a>
          </div>
        ) : (
          <iframe
            src={tvUrl}
            title={`TradingView chart for ${symbol}`}
            className="w-full h-full border-0"
            style={{ minHeight: '420px' }}
            sandbox="allow-scripts allow-same-origin allow-popups"
            onError={() => setIframeError(true)}
            data-testid="tv-iframe"
          />
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function TVChartPanel({ symbol, tvMetrics }: TVChartPanelProps) {
  return (
    <div
      id="tabpanel-chart"
      role="tabpanel"
      aria-labelledby="tab-chart"
      className="flex flex-col md:flex-row min-h-[520px]"
      data-testid="tv-chart-panel"
    >
      {/* Left 36%: TV signals */}
      <div
        className="w-full md:w-[36%] border-b md:border-b-0 md:border-r border-paper-rule"
        style={{ flex: '0 0 auto' }}
      >
        <TVSignalsPanel tvMetrics={tvMetrics} />
      </div>

      {/* Right 64%: TV iframe */}
      <div className="flex-1 min-h-[420px]">
        <TVIframePanel symbol={symbol} />
      </div>
    </div>
  )
}

export default TVChartPanel
