// src/lib/__tests__/sql-double-to-text.test.ts — the guard for the defect that took /pulse down.
//
// WHAT HAPPENED. `percentile_cont(0.5) WITHIN GROUP (ORDER BY t.ret_3m)::text` looks harmless.
// percentile_cont returns DOUBLE PRECISION, and postgres renders a double in SCIENTIFIC NOTATION
// once the magnitude is small enough — interpolating a median between two returns that nearly
// cancel gives something like "-1.4210854715202004e-14". The board's formatters refuse a string
// like that on purpose (`DECIMAL_RE` in src/lib/format.ts: a NUMERIC must never have passed
// through a double), so the render threw, and because the throw was in the COMPONENT rather than
// the query it sailed past the page's `attempt()` wrapper and became a 500. /pulse answered 500
// in public for as long as it existed.
//
// Casting to numeric first fixes it: numeric always renders plain decimal. This test is the guard
// that catches the next one, because nothing else will — the shape only fails on real data, and
// only on some of it.
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { formatPct } from '@/lib/format'

const QUERIES = join(process.cwd(), 'src', 'lib', 'queries')

/** Every aggregate postgres answers in `double precision` rather than `numeric`. */
const DOUBLE_AGGREGATES = ['percentile_cont', 'percentile_disc', 'corr', 'regr_slope', 'regr_intercept']

function sources(): { file: string; text: string }[] {
  return readdirSync(QUERIES)
    .filter((f) => f.endsWith('.ts'))
    .map((f) => ({ file: f, text: readFileSync(join(QUERIES, f), 'utf8') }))
}

describe('a double never reaches the browser as text', () => {
  it('casts every double-precision aggregate through numeric before text', () => {
    const offenders: string[] = []
    for (const { file, text } of sources()) {
      for (const agg of DOUBLE_AGGREGATES) {
        // the call, whatever is between its parentheses and any WITHIN GROUP clause, then the
        // cast that immediately follows it
        const re = new RegExp(`${agg}\\s*\\([^)]*\\)(\\s*WITHIN GROUP\\s*\\([^)]*\\))?\\s*::\\s*(\\w+)`, 'gi')
        for (const m of text.matchAll(re)) {
          if (!/^numeric$/i.test(m[2])) offenders.push(`${file}: ${agg} → ::${m[2]}`)
        }
      }
    }
    expect(offenders).toEqual([])
  })

  it('is worth guarding because the formatter REFUSES the string a double produces', () => {
    // Not a bug in the formatter — the refusal is what makes a double-shaped number impossible to
    // print as a decimal by accident. The fix belongs at the query, and this pins the contract so
    // nobody "fixes" it by loosening DECIMAL_RE instead.
    expect(() => formatPct('-1.4210854715202004e-14')).toThrow(TypeError)
    expect(() => formatPct('5e-17')).toThrow(TypeError)
    // The same value written as a decimal formats fine — and prints 0.0%, not −0.0%, because a
    // minus sign in front of a rounded zero claims a direction the number does not have.
    expect(formatPct('-0.00000000000001421085')).toBe('0.0%')
  })
})
