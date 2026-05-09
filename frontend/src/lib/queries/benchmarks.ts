// src/lib/queries/benchmarks.ts
import 'server-only'
import sql from '@/lib/db'

export type BenchmarkRow = {
  benchmark_code: string
  date: Date
  close: string
  ret_1d: string | null
  ret_1w: string | null
  ret_1m: string | null
  ret_3m: string | null
  ret_6m: string | null
  ret_12m: string | null
}

export type BenchmarkMeta = {
  benchmark_code: string
  benchmark_name: string
  benchmark_type: string
}

export async function getBenchmarkHistory(
  code: string,
  days: number
): Promise<BenchmarkRow[]> {
  return sql<BenchmarkRow[]>`
    SELECT benchmark_code, date, close, ret_1d, ret_1w, ret_1m, ret_3m, ret_6m, ret_12m
    FROM atlas.atlas_benchmark_returns_cache
    WHERE benchmark_code = ${code}
      AND date >= NOW() - (${days} || ' days')::INTERVAL
    ORDER BY date ASC
  `
}

export async function getAllBenchmarks(): Promise<BenchmarkMeta[]> {
  return sql<BenchmarkMeta[]>`
    SELECT benchmark_code, benchmark_name, benchmark_type
    FROM atlas.atlas_benchmark_master
    WHERE is_active = TRUE
    ORDER BY benchmark_type, benchmark_code
  `
}
