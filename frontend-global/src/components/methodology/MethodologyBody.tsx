// src/components/methodology/MethodologyBody.tsx — what a score on this board means, as a page a
// fund manager can OPEN rather than read end to end.
//
// The glass-box rule (CONTEXT.md): a reader must get from a number on a card to the rule that
// produced it without asking anyone. The previous version of this file was seven paragraphs, all
// true and read once. The FM: "Methodology can become less verbose and more interactive." So the
// path is now a walk: the nightly in four steps, then every lens as a section that opens onto its
// own sub-scores, then the ladder, then the rules — each collapsed to its one-line claim until
// asked. Nothing that was true has been removed; it has been put where someone goes when they ask.
//
// NO NUMBER IS WRITTEN HERE. Weights and cut points come from the page above, which reads them
// from atlas_global.atlas_thresholds; the sub-score names come from src/lib/scores.ts, which
// mirrors the journal's own columns. A hardcoded weight would be a second source of truth and wrong
// the first time the FM re-tuned one.
import type { ReactNode } from 'react'
import { ETF_LENS_SUBS, subLabel } from '@/lib/scores'
import type { LensWeight, TierRule } from '@/lib/queries/methodology'

function Fold({ title, claim, children, open = false }: { title: string; claim: string; children: ReactNode; open?: boolean }) {
  return (
    <details className="fold panel" open={open}>
      <summary className="fold-summary">
        <span className="text-body font-medium text-ink">{title}</span>
        <span className="text-meta text-ink-2">{claim}</span>
      </summary>
      <div className="fold-body text-body text-ink-2">{children}</div>
    </details>
  )
}

/** What each sub-score is, in the producer's terms (atlas/global_market/scoring/etf_lenses.py). */
const SUB_NOTE: Record<string, string> = {
  tech_trend: 'India’s own trend scorer, unmodified: price against the 21-, 50- and 200-day averages, their alignment, the slope, RSI and the week’s return.',
  tech_rs_spy: 'Relative strength against SPY over 3, 6 and 12 months in the relative form (1+r)/(1+r_SPY) − 1, laddered into points.',
  tech_rs_peer: 'Where the fund’s 6-month return sits inside its own peer group, as a percentile laddered into points.',
  tech_structure: 'The averages themselves in order — 21 over 50 over 200 — India’s structure scorer.',
  risk_vol: 'Annualised volatility, as a quintile within the asset group; 1 = calmest.',
  risk_mdd: 'Worst 12-month drawdown, as a quintile within the asset group; 1 = shallowest.',
  risk_downside: 'Downside deviation over 63 sessions, as a quintile within the asset group.',
  risk_beta: 'Beta against SPY, banded at absolute cut points — 1.0 means “moves with the index” whatever the group.',
  cost_expense: 'The expense ratio’s percentile within the asset group. Waits on an issuer feed; absent today.',
  cost_adv: 'Median traded value over 60 sessions, banded in dollars — “can I get in and out” has absolute answers.',
  cost_aum: 'Fund assets from the N-PORT filing, banded.',
  cost_concentration: 'Top-ten holdings weight from the latest holdings snapshot; lower is the good end.',
  flow_so_21d: 'Change in shares outstanding over 21 sessions — creations and redemptions. No producer yet.',
  flow_so_63d: 'The same over 63 sessions. No producer yet.',
  quality_composite: 'The holdings-weighted mean of the held stocks’ own composites. No producer yet.',
  quality_leaders: 'The share of the fund held in top-decile stocks. No producer yet.',
}

const STATE_WORD: Record<LensWeight['state'], { word: string; tone: string }> = {
  computed: { word: 'computed, blended', tone: 'text-pos' },
  partial: { word: 'partly computed, blended', tone: 'text-pos' },
  overlay: { word: 'computed, an overlay at weight 0', tone: 'text-warn' },
  absent: { word: 'no producer yet — absent, not zero', tone: 'text-ink-3' },
}

export function MethodologyBody({ lenses, tiers }: { lenses: LensWeight[]; tiers: TierRule[] }) {
  const blended = lenses.filter((l) => l.has_producer)
  return (
    <div className="mt-6 space-y-2">
      <Fold title="The nightly, in four steps" claim="bars → technicals → lenses → a rank inside a peer group" open>
        <ol className="list-decimal space-y-1.5 pl-5">
          <li>
            <b>Bars.</b> The session’s prices arrive on three bases — what traded, split-adjusted, total-return —
            and are checked against FRED’s S&P index before anything divides by them.
          </li>
          <li>
            <b>Technicals.</b> Every number behind every column is computed once, for every active fund and index
            member: averages and their flags, returns, relative strength, volatility, drawdown, traded value.
          </li>
          <li>
            <b>Lenses.</b> Each lens reads its inputs and scores 0–100 as the mean of its present sub-scores.
            A sub-score with no data is left out of the mean; a lens with no data at all is absent. The composite is
            the weighted mean of the lenses that are present and carry weight, renormalised over them.
          </li>
          <li>
            <b>Rank.</b> Deciles are cut on read within the peer group — asset class × strategy for a fund, size
            cohort for a company — never stored. Leader means top decile of that group. Then the gates run; a red
            one keeps the previous session on the board.
          </li>
        </ol>
        <p className="mt-3">
          Today the composite is built from <b>{blended.length} of {lenses.length} lenses</b>:{' '}
          {blended.map((l) => l.label).join(' and ')}. The board prints that count beside every score, so a
          two-lens composite cannot be read as a five-lens one.
        </p>
      </Fold>

      {lenses.map((l) => {
        const subs = ETF_LENS_SUBS[l.lens] ?? []
        const s = STATE_WORD[l.state]
        return (
          <Fold key={l.lens} title={`${l.label} lens`} claim={`${l.reads} · ${s.word}`}>
            <p className={s.tone}>{l.note}</p>
            <p className="mt-2 text-meta text-ink-3">
              Weight in the blend: <span className="num text-ink">{(Number(l.weight) * 100).toFixed(0)}%</span> —
              a row in the thresholds table, read on each run.
            </p>
            <p className="mt-3 text-meta font-semibold uppercase tracking-[0.08em] text-ink-3">Sub-scores</p>
            <ul className="mt-1 space-y-1">
              {subs.map((k) => (
                <li key={k} className="flex flex-wrap gap-x-2">
                  <span className="text-ink">{subLabel(k)}</span>
                  <code className="text-meta">{k}</code>
                  <span className="basis-full text-table text-ink-2">{SUB_NOTE[k] ?? ''}</span>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-meta text-ink-3">
              Lens = mean of the present sub-scores × 4 (each sub-score is 0–25). Every cut point a sub-score
              uses is a thresholds row.
            </p>
          </Fold>
        )
      })}

      <Fold title="Conviction tiers" claim="agreement between independent reads, not a higher score">
        <p>
          The tier asks two things of a composite: how high it is, and how many independent lenses agreed. The
          top tiers need several lenses to be present, so while only {blended.length} carry weight no fund can reach
          them however strong it looks. That is the methodology working — conviction is agreement, and there
          are {blended.length} opinions in the room today.
        </p>
        <table className="tbl mt-3 max-w-[48ch]">
          <thead>
            <tr>
              <th>Tier</th>
              <th className="r">Composite at least</th>
              <th className="r">Lenses at least</th>
            </tr>
          </thead>
          <tbody>
            {tiers.map((t) => (
              <tr key={t.tier}>
                <td className="text-ink">{t.tier}</td>
                <td className="num r">{t.minScore ?? '—'}</td>
                <td className="num r">{t.minLenses ?? '—'}</td>
              </tr>
            ))}
            <tr>
              <td className="text-ink-3">Below threshold</td>
              <td className="num r text-ink-3">—</td>
              <td className="num r text-ink-3">—</td>
            </tr>
          </tbody>
        </table>
      </Fold>

      <Fold title="Peer groups and deciles" claim="nothing is ranked against everything">
        <p>
          A gold-miners fund, a Treasury fund and an S&amp;P tracker have nothing to say to one another, so every
          fund is ranked inside its peer group: its asset class crossed with what it does, both read from its own
          registered name by an ordered set of rules, with the rule that fired and the words it matched recorded.
          A name no rule reads is marked <b>Unclassified</b> and shown as such — not filed somewhere plausible.
        </p>
        <p className="mt-2">
          A group too small to support a distribution falls back to its asset class, and the row records which
          grouping was used. Within a group the composites are cut into ten equal bands on read; <b>Decile 10</b>{' '}
          is the strongest tenth of that group and <b>Leader</b> means exactly that.
        </p>
      </Fold>

      <Fold title="Relative strength" claim="+8% means it beat the index by eight points, not that it rose eight">
        <p>
          Every figure labelled RS is (1&nbsp;+&nbsp;r) ÷ (1&nbsp;+&nbsp;r<sub>SPY</sub>) − 1 over the window:
          what is left after the index is taken out. The tint saturates at ±20 points, and every tinted cell
          prints its value, so the board reads in greyscale.
        </p>
      </Fold>

      <Fold title="What is excluded, and why" claim="geared and inverse funds are measured and never offered">
        <p>
          Geared and inverse funds are classified, scored and ranked only against each other; the universe rules
          never offer them, because a two-times daily fund topping a ranking is the kind of wrong nobody notices
          until after they have bought it. Funds below the liquidity floor are out for a plainer reason: a fund
          you cannot get out of is not an option. Nothing excluded is hidden — every list can show the full set
          with each row’s reason.
        </p>
      </Fold>

      <Fold title="These weights are seeds" claim="a lens keeps its weight only once its signal is measured on real history">
        <p>
          The current weights are starting points, not conclusions. A lens earns its weight by being measured
          against forward returns on real history; one that fails the floor goes to zero and becomes an overlay
          until it earns one. Risk is held that way today by the FM’s rule: volatility, drawdown, downside
          deviation and beta sit beside the score rather than inside it, because folding them in makes a dull
          fund outrank a strong one. Until that measurement exists the board says what it measures and how, and
          does not claim the ordering has been validated.
        </p>
      </Fold>
    </div>
  )
}
