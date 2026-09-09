// src/components/entity/ClassificationCard.tsx — why this fund sits in the peer group it sits in.
//
// classify_etfs.py decides every field below from the fund's REGISTERED NAME and writes the rule
// that fired and the words it matched into `evidence`. Both are printed here, because a peer group
// a reader cannot audit is a peer group a reader cannot trust — and the peer group is what makes a
// decile mean anything.
//
// `confidence` is deliberately absent: a regex either matched or it did not, and a deterministic
// match has no probability to report. A name no rule reads gets status `review` and is shown as
// Unclassified — a work queue, not a silent default bucket.
import { Chip } from '@/components/ui/Chip'
import { Section } from '@/components/ui/Section'
import { formatIsoDate } from '@/lib/format'
import type { Classification } from '@/lib/queries/scores'
import { peerGroupLabel } from '@/lib/scores'
import { FactList, type Fact } from './FactList'

type Evidence = { strategy_rule?: unknown; matched_text?: unknown; leverage_rule?: unknown; name?: unknown }

const text = (v: unknown): string | null => (typeof v === 'string' && v !== '' ? v : null)

const SOURCE: Record<string, string> = { rules: 'name rules (classify_etfs.py)' }

export function ClassificationCard({ c }: { c: Classification | null }) {
  if (!c) {
    return (
      <Section title="Classification" note="not classified yet">
        <p className="text-body text-ink-2">
          No row in <code>etf_classification</code> for this fund.{' '}
          <code>scripts/global_market/classify_etfs.py</code> writes one per active ETF from its
          registered name; until it runs, this fund has no peer group and cannot be ranked.
        </p>
      </Section>
    )
  }

  const e = (c.evidence ?? {}) as Evidence
  const rule = text(e.strategy_rule)
  const matched = text(e.matched_text)
  const source = `${SOURCE[c.classified_by] ?? c.classified_by}, from ${formatIsoDate(c.valid_from)}`
  const unread = c.status === 'review' || c.strategy == null

  const facts: Fact[] = [
    {
      label: 'Peer group',
      value: <Chip>{peerGroupLabel(c.strategy ? `${c.asset_class ?? 'unclassified'}:${c.strategy}` : null)}</Chip>,
      source: 'asset class × strategy',
    },
    {
      label: 'Rule that fired',
      value: unread ? 'none — no rule read this name' : (rule ?? 'not recorded'),
      source,
    },
    {
      label: 'Text it matched',
      value: matched ? <span className="text-ink">“{matched}”</span> : 'nothing matched',
      source: text(e.name) ?? 'the fund’s registered name',
    },
  ]
  const flags = [
    c.leveraged ? 'leveraged' : null,
    c.inverse ? 'inverse' : null,
    c.hedged ? 'currency-hedged' : null,
  ].filter(Boolean) as string[]
  facts.push({
    label: 'Structure',
    value: flags.length ? flags.join(', ') : 'plain — not geared, not inverse, not hedged',
    source: text(e.leverage_rule) ?? source,
  })
  if (c.country_codes && c.country_codes.length > 0) {
    facts.push({ label: 'Country', value: c.country_codes.join(', '), source })
  }

  return (
    <Section title="Classification" note={unread ? 'unclassified — in the review queue' : 'from the fund’s own name'}>
      <FactList facts={facts} />
      {unread && (
        <p className="mt-3 max-w-[72ch] text-body text-ink-2">
          About a fifth of listed fund names match no strategy rule. They are shown as Unclassified
          rather than filed under a default bucket, which would corrupt the peer group they landed
          in. The LLM classification layer that reads these names needs the FM’s labelled eval set
          before it is allowed to write a field.
        </p>
      )}
    </Section>
  )
}
