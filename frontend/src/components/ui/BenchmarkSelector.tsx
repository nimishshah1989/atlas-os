'use client'
import { useRouter, useSearchParams, usePathname } from 'next/navigation'

export type BenchmarkCode =
  | 'NIFTY50'
  | 'NIFTY500'
  | 'NIFTY100'
  | 'MIDCAP150'
  | 'SMALLCAP250'
  | 'GOLD'
  | 'MSCIWORLD'
  | 'SP500'

export const BENCHMARK_LABELS: Record<string, string> = {
  NIFTY50:          'Nifty 50',
  NIFTY500:         'Nifty 500',
  NIFTY100:         'Nifty 100',
  MIDCAP150:        'Midcap 150',
  SMALLCAP250:      'Smallcap 250',
  GOLD:             'Gold',
  MSCIWORLD:        'MSCI World',
  SP500:            'S&P 500',
  MICROCAP_CUSTOM:  'Microcap (Atlas)',
}

type Props = {
  value: string
  availableCodes: string[]
  paramName?: string
}

export function BenchmarkSelector({ value, availableCodes, paramName = 'benchmark' }: Props) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  function select(code: string) {
    const params = new URLSearchParams(searchParams.toString())
    params.set(paramName, code)
    router.push(`${pathname}?${params.toString()}`)
  }

  return (
    <select
      value={value}
      onChange={(e) => select(e.target.value)}
      className="text-xs font-sans border border-paper-rule rounded-[2px] px-2 py-1 bg-paper text-ink-secondary focus:outline-none focus:border-accent"
      aria-label="Benchmark"
    >
      {availableCodes.map((code) => (
        <option key={code} value={code}>
          vs. {BENCHMARK_LABELS[code] ?? code}
        </option>
      ))}
    </select>
  )
}
