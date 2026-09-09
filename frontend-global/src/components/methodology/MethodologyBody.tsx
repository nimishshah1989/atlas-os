// src/components/methodology/MethodologyBody.tsx — what a score on this board means, in words.
//
// The glass-box rule (CONTEXT.md): a reader must be able to get from a number on a card to the
// rule that produced it without asking anyone. This is that path written down — and it is
// deliberately prose, not a table of magic numbers, because the numbers live in
// atlas_global.atlas_thresholds and are read from there by the page above this one. A hardcoded
// weight here would become a second source of truth and would be wrong the first time the FM
// re-tunes anything.
//
// It also states, plainly and near the top, what is NOT yet measured. A board that shows a
// composite built from one lens while implying five is worse than one that shows nothing.
import type { ReactNode } from 'react'

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-8">
      <h2 className="font-serif text-h2 text-ink">{title}</h2>
      <div className="mt-2 max-w-[70ch] text-body text-ink-2">{children}</div>
    </section>
  )
}

export function MethodologyBody({ activeLenses, totalLenses }: { activeLenses: string[]; totalLenses: number }) {
  return (
    <>
      <Section title="What a score is">
        <p>
          Every instrument is read through several independent <b>lenses</b>. Each lens scores 0 to
          100 from its own sub-scores, and the <b>composite</b> is the weighted mean of the lenses
          that could actually be computed for that instrument, renormalised over them. A lens with
          no data does not score zero — it is absent, and the missing weight is redistributed. A
          fund is not bad at something nobody measured.
        </p>
        <p className="mt-3">
          Every weight, band and cut point behind those numbers is a row in the thresholds table,
          not a constant in code. Change a row and the next run scores differently, with no
          deployment. That is why this page describes the <i>rules</i> and the page above it shows
          the <i>values</i>: there is one source of truth and it is the database.
        </p>
      </Section>

      <Section title="What is measured today, and what is not">
        <p>
          {activeLenses.length} of {totalLenses} lenses have a producer:{' '}
          <b>{activeLenses.join(', ')}</b>. Every score on this board carries its own{' '}
          <b>n of {totalLenses} lenses</b> label, so a one-lens composite can never be mistaken for
          a complete one.
        </p>
        <p className="mt-3">
          The rest are not estimated, approximated or filled in. They are absent until their data
          is ingested, and the score says so. The sources are identified and free — company
          financials, corporate events, insider filings and fund holdings from public filings — but
          data that has not been ingested is not data, and a number invented to fill a column is
          the one failure this board is built to prevent.
        </p>
      </Section>

      <Section title="Why nothing is ranked against everything">
        <p>
          A gold-miners fund, a Treasury fund and an S&amp;P tracker have nothing to say to one
          another. Ranking them in one table produces an ordering that describes no decision anyone
          would make. So every fund is <b>ranked inside its peer group</b>: its asset class crossed
          with what it actually does — a sector fund against sector funds, a country fund against
          country funds.
        </p>
        <p className="mt-3">
          A group too small to support a distribution cannot support a percentile either: ten funds
          cannot have deciles. Those funds fall back to their broader asset class, and each row
          records which grouping was used, so &ldquo;fourth of thirty-four sector funds&rdquo; is
          never confused with &ldquo;fourth of two hundred equity funds&rdquo;.
        </p>
      </Section>

      <Section title="Deciles, tiers and what Leader means">
        <p>
          Within a peer group the composites are cut into ten equal bands. <b>Decile 10</b> is the
          strongest tenth of that group and <b>Leader</b> means exactly that — top decile among its
          own peers, never top decile of everything. Deciles are computed when the page is read,
          never stored: a rank is a statement about a population on a date, and a stored rank goes
          stale the moment a score moves.
        </p>
        <p className="mt-3">
          The <b>conviction tier</b> is a second, stricter reading: it asks not only how high the
          composite is but how many independent lenses agree. The top tiers require several lenses
          to be present, so while only {activeLenses.length} of {totalLenses} has a producer, no
          instrument can reach them however strong it looks. That is the methodology working, not a
          defect — conviction means agreement, and there is only one opinion in the room today.
        </p>
      </Section>

      <Section title="Relative strength is relative">
        <p>
          Every figure labelled RS compares an instrument to the S&amp;P 500 in the form
          (1&nbsp;+&nbsp;r) ÷ (1&nbsp;+&nbsp;r<sub>SPY</sub>) − 1. <b>+8% means it beat the index by
          eight percent</b> over that window — not that it rose eight percent. A reader who takes
          the second meaning has learned something false, which is why the form is stated wherever
          the number appears.
        </p>
      </Section>

      <Section title="What is excluded, and why">
        <p>
          Geared and inverse funds are classified and listed but never scored. They answer a
          different question from &ldquo;what should I hold&rdquo;, and a two-times daily fund
          topping a ranking is the kind of wrong nobody notices until after they have bought it.
          Funds below the liquidity floor are excluded for a plainer reason: a fund you cannot get
          out of is not an instrument you should be shown as an option.
        </p>
        <p className="mt-3">
          Nothing excluded is hidden. Every list can show the full set with the reason each row is
          out, because &ldquo;we chose not to rank this&rdquo; and &ldquo;this does not exist&rdquo;
          are different statements.
        </p>
      </Section>

      <Section title="How the fund groups are decided">
        <p>
          A fund&rsquo;s peer group comes from its own registered name, read by an ordered set of
          rules. An issuer states what a fund does in its title and is not free to misdescribe it,
          so the title is evidence rather than a guess — and every classification records the rule
          that fired and the words it matched, so any grouping can be checked.
        </p>
        <p className="mt-3">
          Where no rule reads a name, the fund is marked <b>Unclassified</b> and shown as such. It
          is not quietly filed under a broad bucket: one mis-filed fund corrupts the peer group it
          lands in, and the whole point of the group is that its members are comparable.
        </p>
      </Section>

      <Section title="These weights are not yet proven">
        <p>
          The current weights are <b>seeds</b> — reasonable starting points, not conclusions. A lens
          keeps its weight only once its signal has been measured against forward returns on real
          history; anything that fails to clear the floor goes to zero weight and becomes an
          overlay until it earns one. Until that work is done this board states what it measures and
          how, and does not claim the ordering has been validated.
        </p>
        <p className="mt-3">
          Risk is computed on that basis today: volatility, drawdown, downside deviation and beta
          are shown beside the score rather than inside it. Folding them into a composite makes a
          dull instrument outrank a strong one, which is not what &ldquo;what should I buy&rdquo;
          asks.
        </p>
      </Section>
    </>
  )
}
