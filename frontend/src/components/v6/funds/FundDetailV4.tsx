// FundDetailV4 — the v4 mutual-fund detail page. Lens-first, native foundation_staging.
// A fund is a holdings-weighted roll-up of the stock atom (D26/D27): the HEADLINE is
// LEADERSHIP-BREADTH (% of holdings weight that are top-decile leaders in ≥2 conviction lenses),
// NOT a composite. The fund-specific differentiator is ACTIVE-MOVEMENT — the month-over-month
// holdings delta (is the manager adding leaders?). The 6-lens vector + look-through are a
// TRANSPARENCY view of what's held and how it scores — descriptive, NOT an outperformance predictor.
import Link from 'next/link'
import { notFound } from 'next/navigation'

import { getFundLensDetail, type FundLensDetail, type FundHolding, type FundMove } from '@/lib/queries/v6/fund_lens'

const HOLDING_CAP = 50

// ── colour helpers (shared idioms with the stocks / ETF pages) ────────────
const decileText = (d: number | null) =>
  d == null ? 'text-ink-tertiary' : d >= 8 ? 'text-signal-pos' : d >= 5 ? 'text-ink-secondary' : 'text-signal-neg'

const leadText = (lead: number) =>
  lead >= 3 ? 'text-signal-pos' : lead === 2 ? 'text-teal' : lead === 1 ? 'text-signal-warn' : 'text-ink-tertiary'

const pctText = (v: number | null) =>
  v == null ? 'text-ink-tertiary' : v >= 0 ? 'text-signal-pos' : 'text-signal-neg'

// rs_3m is a FRACTION (0.05 = +5%) → ×100 for display.
const fmtRs = (v: number | null) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}%`)
// weight is a PERCENT (6.17 = 6.17%) → render as-is, NO ×100.
const fmtWeight = (w: number | null) => (w == null ? '—' : `${w.toFixed(2)}%`)

// ── holdings-weighted six-lens vector (0..100, bars) ──────────────────────
const LENS_VECTOR: { key: keyof Pick<FundLensDetail, 'v_tech' | 'v_fund' | 'v_cat' | 'v_flow' | 'v_val'>; label: string }[] = [
  { key: 'v_tech', label: 'Technical' },
  { key: 'v_fund', label: 'Fundamental' },
  { key: 'v_cat', label: 'Catalyst' },
  { key: 'v_flow', label: 'Flow' },
  { key: 'v_val', label: 'Valuation' },
]
const barColor = (v: number) => (v >= 80 ? 'bg-signal-pos' : v >= 50 ? 'bg-signal-warn' : 'bg-signal-neg')

function LensVector({ fund }: { fund: FundLensDetail }) {
  const scored = LENS_VECTOR
    .map(l => ({ label: l.label, v: fund[l.key] }))
    .filter((x): x is { label: string; v: number } => x.v != null)
  return (
    <div className="space-y-2 max-w-[560px]">
      {scored.length === 0 && <p className="font-sans text-[13px] text-ink-tertiary italic">No scored holdings.</p>}
      {scored.map(l => (
        <div key={l.label} className="flex items-center gap-3">
          <span className="w-[96px] shrink-0 font-sans text-xs text-ink-secondary">{l.label}</span>
          <span className="w-[34px] shrink-0 font-mono text-xs tabular-nums text-ink-primary text-right">{l.v.toFixed(0)}</span>
          <span className="flex-1 h-[7px] bg-paper-deep rounded-[2px] overflow-hidden">
            <span className={`block h-full rounded-[2px] ${barColor(l.v)}`} style={{ width: `${Math.min(100, l.v)}%` }} />
          </span>
        </div>
      ))}
    </div>
  )
}

// ── active-movement: one column of moves (added / exited) ─────────────────
function MoveList({ moves }: { moves: FundMove[] }) {
  if (moves.length === 0) return <p className="font-sans text-[13px] text-ink-tertiary italic">—</p>
  return (
    <div className="space-y-1">
      {moves.map(m => (
        <div key={m.symbol} className="flex items-center justify-between gap-3 py-1 border-b border-paper-rule/50">
          <a href={`/stocks/${m.symbol}`} className="font-mono text-[12px] font-semibold text-ink-primary no-underline hover:text-teal hover:underline truncate">
            {m.symbol}
          </a>
          <span className="font-sans text-[11px] text-ink-tertiary truncate flex-1 min-w-0">{m.name ?? ''}</span>
          <span className="font-mono text-[12px] tabular-nums text-ink-secondary shrink-0">{fmtWeight(m.weight)}</span>
          <span className={`font-mono text-[11px] tabular-nums shrink-0 ${m.lead >= 2 ? 'text-signal-pos' : 'text-ink-tertiary'}`}>{m.lead}/4</span>
        </div>
      ))}
    </div>
  )
}

function ActiveMovement({ fund }: { fund: FundLensDetail }) {
  const mv = fund.movement
  if (!mv) {
    return (
      <p className="font-sans text-[13px] text-ink-tertiary italic">
        Only one holdings snapshot — month-over-month movement needs a second disclosure.
      </p>
    )
  }
  return (
    <>
      <div className="flex flex-wrap items-center gap-3 mb-5">
        <span className="font-mono text-[12px] font-semibold px-2.5 py-1 rounded-sm bg-paper-soft border border-paper-rule text-signal-pos">
          +{mv.leaders_added} leaders added
        </span>
        <span className="font-mono text-[12px] font-semibold px-2.5 py-1 rounded-sm bg-paper-soft border border-paper-rule text-signal-neg">
          {mv.leaders_dropped} leaders dropped
        </span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 max-w-[920px]">
        <div>
          <h3 className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary font-semibold mb-2">Added</h3>
          <MoveList moves={mv.added} />
        </div>
        <div>
          <h3 className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary font-semibold mb-2">Exited</h3>
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
          <tr className="border-b border-paper-rule">
            {(['Symbol', 'Sector'] as const).map(h => (
              <th key={h} className="font-sans text-[10px] uppercase tracking-wider pb-2 px-2 text-left text-ink-tertiary whitespace-nowrap">{h}</th>
            ))}
            {(['Weight', 'Tch', 'Fnd', 'Cat', 'Flw', 'Val', 'Lead', 'RS 3M'] as const).map(h => (
              <th key={h} className="font-sans text-[10px] uppercase tracking-wider pb-2 px-2 text-right text-ink-tertiary whitespace-nowrap">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(h => (
            <tr key={h.symbol} className="border-b border-paper-rule/50 hover:bg-paper-soft">
              <td className="py-1.5 px-2 font-mono text-[12px] font-semibold whitespace-nowrap">
                <a href={`/stocks/${h.symbol}`} className="text-ink-primary no-underline hover:text-teal hover:underline">{h.symbol}</a>
              </td>
              <td className="py-1.5 px-2 font-sans text-[11px] text-ink-secondary truncate max-w-[160px]">{h.sector ?? '—'}</td>
              <td className="py-1.5 px-2 text-right font-mono text-[12px] tabular-nums text-ink-secondary">{fmtWeight(h.weight)}</td>
              <td className={`py-1.5 px-2 text-right font-mono text-[12px] tabular-nums ${decileText(h.d_tech)}`}>{h.d_tech ?? '—'}</td>
              <td className={`py-1.5 px-2 text-right font-mono text-[12px] tabular-nums ${decileText(h.d_fund)}`}>{h.d_fund ?? '—'}</td>
              <td className={`py-1.5 px-2 text-right font-mono text-[12px] tabular-nums ${decileText(h.d_cat)}`}>{h.d_cat ?? '—'}</td>
              <td className={`py-1.5 px-2 text-right font-mono text-[12px] tabular-nums ${decileText(h.d_flow)}`}>{h.d_flow ?? '—'}</td>
              <td className={`py-1.5 px-2 text-right font-mono text-[12px] tabular-nums ${decileText(h.d_val)}`}>{h.d_val ?? '—'}</td>
              <td className={`py-1.5 px-2 text-right font-mono text-[12px] tabular-nums ${leadText(h.lead)}`}>{h.lead}/4</td>
              <td className={`py-1.5 px-2 text-right font-mono text-[12px] tabular-nums ${pctText(h.rs_3m)}`}>{fmtRs(h.rs_3m)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {truncated && (
        <p className="font-sans text-[11px] text-ink-tertiary mt-3">
          showing top {HOLDING_CAP} of {holdings.length} holdings by weight
        </p>
      )}
    </div>
  )
}

export async function FundDetailV4({ mstarId }: { mstarId: string }) {
  const fund = await getFundLensDetail(mstarId)
  if (!fund) notFound()

  const breadthPct = fund.breadth == null ? '—' : `${(fund.breadth * 100).toFixed(0)}%`
  const expenseStr = fund.expense == null ? null : `expense ${fund.expense.toFixed(2)}%` // already in percent units
  const navStr = fund.nav == null ? null
    : `NAV ₹${fund.nav.toFixed(2)}${fund.nav_date ? ` (${fund.nav_date})` : ''}`
  const subParts = [
    fund.category,
    fund.amc,
    expenseStr,
    `${fund.n_holdings} holdings`,
    navStr,
    fund.isin,
  ].filter((x): x is string => !!x)

  return (
    <div className="max-w-[1400px] mx-auto">
      {/* ── Header ── */}
      <section className="px-8 py-9 border-b border-paper-rule">
        <nav className="font-sans text-[12px] text-ink-tertiary mb-3" aria-label="Breadcrumb">
          <Link href="/" className="text-teal hover:underline no-underline">Atlas</Link> ›{' '}
          <Link href="/funds" className="text-teal hover:underline no-underline">Funds</Link> ›{' '}
          <span aria-current="page">{fund.name}</span>
        </nav>
        <div className="flex items-start justify-between gap-6 flex-wrap">
          <div className="min-w-0 flex-1">
            <h1 className="font-serif text-[44px] font-normal tracking-[-0.011em] text-ink-primary leading-[1.05]">{fund.name}</h1>
            <div className="font-mono text-[12px] text-ink-tertiary mt-2">{subParts.join(' · ')}</div>
            <p className="font-sans text-[15px] text-ink-secondary max-w-[760px] mt-3">
              How this fund&apos;s holdings score on the six lenses, weighted by holding weight — plus what the
              manager is actively buying and selling. A transparency roll-up of the stock atom — descriptive,
              <em> not</em> a forecast of outperformance.
            </p>
          </div>
          {/* leadership-breadth headline badge */}
          <div className="shrink-0 bg-paper-soft border border-paper-rule rounded-sm px-5 py-4 text-center min-w-[180px]">
            <div className="font-mono text-[40px] font-medium leading-none text-signal-pos">{breadthPct}</div>
            <div className="font-sans text-[10px] uppercase tracking-[0.14em] text-ink-tertiary font-semibold mt-2">leadership-breadth</div>
            <div className="font-sans text-[11px] text-ink-tertiary mt-1 leading-snug">
              {fund.n_leaders} of {fund.n_holdings} holdings lead ≥2 lenses
            </div>
          </div>
        </div>
      </section>

      {/* ── Holdings-weighted six-lens vector ── */}
      <section className="px-8 py-9 border-b border-paper-rule" aria-label="Holdings-weighted lens vector">
        <div className="mb-5">
          <h2 className="font-serif text-[28px] font-normal tracking-tight text-ink-primary">How the holdings score on each lens</h2>
          <p className="font-sans text-[13px] text-ink-tertiary max-w-[760px] leading-[1.45] mt-1">
            How the fund&apos;s holdings score on each lens (weight-weighted) — descriptive, not a forecast.
          </p>
        </div>
        <LensVector fund={fund} />
      </section>

      {/* ── Active-movement panel (the fund differentiator) ── */}
      <section className="px-8 py-9 border-b border-paper-rule" aria-label="Active movement">
        <div className="mb-5">
          <h2 className="font-serif text-[28px] font-normal tracking-tight text-ink-primary">
            Active movement{fund.movement?.prior_date ? ` · since ${fund.movement.prior_date}` : ''}
          </h2>
          <p className="font-sans text-[13px] text-ink-tertiary max-w-[760px] leading-[1.45] mt-1">
            What the manager bought and sold between the last two monthly disclosures — and whether the net
            move added top-decile leaders.
          </p>
        </div>
        <ActiveMovement fund={fund} />
      </section>

      {/* ── Look-through holdings ── */}
      <section className="px-8 py-9 border-b border-paper-rule" aria-label="Look-through holdings">
        <div className="mb-5">
          <h2 className="font-serif text-[28px] font-normal tracking-tight text-ink-primary">Look-through holdings</h2>
          <p className="font-sans text-[13px] text-ink-tertiary max-w-[760px] leading-[1.45] mt-1">
            Every holding by weight, with each name&apos;s lens deciles, leadership and 3-month RS. Click a symbol for its full evidence.
          </p>
        </div>
        {fund.holdings.length > 0
          ? <HoldingsTable holdings={fund.holdings} />
          : <p className="font-sans text-[13px] text-ink-tertiary italic">No scored holdings for this fund.</p>}
      </section>

      <div className="px-8 py-6 font-sans text-[12px] text-ink-tertiary leading-[1.6]">
        Native from <strong className="text-ink-secondary">foundation_staging</strong> — the lens journal looked through
        de_mf_holdings; identity + NAV from Morningstar (de_mf_master / de_mf_nav_daily).{' '}
        <Link href="/funds" className="text-teal hover:underline">← Back to Funds</Link>
      </div>
    </div>
  )
}
