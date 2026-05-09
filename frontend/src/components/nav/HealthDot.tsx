// src/components/nav/HealthDot.tsx
import { getHeaderStatus } from '@/lib/queries/health'

export async function HealthDot() {
  let level: 'green' | 'yellow' | 'red' = 'yellow'
  let message = 'Unknown'
  try {
    const s = await getHeaderStatus()
    level = s.level
    message = s.message
  } catch {
    // DB unreachable — show yellow
  }

  const colors: Record<typeof level, string> = {
    green:  'bg-signal-pos',
    yellow: 'bg-signal-warn',
    red:    'bg-signal-neg',
  }

  return (
    <span
      title={message}
      className={`inline-block w-2 h-2 rounded-full ${colors[level]}`}
    />
  )
}
