// allow-large: Atlas methodology explainer — single comprehensive page
// covering states + conviction + tiers + auto-optimization in one place.
// Designed to be read top-to-bottom by an FM or analyst who has never
// seen the system.
export const dynamic = 'force-dynamic'

import Link from 'next/link'
import { getActiveWeightSetsWithTrail } from '@/lib/queries/weight_performance'

const TIER_LABEL: Record<string, string> = {
  tier_1_megacap: 'Tier 1 · Mega-cap (top 50)',
  tier_2_largecap: 'Tier 2 · Large-cap (51–150)',
  tier_3_uppermid: 'Tier 3 · Upper mid-cap (151–300)',
  tier_4_lowermid: 'Tier 4 · Lower mid-cap (301–500)',
  tier_5_smallcap: 'Tier 5 · Small-cap (501–1000)',
}

function fmtIc(v: string | number | null): string {
  if (v === null || v === undefined) return '—'
  const n = typeof v === 'string' ? parseFloat(v) : v
  if (Number.isNaN(n)) return '—'
  const sign = n >= 0 ? '+' : ''
  return `${sign}${n.toFixed(4)}`
}

function tierConfidenceLabel(predictedIc: string | null): {
  label: string
  color: string
} {
  if (predictedIc === null) {
    return { label: 'Descriptive only', color: 'text-ink-tertiary' }
  }
  const n = Math.abs(parseFloat(predictedIc))
  if (n >= 0.05) return { label: '★ Industry-grade', color: 'text-teal' }
  return { label: 'Baseline', color: 'text-ink-secondary' }
}

export default async function MethodologyPage() {
  const activeSets = await getActiveWeightSetsWithTrail()

  return (
    <main className="max-w-3xl mx-auto px-6 sm:px-10 py-10 bg-white min-h-screen">
      <header className="mb-10">
        <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">
          Atlas · Methodology
        </div>
        <h1 className="font-serif text-3xl text-ink-primary mt-1">
          How Atlas Thinks
        </h1>
        <p className="font-serif text-base text-ink-secondary leading-relaxed mt-3 max-w-2xl">
          The end-to-end explanation of what every signal on this dashboard
          means, how it&apos;s computed, and how the system is supposed to
          adapt as the market changes. Read this once. Refer back when a
          number on another page surprises you.
        </p>
      </header>

      {/* ───────────────────────────────────────────────────────────────── */}
      <section id="states" className="mb-10">
        <h2 className="font-serif text-xl text-ink-primary mb-3 pb-2 border-b border-paper-rule">
          1 · Atlas States — the four lenses
        </h2>
        <p className="font-serif text-base text-ink-secondary leading-relaxed mb-3">
          Every stock and ETF is classified along four independent axes,
          recomputed nightly. These are <em>where</em> a stock is — not
          whether to buy it.
        </p>
        <ul className="space-y-2 ml-1 mb-4">
          <li className="font-sans text-sm text-ink-primary">
            <span className="font-semibold">RS State</span> ·{' '}
            <span className="font-sans text-ink-secondary">
              Leader, Strong, Emerging, Average, Weak, Laggard, Consolidating.
              Computed from 3-month relative strength vs the universe.
            </span>
          </li>
          <li className="font-sans text-sm text-ink-primary">
            <span className="font-semibold">Momentum State</span> ·{' '}
            <span className="font-sans text-ink-secondary">
              Accelerating, Improving, Flat, Deteriorating, Collapsing. Rate
              of change of the RS percentile.
            </span>
          </li>
          <li className="font-sans text-sm text-ink-primary">
            <span className="font-semibold">Risk State</span> ·{' '}
            <span className="font-sans text-ink-secondary">
              Low, Normal, Elevated, High, Below Trend. Realized volatility
              and drawdown vs benchmark.
            </span>
          </li>
          <li className="font-sans text-sm text-ink-primary">
            <span className="font-semibold">Volume State</span> ·{' '}
            <span className="font-sans text-ink-secondary">
              Accumulation, Steady-Buying, Neutral, Distribution, Heavy
              Distribution. Volume vs 20-day average with price-direction
              context.
            </span>
          </li>
        </ul>
        <div className="bg-paper-rule/30 border-l-2 border-teal pl-4 py-3 mb-3">
          <p className="font-serif text-sm text-ink-primary leading-relaxed">
            <strong>What states do not tell you:</strong> a stock can be in
            Leader RS state because of price action alone. They don&apos;t tell
            you whether all the underlying signals are pulling in the same
            direction, or how confident we should be about the read.
          </p>
        </div>
      </section>

      {/* ───────────────────────────────────────────────────────────────── */}
      <section id="conviction" className="mb-10">
        <h2 className="font-serif text-xl text-ink-primary mb-3 pb-2 border-b border-paper-rule">
          2 · Conviction Score — the overlay
        </h2>
        <p className="font-serif text-base text-ink-secondary leading-relaxed mb-3">
          A number from 0 to 100 attached to every stock in the top 1000 by
          liquidity. Conviction is a weighted blend of <em>eleven</em>{' '}
          underlying signals: 3-month RS percentile, 6-month and 12-1m
          returns, 30-week trend slope, distance from moving average,
          63-day volatility ratio and effort ratio, realized volatility,
          drawdown, EMA ratio, and ATR.
        </p>
        <p className="font-serif text-base text-ink-secondary leading-relaxed mb-3">
          The weights are not handpicked. They&apos;re calibrated by{' '}
          <strong>Information Coefficient (IC)</strong>, which measures the
          rank-correlation between each signal&apos;s value today and the
          actual realized return 21 trading days later. We split history
          into a 4-year training window and a 3-year out-of-sample holdout
          to make sure the weights generalize.
        </p>
        <div className="bg-paper-rule/30 border-l-2 border-teal pl-4 py-3 mb-3">
          <p className="font-serif text-sm text-ink-primary leading-relaxed mb-2">
            <strong>How to read IC:</strong>
          </p>
          <ul className="font-serif text-sm text-ink-secondary space-y-1 ml-3">
            <li>IC = 0.00 · the signal is no better than a coin flip</li>
            <li>
              IC = 0.05 · industry-grade; the signal is right about 52% of
              the time, which compounds to real money over hundreds of bets
            </li>
            <li>IC = 0.10 · excellent; right about 55% of the time</li>
            <li>
              IC negative · the signal predicts the <em>opposite</em>{' '}
              direction. Atlas inverts such signals (called &ldquo;flipped&rdquo;) so they
              contribute positively to conviction.
            </li>
          </ul>
        </div>
      </section>

      {/* ───────────────────────────────────────────────────────────────── */}
      <section id="tiers" className="mb-10">
        <h2 className="font-serif text-xl text-ink-primary mb-3 pb-2 border-b border-paper-rule">
          3 · Liquidity Tiers — why one weight set isn&apos;t enough
        </h2>
        <p className="font-serif text-base text-ink-secondary leading-relaxed mb-3">
          A mega-cap behaves differently from a small-cap. The signals that
          predict NIFTY 50 names don&apos;t predict 700th-by-ADV the same way.
          So Atlas splits the universe into five tiers by 20-day average
          daily traded value, and computes a <em>separate</em> weight set
          per tier.
        </p>
        <p className="font-serif text-base text-ink-secondary leading-relaxed mb-3">
          Each tier carries a confidence label:
        </p>
        <div className="overflow-x-auto border border-paper-rule rounded-sm mb-4">
          <table className="w-full font-sans text-xs">
            <thead>
              <tr className="border-b border-paper-rule bg-paper">
                <th className="text-left px-3 py-2 font-semibold text-[10px] uppercase tracking-wider text-ink-tertiary">
                  Tier
                </th>
                <th className="text-right px-3 py-2 font-semibold text-[10px] uppercase tracking-wider text-ink-tertiary">
                  Predicted IC
                </th>
                <th className="text-left px-3 py-2 font-semibold text-[10px] uppercase tracking-wider text-ink-tertiary">
                  Confidence
                </th>
              </tr>
            </thead>
            <tbody>
              {activeSets.length === 0 ? (
                <tr>
                  <td
                    colSpan={3}
                    className="px-3 py-3 text-center text-ink-tertiary"
                  >
                    No active weight sets yet.
                  </td>
                </tr>
              ) : (
                activeSets.map((s) => {
                  const conf = tierConfidenceLabel(s.predicted_ic)
                  return (
                    <tr key={s.tier} className="border-b border-paper-rule/40">
                      <td className="px-3 py-2 font-sans text-ink-primary">
                        {TIER_LABEL[s.tier] ?? s.tier}
                      </td>
                      <td className="px-3 py-2 text-right font-mono tabular-nums text-ink-primary">
                        {fmtIc(s.predicted_ic)}
                      </td>
                      <td
                        className={`px-3 py-2 font-sans font-semibold ${conf.color}`}
                      >
                        {conf.label}
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
        <div className="bg-paper-rule/30 border-l-2 border-teal pl-4 py-3 mb-3">
          <p className="font-serif text-sm text-ink-primary leading-relaxed">
            <strong>Why this matters for users:</strong> a conviction of 85
            in a T1 (industry-grade) tier carries far more weight than the
            same 85 in a T2 (baseline) tier. The UI shows tier-conditional
            badges on every conviction number so you don&apos;t mistake one
            for the other.
          </p>
        </div>
      </section>

      {/* ───────────────────────────────────────────────────────────────── */}
      <section id="loop" className="mb-10">
        <h2 className="font-serif text-xl text-ink-primary mb-3 pb-2 border-b border-paper-rule">
          4 · The auto-optimization loop
        </h2>
        <p className="font-serif text-base text-ink-secondary leading-relaxed mb-3">
          Markets change. The weights that worked last year may not work
          this year. So every night Atlas runs a four-step loop:
        </p>
        <ol className="space-y-3 mb-4 font-serif text-base text-ink-secondary leading-relaxed list-decimal ml-5">
          <li>
            <strong>Measure.</strong> For each tier and signal, recompute IC
            over the most recent 90 days. Write to{' '}
            <code className="font-mono text-xs bg-paper-rule/30 px-1">
              atlas_signal_ic_rolling
            </code>
            .
          </li>
          <li>
            <strong>Propose.</strong> If the new IC measurements differ
            materially from current weights (max element-wise difference ≥
            0.05), generate a candidate weight set that re-weights each
            signal in proportion to its recent |IC|. Push to{' '}
            <Link
              href="/admin/composite-proposals"
              className="text-teal hover:underline"
            >
              /admin/composite-proposals
            </Link>{' '}
            for review.
          </li>
          <li>
            <strong>Approve / smooth.</strong> A fund manager reviews the
            proposal and either approves, rejects, or snoozes it. On
            approval, the new active weight set is{' '}
            <strong>0.85 × current + 0.15 × proposed</strong> — a Bayesian
            blend. Why 15%? Empirically captures most of the predicted lift
            while keeping the live composite stable enough that intuition
            still holds.
          </li>
          <li>
            <strong>Monitor.</strong> Every night after approval, Atlas
            measures the <em>realized</em> IC of the new weight set against
            actual market moves. If realized stays below 50% of predicted
            for 60 consecutive days, the system{' '}
            <strong>auto-reverts</strong> to the previous weight set. See{' '}
            <Link
              href="/admin/weight-performance"
              className="text-teal hover:underline"
            >
              /admin/weight-performance
            </Link>
            .
          </li>
        </ol>
      </section>

      {/* ───────────────────────────────────────────────────────────────── */}
      <section id="hit-rate" className="mb-10">
        <h2 className="font-serif text-xl text-ink-primary mb-3 pb-2 border-b border-paper-rule">
          5 · Per-stock hit-rate
        </h2>
        <p className="font-serif text-base text-ink-secondary leading-relaxed mb-3">
          On every stock&apos;s deep-dive page you&apos;ll see a line like:
        </p>
        <div className="bg-paper-rule/20 border border-paper-rule px-4 py-3 mb-3 font-sans text-sm text-ink-secondary italic">
          Last 20 trading days:{' '}
          <span className="font-mono text-signal-pos">14/20</span>{' '}
          high-conviction days outperformed tier median (
          <span className="font-mono text-signal-pos">70%</span>).
        </div>
        <p className="font-serif text-base text-ink-secondary leading-relaxed mb-3">
          A &ldquo;high-conviction day&rdquo; is a day on which the stock&apos;s conviction
          was at or above the tier-median conviction. The hit-rate is the
          fraction of those days that produced a forward 21-day return
          exceeding the tier-median forward return. It answers: <em>when
          this stock has looked good by Atlas&apos;s lights, has it actually
          delivered?</em>
        </p>
      </section>

      {/* ───────────────────────────────────────────────────────────────── */}
      <section id="decisions" className="mb-10">
        <h2 className="font-serif text-xl text-ink-primary mb-3 pb-2 border-b border-paper-rule">
          6 · What FM action does
        </h2>
        <p className="font-serif text-base text-ink-secondary leading-relaxed mb-3">
          The system is designed so the FM has the final word at three
          decision points:
        </p>
        <ul className="space-y-3 mb-4 font-serif text-base text-ink-secondary leading-relaxed ml-3">
          <li>
            <strong>Approve a weight proposal.</strong> Blends the candidate
            in at 15%. Tomorrow&apos;s conviction scores will move slightly.
            Stage 4c then watches whether the new set actually delivers
            predicted IC.
          </li>
          <li>
            <strong>Reject a weight proposal.</strong> Marks it dead. The
            system will likely propose a different set the next night if
            the IC data still says weights should change.
          </li>
          <li>
            <strong>Snooze a weight proposal.</strong> Defers reconsideration
            until a chosen future date. Useful when you don&apos;t trust
            the recent data window (e.g. a one-off event).
          </li>
        </ul>
        <div className="bg-paper-rule/30 border-l-2 border-teal pl-4 py-3 mb-3">
          <p className="font-serif text-sm text-ink-primary leading-relaxed">
            <strong>Important:</strong> the FM never sets weights by hand.
            The system always proposes; the FM always approves, rejects, or
            snoozes. This keeps every weight change traceable in{' '}
            <code className="font-mono text-xs bg-paper-rule/30 px-1">
              atlas_weight_proposals
            </code>{' '}
            with reviewer, notes, and timestamp — the SEBI-audit trail.
          </p>
        </div>
      </section>

      {/* ───────────────────────────────────────────────────────────────── */}
      <section id="not" className="mb-10">
        <h2 className="font-serif text-xl text-ink-primary mb-3 pb-2 border-b border-paper-rule">
          7 · What this is NOT
        </h2>
        <ul className="space-y-2 font-serif text-base text-ink-secondary leading-relaxed ml-3">
          <li>
            <strong>Not investment advice.</strong> Atlas surfaces
            measurements and rankings. No buy/sell/recommend language
            appears anywhere user-facing, per SEBI guidance.
          </li>
          <li>
            <strong>Not a black box.</strong> Every conviction score has a
            JSONB breakdown showing which signals drove the number, what
            percentile each signal sat at, and how much each one
            contributed.
          </li>
          <li>
            <strong>Not opinionated about timing.</strong> Conviction is a
            relative measurement against the current universe and tier. It
            does not say &ldquo;buy now&rdquo;; it says &ldquo;this name is
            stronger than that name by these signals today.&rdquo;
          </li>
        </ul>
      </section>

      {/* ───────────────────────────────────────────────────────────────── */}
      <section id="links" className="mt-12 border-t border-paper-rule pt-6">
        <h3 className="font-sans text-[11px] text-ink-tertiary uppercase tracking-wider mb-3">
          Where to look next
        </h3>
        <ul className="space-y-1.5 font-sans text-sm">
          <li>
            <Link
              href="/intelligence"
              className="text-teal hover:underline"
            >
              /intelligence
            </Link>
            <span className="text-ink-tertiary">
              {' '}
              · morning dashboard — regime, sectors, top conviction, daily
              brief
            </span>
          </li>
          <li>
            <Link href="/stocks" className="text-teal hover:underline">
              /stocks
            </Link>
            <span className="text-ink-tertiary">
              {' '}
              · screener with the Conviction column visible by default
            </span>
          </li>
          <li>
            <Link
              href="/admin/composite-proposals"
              className="text-teal hover:underline"
            >
              /admin/composite-proposals
            </Link>
            <span className="text-ink-tertiary">
              {' '}
              · pending FM approvals (admin only)
            </span>
          </li>
          <li>
            <Link
              href="/admin/weight-performance"
              className="text-teal hover:underline"
            >
              /admin/weight-performance
            </Link>
            <span className="text-ink-tertiary">
              {' '}
              · realized-vs-predicted IC per active weight set
            </span>
          </li>
        </ul>
      </section>

      <footer className="mt-12 pt-6 border-t border-paper-rule font-sans text-[11px] text-ink-tertiary">
        Last methodology revision: 2026-05-12. See
        <code className="font-mono mx-1">docs/phase2/00-master-plan.html</code>
        and
        <code className="font-mono mx-1">
          docs/phase2/plans/2026-05-12-sp04-stage*.md
        </code>
        for full sub-project history.
      </footer>
    </main>
  )
}
