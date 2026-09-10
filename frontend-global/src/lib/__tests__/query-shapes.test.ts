// src/lib/__tests__/query-shapes.test.ts — the guards for two defects that reached production
// in hand-written SQL, neither of which tsc, eslint or any database-free test can see.
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

// The second defect this file guards, found the same way: /themes went out reading
// `SELECT value FROM atlas_global.atlas_thresholds WHERE key = …`. The columns are
// `threshold_key` and `threshold_value` — India's shape, which this table copies verbatim so
// `load_thresholds` and the admin panel work unchanged on both boards. The page failed honestly
// ("column \"value\" does not exist") rather than crashing, which is the design working, but the
// FM saw an error where a list of themes should have been. A guessed column name in a
// hand-written query is not caught by tsc, by eslint or by any test that does not touch a
// database, so it is caught here instead.
describe('a threshold is read by the column names the table actually has', () => {
  it('never reaches for `key` or `value` on atlas_thresholds', () => {
    const offenders: string[] = []
    for (const { file, text } of sources()) {
      // every statement that names the table, up to the next backtick that closes the template
      for (const m of text.matchAll(/atlas_global\.atlas_thresholds[\s\S]{0,400}?`/g)) {
        const stmt = m[0]
        if (/\bWHERE\b[\s\S]*?\bkey\s*(=|IN|LIKE)/i.test(stmt) && !/threshold_key/i.test(stmt)) {
          offenders.push(`${file}: filters atlas_thresholds on \`key\`, not \`threshold_key\``)
        }
        if (/SELECT\s+value\b/i.test(stmt)) {
          offenders.push(`${file}: selects \`value\` from atlas_thresholds, not \`threshold_value\``)
        }
      }
    }
    expect(offenders).toEqual([])
  })

  it('reads only ACTIVE rows — a retired threshold is not a threshold in force', () => {
    for (const { file, text } of sources()) {
      for (const m of text.matchAll(/atlas_global\.atlas_thresholds[\s\S]{0,400}?`/g)) {
        if (/\bWHERE\b/i.test(m[0])) expect(m[0], file).toMatch(/is_active/)
      }
    }
  })
})

describe('a double never reaches the browser as text', () => {
  // EVERY CALL SITE IS EXAMINED BY CONSTRUCTION: find the call, then read forward to the FIRST
  // cast that follows it and require that cast to be numeric. Whatever sits in between —
  // WITHIN GROUP, FILTER, arithmetic, a wrapping paren — cannot switch the check off.
  //
  // THAT MATTERS BECAUSE THIS GUARD ONCE WENT BLIND AND STAYED GREEN. It used to match the call,
  // an optional WITHIN GROUP and then the cast, as one rigid shape. Adding
  // `FILTER (WHERE in_universe)` between the two made it match NOTHING in themes.ts or
  // sectors.ts — nine percentile_cont calls, zero inspected, every test passing.
  function firstCastAfter(text: string, from: number): string | null {
    const cast = /::\s*(\w+)/.exec(text.slice(from, from + 400))
    return cast ? cast[1] : null
  }

  it('casts every double-precision aggregate through numeric before text', () => {
    const offenders: string[] = []
    let inspected = 0
    for (const { file, text } of sources()) {
      for (const agg of DOUBLE_AGGREGATES) {
        for (const m of text.matchAll(new RegExp(`${agg}\\s*\\(`, 'gi'))) {
          inspected++
          const cast = firstCastAfter(text, m.index + m[0].length)
          if (cast == null) offenders.push(`${file}: ${agg} with no cast at all`)
          else if (!/^numeric$/i.test(cast)) offenders.push(`${file}: ${agg} → ::${cast}`)
        }
      }
    }
    expect(offenders).toEqual([])
    // A guard that inspects nothing passes for the wrong reason. These queries do use these
    // aggregates; if this ever reaches zero the queries changed shape and the rule needs rewriting,
    // not deleting.
    expect(inspected).toBeGreaterThan(0)
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

// ── measured is not offered ───────────────────────────────────────────────────────────────────
//
// THE DEFECT THIS GUARDS, measured on the live board on 2026-09-10. score_etfs.py grades nearly
// every classified fund — the FM asked for that ("we should score all the funds… coverage close to
// 100%") — so 5,486 funds carried a composite while `universe_snapshot` admitted 1,749. The
// country, theme and sector surfaces ranked on the composite alone, and inherited every fund the
// FM's own rules exclude:
//
//   • Semiconductors was headed by SMHD, MicroSectors -3x SHORT Semiconductor ETNs, top of the
//     theme on a composite of 93.75 earned by semiconductors FALLING.
//   • Artificial Intelligence was headed by COOL, which trades zero dollars a day, and carried a
//     Direxion AI BEAR 2X inside the ranking.
//   • Japan's ranking held 18 funds where 9 clear the rules, and "build a basket from the top 12"
//     seeded ProShares Ultra MSCI Japan, a 2x geared product, at rank 12.
//   • Ten themes' median composite moved by a point or more once the geared funds came out;
//     Quantum Computing moved 22.7 → 39.7.
//
// The stock half of sectors.ts never had the defect — it joins a `universe AS (… AND in_universe)`
// CTE — which is the pattern the ETF half now follows.
describe('a fund is ranked only among the funds the universe offers', () => {
  const source = (file: string) => sources().find((s) => s.file === file)?.text ?? ''

  // The load-bearing clause of each population cut, by the surface it serves. Deleting one is what
  // this test exists to notice.
  const CUTS: [string, string, string][] = [
    ['countries.ts', 'the market ranking', 'JOIN universe u ON u.instrument_id = g.instrument_id AND u.in_universe'],
    ['themes.ts', "the theme list's headline fund", 'FROM member m WHERE m.composite IS NOT NULL AND m.in_universe'],
    ['themes.ts', "one theme's ranking", 'FROM mine WHERE composite IS NOT NULL AND in_universe'],
    ['sectors.ts', 'the fund leaf of the sector tree', 'CASE WHEN s.in_universe THEN RANK() OVER ('],
    ['sectors.ts', 'the stock half, which always did this', 'AND in_universe'],
  ]

  it.each(CUTS)('%s: %s', (file, _what, clause) => {
    expect(source(file)).toContain(clause)
  })

  it('cuts each roll-up figure over the population that answers ITS question', () => {
    // TWO POPULATIONS, AND THIS TEST EXISTS BECAUSE ONE OF THEM ATE THE OTHER. The first version
    // of this rule put every figure on in_universe, which fixed the -3x short ETN heading
    // Semiconductors and then cut Health Care's median to four funds — eight of its twelve are
    // under the liquidity floor and NOT ONE is geared. The FM: "the overall score of that
    // healthcare sector is from the 12 ETFs that are there and for which we have the data,
    // right?" Right. A fund he cannot trade still tells you what health care did; a 2x fund does
    // not, because its return is a multiple of the thing by construction.
    //
    // So: DESCRIBE with `comparable` (everything graded but the geared and inverse), RECOMMEND
    // with `in_universe` (what he can actually buy).
    const rollup = source('sectors.ts')

    // in_universe: the buyable count, and both halves of the fund to own. Nothing else.
    expect(rollup.match(/FILTER \(WHERE in_universe\)/g) ?? []).toHaveLength(3)
    expect(rollup).toContain('FILTER (WHERE in_universe))[1]            AS top_symbol')
    expect(rollup).toContain('FILTER (WHERE in_universe))[1]            AS top_name')

    // comparable: the comparable count, the median, three relative strengths, the above-EMA
    // denominator — and the numerator, which reads as a conjunction rather than a bare FILTER.
    expect(rollup.match(/FILTER \(WHERE comparable\)/g) ?? []).toHaveLength(6)
    expect(rollup).toContain('count(above_ema_200) FILTER (WHERE comparable)')
    expect(rollup).toContain('above_ema_200 AND comparable')
  })

  it('has no ranking window it has not been told about', () => {
    // A pinned count, so a NEW ranking cannot be added without this test being read. If it fails,
    // add the ranking's own universe cut to CUTS above and then move the number.
    const counted = Object.fromEntries(
      ['countries.ts', 'themes.ts', 'sectors.ts'].map((f) => [
        f,
        (source(f).match(/(?:RANK|NTILE|ntile)\s*\(/g) ?? []).length,
      ]),
    )
    expect(counted).toEqual({ 'countries.ts': 4, 'themes.ts': 5, 'sectors.ts': 5 })
  })
})
