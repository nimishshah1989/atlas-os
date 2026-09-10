// src/lib/__tests__/countryPicks.test.ts — the answer layer, on the market that provoked it.
//
// EVERY ROW BELOW IS REAL, read back from the live board on 2026-09-10 for the 2026-09-09 session
// (https://global.jslwealth.in/countries/jp and the /etfs payload): the twenty US-listed funds
// classified as Japan, with the composite score_etfs.py wrote, the 60-session median $ volume
// compute_technicals.py wrote, and the universe verdict build_universe_snapshot.py wrote. Nine of
// the twenty clear the FM's rules. Ranks are the query's RANK() over exactly those nine by
// composite descending — the rule applied to real numbers, not a number invented here (rule #0).
//
// Expense ratio is null on all twenty because atlas_global.etf_meta.expense_ratio is empty for
// every one of the 5,659 funds on the board. That is a real gap, recorded here rather than papered
// over with a plausible-looking fee, and it is why "cheapest" is not one of the decisions below.
import { describe, expect, it } from 'vitest'
import { countryPicks, countryRest } from '@/lib/countryPicks'
import type { CountryFund } from '@/lib/countries'

type Row = {
  symbol: string
  name: string
  rank: number | null
  composite: string | null
  adv: string | null
  aum: string | null
  hedged?: true
  leveraged?: true
  inverse?: true
  why?: string
  rep?: true
}

const JAPAN: Row[] = [
  { symbol: 'EWJ',  name: 'iShares MSCI Japan Index Fund',            rank: 1, composite: '93.32', adv: '397078819.5900', aum: '21298173248.84', rep: true },
  { symbol: 'BBJP', name: 'JPMorgan BetaBuilders Japan ETF',          rank: 2, composite: '87.59', adv: '79006506.6150',  aum: '16591498654.14' },
  { symbol: 'EWJV', name: 'iShares MSCI Japan Value ETF',             rank: 3, composite: '83.74', adv: '4637334.6364',   aum: '715252615.21' },
  { symbol: 'FLJP', name: 'Franklin FTSE Japan ETF',                  rank: 4, composite: '83.50', adv: '29925621.2750',  aum: null },
  { symbol: 'DXJ',  name: 'WisdomTree Japan Hedged Equity Fund',      rank: 5, composite: '77.81', adv: '40493559.8350',  aum: '7079662663.35', hedged: true },
  { symbol: 'DFJ',  name: 'WisdomTree Japan SmallCap Fund',           rank: 6, composite: '75.98', adv: '2496833.4300',   aum: '374014030.50' },
  { symbol: 'OPPJ', name: 'WisdomTree Japan Opportunities Fund',      rank: 7, composite: '74.64', adv: '2234461.6100',   aum: '280235361.58' },
  { symbol: 'SCJ',  name: 'iShares MSCI Japan Sm Cap',                rank: 8, composite: '72.61', adv: '3661260.5146',   aum: '245150956.69' },
  { symbol: 'DBJP', name: 'Xtrackers MSCI Japan Hedged Equity ETF',   rank: 9, composite: '70.54', adv: '1707892.4185',   aum: '659822735.31', hedged: true },
  { symbol: 'FJP',  name: 'First Trust Japan AlphaDEX Fund',          rank: null, composite: '72.61', adv: '662328.8335', aum: '253827253.65', why: 'below_floor' },
  { symbol: 'FLJH', name: 'Franklin FTSE Japan Hedged ETF',           rank: null, composite: '68.11', adv: '933325.8220', aum: '171802864.09', why: 'below_floor', hedged: true },
  { symbol: 'EZJ',  name: 'ProShares Ultra MSCI Japan',               rank: null, composite: '68.00', adv: '97551.7453',  aum: null, why: 'leveraged', leveraged: true },
  { symbol: 'GSJY', name: 'Goldman Sachs ActiveBeta Japan Equity ETF', rank: null, composite: '63.86', adv: '178221.3935', aum: null, why: 'below_floor' },
  { symbol: 'JPAN', name: 'Matthews Japan Active ETF',                rank: null, composite: '61.32', adv: '44635.9241',  aum: null, why: 'below_floor' },
  { symbol: 'MJSC', name: 'MUFG Japan Small Cap Active ETF',          rank: null, composite: '47.32', adv: '6984.0215',   aum: null, why: 'below_floor' },
  { symbol: 'NBJP', name: 'Neuberger Japan Equity ETF',               rank: null, composite: '47.00', adv: '119219.5472', aum: null, why: 'below_floor' },
  { symbol: 'JAPN', name: 'Horizon Kinetics Japan Owner Operator ETF', rank: null, composite: '46.05', adv: '74237.6058', aum: null, why: 'below_floor' },
  { symbol: 'EWV',  name: 'ProShares UltraShort MSCI Japan',          rank: null, composite: '7.55',  adv: '113078.9448', aum: null, why: 'leveraged', leveraged: true, inverse: true },
  // The last two carry no composite at all: too new for the scorer to have measured anything.
  { symbol: 'JPND', name: 'MicroSectors -3x Short Japan ETNs',         rank: null, composite: null, adv: null, aum: null, why: 'too_few_observations', leveraged: true, inverse: true },
  { symbol: 'JPNU', name: 'MicroSectors 3x Long Japan ETNs',           rank: null, composite: null, adv: null, aum: null, why: 'too_few_observations', leveraged: true },
]

/** The query's row shape over those facts. Order is the query's: ranked first, strongest down,
 *  then everything the universe does not offer, most traded first. */
const funds: CountryFund[] = JAPAN.map((r) => ({
  instrument_id: `id:${r.symbol}`,
  symbol: r.symbol,
  name: r.name,
  rank: r.rank,
  composite: r.composite,
  decile: null,
  adv_usd_60d_median: r.adv,
  expense_ratio: null,
  aum_usd: r.aum,
  leveraged: r.leveraged ?? false,
  inverse: r.inverse ?? false,
  hedged: r.hedged ?? false,
  in_universe: r.rank != null,
  exclusion_reason: r.why ?? null,
  is_representative: r.rep ?? false,
  rs: { '1w': null, '1m': null, '3m': null, '6m': null, '12m': null, '24m': null },
}))

const of = (fs: CountryFund[]) => countryPicks(fs).map((p) => [p.kind, p.fund.symbol])

describe('twenty Japan funds, and the two decisions inside them', () => {
  it('answers with EWJ and DXJ, not with a ranking', () => {
    // The FM: "If you have 18, 20 ETFs under Japan, which one will I even buy?" EWJ is the core
    // and DXJ is the currency call. Everything else is one of those two taken worse.
    expect(of(funds)).toEqual([
      ['core', 'EWJ'],
      ['hedged', 'DXJ'],
    ])
  })

  it('does not card EWJ twice for topping the ranking it already represents', () => {
    // EWJ is both the representative and rank 1. Two cards for one fund is not two decisions.
    expect(of(funds).filter(([, symbol]) => symbol === 'EWJ')).toHaveLength(1)
  })

  it('cards the top of the ranking when it is NOT the core', () => {
    // The representative is chosen on liquidity and rank 1 on score, so they come apart — and when
    // they do, "the one everyone trades" and "the one scoring highest" are two real answers.
    const advLed = funds.map((f) => (f.symbol === 'BBJP' ? { ...f, is_representative: true } : { ...f, is_representative: false }))
    expect(of(advLed)).toEqual([
      ['core', 'BBJP'],
      ['strongest', 'EWJ'],
      ['hedged', 'DXJ'],
    ])
  })

  it('never offers a hedge the FM cannot buy', () => {
    // FLJH is currency-hedged and trades $933k a day, under the floor. With DXJ and DBJP removed
    // it is the only hedged fund left, and the right number of hedge cards is then zero.
    const thin = funds.filter((f) => f.symbol !== 'DXJ' && f.symbol !== 'DBJP')
    expect(of(thin).map(([kind]) => kind)).not.toContain('hedged')
  })

  it('has nothing to say about a market with no funds', () => {
    expect(countryPicks([])).toEqual([])
    expect(countryRest([], [])).toBeNull()
  })
})

describe('what the other eighteen funds are, in one sentence', () => {
  it('counts them by whether they can be bought, and if not, which rule says no', () => {
    // Seven more ranked (BBJP, EWJV, FLJP, DFJ, OPPJ, SCJ, DBJP), then the excluded: seven below
    // the floor (FJP, FLJH, GSJY, JPAN, MJSC, NBJP, JAPN), two geared (EZJ, EWV) and two ETNs the
    // scorer has not measured yet (JPND, JPNU).
    expect(countryRest(funds, countryPicks(funds))).toBe(
      '18 other funds cover this market: 7 more you can buy, ranked below, ' +
        '7 below the liquidity floor, 2 geared, 2 too little history.',
    )
  })

  it('says nothing when every fund covering the market is already a card', () => {
    const two = funds.filter((f) => f.symbol === 'EWJ' || f.symbol === 'DXJ')
    expect(countryRest(two, countryPicks(two))).toBeNull()
  })
})
