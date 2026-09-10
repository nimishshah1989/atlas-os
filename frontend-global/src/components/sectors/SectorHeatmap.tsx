'use client'
// SectorHeatmap — the drill-down, in Atlas India's SectorHeatmapV4 idiom: a row EXPANDS IN PLACE
// into its children, rendered in the SAME columns, so nobody loses their place and no column has
// to be re-learned at depth. Sector → theme → fund, three levels, one header.
//
// The FM: "we have a main sector, then subsector performance, and then, within that, the ETF…
// those kinds of consistent drill-down views can be built as we have it in atlas as well" — and
// on what the board is for: "which are the best-performing themes and sub-themes… that's where
// the game becomes beautiful, because it's not just some 21 sectors."
//
// COLOUR IS THE SECOND CHANNEL, NEVER THE ONLY ONE (scores.ts rule 3). Every tinted cell also
// prints its value, so the board reads in greyscale, to a colour-blind reader, and in a pasted
// screenshot.
//
// EVERY TINT HAS A STATED BASELINE, because a colour with no zero is decoration:
//   · relative strength — zero is the S&P 500. Green means it beat the index, red means it lost
//     to it, and the saturation is how far, capped at ±20 points (`rsTint`'s own constant, shared
//     with the country grid so the two surfaces cannot disagree).
//   · breadth — the baseline is HALF, drawn as a hairline in the bar. More than half the members
//     above their own 200-day line is a rising group; the bar shows which side of that it is on.
//   · score — the baseline is THE POPULATION ON SCREEN, and the rank beside it names the
//     population. No band is invented here: every methodology cut lives in atlas_thresholds
//     (rule #1), and a "green above 60" typed into a component would be exactly that.
import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { InfoTip } from '@/components/ui/InfoTip'
import { formatDecimal, formatPct, formatUsdCompact } from '@/lib/format'
import { rsTint } from '@/lib/scores'
import {
  SECTOR_WINDOWS,
  scoreSpan,
  sortTree,
  type SectorNode,
  type SectorTree,
  type SortKey,
} from '@/lib/sectors'

// ── the columns, once, for all three levels ─────────────────────────────────

// `.panel table th` in globals.css already carries the desk's header style — uppercase, sized,
// ruled — at a specificity no utility class beats, and one header style across every table on the
// board is exactly the consistency this board is short of. So only the ALIGNMENT is set here, and
// inline, which is the one channel that wins.
const L = { textAlign: 'left' } as const
const R = { textAlign: 'right' } as const
const NUM = 'px-2 py-1.5 text-right font-num text-[12.5px] tabular-nums'

/** Where a level's rows are indented to, and what its children are CALLED — the word a reader
 *  needs to know what expanding will show them. */
const LEVEL: Record<SectorNode['level'], { pad: number; child: string }> = {
  sector: { pad: 8, child: 'theme' },
  theme: { pad: 26, child: 'fund' },
  fund: { pad: 44, child: '' },
}

/** "1 theme", not "1 themes". A sector carrying exactly one theme is a real and common row —
 *  Consumer Staples, Consumer Discretionary and Communication Services each have one today — and
 *  the board is read by someone who notices. */
const count = (n: number, one: string) => `${n} ${n === 1 ? one : `${one}s`}`

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      width="9" height="9" viewBox="0 0 10 10" aria-hidden
      className={`shrink-0 transition-transform ${open ? 'rotate-90' : ''}`}
    >
      <path d="M3 1.5 L7 5 L3 8.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/** Breadth as a bar with the half-way line drawn on it. The number is printed either way; the bar
 *  is what makes "more up than down" readable without reading. */
function BreadthBar({ frac }: { frac: string | null }) {
  if (frac == null || frac === '') return <span className="text-ink-3">—</span>
  const pct = Math.max(0, Math.min(1, Number(frac))) * 100
  const above = pct >= 50
  return (
    <span className="flex items-center justify-end gap-1.5">
      <span className="relative h-[7px] w-[42px] overflow-hidden rounded-full bg-inset">
        <span
          className="absolute inset-y-0 left-0 rounded-full"
          style={{ width: `${pct}%`, background: above ? 'var(--color-pos)' : 'var(--color-neg)' }}
        />
        {/* the baseline: half the members */}
        <span className="absolute inset-y-0 left-1/2 w-px bg-edge-strong" />
      </span>
      <span className="w-[34px] text-right">{formatPct(frac, 0)}</span>
    </span>
  )
}

/** The score, with its standing in the population that produced it. The tint is positional — the
 *  best row on screen at this level is fully inked, the worst is bare — and `rank of n` beside it
 *  names the population, so the colour can never be read as an absolute verdict. */
function ScoreCell({ node, span }: { node: SectorNode; span: { best: number; worst: number } | null }) {
  if (node.composite == null) {
    return (
      <span className="text-ink-3" title="No member of this group carries a composite yet">
        —
      </span>
    )
  }
  const v = Number(node.composite)
  const width = span ? span.best - span.worst : 0
  // A floor of 8 percent so the weakest row is still visibly a row, and a ceiling of 70 so the
  // strongest never reads as a solid block. A population with no spread gets the middle of that.
  const share = span && width > 0 ? ((v - span.worst) / width) * 0.62 + 0.08 : 0.35
  return (
    <span className="flex items-center justify-end gap-1.5">
      <span
        className="rounded-tile px-1.5 py-px font-display text-[12.5px] font-semibold text-ink"
        style={{ background: `color-mix(in srgb, var(--color-pos) ${(share * 100).toFixed(0)}%, transparent)` }}
      >
        {formatDecimal(node.composite, 1)}
      </span>
      {node.rank != null && (
        <span className="w-[42px] text-right text-[11px] text-ink-3" title={`${node.rank} of ${node.n_ranked} buyable, ranked among its siblings`}>
          {node.rank}/{node.n_ranked}
        </span>
      )}
    </span>
  )
}

function RsCell({ value }: { value: string | null }) {
  return (
    <td className={NUM} style={{ background: rsTint(value) }}>
      {value == null ? <span className="text-ink-3">—</span> : formatPct(value, 1, { sign: true })}
    </td>
  )
}

// ── a row, and its children ─────────────────────────────────────────────────

/** Where a node's own page lives — the sector board and the instrument board are one product, so
 *  every name on it is a door. */
function hrefOf(node: SectorNode): string | null {
  if (node.level === 'sector') return `/sectors/${encodeURIComponent(node.id)}`
  if (node.level === 'theme') return `/themes/${encodeURIComponent(node.id)}`
  if (node.level === 'fund' && node.symbol) return `/etfs/${encodeURIComponent(node.symbol)}`
  return null
}

type RowProps = {
  node: SectorNode
  open: Set<string>
  toggle: (key: string) => void
  /** The score range of this node's SIBLINGS — the population its tint is cut against. Null
   *  when none of them is scored, and then nothing is tinted at all. */
  span: { best: number; worst: number } | null
}

function Row({ node, open, toggle, span }: RowProps) {
  const key = `${node.level}:${node.id}`
  const isOpen = open.has(key)
  const meta = LEVEL[node.level]
  const href = hrefOf(node)
  const kids = node.children
  const kidSpan = scoreSpan(kids)

  return (
    <>
      <tr
        // A sector row is an anchor target: /sectors#energy arrives from a theme's breadcrumb and
        // from anywhere else that names a sector, and the effect below opens it on arrival.
        id={node.level === 'sector' ? node.id : undefined}
        className={`border-t border-hair transition-colors hover:bg-raised ${
          node.level === 'sector' ? 'bg-panel' : ''
        }`}
      >
        <td className="py-1.5 pr-2" style={{ paddingLeft: meta.pad }}>
          <span className="flex items-center gap-1.5">
            {kids.length > 0 ? (
              <button
                type="button"
                onClick={() => toggle(key)}
                aria-expanded={isOpen}
                aria-label={`${isOpen ? 'Collapse' : 'Expand'} ${node.name} — ${count(kids.length, meta.child)}`}
                className="flex h-4 w-4 items-center justify-center rounded text-ink-3 hover:bg-inset hover:text-ink"
              >
                <Chevron open={isOpen} />
              </button>
            ) : (
              <span className="h-4 w-4" />
            )}
            {node.symbol && <span className="dt-symbol shrink-0">{node.symbol}</span>}
            {href ? (
              <Link
                href={href}
                className={`truncate hover:underline ${
                  node.level === 'sector' ? 'font-display text-[13.5px] font-semibold text-ink' : 'text-[13px] text-ink'
                }`}
                title={node.name}
              >
                {node.name}
              </Link>
            ) : (
              <span
                className={`truncate ${
                  node.level === 'sector' ? 'font-display text-[13.5px] font-semibold text-ink' : 'text-[13px] text-ink'
                }`}
                title={node.name}
              >
                {node.name}
              </span>
            )}
          </span>
        </td>
        {/* TWO POPULATIONS, TWO COLUMNS, because the FM asked for both and he was right to:
            "viable is 4 out of 12, and score is 12 out of 12. We should show both numbers." */}
        <td
          className={`${NUM} text-ink-2`}
          title={`${node.n_offered} of ${node.n_funds} funds clear your universe rules — above the liquidity floor, not geared, not inverse. The ranking and the fund to own come from these.`}
        >
          {node.level === 'fund' ? '' : `${node.n_offered}/${node.n_funds}`}
        </td>
        <td
          className={`${NUM} text-ink-2`}
          title={`${node.n_comparable} of ${node.n_funds} funds carry a score that can share a median — everything graded except the geared and inverse. The score, the relative strengths and the breadth on this row are over these.`}
        >
          {node.level === 'fund' ? '' : `${node.n_comparable}/${node.n_funds}`}
        </td>
        <td className={NUM}>
          <ScoreCell node={node} span={span} />
        </td>
        <td className={NUM}>
          <BreadthBar frac={node.above_ema200_frac} />
        </td>
        {SECTOR_WINDOWS.map((w) => (
          <RsCell key={w} value={node.rs[w]} />
        ))}
        <td className={`${NUM} text-ink-2`} title={node.aum_usd ? `${node.aum_usd} USD` : undefined}>
          {formatUsdCompact(node.aum_usd)}
        </td>
        <td className="px-2 py-1.5 text-left text-[12px]">
          {node.level !== 'fund' && node.top_symbol ? (
            <Link
              href={`/etfs/${encodeURIComponent(node.top_symbol)}`}
              className="dt-symbol hover:underline"
              title={node.top_name ?? undefined}
            >
              {node.top_symbol}
            </Link>
          ) : (
            <span className="text-ink-3">—</span>
          )}
        </td>
      </tr>
      {isOpen &&
        kids.map((k) => (
          <Row key={`${k.level}:${k.id}`} node={k} open={open} toggle={toggle} span={kidSpan} />
        ))}
    </>
  )
}

// ── the table ───────────────────────────────────────────────────────────────

const SORTS: { key: SortKey; label: string }[] = [
  { key: 'composite', label: 'Score' },
  { key: '3m', label: 'vs S&P 3m' },
  { key: '6m', label: 'vs S&P 6m' },
  { key: '12m', label: 'vs S&P 12m' },
  { key: 'breadth', label: 'Breadth' },
  { key: 'aum', label: 'Assets' },
  { key: 'name', label: 'Name' },
]

export function SectorHeatmap({
  tree,
  heading = 'Sector · theme · fund',
  emptyNote,
}: {
  tree: SectorTree
  /** What the first column is called. A sector's own page hands this component its THEMES as the
   *  top level, so the header has to say so — the columns are identical either way, which is the
   *  whole reason one component draws both. */
  heading?: string
  emptyNote?: string
}) {
  const [open, setOpen] = useState<Set<string>>(new Set())
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'composite', dir: -1 })

  // Arriving at /sectors#energy opens Energy and scrolls to it. Read once, on mount: the hash is
  // where the reader came FROM, not a control they keep using, and re-reading it would fight
  // every collapse they make afterwards.
  useEffect(() => {
    const id = decodeURIComponent(window.location.hash.replace(/^#/, ''))
    if (!id) return
    setOpen(new Set([`sector:${id}`]))  // a hash only ever names a sector
    document.getElementById(id)?.scrollIntoView({ block: 'center' })
  }, [])

  /** A row's key in the open set. Derived from the row, never written down: this component is
   *  handed sectors on /sectors and THEMES on a sector's own page, so a literal 'sector:' prefix
   *  is silently wrong on one of them — which is exactly how "Expand all" came to do nothing. */
  const keyOf = (n: SectorNode) => `${n.level}:${n.id}`

  const toggle = (key: string) =>
    setOpen((prev) => {
      const next = new Set(prev)
      if (!next.delete(key)) next.add(key)
      return next
    })

  const rows = useMemo(() => sortTree(tree.rows, sort.key, sort.dir), [tree.rows, sort])
  const span = useMemo(() => scoreSpan(rows), [rows])

  const allOpen = open.size > 0
  const expandAll = () => setOpen(allOpen ? new Set() : new Set(rows.map(keyOf)))

  if (tree.rows.length === 0) {
    return (
      <p className="panel px-4 py-6 text-[13px] text-ink-2">
        {emptyNote ??
          'No fund carries a theme yet. classify_etfs.py writes them and seed_taxonomy.py seeds the ' +
            'categories they point at — until both have run against this schema, this board has ' +
            'nothing real to rank.'}
      </p>
    )
  }

  return (
    <div className="panel overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-hair px-3 py-2">
        <div className="flex flex-wrap items-center gap-1">
          <span className="mr-1 font-num text-[9.5px] uppercase tracking-[0.1em] text-ink-3">Sort</span>
          {SORTS.map((s) => {
            const on = sort.key === s.key
            return (
              <button
                key={s.key}
                type="button"
                onClick={() => setSort((p) => ({ key: s.key, dir: p.key === s.key ? ((p.dir * -1) as 1 | -1) : -1 }))}
                className={`rounded-tile px-2 py-0.5 font-num text-[11px] transition-colors ${
                  on ? 'bg-ink text-panel' : 'text-ink-2 hover:bg-inset'
                }`}
              >
                {s.label}
                {on && <span className="ml-1">{sort.dir === -1 ? '↓' : '↑'}</span>}
              </button>
            )
          })}
        </div>
        <button
          type="button"
          onClick={expandAll}
          className="rounded-tile border border-edge-rule px-2 py-0.5 font-num text-[11px] text-ink-2 hover:bg-inset"
        >
          {allOpen ? 'Collapse all' : 'Expand all'}
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[1010px] border-collapse">
          <thead>
            <tr className="bg-raised">
              <th style={{ ...L, paddingLeft: 8 }}>{heading}</th>
              <th style={R}>
                Buyable{' '}
                <InfoTip title="What you could actually trade">
                  The second number is every fund the classifier put here; the first is how many
                  clear YOUR universe rules — above the liquidity floor, not geared, not inverse,
                  with enough history to measure. The RANKING and the fund to own come from these,
                  because a page that answers &ldquo;which fund do I buy&rdquo; may not answer with
                  one you cannot. Lower the floor on the admin panel and more become buyable.
                </InfoTip>
              </th>
              <th style={R}>
                Scored{' '}
                <InfoTip title="What the score is measured over">
                  How many of the same funds carry a score that can share a median: everything the
                  scorer graded EXCEPT the geared and the inverse, whose returns are a multiple or a
                  negation of the thing and would poison the median — that is how a -3x short ETN
                  came to head Semiconductors. A fund under your liquidity floor is not excluded
                  here: it is an ordinary fund you happen not to be able to trade, and what it did
                  is still evidence about the sector. The Score, the relative strengths and the
                  Breadth on the row are all over this number.
                </InfoTip>
              </th>
              <th style={R}>
                Score{' '}
                <InfoTip title="The median member, and its rank">
                  The MEDIAN composite of the buyable funds in the group — never a mean, so one
                  giant fund cannot carry a theme, and never over funds you could not act on. The
                  shade is cut against the other rows at the same level, and the rank beside it
                  names that population.
                </InfoTip>
              </th>
              <th style={R}>
                Breadth{' '}
                <InfoTip title="How many members are actually rising">
                  Share of the group&apos;s BUYABLE funds trading above their own 200-day average. The
                  hairline in the bar is HALF — right of it, more members are rising than falling.
                  Funds too young for a 200-day line are left out of both sides of the fraction.
                </InfoTip>
              </th>
              {SECTOR_WINDOWS.map((w) => (
                <th key={w} style={R}>
                  vs S&P {w}
                </th>
              ))}
              <th style={R}>Assets</th>
              <th style={L}>
                Best fund{' '}
                <InfoTip title="What you would buy for it">
                  The highest-scoring fund anywhere under this row. Open the row to see it ranked
                  against its alternatives.
                </InfoTip>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <Row key={keyOf(r)} node={r} open={open} toggle={toggle} span={span} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
