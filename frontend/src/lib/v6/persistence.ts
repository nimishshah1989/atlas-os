// frontend/src/lib/v6/persistence.ts
//
// Shared persistence hooks for v6 UI controls.
// Pattern: URL-param-primary + localStorage-seed.
//   - URL `?tenure=3m` overrides localStorage.
//   - Click writes BOTH URL param AND localStorage.
//   - localStorage key format: `v6.<type>.<pageKey>`
// Suspense-safe: hooks use `useSearchParams` inside client components;
// consumer pages must wrap in <Suspense> (handled in Phase A.9).

'use client'

import { useCallback } from 'react'
import { useRouter, useSearchParams, usePathname } from 'next/navigation'

// ── Types ────────────────────────────────────────────────────────────────────

export type TenureValue = '1m' | '3m' | '6m' | '12m'
export type BenchmarkValue = 'nifty50' | 'nifty500' | 'gold'

const TENURE_VALUES: readonly TenureValue[] = ['1m', '3m', '6m', '12m']
const BENCHMARK_VALUES: readonly BenchmarkValue[] = ['nifty50', 'nifty500', 'gold']

const DEFAULT_TENURE: TenureValue = '6m'
const DEFAULT_BENCHMARK: BenchmarkValue = 'nifty500'

// ── Helpers ──────────────────────────────────────────────────────────────────

function readLS(key: string): string | null {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

function writeLS(key: string, value: string): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(key, value)
  } catch {
    // Storage may be disabled (private browsing, quota). Silently ignore.
  }
}

function isTenureValue(v: string | null): v is TenureValue {
  return TENURE_VALUES.includes(v as TenureValue)
}

function isBenchmarkValue(v: string | null): v is BenchmarkValue {
  return BENCHMARK_VALUES.includes(v as BenchmarkValue)
}

// ── useTenurePreference ───────────────────────────────────────────────────────

/**
 * Returns the active tenure selection and a setter for the given page.
 *
 * Resolution order:
 *   1. URL `?tenure=<value>` — highest priority
 *   2. localStorage `v6.tenure.<pageKey>` — seeds when URL param absent
 *   3. Default `6m`
 *
 * Setting a value writes both the URL query param and localStorage.
 */
export function useTenurePreference(pageKey: string): {
  tenure: TenureValue
  setTenure: (value: TenureValue) => void
} {
  const searchParams = useSearchParams()
  const router = useRouter()
  const pathname = usePathname()

  const lsKey = `v6.tenure.${pageKey}`

  // Derive current tenure (URL > LS > default)
  const rawUrl = searchParams.get('tenure')
  const rawLS = readLS(lsKey)

  let tenure: TenureValue
  if (isTenureValue(rawUrl)) {
    tenure = rawUrl
  } else if (isTenureValue(rawLS)) {
    tenure = rawLS
  } else {
    tenure = DEFAULT_TENURE
  }

  const setTenure = useCallback(
    (value: TenureValue) => {
      writeLS(lsKey, value)
      const params = new URLSearchParams(searchParams.toString())
      params.set('tenure', value)
      router.replace(`${pathname}?${params.toString()}`, { scroll: false })
    },
    [lsKey, pathname, router, searchParams],
  )

  return { tenure, setTenure }
}

// ── useBenchmarkPreference ────────────────────────────────────────────────────

/**
 * Returns the active benchmark selection and a setter for the given page.
 * A.2 will implement gold availability check and hide the gold pill when absent.
 *
 * Resolution order:
 *   1. URL `?benchmark=<value>`
 *   2. localStorage `v6.benchmark.<pageKey>`
 *   3. Default `nifty500`
 */
export function useBenchmarkPreference(pageKey: string): {
  benchmark: BenchmarkValue
  setBenchmark: (value: BenchmarkValue) => void
} {
  const searchParams = useSearchParams()
  const router = useRouter()
  const pathname = usePathname()

  const lsKey = `v6.benchmark.${pageKey}`

  const rawUrl = searchParams.get('benchmark')
  const rawLS = readLS(lsKey)

  let benchmark: BenchmarkValue
  if (isBenchmarkValue(rawUrl)) {
    benchmark = rawUrl
  } else if (isBenchmarkValue(rawLS)) {
    benchmark = rawLS
  } else {
    benchmark = DEFAULT_BENCHMARK
  }

  const setBenchmark = useCallback(
    (value: BenchmarkValue) => {
      writeLS(lsKey, value)
      const params = new URLSearchParams(searchParams.toString())
      params.set('benchmark', value)
      router.replace(`${pathname}?${params.toString()}`, { scroll: false })
    },
    [lsKey, pathname, router, searchParams],
  )

  return { benchmark, setBenchmark }
}
