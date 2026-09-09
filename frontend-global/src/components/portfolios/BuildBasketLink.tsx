// src/components/portfolios/BuildBasketLink.tsx — the way in to the builder from a ranked list.
//
// The FM's product, in his words: "we want to create centered funds, like funds around, let's just
// say, gold and silver miners. We want to create funds around water and food security." /themes
// and /countries rank the funds; this is the one click from that ranking to a basket of them.
//
// WHAT IT CARRIES AND WHAT IT DOES NOT. It carries symbols and a name in the URL and nothing else.
// The weights are equal — a starting point, not a recommendation, because equal weight says "I
// have not decided yet" and that is the honest state of a list one click old. Every symbol, every
// weight and the Σ=1 rule are checked again by the server action against instrument_master and the
// FM's own thresholds, so this link cannot write anything: it can only open a form.
//
// ONLY RANKED FUNDS GO IN. A fund with no rank was never scored — it is geared, inverse, hedged or
// below the liquidity floor — and putting one into a basket seed would propose buying something
// the board deliberately refused to grade.
import Link from 'next/link'

/** The most a seeded basket opens with. Beyond this the FM is not choosing, they are indexing —
 *  and the builder's own position cap would refuse the weights anyway. */
export const SEED_LIMIT = 12

export function BuildBasketLink({
  symbols,
  name,
  label,
}: {
  /** In rank order, strongest first. Unranked names must already have been filtered out. */
  symbols: string[]
  /** What the basket opens called — the theme's or the market's own name. */
  name: string
  label: string
}) {
  const picked = symbols.slice(0, SEED_LIMIT)
  if (picked.length === 0) return null
  const href = `/portfolios/new?symbols=${encodeURIComponent(picked.join(','))}&name=${encodeURIComponent(name)}`
  return (
    <Link href={href} className="text-meta text-ink-2 no-underline hover:text-ink">
      {label} <span aria-hidden="true">→</span>
    </Link>
  )
}
