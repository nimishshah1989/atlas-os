// SP04 Stage 4c — small sparkline showing 30-day realized IC vs predicted.
// Red threshold line at 0.5×predicted highlights revert territory.
'use client'

import {
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  XAxis,
  YAxis,
  Tooltip,
} from 'recharts'
import { useThemeTokens } from '@/components/v4/ui/useThemeTokens'

type TrailRow = {
  as_of_date: string | Date
  realized_ic: string | null
  ic_ratio: string | null
}

type Props = {
  trail: TrailRow[]
  predictedIc: string | null
}

export function RealizedICSparkline({ trail, predictedIc }: Props) {
  const t = useThemeTokens()
  if (trail.length === 0) {
    return (
      <span className="font-sans text-[10px] text-txt-3">
        no realized-IC data yet
      </span>
    )
  }
  const predicted = predictedIc ? parseFloat(predictedIc) : null
  const threshold = predicted !== null ? predicted * 0.5 : null

  // Theme-aware line/axis colours (fall back to neutral defaults off-theme).
  const revertLine = t?.neg ?? '#C84B3B'
  const predLine = t?.tick ?? '#7A7A7A'
  const realizedLine = t?.pos ?? '#1D9E75'
  const tipBg = t?.surface ?? '#FFFFFF'
  const tipBorder = t?.rule ?? '#E5E2DC'
  const tipText = t?.txt1 ?? '#131922'

  const data = trail.map((t) => ({
    date: typeof t.as_of_date === 'string' ? t.as_of_date.slice(5) : '',
    realized: t.realized_ic ? parseFloat(t.realized_ic) : null,
    ratio: t.ic_ratio ? parseFloat(t.ic_ratio) : null,
  }))

  return (
    <div className="h-12 w-48">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
          <XAxis dataKey="date" hide />
          <YAxis hide domain={['auto', 'auto']} />
          {threshold !== null && (
            <ReferenceLine
              y={threshold}
              stroke={revertLine}
              strokeDasharray="2 2"
              strokeWidth={1}
            />
          )}
          {predicted !== null && (
            <ReferenceLine
              y={predicted}
              stroke={predLine}
              strokeDasharray="2 2"
              strokeWidth={1}
            />
          )}
          <Tooltip
            contentStyle={{
              fontSize: '11px',
              padding: '4px 8px',
              backgroundColor: tipBg,
              border: `1px solid ${tipBorder}`,
              borderRadius: '9px',
              color: tipText,
            }}
          />
          <Line
            type="monotone"
            dataKey="realized"
            stroke={realizedLine}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
