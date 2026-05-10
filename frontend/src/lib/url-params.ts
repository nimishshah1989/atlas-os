export const VALID_PERIODS = ['1M', '3M', '6M', '1Y'] as const
export type Period = typeof VALID_PERIODS[number]
export const DEFAULT_PERIOD: Period = '3M'

export const VALID_BENCHMARKS = [
  'NIFTY50', 'NIFTY500', 'NIFTY100', 'MIDCAP150', 'SMALLCAP250', 'GOLD', 'MSCIWORLD', 'SP500',
] as const
export type Benchmark = typeof VALID_BENCHMARKS[number]
export const DEFAULT_BENCHMARK: Benchmark = 'NIFTY500'

export function validatePeriod(raw: string | undefined | null): Period {
  if (raw && (VALID_PERIODS as readonly string[]).includes(raw)) return raw as Period
  return DEFAULT_PERIOD
}

export function validateBenchmark(raw: string | undefined | null): Benchmark {
  if (raw && (VALID_BENCHMARKS as readonly string[]).includes(raw)) return raw as Benchmark
  return DEFAULT_BENCHMARK
}
