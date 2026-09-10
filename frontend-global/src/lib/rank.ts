// src/lib/rank.ts — the board's three ranked populations, reduced to one shape for the pulse.
//
// The FM: "none of these pages should be independent." So the pulse does not re-query anything: it
// maps the SAME cached results /sectors, /themes and /countries render, into one row type. A
// summary that computed its own numbers would be a fourth opinion, and the first thing anyone
// would find is the day it disagreed with the page it summarises.
//
// STRONGEST FIRST, AND UNSCORED IS NOT LAST — IT IS ABSENT. A group nobody has scored has no
// place in a ranking of scores (rule #0); the strip prints the count it kept so nothing goes
// missing silently.
import type { CountryRow } from '@/lib/countries'
import type { RankItem } from '@/components/pulse/RankStrip'
import type { SectorNode } from '@/lib/sectors'
import type { ThemeRow } from '@/lib/themes'

const byScore = (a: RankItem, b: RankItem) => Number(b.score) - Number(a.score)

const plural = (n: number, one: string) => `${n} ${n === 1 ? one : `${one}s`}`

/** GICS sectors → the strip. The href opens that sector's themes in place on /sectors. */
export function sectorItems(rows: readonly SectorNode[]): RankItem[] {
  return rows
    .filter((r) => r.composite != null)
    .map((r) => ({
      id: r.id,
      name: r.name,
      href: `/sectors/${encodeURIComponent(r.id)}`,
      score: r.composite,
      rs: r.rs['3m'],
      meta: plural(r.n_children, 'theme'),
    }))
    .sort(byScore)
}

/** Themes → the strip. This is the FM's headline question — which bets are working — so the meta
 *  column is how many funds express it, which is what says whether the answer is investable. */
export function themeItems(rows: readonly ThemeRow[]): RankItem[] {
  return rows
    .filter((r) => r.median_composite != null)
    .map((r) => ({
      id: r.id,
      name: r.name,
      href: `/themes/${encodeURIComponent(r.id)}`,
      score: r.median_composite,
      rs: r.rs['3m'],
      meta: plural(r.n_scored, 'fund'),
    }))
    .sort(byScore)
}

/** Markets → the strip. A country's score is its REPRESENTATIVE fund's, not a median — that is the
 *  rule build_country_views.py writes and countries.ts reads, and the meta column names the fund
 *  so the difference is on the screen rather than in a document. */
export function countryItems(rows: readonly CountryRow[]): RankItem[] {
  return rows
    .filter((r) => r.composite != null)
    .map((r) => ({
      id: r.iso2,
      name: r.name,
      href: `/countries/${encodeURIComponent(r.iso2.toLowerCase())}`,
      score: r.composite,
      rs: r.rs['3m'],
      meta: r.symbol,
    }))
    .sort(byScore)
}
