// FundDetailV4 — the v4 mutual-fund detail page. Lens-first, native foundation_staging.
// A fund is a holdings-weighted roll-up of the stock atom (D26/D27): the HEADLINE is
// LEADERSHIP-BREADTH (% of holdings weight that are top-decile leaders in ≥2 conviction lenses),
// NOT a composite. The fund-specific differentiator is ACTIVE-MOVEMENT — the month-over-month
// holdings delta (is the manager adding leaders?). The 6-lens vector + look-through are a
// TRANSPARENCY view of what's held and how it scores — descriptive, NOT an outperformance predictor.
import Link from 'next/link'
import { notFound } from 'next/navigation'

import { getFundLensDetail, type FundLensDetail, type FundHolding, type FundMove } from '@/lib/queries/v6/fund_lens'
import { Panel } from '@/components/v4/ui/Panel'
import { StatCard, type Tone } from '@/components/v4/ui/StatCard'
import { decileColor } from '@/components/v4/ui/decile'
import { ScoreDerivationTree } from '@/components/v6/shared/ScoreDerivationTree'
import { holdingsToDerivation } from '@/components/v4/adapters/holdingsToDerivation'
import { getConstituentDrivers } from '@/lib/queries/v6/drivers'
import { TermInfo } from '@/components/v6/shared/TermInfo'

const HOLDING_CAP = 50

// ── colour helpers (shared idioms with the stocks / ETF pages) ────────────
// per-stock deciles take the shared perceptual ramp via inline style (decileColor);
// null falls back to the tertiary text token.
const decileStyle = (d: number | null) => ({ color: d == null ? 'var(--color-txt-3)' : decileColor(d) })

const leadText = (lead: number) =>
  lead >= 2 ? 'text-sig-pos' : lead === 1 ? 'text-sig-warn' : 'text-txt-3'

const pctText = (v: number | null) =>
  v == null ? 'text-txt-3' : v >= 0 ? 'text-sig-pos' : 'text-sig-neg'

// rs_3m is a FRACTION (0.05 = +5%) → ×100 for display.
const fmtRs = (v: number | null) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}%`)
// weight is a PERCENT (6.17 = 6.17%) → render as-is, NO ×100.
const fmtWeight = (w: number | null) => (w == null ? '—' : `${w.toFixed(2)}%`)

// ── active-movement: one column of moves (added / exited) ─────────────────
function MoveList({ moves }: { moves: FundMove[] }) {
  if (moves.length === 0) return <p className="font-sans text-[13px] italic text-txt-3">—</p>
  return (
    <div className="space-y-1">
      {moves.map(m => (
        <div key={m.symbol} className="flex items-center justify-between gap-3 border-b border-edge-hair py-1">
          <a href={`/stocks/${m.symbol}`} className="truncate font-num text-[12px] font-semibold tabular-nums text-txt-1 no-underline hover:text-brand hover:underline">
            {m.symbol}
          </a>
          <span className="min-w-0 flex-1 truncate font-sans text-[11px] text-txt-3">{m.name ?? ''}</span>
          <span className="shrink-0 font-num text-[12px] tabular-nums text-txt-2">{fmtWeight(m.weight)}</span>
          <span className={`shrink-0 font-num text-[11px] tabular-nums ${m.lead >= 2 ? 'text-sig-pos' : 'text-txt-3'}`}>{m.lead}/2</span>
        </div>
      ))}
    </div>
  )
}

function ActiveMovement({ fund }: { fund: FundLensDetail }) {
  const mv = fund.movement
  if (!mv) {
    return (
      <p className="font-sans text-[13px] italic text-txt-3">
        Only one holdings snapshot — month-over-month movement needs a second disclosure.
      </p>
    )
  }
  return (
    <>
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <span className="rounded-tile border border-sig-pos/30 bg-sig-pos/10 px-2.5 py-1 font-num text-[12px] font-semibold tabular-nums text-sig-pos">
          +{mv.leaders_added} leaders added
        </span>
        <span className="rounded-tile border border-sig-neg/30 bg-sig-neg/10 px-2.5 py-1 font-num text-[12px] font-semibold tabular-nums text-sig-neg">
          {mv.leaders_dropped} leaders dropped
        </span>
      </div>
      <div className="grid max-w-[920px] grid-cols-1 gap-8 md:grid-cols-2">
        <div>
          <h3 className="mb-2 font-num text-[10px] uppercase tracking-[0.14em] text-sig-pos">Added ↑</h3>
          <MoveList moves={mv.added} />
        </div>
        <div>
          <h3 className="mb-2 font-num text-[10px] uppercase tracking-[0.14em] text-sig-neg">Exited ↓</h3>
          <MoveList moves={mv.exited} />
        </div>
      </div>
    </>
  )
}

// ── look-through holdings table (sorted by weight desc upstream) ──────────
function HoldingsTable({ holdings }: { holdings: FundHolding[] }) {
  const rows = holdings.slice(0, HOLDING_CAP)
  const truncated = holdings.length > HOLDING_CAP
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-edge-rule">
            {([['Symbol', undefined], ['Sector', 'sector_name']] as const).map(([h, term]) => (
              <th key={h} className="whitespace-nowrap px-2 pb-2 text-left font-sans text-[10px] uppercase tracking-wider text-txt-3">{h}{term && <TermInfo term={term} />}</th>
            ))}
            {([['Weight', 'holding_weight'], ['Tch', 'decile'], ['Fnd', 'decile'], ['Cat', 'decile'], ['Flw', 'decile'], ['Val', 'decile'], ['Lead', 'lead'], ['RS 3M', 'rs']] as const).map(([h, term]) => (
              <th key={h} className="whitespace-nowrap px-2 pb-2 text-right font-sans text-[10px] uppercase tracking-wider text-txt-3">{h}{term && <TermInfo term={term} />}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(h => (
            <tr key={h.symbol} className="border-b border-edge-hair hover:bg-surface-raised">
              <td className="whitespace-nowrap px-2 py-1.5 font-num text-[12px] font-semibold tabular-nums">
                <a href={`/stocks/${h.symbol}`} className="text-txt-1 no-underline hover:text-brand hover:underline">{h.symbol}</a>
              </td>
              <td className="max-w-[160px] truncate px-2 py-1.5 font-sans text-[11px] text-txt-2">{h.sector ?? '—'}</td>
              <td className="px-2 py-1.5 text-right font-num text-[12px] tabular-nums text-txt-2">{fmtWeight(h.weight)}</td>
              <td className="px-2 py-1.5 text-right font-num text-[12px] tabular-nums" style={decileStyle(h.d_tech)}>{h.d_tech ?? '—'}</td>
              <td className="px-2 py-1.5 text-right font-num text-[12px] tabular-nums" style={decileStyle(h.d_fund)}>{h.d_fund ?? '—'}</td>
              <td className="px-2 py-1.5 text-right font-num text-[12px] tabular-nums" style={decileStyle(h.d_cat)}>{h.d_cat ?? '—'}</td>
              <td className="px-2 py-1.5 text-right font-num text-[12px] tabular-nums" style={decileStyle(h.d_flow)}>{h.d_flow ?? '—'}</td>
              <td className="px-2 py-1.5 text-right font-num text-[12px] tabular-nums" style={decileStyle(h.d_val)}>{h.d_val ?? '—'}</td>
              <td className={`px-2 py-1.5 text-right font-num text-[12px] tabular-nums ${leadText(h.lead)}`}>{h.lead}/2</td>
              <td className={`px-2 py-1.5 text-right font-num text-[12px] tabular-nums ${pctText(h.rs_3m)}`}>{fmtRs(h.rs_3m)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {truncated && (
        <p className="mt-3 font-sans text-[11px] text-txt-3">
          showing top {HOLDING_CAP} of {holdings.length} holdings by weight
        </p>
      )}
    </div>
  )
}

export async function FundDetailV4({ mstarId }: { mstarId: string }) {
  const fund = await getFundLensDetail(mstarId)
  if (!fund) notFound()
  // Per-holding drivers (top catalyst filing, flow input, RS, ROE) → shown on each name in the tree.
  const drivers = await getConstituentDrivers(fund.holdings.map((h) => h.symbol)).catch(() => ({}))

  const breadthPct = fund.breadth == null ? '—' : `${(fund.breadth * 100).toFixed(0)}%`
  const subParts = [fund.category, fund.amc, fund.isin].filter((x): x is string => !!x)

  // headline stat tiles (real numbers at a glance)
  const tiles: { label: string; value: string; sub?: string; tone?: Tone }[] = [
    { label: 'Leadership-breadth', value: breadthPct, tone: 'pos', sub: `${fund.n_leaders} of ${fund.n_holdings} lead ≥2 lenses` },
    { label: 'Holdings', value: String(fund.n_holdings), sub: 'scored look-through names' },
    { label: 'NAV', value: fund.nav == null ? '—' : `₹${fund.nav.toFixed(2)}`, sub: fund.nav_date ?? 'latest disclosure' },
    { label: 'Expense', value: fund.expense == null ? '—' : `${fund.expense.toFixed(2)}%`, sub: 'regular-plan TER' },
  ]

  return (
    <div className="mx-auto max-w-[1280px] space-y-6 px-6 py-7">
      {/* ── Header ── */}
      <header>
        <nav className="mb-3 font-sans text-[12px] text-txt-3" aria-label="Breadcrumb">
          <Link href="/" className="text-brand no-underline hover:underline">Atlas</Link> ›{' '}
          <Link href="/funds" className="text-brand no-underline hover:underline">Funds</Link> ›{' '}
          <span aria-current="page">{fund.name}</span>
        </nav>
        <h1 className="font-display text-[32px] font-bold leading-tight tracking-tight text-txt-1">{fund.name}</h1>
        {subParts.length > 0 && <div className="mt-2 font-num text-[12px] tabular-nums text-txt-3">{subParts.join(' · ')}</div>}
        <p className="mt-3 max-w-[760px] font-sans text-[15px] text-txt-2">
          How this fund&apos;s holdings score on the six lenses, weighted by holding weight — plus what the
          manager is actively buying and selling. A transparency roll-up of the stock atom — descriptive,
          <em> not</em> a forecast of outperformance.
        </p>

        <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {tiles.map(t => <StatCard key={t.label} label={t.label} value={t.value} sub={t.sub} tone={t.tone ?? 'neutral'} />)}
        </div>
      </header>

      {/* ── Glass box: Score-Derivation Tree (Leadership-breadth → lens → holdings by contribution) ── */}
      <section aria-label="How the score is built">
        <div className="mb-4">
          <p className="font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">Glass box</p>
          <h2 className="font-display text-[22px] font-medium tracking-tight text-txt-1">How the score is built</h2>
          <p className="mt-1 max-w-[760px] font-sans text-[13px] text-txt-2">
            Click a lens to expand its holdings, ranked by contribution (weight × decile); each name links to its own evidence. Descriptive, not a forecast.
          </p>
        </div>
        <ScoreDerivationTree root={holdingsToDerivation(fund.name, fund, fund.holdings, drivers)} />
      </section>

      {/* ── Active-movement panel (the fund differentiator) ── */}
      <Panel
        eyebrow="Differentiator"
        title={`Active movement${fund.movement?.prior_date ? ` · since ${fund.movement.prior_date}` : ''}`}
        info={{
          title: 'Active movement',
          body: 'What the manager bought and sold between the last two monthly disclosures — and whether the net move added top-decile leaders.',
        }}
      >
        <ActiveMovement fund={fund} />
      </Panel>

      {/* ── Look-through holdings ── */}
      <Panel
        eyebrow="Look-through"
        title="Look-through holdings"
        info={{
          title: 'Look-through holdings',
          body: 'Every holding by weight, with each name’s lens deciles, leadership and 3-month RS. Click a symbol for its full evidence.',
        }}
      >
        {fund.holdings.length > 0
          ? <HoldingsTable holdings={fund.holdings} />
          : <p className="font-sans text-[13px] italic text-txt-3">No scored holdings for this fund.</p>}
      </Panel>

      <div className="font-sans text-[12px] leading-[1.6] text-txt-3">
        Native from <strong className="text-txt-2">foundation_staging</strong> — the lens journal looked through
        de_mf_holdings; identity + NAV from Morningstar (de_mf_master / de_mf_nav_daily).{' '}
        <Link href="/funds" className="text-brand hover:underline">← Back to Funds</Link>
      </div>
    </div>
  )
}
