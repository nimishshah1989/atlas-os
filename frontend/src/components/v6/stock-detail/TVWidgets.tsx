'use client'

// Reusable TradingView embed widgets. All use light theme to match Atlas paper aesthetic.
// Each is a thin iframe wrapper — no client-side state, just URL composition.

interface TVWidgetProps {
  symbol: string
}

// ─── Symbol Info (price + key stats card) ─────────────────────────────────────
export function TVSymbolInfo({ symbol }: TVWidgetProps) {
  const url =
    `https://www.tradingview.com/embed-widget/symbol-info/?symbol=NSE%3A${encodeURIComponent(symbol)}` +
    `&colorTheme=light&isTransparent=true&locale=en&autosize=true`
  return (
    <iframe
      src={url}
      className="w-full h-[180px] border-0 bg-paper"
      sandbox="allow-scripts allow-same-origin allow-popups allow-forms allow-popups-to-escape-sandbox"
      title={`${symbol} info`}
      loading="lazy"
    />
  )
}

// ─── Technical Analysis (BUY/SELL gauge) ──────────────────────────────────────
interface TVTechnicalAnalysisProps extends TVWidgetProps {
  interval?: '1m' | '5m' | '15m' | '1h' | '4h' | '1D' | '1W' | '1M'
}
export function TVTechnicalAnalysis({ symbol, interval = '1D' }: TVTechnicalAnalysisProps) {
  const url =
    `https://www.tradingview.com/embed-widget/technical-analysis/?symbol=NSE%3A${encodeURIComponent(symbol)}` +
    `&interval=${interval}&colorTheme=light&isTransparent=true&showIntervalTabs=true&locale=en&autosize=true`
  return (
    <iframe
      src={url}
      className="w-full h-[450px] border-0 bg-paper"
      sandbox="allow-scripts allow-same-origin allow-popups allow-forms allow-popups-to-escape-sandbox"
      title={`${symbol} technical analysis`}
      loading="lazy"
    />
  )
}

// ─── Financials ───────────────────────────────────────────────────────────────
export function TVFinancials({ symbol }: TVWidgetProps) {
  const url =
    `https://www.tradingview.com/embed-widget/financials/?symbol=NSE%3A${encodeURIComponent(symbol)}` +
    `&colorTheme=light&isTransparent=true&displayMode=regular&locale=en&autosize=true`
  return (
    <iframe
      src={url}
      className="w-full h-[550px] border-0 bg-paper"
      sandbox="allow-scripts allow-same-origin allow-popups allow-forms allow-popups-to-escape-sandbox"
      title={`${symbol} financials`}
      loading="lazy"
    />
  )
}

// ─── Company Profile ──────────────────────────────────────────────────────────
export function TVCompanyProfile({ symbol }: TVWidgetProps) {
  const url =
    `https://www.tradingview.com/embed-widget/symbol-profile/?symbol=NSE%3A${encodeURIComponent(symbol)}` +
    `&colorTheme=light&isTransparent=true&locale=en&autosize=true`
  return (
    <iframe
      src={url}
      className="w-full h-[400px] border-0 bg-paper"
      sandbox="allow-scripts allow-same-origin allow-popups allow-forms allow-popups-to-escape-sandbox"
      title={`${symbol} company profile`}
      loading="lazy"
    />
  )
}

// ─── News Timeline ────────────────────────────────────────────────────────────
export function TVNews({ symbol }: TVWidgetProps) {
  const url =
    `https://www.tradingview.com/embed-widget/timeline/?feedMode=symbol` +
    `&symbol=NSE%3A${encodeURIComponent(symbol)}` +
    `&colorTheme=light&isTransparent=true&displayMode=regular&locale=en&autosize=true`
  return (
    <iframe
      src={url}
      className="w-full h-[500px] border-0 bg-paper"
      sandbox="allow-scripts allow-same-origin allow-popups allow-forms allow-popups-to-escape-sandbox"
      title={`${symbol} news`}
      loading="lazy"
    />
  )
}

// ─── Mini Symbol Overview (sparkline) ─────────────────────────────────────────
interface TVMiniProps extends TVWidgetProps {
  dateRange?: '1D' | '1M' | '3M' | '12M' | '60M' | 'ALL'
  exchange?: 'NSE' | 'INDEX'
}
export function TVMiniOverview({ symbol, dateRange = '12M', exchange = 'NSE' }: TVMiniProps) {
  const url =
    `https://www.tradingview.com/embed-widget/mini-symbol-overview/?symbol=${exchange}%3A${encodeURIComponent(symbol)}` +
    `&dateRange=${dateRange}&colorTheme=light&trendLineColor=%231D9E75&underLineColor=rgba%2829%2C158%2C117%2C0.15%29` +
    `&isTransparent=true&autosize=true&locale=en`
  return (
    <iframe
      src={url}
      className="w-full h-[120px] border-0 bg-paper"
      sandbox="allow-scripts allow-same-origin allow-popups allow-forms allow-popups-to-escape-sandbox"
      title={`${symbol} ${dateRange} sparkline`}
      loading="lazy"
    />
  )
}
