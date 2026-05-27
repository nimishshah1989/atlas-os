// frontend/src/components/v6/PerWindowChart.tsx
//
// Small ~120×60 sparkline of OOS performance across rolling windows.
// Discrete bar chart — windows are independent. Bars colored by sign.
// Pure SVG (no Recharts) to keep table-row weight low.

type WindowSample = {
  label: string
  value: number
  passed?: boolean
}

type Props = {
  windows: WindowSample[]
  width?: number
  height?: number
  className?: string
}

export function PerWindowChart({
  windows,
  width = 120,
  height = 60,
  className = '',
}: Props) {
  if (windows.length === 0) {
    return (
      <span
        className={`inline-block ${className}`}
        style={{ width, height }}
      />
    )
  }

  const values = windows.map(w => w.value)
  const max = Math.max(...values, 0)
  const min = Math.min(...values, 0)
  const range = max - min || 1
  const zeroY = height - ((0 - min) / range) * height

  const barWidth = (width / windows.length) * 0.7
  const gap = (width / windows.length) * 0.3

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={`inline-block ${className}`}
      aria-hidden
    >
      {/* zero line */}
      <line
        x1={0} y1={zeroY} x2={width} y2={zeroY}
        stroke="var(--color-paper-rule)"
        strokeWidth={0.5}
        strokeDasharray="2,2"
      />
      {windows.map((w, i) => {
        const x = i * (barWidth + gap) + gap / 2
        const y = w.value >= 0
          ? zeroY - ((w.value / range) * height * (w.value / Math.max(w.value, max || 1)))
          : zeroY
        const h = Math.abs((w.value / range) * height)
        const yTop = w.value >= 0 ? zeroY - h : zeroY
        const color = w.passed === false
          ? 'var(--color-ink-tertiary)'
          : w.value >= 0
            ? 'var(--color-signal-pos)'
            : 'var(--color-signal-neg)'
        return (
          <g key={`${w.label}-${i}`}>
            <rect
              x={x}
              y={yTop}
              width={barWidth}
              height={Math.max(h, 1)}
              fill={color}
              opacity={w.passed === false ? 0.4 : 0.9}
            >
              <title>{`${w.label}: ${(w.value * 100).toFixed(2)}%`}</title>
            </rect>
          </g>
        )
      })}
    </svg>
  )
}
