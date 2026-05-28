'use client'
import {
  LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from 'recharts'
import type { FundMetricHistoryRow } from '@/lib/queries/funds'

function formatDate(d: Date): string {
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
  return `${String(d.getDate()).padStart(2,'0')}-${months[d.getMonth()]}`
}

type MiniTooltipProps = { active?: boolean; payload?: { value: number }[]; label?: string; unit: string }
function MiniTooltip({ active, payload, label, unit }: MiniTooltipProps) {
  if (!active || !payload?.length) return null
  const val = payload[0]?.value
  return (
    <div className="bg-paper border border-paper-rule rounded-sm shadow-sm px-2 py-1 text-[10px] font-sans">
      <div className="text-ink-tertiary">{label}</div>
      <div className="font-mono font-semibold text-ink-primary">
        {typeof val === 'number' ? `${val.toFixed(1)}${unit}` : '—'}
      </div>
    </div>
  )
}

function MiniChart({
  data,
  dataKey,
  color,
  unit,
  referenceY,
}: {
  data: { date: string; [k: string]: number | string | null }[]
  dataKey: string
  color: string
  unit: string
  referenceY?: number
}) {
  if (data.length < 5) {
    return (
      <div className="flex items-center justify-center h-20 border border-paper-rule/40 rounded-sm">
        <p className="font-sans text-[10px] text-ink-tertiary">Insufficient history</p>
      </div>
    )
  }
  return (
    <div style={{ height: 80, minHeight: 80 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 2, right: 4, bottom: 2, left: 28 }}>
          <XAxis dataKey="date" tick={false} axisLine={false} tickLine={false} />
          <YAxis
            tick={{ fontSize: 8, fill: '#94a3b8' }}
            tickFormatter={v => `${v.toFixed(0)}${unit}`}
            width={26}
          />
          {referenceY !== undefined && (
            <ReferenceLine y={referenceY} stroke="#cbd5e1" strokeDasharray="3 2" strokeWidth={1} />
          )}
          <Tooltip content={<MiniTooltip unit={unit} />} />
          <Line
            type="monotone"
            dataKey={dataKey}
            stroke={color}
            strokeWidth={1.5}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export function FundRiskPanel({ metricHistory }: { metricHistory: FundMetricHistoryRow[] }) {
  const volData = metricHistory
    .filter(r => r.realized_vol_63 != null)
    .map(r => ({
      date: formatDate(new Date(r.nav_date)),
      vol: parseFloat(r.realized_vol_63!) * 100,
    }))

  const drawdownData = metricHistory
    .filter(r => r.drawdown_ratio_252 != null)
    .map(r => ({
      date: formatDate(new Date(r.nav_date)),
      drawdown: parseFloat(r.drawdown_ratio_252!) * 100,
    }))

  const retData = metricHistory
    .filter(r => r.ret_3m != null || r.ret_6m != null)
    .map(r => ({
      date: formatDate(new Date(r.nav_date)),
      ret_3m: r.ret_3m != null ? parseFloat(r.ret_3m) * 100 : null,
      ret_6m: r.ret_6m != null ? parseFloat(r.ret_6m) * 100 : null,
    }))

  // Latest values for display
  const latest = metricHistory[metricHistory.length - 1]
  const currentVol = latest?.realized_vol_63 != null ? (parseFloat(latest.realized_vol_63) * 100).toFixed(0) : null
  const currentDrawdown = latest?.drawdown_ratio_252 != null ? (parseFloat(latest.drawdown_ratio_252) * 100).toFixed(1) : null
  const current3m = latest?.ret_3m != null ? (parseFloat(latest.ret_3m) * 100).toFixed(1) : null
  const current12m = latest?.ret_12m != null ? (parseFloat(latest.ret_12m) * 100).toFixed(1) : null

  return (
    <div className="space-y-4">
      <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">
        Risk &amp; Return Metrics
      </div>

      {/* Current values row */}
      <div className="grid grid-cols-4 gap-3 text-center">
        {[
          { label: 'Vol 63D', value: currentVol != null ? `${currentVol}%` : '—', tone: 'neutral' as const },
          { label: 'Drawdown 1Y', value: currentDrawdown != null ? `${parseFloat(currentDrawdown) >= 0 ? '+' : ''}${currentDrawdown}%` : '—', tone: (currentDrawdown != null && parseFloat(currentDrawdown) < -10 ? 'neg' : 'neutral') as 'neg' | 'neutral' },
          { label: '3M Return', value: current3m != null ? `${parseFloat(current3m) >= 0 ? '+' : ''}${current3m}%` : '—', tone: (current3m != null ? (parseFloat(current3m) >= 0 ? 'pos' : 'neg') : 'neutral') as 'pos' | 'neg' | 'neutral' },
          { label: '12M Return', value: current12m != null ? `${parseFloat(current12m) >= 0 ? '+' : ''}${current12m}%` : '—', tone: (current12m != null ? (parseFloat(current12m) >= 0 ? 'pos' : 'neg') : 'neutral') as 'pos' | 'neg' | 'neutral' },
        ].map(({ label, value, tone }) => (
          <div key={label} className="flex flex-col gap-0.5">
            <div className="font-sans text-[9px] font-semibold text-ink-tertiary uppercase tracking-wider">{label}</div>
            <div className={`font-mono text-xs font-semibold tabular-nums ${
              tone === 'pos' ? 'text-signal-pos' : tone === 'neg' ? 'text-signal-neg' : 'text-ink-primary'
            }`}>
              {value}
            </div>
          </div>
        ))}
      </div>

      {/* Mini charts row */}
      <div className="grid grid-cols-3 gap-4">
        <div>
          <div className="font-sans text-[9px] text-ink-tertiary mb-1">Volatility (63D Ann.)</div>
          <MiniChart data={volData} dataKey="vol" color="#f59e0b" unit="%" referenceY={20} />
        </div>
        <div>
          <div className="font-sans text-[9px] text-ink-tertiary mb-1">Drawdown vs 1Y High (%)</div>
          <MiniChart data={drawdownData} dataKey="drawdown" color="#ef4444" unit="%" referenceY={-10} />
        </div>
        <div>
          <div className="font-sans text-[9px] text-ink-tertiary mb-1">3M &amp; 6M Trailing Return</div>
          {retData.length < 5 ? (
            <div className="flex items-center justify-center h-20 border border-paper-rule/40 rounded-sm">
              <p className="font-sans text-[10px] text-ink-tertiary">Insufficient history</p>
            </div>
          ) : (
            <div style={{ height: 80 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={retData} margin={{ top: 2, right: 4, bottom: 2, left: 28 }}>
                  <XAxis dataKey="date" tick={false} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 8, fill: '#94a3b8' }} tickFormatter={v => `${v.toFixed(0)}%`} width={26} />
                  <ReferenceLine y={0} stroke="#cbd5e1" strokeDasharray="3 2" strokeWidth={1} />
                  <Tooltip
                    contentStyle={{ fontSize: 10, fontFamily: 'var(--font-sans)' }}
                    formatter={(v, name) => {
                      const n = typeof v === 'number' ? v : Number(v)
                      return [`${n >= 0 ? '+' : ''}${n.toFixed(1)}%`, name === 'ret_3m' ? '3M' : '6M']
                    }}
                  />
                  <Line type="monotone" dataKey="ret_3m" stroke="#1D9E75" strokeWidth={1.5} dot={false} />
                  <Line type="monotone" dataKey="ret_6m" stroke="#0ea5e9" strokeWidth={1.5} dot={false} strokeDasharray="3 2" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
