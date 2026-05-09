'use client'
import { useRouter, useSearchParams, usePathname } from 'next/navigation'
import { type TimeRange } from '@/lib/time-range'

export type { TimeRange }

type Props = {
  value: TimeRange
  options?: TimeRange[]
  paramName?: string
}

export function TimeRangeToggle({
  value,
  options = ['1W', '1M', '3M', '6M'],
  paramName = 'range',
}: Props) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  function select(range: TimeRange) {
    const params = new URLSearchParams(searchParams.toString())
    params.set(paramName, range)
    router.push(`${pathname}?${params.toString()}`)
  }

  return (
    <div className="inline-flex border border-paper-rule rounded-[2px] overflow-hidden" role="group" aria-label="Time range">
      {options.map((opt) => (
        <button
          key={opt}
          onClick={() => select(opt)}
          className={`px-2 py-1 text-xs font-sans transition-colors
            ${opt === value
              ? 'bg-accent text-paper'
              : 'text-ink-secondary hover:text-ink-primary hover:bg-paper-rule/20'
            }`}
          aria-pressed={opt === value}
        >
          {opt}
        </button>
      ))}
    </div>
  )
}

export { rangeToDays } from '@/lib/time-range'
