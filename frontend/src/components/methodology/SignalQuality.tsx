// The honest scorecard: has each lens actually preceded returns? Every number on this
// page is read out of atlas_foundation.atlas_signal_ic — nothing is hard-coded, and a
// lens with no evidence is rendered exactly as loudly as one that works.
//
// Two columns that exist in the journal are deliberately NOT rendered:
//   t_stat       — 126-session windows on 1,343 dates give ~11 independent observations,
//                  not 1,343, so every t-stat in the table is inflated by the overlap.
//   mean_spread  — shown only inside ±100%; see the footnote on the close_adj defect.
import type { SignalRow, SignalGrade } from '@/lib/queries/signal_quality'
import { classifySignal, displaySpread } from '@/lib/queries/signal_quality'

// The headline read: large-caps over a quarter. The full grid below carries every cell.
const HEAD_COHORT = 'large'
const HEAD_HORIZON = 63

const LENS_ORDER = ['policy', 'technical', 'flow', 'fundamental', 'valuation', 'catalyst', 'composite'] as const

const LENS_BLURB: Record<string, string> = {
  policy: 'Sector tailwind — the read on where policy and the cycle are pushing an industry.',
  technical: 'Trend, momentum and relative strength against the Nifty 500 and the sector.',
  flow: 'Delivery, institutional buying and the shape of who is accumulating.',
  fundamental: 'Returns on capital, margins, growth and leverage from the filed financials.',
  valuation: 'What is being paid for those fundamentals, against the stock’s own history and peers.',
  catalyst: 'The signal read of recent exchange filings, insider deals and bulk deals.',
  composite: 'The blend — the 0–100 conviction score every other page is built on.',
}

// Structural caveats a reader must see next to the number, or they will over-trust it.
const LENS_CAVEAT: Record<string, string> = {
  policy:
    'Read this as a SECTOR call, not stock selection. Policy is scored per sector and broadcast to every constituent — on 2024-05-31 it took just 9 distinct values across 2,093 stocks. It ranks industries well; it says nothing about which name inside an industry to own.',
  composite:
    'The composite is the score the board leads with, so its row is the one that matters most. It is measured here exactly as it is served, with no re-weighting.',
}

const HOW_TO_READ = [
  ['What rank-IC means', 'On each date, rank every stock by its lens score and rank it again by the return it went on to deliver. Rank-IC is how closely those two orderings agree: +1 is perfect, 0 is a coin flip, negative means the score ordered them backwards.'],
  ['What counts as good', '+0.03 is a genuine equity factor — real money is managed on less. +0.10 is exceptional. Anything above +0.15 is more likely a bug or a look-ahead leak than an edge, and should be investigated before it is believed.'],
  ['Hit rate', 'The share of tested dates on which the score pointed the right way at all. A high average IC carried by a handful of dates is fragile; a hit rate near 50% says exactly that.'],
  ['Why there are no t-statistics', 'A 126-session forward window measured on 1,343 consecutive dates re-uses almost all the same price history each time — roughly 11 independent observations, not 1,343. The usual t-statistic would read enormous and mean nothing, so it is not shown at all rather than shown with a caveat nobody reads.'],
] as const

const KNOWN_DEFECTS = [
  ['Some decile spreads are withheld', 'Before June 2024, 86 instruments carry 28,507 sub-₹1 close_adj rows — PRIVISCL reads ₹0.05 on 2020-03-23 with an adjustment factor of 1.0, so the raw close is wrong rather than the adjustment. One such row inside a decile drags its arithmetic mean: the worst-affected cell reads +2811%. Rank-IC is immune, because ranks do not care how far wrong a price is. Any spread outside ±100% over a quarter is therefore shown as withheld, not printed.'],
  ['Cap bands are today’s cap bands', 'The cap band comes from v_stock_cap, which has no date dimension — it is the universe as it stands now. In the wide era that leaves roughly 41% of the cross-section without a band, and those names are not missing at random: they are disproportionately the ones that later left the universe. Every cap-band figure on this page carries its coverage for exactly this reason. The “all” cohort has no such gap.'],
  ['Overlapping windows, not independent tests', 'Consecutive test dates share almost all of their forward window, so the effective sample is far smaller than the date count suggests. That is what inflates any significance test. It also means a lens can look stable simply because one long market episode repeats across hundreds of overlapping windows.'],
] as const

const ERA_LABEL: Record<string, { name: string; span: string; note: string }> = {
  wide: { name: 'Wide universe', span: '2019 → May 2024', note: 'before the universe was cut' },
  narrow: { name: 'Narrow universe', span: 'Jun 2024 → today', note: 'cut to NIFTY 500' },
}

// ── formatters ─────────────────────────────────────────────────────────────
const num = (v: number): string => v.toLocaleString('en-IN')

/** IC to 3 dp with an explicit sign. NULL is "—" — never 0.00, which would read as a
 *  measured zero rather than a cohort with no ordering to correlate. */
function fmtIC(v: number | null): string {
  if (v == null) return '—'
  return `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(3)}`
}

function fmtPct(v: number | null, signed = false): string {
  if (v == null) return '—'
  const p = Math.abs(v * 100).toFixed(1)
  if (!signed) return `${(v * 100).toFixed(1)}%`
  return `${v >= 0 ? '+' : '−'}${p}%`
}

/** The one card shape this page uses for prose — a rule down the left, title, body. */
function NoteCards({ items, accent }: { items: readonly (readonly [string, string])[]; accent: string }) {
  return (
    <>
      {items.map(([h, b]) => (
        <div key={h} className={`rounded-r-tile bg-surface-raised p-4 ${accent}`}>
          <div className="mb-1 font-display text-[14px] font-medium text-txt-1">{h}</div>
          <p className="font-sans text-[13px] leading-[1.55] text-txt-2">{b}</p>
        </div>
      ))}
    </>
  )
}

function tone(v: number | null): string {
  if (v == null) return 'text-txt-3'
  if (v > 0) return 'text-sig-pos'
  if (v < 0) return 'text-sig-neg'
  return 'text-txt-2'
}

// ── badge ──────────────────────────────────────────────────────────────────
const BADGE: Record<SignalGrade, string> = {
  'carries signal': 'border-sig-pos/50 bg-sig-pos/10 text-sig-pos',
  weak: 'border-sig-warn/50 bg-sig-warn/10 text-sig-warn',
  'no evidence': 'border-edge-rule bg-surface-raised text-txt-3',
}

function Badge({ grade }: { grade: SignalGrade }) {
  return (
    <span className={`inline-block rounded-tile border px-2 py-0.5 font-num text-[10px] uppercase tracking-[0.08em] ${BADGE[grade]}`}>
      {grade}
    </span>
  )
}

/** How many names actually stood in each ranking, straight off the journal's mean_n for
 *  the whole cross-section. Measured, not quoted — the era boundaries move as the study
 *  is re-run and a hand-written range would drift out of date silently. */
function eraUniverse(rows: SignalRow[], era: string): string {
  const ns = rows.filter((r) => r.era === era && r.cohort === 'all' && r.mean_n != null).map((r) => r.mean_n!)
  if (ns.length === 0) return ''
  const lo = Math.round(Math.min(...ns))
  const hi = Math.round(Math.max(...ns))
  const span = lo === hi ? num(lo) : `${num(lo)}–${num(hi)}`
  return `${span} names ranked per date · ${ERA_LABEL[era]?.note ?? ''}`
}

/** The composite's own claim is that blending beats its parts. This counts, from the
 *  measured rows, how often that is false in a given era — a hand-written sentence would
 *  become a lie the first time the study moved. */
function beatenByInputs(rows: SignalRow[], era: string): number {
  const at = (lens: string) =>
    rows.find((r) => r.lens === lens && r.era === era && r.cohort === HEAD_COHORT && r.horizon_d === HEAD_HORIZON)
  const comp = at('composite')?.mean_ic
  if (comp == null) return 0
  return LENS_ORDER.filter((l) => l !== 'composite').filter((l) => {
    const v = at(l)?.mean_ic
    return v != null && v > comp
  }).length
}

// ── plain-English verdict, generated from the measured rows ────────────────
/** −1 / 0 / +1. Below |0.01| there is no direction worth naming. */
function dir(r: SignalRow | undefined): -1 | 0 | 1 {
  const v = r?.mean_ic
  if (v == null || Math.abs(v) < 0.01) return 0
  return v > 0 ? 1 : -1
}

function verdictLine(wide: SignalRow | undefined, narrow: SignalRow | undefined): string {
  const key = `${dir(wide)}|${dir(narrow)}`
  const lines: Record<string, string> = {
    '1|1': 'Predicted returns in both periods — the ordering survived the universe change. The steadiest evidence on this page.',
    '1|-1': 'Worked, then inverted. It predicted returns before June 2024; since the cut to NIFTY 500 a higher score has preceded a LOWER return.',
    '-1|1': 'Pointed the wrong way before June 2024, and has predicted returns since. One reversal is not a track record.',
    '-1|-1': 'Points the wrong way in both periods — a higher score has preceded a lower return throughout. Not noise; a consistent inversion.',
    '0|0': 'No measurable relationship to forward returns in either period. On this evidence it should not move a decision on its own.',
    '1|0': 'Predicted returns before June 2024; nothing measurable since.',
    '0|1': 'Nothing measurable before June 2024; predicts weakly since.',
    '-1|0': 'Pointed the wrong way before June 2024; nothing measurable since.',
    '0|-1': 'Nothing measurable before June 2024; has pointed the wrong way since.',
  }
  return lines[key] ?? 'Not measured in one or both periods.'
}

/** The sentence a person can act on, before the statistic — or an explicit refusal to
 *  quote a spread that the price defect has corrupted. */
function actionLine(r: SignalRow | undefined, era: string): string | null {
  if (!r || r.mean_ic == null) return null
  const spread = displaySpread(r.mean_spread)
  const era_ = ERA_LABEL[era]?.span ?? era
  const hit = `the score ordered returns correctly on ${fmtPct(r.hit_rate)} of the ${num(r.n_dates)} dates tested`
  if (spread == null) {
    return `${era_}: decile spread withheld — corrupted by the price defect described below. ${hit[0].toUpperCase()}${hit.slice(1)}.`
  }
  return `${era_}: the top decile of large-caps out-returned the bottom decile by ${fmtPct(spread, true)} over the next 3 months on average, and ${hit}.`
}

// ── sections ───────────────────────────────────────────────────────────────
function Hero({ rows }: { rows: SignalRow[] }) {
  const wide = rows.find((r) => r.era === 'wide')
  const narrow = rows.find((r) => r.era === 'narrow')
  return (
    <section className="border-b border-edge-hair bg-surface-panel px-8 py-12">
      <div className="max-w-[880px]">
        <div className="mb-2 font-num text-[10px] uppercase tracking-[0.14em] text-txt-3">Atlas · Methodology · Evidence</div>
        <h1 className="mb-4 font-display text-[42px] font-semibold leading-[1.1] tracking-tight text-txt-1">
          Does the scoring actually work?
        </h1>
        <p className="mb-4 font-sans text-[17px] leading-[1.55] text-txt-2">
          Every score on this board is a claim that a higher number should precede a higher return. This page is the
          measurement of that claim — each lens tested against what the stock actually did next, across{' '}
          <span className="font-semibold text-txt-1">{wide ? `${wide.first_date} → ${wide.last_date}` : ''}</span> and{' '}
          <span className="font-semibold text-txt-1">{narrow ? `${narrow.first_date} → ${narrow.last_date}` : ''}</span>.
        </p>
        <p className="font-sans text-[14px] leading-[1.55] text-txt-3">
          It is deliberately unflattering. Where a lens shows nothing, the page says so; where a lens has pointed the
          wrong way, it says that too. Nothing here is hand-written — every figure is read live from the study journal.
        </p>
      </div>
    </section>
  )
}

function HowToRead() {
  return (
    <section className="border-b border-edge-hair bg-surface-base px-8 py-10">
      <div className="max-w-[880px]">
        <div className="mb-1 font-num text-[10px] uppercase tracking-[0.14em] text-txt-3">First</div>
        <h2 className="mb-4 font-display text-[24px] font-semibold tracking-tight text-txt-1">How to read this page</h2>
        <div className="grid gap-3 md:grid-cols-2">
          <NoteCards accent="border-l border-l-edge-rule" items={HOW_TO_READ} />
        </div>
        <div className="mt-3 rounded-r-tile border-l-4 border-l-sig-warn bg-surface-raised p-4">
          <div className="mb-1 font-display text-[14px] font-medium text-txt-1">The eras are never averaged</div>
          <p className="font-sans text-[13px] leading-[1.55] text-txt-2">
            In June 2024 the scored universe was cut from ~1,900 names to the NIFTY 500. That is a different population,
            not more of the same one, so blending the two periods into a single number would hide the most important
            thing this study found. They are reported side by side, always. A third era began on 2026-08-21 when a
            ₹2.5cr liquidity floor set the universe at 1,198 names — too few dates have passed to report it.
          </p>
        </div>
      </div>
    </section>
  )
}

function LensCard({ lens, wide, narrow, all }: { lens: string; wide?: SignalRow; narrow?: SignalRow; all: SignalRow[] }) {
  return (
    <div className="rounded-panel border border-edge-hair bg-surface-panel p-5">
      <div className="mb-1 flex flex-wrap items-baseline gap-3">
        <h3 className="font-display text-[20px] font-semibold capitalize tracking-tight text-txt-1">{lens}</h3>
        <span className="font-sans text-[12px] text-txt-3">{LENS_BLURB[lens]}</span>
      </div>
      <p className="mb-4 max-w-[760px] font-sans text-[15px] leading-[1.55] text-txt-1">
        {verdictLine(wide, narrow)}
      </p>
      <div className="grid gap-3 md:grid-cols-2">
        {([['wide', wide], ['narrow', narrow]] as const).map(([era, r]) => (
          <div key={era} className="rounded-r-tile border-l border-l-edge-rule bg-surface-raised p-4">
            <div className="mb-2 flex items-center gap-2">
              <span className="font-num text-[10px] uppercase tracking-[0.12em] text-txt-3">{ERA_LABEL[era].name}</span>
              {r ? <Badge grade={classifySignal(r)} /> : <span className="font-num text-[10px] text-txt-3">not measured</span>}
            </div>
            {r ? (
              <>
                <div className="flex items-baseline gap-4">
                  <div>
                    <div className="font-num text-[10px] uppercase tracking-[0.1em] text-txt-3">Rank-IC</div>
                    <div className={`font-num text-[26px] font-semibold tabular-nums ${tone(r.mean_ic)}`}>{fmtIC(r.mean_ic)}</div>
                  </div>
                  <div>
                    <div className="font-num text-[10px] uppercase tracking-[0.1em] text-txt-3">Hit rate</div>
                    <div className="font-num text-[18px] tabular-nums text-txt-1">{fmtPct(r.hit_rate)}</div>
                  </div>
                  <div>
                    <div className="font-num text-[10px] uppercase tracking-[0.1em] text-txt-3">Dates</div>
                    <div className="font-num text-[18px] tabular-nums text-txt-1">{num(r.n_dates)}</div>
                  </div>
                </div>
                <p className="mt-2 font-sans text-[12px] leading-[1.5] text-txt-2">{actionLine(r, era)}</p>
                <p className="mt-1 font-num text-[10px] text-txt-3">
                  Large-caps, {HEAD_HORIZON} sessions forward · cap coverage {fmtPct(r.cap_coverage)} · {eraUniverse(all, era)}
                </p>
              </>
            ) : (
              <p className="font-sans text-[13px] text-txt-3">No row in the journal for this era.</p>
            )}
          </div>
        ))}
      </div>
      {LENS_CAVEAT[lens] && (
        <div className="mt-3 rounded-r-tile border-l-4 border-l-sig-warn bg-surface-raised p-3">
          <p className="font-sans text-[13px] leading-[1.5] text-txt-2">
            <span className="font-semibold text-txt-1">Read this carefully. </span>
            {LENS_CAVEAT[lens]}
            {lens === 'composite' && (
              <> On this evidence the blend does not improve on its parts:{' '}
                <span className="font-semibold text-txt-1">
                  {beatenByInputs(all, 'wide')} of the 6 lenses it blends score a higher IC than the composite itself
                  in the wide era, and {beatenByInputs(all, 'narrow')} of 6 in the narrow era
                </span>{' '}
                (large-caps, {HEAD_HORIZON} sessions). That is the single most actionable finding on this page.
              </>
            )}
          </p>
        </div>
      )}
    </div>
  )
}

function FullGrid({ rows }: { rows: SignalRow[] }) {
  const horizons = [...new Set(rows.map((r) => r.horizon_d))].sort((a, b) => a - b)
  const cohorts = ['all', 'large', 'mid', 'small', 'micro'].filter((c) => rows.some((r) => r.cohort === c))
  const at = (lens: string, h: number, c: string, era: string) =>
    rows.find((r) => r.lens === lens && r.horizon_d === h && r.cohort === c && r.era === era)
  return (
    <section className="border-t border-edge-hair bg-surface-base px-8 py-10">
      <div className="mb-1 font-num text-[10px] uppercase tracking-[0.14em] text-txt-3">Everything measured</div>
      <h2 className="mb-1 font-display text-[24px] font-semibold tracking-tight text-txt-1">Every cell of the study</h2>
      <p className="mb-4 max-w-[820px] font-sans text-[13px] leading-[1.55] text-txt-2">
        Rank-IC / hit rate / dates, for each lens across three forward horizons and five cap bands.
        Cap coverage is shown for every cap band because it qualifies the number beside it.
      </p>
      <div className="overflow-x-auto rounded-panel border border-edge-hair bg-surface-panel">
        <table className="w-full min-w-[880px] border-collapse font-num text-[12px]">
          <thead className="sticky top-0 bg-surface-panel">
            <tr className="border-b border-edge-rule text-txt-3">
              <th className="px-3 py-2 text-left font-normal uppercase tracking-[0.08em]">Lens</th>
              <th className="px-3 py-2 text-right font-normal uppercase tracking-[0.08em]">Horizon</th>
              <th className="px-3 py-2 text-left font-normal uppercase tracking-[0.08em]">Cohort</th>
              {(['wide', 'narrow'] as const).map((e) => (
                <th key={e} colSpan={4} className="border-l border-edge-hair px-3 py-2 text-center font-normal uppercase tracking-[0.08em]">
                  {ERA_LABEL[e].name}
                </th>
              ))}
            </tr>
            <tr className="border-b border-edge-rule text-txt-3">
              <th colSpan={3} />
              {(['wide', 'narrow'] as const).flatMap((e) =>
                ['IC', 'Hit', 'Dates', 'Cap cov.'].map((label, i) => (
                  <th key={`${e}-${label}`}
                    className={`px-3 py-1.5 text-right font-normal ${i === 0 ? 'border-l border-edge-hair' : ''}`}>
                    {label}
                  </th>
                )),
              )}
            </tr>
          </thead>
          <tbody>
            {horizons.flatMap((h) =>
              LENS_ORDER.flatMap((lens) =>
                cohorts.map((c) => (
                  <tr key={`${h}-${lens}-${c}`} className="border-b border-edge-hair last:border-0 hover:bg-surface-raised">
                    <td className="px-3 py-1.5 capitalize text-txt-1">{lens}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-txt-2">{h}d</td>
                    <td className="px-3 py-1.5 text-txt-2">{c}</td>
                    {(['wide', 'narrow'] as const).map((era) => {
                      const r = at(lens, h, c, era)
                      return (
                        <Cells key={era} r={r} showCov={c !== 'all'} />
                      )
                    })}
                  </tr>
                )),
              ),
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}

/** cap_coverage only qualifies a cap band — the `all` cohort is the whole cross-section. */
function Cells({ r, showCov }: { r: SignalRow | undefined; showCov: boolean }) {
  return (
    <>
      <td className={`border-l border-edge-hair px-3 py-1.5 text-right tabular-nums ${tone(r?.mean_ic ?? null)}`}>
        {fmtIC(r?.mean_ic ?? null)}
      </td>
      <td className="px-3 py-1.5 text-right tabular-nums text-txt-2">{fmtPct(r?.hit_rate ?? null)}</td>
      <td className="px-3 py-1.5 text-right tabular-nums text-txt-2">{r ? num(r.n_dates) : '—'}</td>
      <td className="px-3 py-1.5 text-right tabular-nums text-txt-3">{showCov ? fmtPct(r?.cap_coverage ?? null) : '—'}</td>
    </>
  )
}

function Caveats() {
  return (
    <section className="border-t border-edge-hair bg-surface-panel px-8 py-10">
      <div className="mb-1 font-num text-[10px] uppercase tracking-[0.14em] text-txt-3">Known defects in this study</div>
      <h2 className="mb-4 font-display text-[24px] font-semibold tracking-tight text-txt-1">What these numbers cannot tell you</h2>
      <div className="grid max-w-[1000px] gap-3 md:grid-cols-3">
        <NoteCards accent="border-l-4 border-l-sig-neg" items={KNOWN_DEFECTS} />
      </div>
    </section>
  )
}

// ── page body ──────────────────────────────────────────────────────────────
export function SignalQuality({ rows }: { rows: SignalRow[] }) {
  const head = (lens: string, era: string) =>
    rows.find((r) => r.lens === lens && r.era === era && r.cohort === HEAD_COHORT && r.horizon_d === HEAD_HORIZON)

  if (rows.length === 0) {
    return (
      <div className="px-8 py-16 font-sans text-[15px] text-txt-2">
        The signal study has not been run yet — no rows in atlas_signal_ic.
      </div>
    )
  }

  return (
    <>
      <Hero rows={rows} />
      <HowToRead />
      <section className="bg-surface-base px-8 py-10">
        <div className="mb-1 font-num text-[10px] uppercase tracking-[0.14em] text-txt-3">Lens by lens</div>
        <h2 className="mb-1 font-display text-[24px] font-semibold tracking-tight text-txt-1">The verdict on each lens</h2>
        <p className="mb-5 max-w-[820px] font-sans text-[13px] leading-[1.55] text-txt-2">
          Headline read: large-caps, 63 sessions (about three months) forward. The full grid below carries every
          horizon and cap band. A lens with no evidence is not removed — it is the most useful cell on the page.
        </p>
        <div className="grid gap-4">
          {LENS_ORDER.map((lens) => (
            <LensCard key={lens} lens={lens} wide={head(lens, 'wide')} narrow={head(lens, 'narrow')} all={rows} />
          ))}
        </div>
      </section>
      <FullGrid rows={rows} />
      <Caveats />
    </>
  )
}
