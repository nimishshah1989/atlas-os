// src/lib/countryPicks.ts — the answer layer above the country's fund table.
//
// The FM, on the country page: "If you have 18, 20 ETFs under Japan, which one will I even buy?"
// Japan really does list twenty. The table below ranks them correctly and still does not answer
// him, because a ranking says which is strongest and he is asking which is THE ONE — and the
// honest answer is that there are only two or three real decisions here and the other seventeen
// funds are the same decision taken worse.
//
// So this names the decisions instead of the funds: the core, the top of the ranking when it is
// not the core, and the currency-hedged alternative, which is a different call rather than a
// better version of the same one. Everything else is counted, not listed — the table below is
// one scroll away and nothing is hidden.
//
// NO NEW NUMBER DECIDES ANYTHING HERE. The core is `is_representative`, chosen by
// build_country_views.py; the top of the ranking is rank 1, cut by the query; hedged is the
// classifier's flag. This module picks between rows, it does not grade them.
import type { CountryFund } from './countries'
import { whyNotOffered } from './universe'

export type PickKind = 'core' | 'strongest' | 'hedged'

export type Pick = {
  kind: PickKind
  /** The decision this fund IS, in the fewest words that stay true. */
  label: string
  /** Why it is the answer to that decision — the rule, not a number the card already shows. */
  note: string
  fund: CountryFund
}

const NOTE: Record<PickKind, string> = {
  core: 'The most-traded fund covering this market that is not geared, inverse or currency-hedged. This page’s score, chart and relative strength are its.',
  strongest: 'Scores highest of every fund covering this market — above the core, which is chosen on liquidity rather than on score.',
  hedged: 'The same market with the currency hedged back to dollars. A separate call, not a cheaper core: it wins when the dollar rises against the local currency and loses when it falls.',
}

const LABEL: Record<PickKind, string> = {
  core: 'The core',
  strongest: 'Top of the ranking',
  hedged: 'Currency-hedged',
}

/** The two or three funds that are actually a decision, strongest claim first.
 *
 *  `funds` arrives in the query's order — ranked first, strongest down, then everything the
 *  universe does not offer, by liquidity — so `find` gives rank 1 for the ranking and the
 *  best-ranked hedged fund for the hedge. The order is the query's and is never re-derived here. */
export function countryPicks(funds: CountryFund[]): Pick[] {
  const picks: Pick[] = []
  const claim = (kind: PickKind, fund: CountryFund | undefined) => {
    if (!fund || picks.some((p) => p.fund.instrument_id === fund.instrument_id)) return
    picks.push({ kind, label: LABEL[kind], note: NOTE[kind], fund })
  }
  claim('core', funds.find((f) => f.is_representative))
  claim('strongest', funds.find((f) => f.rank != null))
  // A CARD IS AN OFFER, so the hedge has to clear the same universe rules as the ranking. A
  // currency-hedged fund below the FM's floor is not the answer to "what if I want the hedge" —
  // it is a fund he cannot buy, wearing a label that says he can.
  claim('hedged', funds.find((f) => f.hedged === true && f.in_universe))
  return picks
}

/** What the funds NOT carded are, so the reader knows the table holds no fourth decision.
 *  Null when every fund covering the market is already a pick.
 *
 *  Counted on the two axes that decide whether a fund is an alternative at all: whether the
 *  universe offers it, and if not, which of the FM's rules keeps it out. Japan lists twenty funds
 *  and nine of them clear the rules — a sentence he can read in one breath, where the table takes
 *  twenty rows to say it. */
export function countryRest(funds: CountryFund[], picks: Pick[]): string | null {
  const carded = new Set(picks.map((p) => p.fund.instrument_id))
  const rest = funds.filter((f) => !carded.has(f.instrument_id))
  if (rest.length === 0) return null

  const ranked = rest.filter((f) => f.rank != null).length
  const reasons = new Map<string, number>()
  for (const f of rest) {
    const why = f.rank == null ? whyNotOffered(f.exclusion_reason) : null
    if (why) reasons.set(why, (reasons.get(why) ?? 0) + 1)
  }
  const parts = [
    ranked > 0 ? `${ranked} more you can buy, ranked below` : null,
    ...[...reasons.entries()].sort((a, b) => b[1] - a[1]).map(([why, n]) => `${n} ${why}`),
  ].filter((p): p is string => p !== null)

  const head = `${rest.length} other ${rest.length === 1 ? 'fund covers' : 'funds cover'} this market`
  return parts.length ? `${head}: ${parts.join(', ')}.` : `${head}.`
}
