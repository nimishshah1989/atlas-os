"use client";

interface SignalReportProps {
  report: {
    id: string;
    ticker: string;
    exchange: string;
    company_name?: string;
    sector?: string;
    triggered_at: string;
    condition_tier: number;
    condition_label: string;
    confirmation_level: string;
    verdict: string;
    conviction_score?: number;
    conviction_trend?: string;
    cts_state?: string;
    rs_rank?: number;
    rs_rank_total?: number;
    rs_percentile?: number;
    sector_regime?: string;
    market_regime?: string;
    rsi_14?: number;
    macd_signal?: string;
    ema_alignment?: string;
    hh_hl_state?: string;
    pattern_label?: string;
    perf_1m?: number;
    perf_3m?: number;
    perf_6m?: number;
    perf_ytd?: number;
    perf_vs_nifty_1m?: number;
    perf_vs_nifty_ytd?: number;
    chart_daily_url?: string;
    chart_weekly_url?: string;
    chart_vs_sector_url?: string;
    screenshot_daily?: string;
    screenshot_weekly?: string;
    narrative?: string;
  };
}

function fmt(v?: number | null, decimals = 1): string {
  if (v == null) return "—";
  return Number(v).toFixed(decimals);
}

function fmtPct(v?: number | null): string {
  if (v == null) return "—";
  const n = Number(v);
  return `${n >= 0 ? "+" : ""}${n.toFixed(1)}%`;
}

function PerfCell({ label, value, vs }: { label: string; value?: number | null; vs?: number | null }) {
  const vStr = fmtPct(value);
  const vsStr = vs != null ? ` vs Nifty ${fmtPct(vs)}` : "";
  const color = value != null && Number(value) >= 0 ? "text-emerald-600" : "text-red-600";
  return (
    <div>
      <div className="text-xs text-gray-500 mb-0.5">{label}</div>
      <div className={`text-sm font-medium ${color}`}>{vStr}{vsStr}</div>
    </div>
  );
}

export function SignalReport({ report: r }: SignalReportProps) {
  const isDual = r.confirmation_level === "dual";
  const verdictColor = r.verdict === "bullish" ? "text-emerald-600" : r.verdict === "bearish" ? "text-red-600" : "text-yellow-600";

  return (
    <div className="max-w-3xl mx-auto space-y-4">
      {/* Header */}
      <div className="bg-white border border-gray-200 rounded-lg p-5">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-lg font-bold text-gray-900">{r.exchange}:{r.ticker}</span>
              {r.company_name && <span className="text-gray-500 text-sm">{r.company_name}</span>}
            </div>
            <p className="text-sm text-gray-700 mt-1">{r.condition_label}</p>
          </div>
          <div className="text-right shrink-0">
            <div className={`text-sm font-semibold uppercase ${verdictColor}`}>{r.verdict}</div>
            {isDual && (
              <div className="text-xs text-emerald-700 font-medium mt-1">DUAL CONFIRMED ✓</div>
            )}
          </div>
        </div>
        <div className="text-xs text-gray-400 mt-2">
          {new Date(r.triggered_at).toLocaleString("en-IN", {
            day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
          })}
        </div>
      </div>

      {/* Atlas Intelligence */}
      <div className="bg-white border border-gray-200 rounded-lg p-5">
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
          Atlas Intelligence
        </h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
          <div>
            <div className="text-gray-500 text-xs mb-0.5">Conviction</div>
            <div className="font-medium">{r.conviction_score != null ? `${(Number(r.conviction_score) * 10).toFixed(1)}/10` : "—"}</div>
          </div>
          <div>
            <div className="text-gray-500 text-xs mb-0.5">CTS State</div>
            <div className="font-medium">{r.cts_state ?? "—"}</div>
          </div>
          <div>
            <div className="text-gray-500 text-xs mb-0.5">RS Rank</div>
            <div className="font-medium">
              {r.rs_percentile != null
                ? `${(Number(r.rs_percentile) * 100).toFixed(0)}th pct${r.rs_rank != null ? ` · #${r.rs_rank}` : ""}`
                : "—"}
            </div>
          </div>
          <div>
            <div className="text-gray-500 text-xs mb-0.5">Regime</div>
            <div className="font-medium text-xs">{r.market_regime ?? "—"}</div>
          </div>
        </div>
        {r.sector && (
          <div className="mt-3 pt-3 border-t border-gray-100 text-xs text-gray-600">
            Sector: <span className="font-medium">{r.sector}</span>
            {r.sector_regime && <> &mdash; {r.sector_regime}</>}
          </div>
        )}
      </div>

      {/* Charts */}
      {(r.screenshot_daily || r.chart_daily_url) && (
        <div className="bg-white border border-gray-200 rounded-lg p-5">
          <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Charts</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {r.screenshot_daily && (
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-gray-500">vs Nifty &mdash; Daily</span>
                  {r.chart_daily_url && (
                    <a href={r.chart_daily_url} target="_blank" rel="noopener noreferrer"
                      className="text-xs text-teal-600 hover:underline">Open in TV ↗</a>
                  )}
                </div>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={`/api/signals/screenshot?path=${encodeURIComponent(r.screenshot_daily)}`}
                  alt={`${r.ticker} daily chart`} className="w-full rounded border border-gray-100" />
              </div>
            )}
            {r.screenshot_weekly && (
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-gray-500">vs Nifty &mdash; Weekly</span>
                  {r.chart_weekly_url && (
                    <a href={r.chart_weekly_url} target="_blank" rel="noopener noreferrer"
                      className="text-xs text-teal-600 hover:underline">Open in TV ↗</a>
                  )}
                </div>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={`/api/signals/screenshot?path=${encodeURIComponent(r.screenshot_weekly)}`}
                  alt={`${r.ticker} weekly chart`} className="w-full rounded border border-gray-100" />
              </div>
            )}
          </div>
        </div>
      )}

      {/* Technical Snapshot */}
      <div className="bg-white border border-gray-200 rounded-lg p-5">
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
          Technical Snapshot
        </h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm mb-3">
          <div>
            <div className="text-gray-500 text-xs mb-0.5">RSI(14)</div>
            <div className="font-medium">{fmt(r.rsi_14)}</div>
          </div>
          <div>
            <div className="text-gray-500 text-xs mb-0.5">MACD</div>
            <div className="font-medium text-xs">{r.macd_signal?.replace(/_/g, " ") ?? "—"}</div>
          </div>
          <div>
            <div className="text-gray-500 text-xs mb-0.5">EMA Alignment</div>
            <div className="font-medium text-xs">{r.ema_alignment?.replace(/_/g, " ") ?? "—"}</div>
          </div>
          <div>
            <div className="text-gray-500 text-xs mb-0.5">HH/HL</div>
            <div className="font-medium text-xs">{r.hh_hl_state?.replace(/_/g, " ") ?? "—"}</div>
          </div>
        </div>
        {r.pattern_label && (
          <div className="text-xs text-gray-700 bg-gray-50 rounded px-3 py-2">{r.pattern_label}</div>
        )}
      </div>

      {/* Performance */}
      <div className="bg-white border border-gray-200 rounded-lg p-5">
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Performance</h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <PerfCell label="1 Month" value={r.perf_1m} vs={r.perf_vs_nifty_1m} />
          <PerfCell label="3 Month" value={r.perf_3m} />
          <PerfCell label="6 Month" value={r.perf_6m} />
          <PerfCell label="YTD" value={r.perf_ytd} vs={r.perf_vs_nifty_ytd} />
        </div>
      </div>

      {/* Narrative */}
      {r.narrative && (
        <div className="bg-white border border-gray-200 rounded-lg p-5">
          <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Narrative</h2>
          <p className="text-sm text-gray-700 leading-relaxed">{r.narrative}</p>
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-3">
        {r.chart_daily_url && (
          <a href={r.chart_daily_url} target="_blank" rel="noopener noreferrer"
            className="text-sm px-4 py-2 rounded-lg border border-teal-300 text-teal-700 hover:bg-teal-50 transition-colors">
            Open in TradingView ↗
          </a>
        )}
      </div>
    </div>
  );
}
