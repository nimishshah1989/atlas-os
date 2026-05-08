type Props = {
  data: (number | null)[]
  width?: number
  height?: number
  color?: string
  className?: string
  /** Draw a horizontal reference line at this value */
  refLine?: number
}

export function Sparkline({
  data,
  width = 80,
  height = 24,
  color = 'currentColor',
  className = '',
  refLine,
}: Props) {
  const valid = data.filter((d): d is number => d !== null)
  if (valid.length < 2) return <span className={`inline-block w-[${width}px] h-[${height}px] ${className}`} />

  const min = Math.min(...valid)
  const max = Math.max(...valid)
  const range = max - min || 1

  const points = data
    .map((v, i) => {
      if (v === null) return null
      const x = (i / (data.length - 1)) * width
      const y = height - ((v - min) / range) * height
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .filter(Boolean)
    .join(' ')

  const refY = refLine !== undefined
    ? height - ((refLine - min) / range) * height
    : null

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={`inline-block ${className}`}
      aria-hidden
    >
      {refY !== null && (
        <line
          x1={0} y1={refY} x2={width} y2={refY}
          stroke="var(--color-paper-rule)"
          strokeWidth={0.5}
          strokeDasharray="2,2"
        />
      )}
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
