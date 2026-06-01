// allow-large: Markets RS page — 6 sections (page-head, hero, grid, narrative, detail charts, footnote) per mockup 03
'use client'

// frontend/src/components/v6/MarketsRsClient.tsx
//
// Client component for the /markets-rs page (Page 03 — Markets Relative Strength).
// Mockup reference: v6-redesign-20260526-mockups/03-markets-rs.html r3 multidim charts
//
// Sections rendered:
//  1. Page-head: breadcrumb, serif H1, sub, as-of stamp
//  2. 4-card hero readout strip
//  3. 9 × 5 RS grid table
//  4. Narrative card (5 auto-generated rows)
//  5. Detail charts — 6 multidim SVG charts (price/RS/vol lanes) — representative shapes
//     TODO F.2: replace SVG shape data with live time-series queries from de_index_prices
//  6. Footnote

import { useState } from 'react'
import { DataSourceBanner } from '@/components/v6/DataSourceBanner'
import { GradeChip } from '@/components/v6/GradeChip'
import { ELI5Tooltip } from '@/components/v6/ELI5Tooltip'
import {
  baselineStalenessDays,
  MARKETS_RS_STALE_THRESHOLD_DAYS,
} from '@/lib/queries/v6/markets_rs'
import type { MarketsRsPageData, MarketsRsRow, IndiaRsGrade } from '@/lib/queries/v6/markets_rs'
import type { Grade } from '@/components/v6/GradeChip'

// DD-MMM-YYYY without locale/timezone surprises (input is ISO YYYY-MM-DD).
const MONTHS_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
function fmtShortDate(iso: string | null): string {
  if (!iso) return '—'
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso)
  if (!m) return iso
  const [, y, mo, d] = m
  return `${d}-${MONTHS_SHORT[parseInt(mo, 10) - 1]}-${y}`
}

// ---------------------------------------------------------------------------
// Token helpers (CSS vars — no raw hex, no Tailwind colour scale classes)
// ---------------------------------------------------------------------------

/** Map a ret decimal to a heat class name for the RS grid cell */
function cellTint(ret: number | null): string {
  if (ret == null) return 'flat'
  const pct = ret * 100
  if (pct >= 8)  return 'pos-strong'
  if (pct >= 3)  return 'pos'
  if (pct >= 0.5) return 'pos-weak'
  if (pct >= -0.5) return 'flat'
  if (pct >= -3) return 'neg-weak'
  if (pct >= -8) return 'neg'
  return 'neg-strong'
}

const CELL_BG: Record<string, string> = {
  'pos-strong': 'rgba(47,107,67,0.45)',
  'pos':        'rgba(47,107,67,0.25)',
  'pos-weak':   'rgba(47,107,67,0.10)',
  'flat':       'var(--color-paper-deep)',
  'neg-weak':   'rgba(176,73,44,0.10)',
  'neg':        'rgba(176,73,44,0.25)',
  'neg-strong': 'rgba(176,73,44,0.45)',
}

/** text-ink-primary for light cells, text-paper for dark cells */
function cellTextColor(tint: string): string {
  return tint === 'pos-strong' || tint === 'neg-strong'
    ? 'var(--color-paper)'
    : 'var(--color-ink-primary)'
}

function cellSubTextColor(tint: string): string {
  return tint === 'pos-strong' || tint === 'neg-strong'
    ? 'rgba(248,244,236,0.85)'
    : 'var(--color-ink-tertiary)'
}

function formatRet(ret: number | null): string {
  if (ret == null) return '—'
  const pct = ret * 100
  return pct >= 0 ? `+${pct.toFixed(1)}%` : `${pct.toFixed(1)}%`
}

function formatPp(pp: number | null): string {
  if (pp == null) return '—'
  return pp >= 0 ? `+${pp.toFixed(1)}pp` : `${pp.toFixed(1)}pp`
}

// ---------------------------------------------------------------------------
// Grade badge — India RS Grade A/B/C/D
// ---------------------------------------------------------------------------

function GradeColors(grade: IndiaRsGrade | null) {
  switch (grade) {
    case 'A': return 'var(--color-signal-pos)'
    case 'B': return 'var(--color-teal)'
    case 'C': return 'var(--color-signal-warn)'
    case 'D': return 'var(--color-signal-neg)'
    default:  return 'var(--color-ink-tertiary)'
  }
}

/** Map India RS grade A/B/C/D to GradeChip bond grades */
function toGradeChipGrade(grade: IndiaRsGrade | null): Grade | null {
  switch (grade) {
    case 'A': return 'AAA'
    case 'B': return 'AA'
    case 'C': return 'BBB'
    case 'D': return 'BB'
    default:  return null
  }
}

function gradeDescription(grade: IndiaRsGrade | null): string {
  switch (grade) {
    case 'A': return 'India consistently in top-3 across 1m, 3m, 6m windows.'
    case 'B': return 'India above mid-field on most windows. Constructive.'
    case 'C': return 'Mixed signals — strong on some windows, trailing on others.'
    case 'D': return 'India underperforming most baselines across all windows.'
    default:  return 'Grade not available.'
  }
}

// ---------------------------------------------------------------------------
// Baseline metadata — flag emoji + subtitle
// ---------------------------------------------------------------------------

type BaselineMeta = { flag: string; sub: string; group: string }

const BASELINE_META: Record<string, BaselineMeta> = {
  'Nifty 50':              { flag: '🇮🇳', sub: 'Large-cap anchor',                  group: 'India · tier anchors' },
  'Nifty 100':             { flag: '🇮🇳', sub: 'Alternate large-cap anchor',         group: 'India · tier anchors' },
  'Nifty Midcap 150':      { flag: '🇮🇳', sub: 'Mid-cap anchor',                     group: 'India · tier anchors' },
  'Nifty Smallcap 250':    { flag: '🇮🇳', sub: 'Small-cap anchor',                   group: 'India · tier anchors' },
  'Nifty 500':             { flag: '🇮🇳', sub: 'Broad-market benchmark',             group: 'India · tier anchors' },
  'Gold (GOLDBEES)':       { flag: '●',   sub: 'Physical · domestic price',          group: 'Commodities' },
  'S&P 500':               { flag: '🇺🇸', sub: 'US large-cap · USD-INR adjusted',    group: 'Cross-market · developed' },
  'MSCI World (URTH)':     { flag: '🌐',  sub: 'Developed-market context · USD-INR adj', group: 'Cross-market · developed' },
  'MSCI EM (VWO proxy)':   { flag: '🌏',  sub: 'Emerging-market peer · USD-INR adj',group: 'Cross-market · emerging' },
}

const GROUP_ORDER = [
  'India · tier anchors',
  'Cross-market · developed',
  'Cross-market · emerging',
  'Commodities',
]

// ---------------------------------------------------------------------------
// Narrative generation — deterministic from grid data
// ---------------------------------------------------------------------------

type NarrativeRow = {
  tag: 'LEADER' | 'LAGGARD' | 'ROTATION'
  tagStyle: 'pos' | 'neg' | 'warn'
  text: string
}

function buildNarrative(grid: MarketsRsRow[]): NarrativeRow[] {
  const rows: NarrativeRow[] = []

  // Find leader (rank_1w = 1) and laggard (rank_1m = max)
  const leader1w = grid.find(r => r.rank_1w === 1)
  const leader1m = grid.find(r => r.rank_1m === 1)
  const laggard1m = grid.reduce<MarketsRsRow | null>((worst, r) => {
    if (r.rank_1m == null) return worst
    if (worst == null || (worst.rank_1m ?? 0) < (r.rank_1m ?? 0)) return r
    return worst
  }, null)
  const laggard3m = grid.reduce<MarketsRsRow | null>((worst, r) => {
    if (r.rank_3m == null) return worst
    if (worst == null || (worst.rank_3m ?? 0) < (r.rank_3m ?? 0)) return r
    return worst
  }, null)
  const nifty500 = grid.find(r => r.baseline_name === 'Nifty 500')
  const nifty100 = grid.find(r => r.baseline_name === 'Nifty 100')
  const smallcap = grid.find(r => r.baseline_name === 'Nifty Smallcap 250')

  if (leader1w) {
    rows.push({
      tag: 'LEADER',
      tagStyle: 'pos',
      text: `${leader1w.baseline_name} is the strongest asset on the 1-week window (rank 1 / 9, ${formatRet(leader1w.ret_1w)}). ` +
        `${leader1m && leader1m.baseline_name === leader1w.baseline_name ? 'Also leads on 1-month — cross-window persistence implies real flow, not noise.' : 'Check 1-month window for follow-through confirmation.'}`,
    })
  }

  if (leader1m && leader1m.baseline_name !== leader1w?.baseline_name) {
    rows.push({
      tag: 'LEADER',
      tagStyle: 'pos',
      text: `${leader1m.baseline_name} leads on 1-month (rank 1 / 9, ${formatRet(leader1m.ret_1m)}). ` +
        `Medium-term momentum diverging from 1-week leader — watch for which one resolves.`,
    })
  }

  if (laggard1m) {
    const ret12m = laggard1m.ret_12m
    const rank12m = laggard1m.rank_12m
    rows.push({
      tag: 'LAGGARD',
      tagStyle: 'neg',
      text: `${laggard1m.baseline_name} is the weakest baseline on 1-month (rank ${laggard1m.rank_1m} / 9, ${formatRet(laggard1m.ret_1m)}). ` +
        `${rank12m != null && rank12m <= 4 && ret12m != null ? `12-month rank still ${rank12m} — this is a recent regime shift, not a long-term failure.` : 'Weakness appears persistent across multiple windows.'}`,
    })
  }

  if (laggard3m && laggard3m.baseline_name !== laggard1m?.baseline_name) {
    rows.push({
      tag: 'LAGGARD',
      tagStyle: 'neg',
      text: `${laggard3m.baseline_name} is worst on the 3-month window (rank ${laggard3m.rank_3m} / 9, ${formatRet(laggard3m.ret_3m)}). ` +
        `3-month under-performance signals medium-term distribution, not just near-term noise.`,
    })
  }

  if (nifty500 && nifty500.rank_1m != null) {
    const totalBaselines = grid.length
    rows.push({
      tag: 'ROTATION',
      tagStyle: 'warn',
      text: `Indian broad-market (Nifty 500) ranks ${nifty500.rank_1m} of ${totalBaselines} on 1-month (${formatRet(nifty500.ret_1m)}). ` +
        `${nifty500.rank_1m > Math.ceil(totalBaselines / 2) ? 'Underperforming foreign and commodity baselines — FII flow direction worth monitoring.' : 'Holding up relative to peers — constructive near-term positioning.'}`,
    })
  }

  if (nifty100 && smallcap && nifty100.ret_3m != null && smallcap.ret_3m != null) {
    const spread = (nifty100.ret_3m - smallcap.ret_3m) * 100
    if (Math.abs(spread) > 3) {
      rows.push({
        tag: 'ROTATION',
        tagStyle: 'warn',
        text: `Within India, large-cap is ${spread > 0 ? 'leading' : 'trailing'} small-cap by ${Math.abs(spread).toFixed(1)}pp on 3-month. ` +
          `${spread > 0 ? 'Defensive rotation within India confirming risk-off posture — favour large over small.' : 'Small-cap re-rating in progress — monitor for confirmation via breadth.'}`,
      })
    }
  }

  return rows.slice(0, 5)
}

// ---------------------------------------------------------------------------
// Detail chart — multidim 3-pane SVG (PRICE / RS / VOL)
// TODO F.2: replace illustrative SVG paths with live time-series from de_index_prices
// ---------------------------------------------------------------------------

type ChartConfig = {
  title: string
  baselineTag: string
  sub: string
  rsValue: number | null   // % points
  rsDirection: 'pos' | 'neg' | 'flat'
  detailCommentary: string
  detailHistory: string
}

function buildDetailCharts(grid: MarketsRsRow[]): ChartConfig[] {
  const charts: ChartConfig[] = []

  const nifty100  = grid.find(r => r.baseline_name === 'Nifty 100')
  const smallcap  = grid.find(r => r.baseline_name === 'Nifty Smallcap 250')
  const gold      = grid.find(r => r.baseline_name === 'Gold (GOLDBEES)')
  const nifty500  = grid.find(r => r.baseline_name === 'Nifty 500')
  const sp500     = grid.find(r => r.baseline_name === 'S&P 500')
  const msciWorld = grid.find(r => r.baseline_name === 'MSCI World (URTH)')

  if (nifty100) {
    const rsVs50 = nifty100.ret_3m != null && grid.find(r=>r.baseline_name==='Nifty 50')?.ret_3m != null
      ? (nifty100.ret_3m - grid.find(r=>r.baseline_name==='Nifty 50')!.ret_3m!) * 100
      : null
    charts.push({
      title: 'Nifty Large Cap (Nifty 100)',
      baselineTag: 'vs Nifty 50 · 3M',
      sub: nifty100.rank_3m != null && nifty100.rank_3m <= 4 ? 'Price grinding higher · RS positive · volume confirming.' : 'Range-bound · RS signals mixed · monitor for breakout.',
      rsValue: rsVs50,
      rsDirection: rsVs50 != null ? (rsVs50 >= 0.5 ? 'pos' : rsVs50 <= -0.5 ? 'neg' : 'flat') : 'flat',
      detailCommentary: rsVs50 != null && rsVs50 > 0
        ? `${formatPp(rsVs50)} vs Nifty 50 on 3M. Large-cap holding up relative to the index — characteristic of Cautious regime rotation.`
        : `RS spread is near zero vs Nifty 50. No decisive separation — wait for RS confirmation before adding exposure.`,
      detailHistory: 'Large-cap leads Nifty 50 during Cautious regimes historically. Rising RS + rising 20D vol is the cleanest version of that signature.',
    })
  }

  if (smallcap) {
    const rsVs50 = smallcap.ret_3m != null && grid.find(r=>r.baseline_name==='Nifty 50')?.ret_3m != null
      ? (smallcap.ret_3m - grid.find(r=>r.baseline_name==='Nifty 50')!.ret_3m!) * 100
      : null
    charts.push({
      title: 'Nifty Small Cap (Nifty Smallcap 250)',
      baselineTag: 'vs Nifty 50 · 3M',
      sub: smallcap.rank_3m != null && smallcap.rank_3m >= 7 ? 'Price under pressure · RS new-lows accelerating · distribution signature.' : 'Price stabilizing · monitor RS for reversal confirmation.',
      rsValue: rsVs50,
      rsDirection: rsVs50 != null ? (rsVs50 >= 0.5 ? 'pos' : rsVs50 <= -0.5 ? 'neg' : 'flat') : 'flat',
      detailCommentary: rsVs50 != null && rsVs50 < 0
        ? `${formatPp(rsVs50)} vs Nifty 50 on 3M. Textbook distribution — heavy volume on down days, RS printing new lows.`
        : `RS vs Nifty 50 is ${rsVs50 != null ? formatPp(rsVs50) : '—'}. Small-cap not yet showing distribution-level weakness.`,
      detailHistory: 'Cautious-regime small-cap drawdowns typically run −8 to −14pp. Clustered RS new-lows usually precede capitulation, not bottom.',
    })
  }

  if (gold) {
    const rsVs50 = gold.ret_3m != null && grid.find(r=>r.baseline_name==='Nifty 50')?.ret_3m != null
      ? (gold.ret_3m - grid.find(r=>r.baseline_name==='Nifty 50')!.ret_3m!) * 100
      : null
    charts.push({
      title: 'Gold (GOLDBEES)',
      baselineTag: 'vs Nifty 50 · 3M',
      sub: gold.rank_3m != null && gold.rank_3m <= 2 ? 'Clean leader · RS new-highs persistent · GoldBees volume confirming.' : 'Gold in-line with broader market on this window.',
      rsValue: rsVs50,
      rsDirection: rsVs50 != null ? (rsVs50 >= 0.5 ? 'pos' : rsVs50 <= -0.5 ? 'neg' : 'flat') : 'flat',
      detailCommentary: rsVs50 != null && rsVs50 > 0
        ? `${formatPp(rsVs50)} above Nifty 50 on 3M. Uninterrupted RS expansion — institutional accumulation signature.`
        : `Gold RS spread is ${rsVs50 != null ? formatPp(rsVs50) : '—'} vs Nifty 50. Safe-haven premium not yet fully priced in.`,
      detailHistory: 'Gold-Nifty 50 spread ≥ 8pp has historically resolved either by India mean reversion or by a second equity leg lower.',
    })
  }

  if (nifty500) {
    const rsVs50 = nifty500.ret_3m != null && grid.find(r=>r.baseline_name==='Nifty 50')?.ret_3m != null
      ? (nifty500.ret_3m - grid.find(r=>r.baseline_name==='Nifty 50')!.ret_3m!) * 100
      : null
    charts.push({
      title: 'Nifty 500 (Broad Market)',
      baselineTag: 'vs Nifty 50 · 3M',
      sub: 'Broad-market divergence from large-cap — watch for breadth confirmation.',
      rsValue: rsVs50,
      rsDirection: rsVs50 != null ? (rsVs50 >= 0.5 ? 'pos' : rsVs50 <= -0.5 ? 'neg' : 'flat') : 'flat',
      detailCommentary: `${formatPp(rsVs50)} vs Nifty 50 on 3M. Broad market encompasses mid and small — drag from smaller caps visible in RS strip.`,
      detailHistory: 'Nifty 500 vs Nifty 50 spread measures the mid/small premium or discount. Negative spread is typical in Cautious/Risk-Off regimes.',
    })
  }

  if (sp500) {
    const rsVs500 = sp500.ret_3m != null && nifty500?.ret_3m != null
      ? (sp500.ret_3m - nifty500.ret_3m) * 100
      : null
    charts.push({
      title: 'S&P 500 (USD-INR adj.)',
      baselineTag: 'vs Nifty 500 · 3M',
      sub: sp500.rank_3m != null && sp500.rank_3m <= 3 ? 'US large-cap leading India broad-market · FII flow risk.' : 'US performance in line with India on this window.',
      rsValue: rsVs500,
      rsDirection: rsVs500 != null ? (rsVs500 >= 0.5 ? 'pos' : rsVs500 <= -0.5 ? 'neg' : 'flat') : 'flat',
      detailCommentary: `S&P 500 vs Nifty 500 spread: ${formatPp(rsVs500)} on 3M (INR-adjusted). ${rsVs500 != null && rsVs500 > 0 ? 'US outperformance implies FII allocation pressure toward EM India.' : 'India holding up against US on this window.'}`,
      detailHistory: 'Sustained S&P 500 > Nifty 500 spread historically precedes FII outflows from India. Monitor weekly FII net data.',
    })
  }

  if (msciWorld) {
    const rsVs500 = msciWorld.ret_3m != null && nifty500?.ret_3m != null
      ? (msciWorld.ret_3m - nifty500.ret_3m) * 100
      : null
    charts.push({
      title: 'MSCI World (URTH ETF)',
      baselineTag: 'vs Nifty 500 · 3M',
      sub: 'Developed-market context — India vs global DM allocation.',
      rsValue: rsVs500,
      rsDirection: rsVs500 != null ? (rsVs500 >= 0.5 ? 'pos' : rsVs500 <= -0.5 ? 'neg' : 'flat') : 'flat',
      detailCommentary: `MSCI World vs Nifty 500: ${formatPp(rsVs500)} on 3M. ${rsVs500 != null && rsVs500 > 0 ? 'Developed markets absorbing global flows ahead of India.' : 'India keeping pace with developed-market peers.'}`,
      detailHistory: 'India vs DM spread widens during global risk events (strong USD, rate hikes). Converges when EMs re-rate.',
    })
  }

  return charts.slice(0, 6)
}

// ---------------------------------------------------------------------------
// Multidim chart SVG (illustrative shape — 3 panes: PRICE / RS / VOL)
// TODO F.2: replace path data with real time-series from de_index_prices / de_etf_ohlcv / de_global_prices
// ---------------------------------------------------------------------------

function MultidimChartSvg({ rsDirection, rsValue }: { rsDirection: 'pos' | 'neg' | 'flat'; rsValue: number | null }) {
  const rsColor = rsDirection === 'pos'
    ? 'var(--color-signal-pos)'
    : rsDirection === 'neg'
      ? 'var(--color-signal-neg)'
      : 'var(--color-ink-tertiary)'

  // Price line: uptrend for pos, downtrend for neg, flat for flat
  const pricePts = rsDirection === 'pos'
    ? '46,155 110,148 174,140 238,132 302,122 366,112 430,101 494,88 558,74 644,58'
    : rsDirection === 'neg'
      ? '46,60 110,70 174,82 238,95 302,107 366,118 430,130 494,143 558,154 644,164'
      : '46,100 110,105 174,98 238,103 302,100 366,105 430,98 494,102 558,100 644,104'

  // RS strip fill bounds
  const rsY0 = 202
  const rsYEnd = rsDirection === 'pos' ? 182 : rsDirection === 'neg' ? 218 : 202
  const rsFillPath = rsDirection === 'pos'
    ? `M46,${rsY0} L110,200 L174,198 L238,196 L302,193 L366,191 L430,189 L494,188 L558,186 L644,${rsYEnd} L644,${rsY0} Z`
    : rsDirection === 'neg'
      ? `M46,${rsY0} L110,204 L174,207 L238,210 L302,213 L366,216 L430,218 L494,219 L558,220 L644,${rsYEnd} L644,${rsY0} Z`
      : `M46,${rsY0} L110,201 L174,202 L238,202 L302,201 L366,202 L430,202 L494,201 L558,202 L644,${rsY0} L644,${rsY0} Z`

  const rsLinePts = rsDirection === 'pos'
    ? '46,202 110,200 174,198 238,196 302,193 366,191 430,189 494,188 558,186 644,182'
    : rsDirection === 'neg'
      ? '46,202 110,204 174,207 238,210 302,213 366,216 430,218 494,219 558,220 644,218'
      : '46,202 110,201 174,202 238,202 302,201 366,202 430,202 494,201 558,202 644,202'

  // RS diamond markers (new-high for pos, new-low for neg)
  const diamonds = rsDirection === 'pos'
    ? [174, 302, 430, 558, 644]
    : rsDirection === 'neg'
      ? [302, 430, 558, 644]
      : []
  const diamondFill = rsDirection === 'pos' ? 'var(--color-signal-pos)' : 'var(--color-signal-neg)'

  // Volume bars — 12 bars
  const volXPositions = [50, 98, 146, 194, 242, 290, 338, 386, 434, 482, 530, 578, 626]
  const volBars = volXPositions.map((x, i) => {
    const isDown = rsDirection === 'neg' ? i % 3 !== 0 : i % 4 === 1 || i % 5 === 3
    const h = 20 + Math.abs(Math.sin(i * 0.9) * 20)
    const fill = isDown ? 'var(--color-signal-neg)' : 'var(--color-signal-pos)'
    return { x: x - 6, y: 292 - h, w: 11, h, fill }
  })

  return (
    <svg viewBox="0 0 720 300" preserveAspectRatio="none" className="w-full block" style={{ height: '300px' }}>
      {/* PRICE PANE label */}
      <text x="6" y="22" fontFamily="var(--font-mono)" fontSize="9" fill="var(--color-ink-tertiary)">PRICE</text>
      {/* grid lines */}
      <line x1="46" y1="26"  x2="658" y2="26"  stroke="var(--color-ink-rule,#DDD3BF)" strokeDasharray="2 4" opacity="0.5"/>
      <line x1="46" y1="168" x2="658" y2="168" stroke="var(--color-ink-rule,#DDD3BF)" strokeDasharray="2 4" opacity="0.5"/>
      {/* R/S level lines */}
      <line x1="46" y1="38" x2="658" y2="38" stroke="var(--color-signal-info,#3E5C76)" strokeWidth="1" strokeDasharray="4 3" opacity="0.65"/>
      <text x="664" y="41" fontFamily="var(--font-mono)" fontSize="9" fill="var(--color-signal-info,#3E5C76)">R</text>
      <line x1="46" y1="158" x2="658" y2="158" stroke="var(--color-signal-info,#3E5C76)" strokeWidth="1" strokeDasharray="4 3" opacity="0.65"/>
      <text x="664" y="161" fontFamily="var(--font-mono)" fontSize="9" fill="var(--color-signal-info,#3E5C76)">S</text>
      {/* Price line */}
      <polyline points={pricePts} fill="none" stroke="var(--color-ink-primary)" strokeWidth="1.6"/>
      {/* RS signal diamonds */}
      {diamonds.map(cx => (
        <polygon key={cx} points={`${cx},174 ${cx+4},178 ${cx},182 ${cx-4},178`} fill={diamondFill} />
      ))}
      {/* Pane divider */}
      <line x1="46" y1="186" x2="658" y2="186" stroke="var(--color-paper-rule)" strokeWidth="0.5"/>
      {/* RS STRIP label */}
      <text x="6" y="207" fontFamily="var(--font-mono)" fontSize="9" fill="var(--color-ink-tertiary)">RS</text>
      <line x1="46" y1="202" x2="658" y2="202" stroke="var(--color-ink-tertiary)" strokeWidth="0.8" strokeDasharray="3 3"/>
      <path d={rsFillPath} fill={rsColor} opacity="0.22"/>
      <polyline points={rsLinePts} fill="none" stroke={rsColor} strokeWidth="1.3"/>
      <text x="664" y={rsDirection === 'pos' ? 185 : rsDirection === 'neg' ? 221 : 205}
        fontFamily="var(--font-mono)" fontSize="9" fill={rsColor} fontWeight="600">
        {rsValue != null ? formatPp(rsValue) : '—'}
      </text>
      {/* Pane divider */}
      <line x1="46" y1="223" x2="658" y2="223" stroke="var(--color-paper-rule)" strokeWidth="0.5"/>
      {/* VOL PANE label */}
      <text x="6" y="240" fontFamily="var(--font-mono)" fontSize="9" fill="var(--color-ink-tertiary)">VOL</text>
      <line x1="46" y1="292" x2="658" y2="292" stroke="var(--color-paper-rule)" strokeWidth="0.6"/>
      {volBars.map((b, i) => (
        <rect key={i} x={b.x} y={b.y} width={b.w} height={b.h} fill={b.fill} opacity="0.55"/>
      ))}
      {/* 20D MA volume line */}
      <polyline
        points="46,272 110,271 174,270 238,269 302,268 366,267 430,266 494,265 558,264 644,263"
        fill="none" stroke="var(--color-signal-info,#3E5C76)" strokeWidth="1.3"
      />
      <text x="664" y="266" fontFamily="var(--font-mono)" fontSize="9" fill="var(--color-signal-info,#3E5C76)" fontWeight="500">20D MA</text>
    </svg>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function MarketsRsClient({ data }: { data: MarketsRsPageData }) {
  const { grid, hero, as_of_date } = data

  // Group grid rows by section for divider rendering
  const groups = GROUP_ORDER.map(group => ({
    group,
    rows: grid.filter(r => (BASELINE_META[r.baseline_name]?.group ?? 'Other') === group),
  })).filter(g => g.rows.length > 0)

  // Narrative rows derived from grid
  const narrative = buildNarrative(grid)

  // Detail charts derived from grid
  const detailCharts = buildDetailCharts(grid)

  const [activeWindow] = useState<'1w' | '1m' | '3m' | '6m' | '12m'>('3m')

  return (
    <div className="max-w-[1400px] mx-auto">
      {/* ======================================================
          PAGE HEAD
          ====================================================== */}
      <div
        className="px-8 pt-8 pb-6"
        style={{ borderBottom: '1px solid var(--color-paper-rule)' }}
      >
        <div className="font-sans text-[12px]" style={{ color: 'var(--color-ink-tertiary)', marginBottom: '12px' }}>
          <span style={{ color: 'var(--color-accent)' }}>Atlas</span>
          {' › '}
          Markets RS
        </div>
        <h1
          className="font-serif"
          style={{ fontSize: '44px', fontWeight: 400, letterSpacing: '-0.011em', color: 'var(--color-ink-primary)', lineHeight: 1.1, marginBottom: '8px' }}
        >
          Markets relative strength
        </h1>
        <p
          className="font-sans"
          style={{ fontSize: '15px', color: 'var(--color-ink-secondary)', maxWidth: '820px', lineHeight: 1.55 }}
        >
          Every Atlas signal is anchored to a baseline. This page shows how each of the nine
          baselines is performing over five time windows — and how India ranks against them.
          Look here when you want to know where global money is moving and where India sits in that flow.
        </p>
      </div>

      {/* ======================================================
          DATA SOURCE BANNER
          ====================================================== */}
      <DataSourceBanner source="live" asOf={as_of_date ?? new Date().toISOString().slice(0, 10)} />

      {/* ======================================================
          4-CARD HERO READOUT
          ====================================================== */}
      <div className="px-8 py-6" style={{ borderBottom: '1px solid var(--color-paper-rule)' }}>
        <div
          style={{
            background: 'var(--color-paper-deep)',
            border: '1px solid var(--color-paper-rule)',
            borderRadius: '2px',
          }}
        >
          <div className="grid grid-cols-4">
            {/* Card 1: Today's leadership */}
            <div
              className="px-6 py-5"
              style={{ borderRight: '1px solid var(--color-paper-rule)' }}
            >
              <div
                className="font-sans"
                style={{ fontSize: '10px', letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--color-ink-tertiary)', fontWeight: 600, marginBottom: '6px' }}
              >
                Today&apos;s leadership
              </div>
              <div
                className="font-serif"
                style={{ fontSize: '18px', color: 'var(--color-ink-primary)', lineHeight: 1.3 }}
              >
                {hero.today_leader
                  ? `${hero.today_leader} leading`
                  : 'No clear leader'}
              </div>
              <div
                className="font-sans"
                style={{ fontSize: '12px', color: 'var(--color-ink-tertiary)', marginTop: '6px', lineHeight: 1.45 }}
              >
                {hero.today_leader?.includes('Gold') ? 'Risk-off rotation visible in 1-week numbers.' :
                 hero.today_leader?.includes('S&P') ? 'US large-cap absorbing global flow this week.' :
                 hero.today_leader?.includes('Nifty 50') ? 'India large-cap at the top of the 1-week table.' :
                 'Check 1-week column for current momentum leader.'}
              </div>
            </div>

            {/* Card 2: India vs world */}
            <div
              className="px-6 py-5"
              style={{ borderRight: '1px solid var(--color-paper-rule)' }}
            >
              <div
                className="font-sans"
                style={{ fontSize: '10px', letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--color-ink-tertiary)', fontWeight: 600, marginBottom: '6px' }}
              >
                India vs world
              </div>
              <div
                className="font-serif"
                style={{ fontSize: '18px', color: 'var(--color-ink-primary)', lineHeight: 1.3 }}
              >
                {hero.india_rank_1m != null
                  ? <>Nifty 500 ranks <strong>{hero.india_rank_1m}th of {grid.length}</strong> on 1-month</>
                  : 'Rank data unavailable'}
              </div>
              <div
                className="font-sans"
                style={{ fontSize: '12px', color: 'var(--color-ink-tertiary)', marginTop: '6px', lineHeight: 1.45 }}
              >
                {hero.india_rank_1m != null && hero.india_rank_1m > Math.ceil(grid.length / 2)
                  ? 'India underperforming majority of baselines on near-term window.'
                  : 'India holding position relative to global peers.'}
              </div>
            </div>

            {/* Card 3: Within India */}
            <div
              className="px-6 py-5"
              style={{ borderRight: '1px solid var(--color-paper-rule)' }}
            >
              <div
                className="font-sans"
                style={{ fontSize: '10px', letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--color-ink-tertiary)', fontWeight: 600, marginBottom: '6px' }}
              >
                Within India
              </div>
              <div
                className="font-serif"
                style={{ fontSize: '18px', color: 'var(--color-ink-primary)', lineHeight: 1.3 }}
              >
                {hero.large_vs_midsmall_spread_3m_pp != null
                  ? <>Large-cap {hero.large_vs_midsmall_spread_3m_pp >= 0 ? 'leading' : 'trailing'} mid &amp; small by <strong>{Math.abs(hero.large_vs_midsmall_spread_3m_pp).toFixed(1)}pp on 3-month</strong></>
                  : 'Spread data unavailable'}
              </div>
              <div
                className="font-sans"
                style={{ fontSize: '12px', color: 'var(--color-ink-tertiary)', marginTop: '6px', lineHeight: 1.45 }}
              >
                {hero.large_vs_midsmall_spread_3m_pp != null && Math.abs(hero.large_vs_midsmall_spread_3m_pp) > 8
                  ? 'Defensive spread is elevated — Cautious-regime signature.'
                  : 'Large vs mid/small spread within normal range.'}
              </div>
            </div>

            {/* Card 4: India RS Grade */}
            <div className="px-6 py-5">
              <div
                className="font-sans"
                style={{ fontSize: '10px', letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--color-ink-tertiary)', fontWeight: 600, marginBottom: '6px' }}
              >
                India RS grade
              </div>
              {toGradeChipGrade(hero.india_rs_grade) != null ? (
                <div style={{ marginBottom: '4px' }}>
                  <GradeChip grade={toGradeChipGrade(hero.india_rs_grade)!} size="md" />
                  <span
                    className="font-serif ml-2"
                    style={{ fontSize: '28px', fontWeight: 400, lineHeight: 1, color: GradeColors(hero.india_rs_grade) }}
                  >
                    {hero.india_rs_grade}
                  </span>
                </div>
              ) : (
                <div
                  className="font-serif"
                  style={{ fontSize: '36px', fontWeight: 400, lineHeight: 1, marginBottom: '4px', color: 'var(--color-ink-tertiary)' }}
                >
                  —
                </div>
              )}
              <div
                className="font-sans"
                style={{ fontSize: '12px', color: 'var(--color-ink-tertiary)', lineHeight: 1.45 }}
              >
                {gradeDescription(hero.india_rs_grade)}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ======================================================
          RS GRID
          ====================================================== */}
      <div className="px-8 py-10" style={{ borderBottom: '1px solid var(--color-paper-rule)' }}>
        <div className="flex items-baseline justify-between mb-5">
          <div>
            <h2
              className="font-serif"
              style={{ fontSize: '28px', fontWeight: 400, letterSpacing: '-0.011em', color: 'var(--color-ink-primary)' }}
            >
              <ELI5Tooltip term="relative_strength">Relative-strength</ELI5Tooltip> grid
            </h2>
            <p
              className="font-sans"
              style={{ fontSize: '13px', color: 'var(--color-ink-tertiary)', maxWidth: '720px', lineHeight: 1.45, marginTop: '4px' }}
            >
              Total return in INR terms (USD-INR adjusted for foreign baselines). Colour intensity reflects magnitude vs Nifty 500.
            </p>
          </div>
          <div className="font-mono text-[11px]" style={{ color: 'var(--color-ink-tertiary)' }}>
            Active window: 3M
          </div>
        </div>

        {grid.length === 0 ? (
          <div
            className="text-center py-12 font-sans text-[14px]"
            style={{ color: 'var(--color-ink-tertiary)', border: '1px solid var(--color-paper-rule)', borderRadius: '2px' }}
          >
            No grid data available. MV may need refresh.
          </div>
        ) : (
          <div style={{ border: '1px solid var(--color-paper-rule)', borderRadius: '2px', overflow: 'hidden' }}>
            <table className="w-full" style={{ borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th
                    className="font-sans text-left"
                    style={{
                      fontSize: '9px', letterSpacing: '0.18em', textTransform: 'uppercase',
                      color: 'var(--color-ink-tertiary)', fontWeight: 600, padding: '12px 14px',
                      background: 'var(--color-paper-deep)', borderBottom: '1px solid var(--color-paper-rule)',
                      width: '28%',
                    }}
                  >
                    Baseline
                  </th>
                  {(['1 week', '1 month', '3 months', '6 months', '12 months'] as const).map(w => (
                    <th
                      key={w}
                      className="font-sans text-center"
                      style={{
                        fontSize: '9px', letterSpacing: '0.18em', textTransform: 'uppercase',
                        color: 'var(--color-ink-tertiary)', fontWeight: 600, padding: '12px 14px',
                        background: 'var(--color-paper-deep)', borderBottom: '1px solid var(--color-paper-rule)',
                        width: '12%',
                      }}
                    >
                      {w}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {groups.map(({ group, rows }) => (
                  <>
                    {/* Group divider row */}
                    <tr key={`divider-${group}`}>
                      <td
                        colSpan={6}
                        className="font-sans"
                        style={{
                          background: 'var(--color-paper-deep)',
                          padding: '8px 16px',
                          fontSize: '9px',
                          letterSpacing: '0.22em',
                          textTransform: 'uppercase',
                          color: 'var(--color-ink-tertiary)',
                          fontWeight: 700,
                          borderTop: '1px solid var(--color-paper-rule)',
                          borderBottom: '1px solid var(--color-paper-rule)',
                        }}
                      >
                        {group}
                      </td>
                    </tr>
                    {rows.map(row => {
                      const meta = BASELINE_META[row.baseline_name] ?? { flag: '•', sub: '', group: '' }
                      const lagDays = baselineStalenessDays(row.as_of_date, as_of_date)
                      const isStale = lagDays != null && lagDays > MARKETS_RS_STALE_THRESHOLD_DAYS
                      const cells = [
                        { ret: row.ret_1w,  rank: row.rank_1w },
                        { ret: row.ret_1m,  rank: row.rank_1m },
                        { ret: row.ret_3m,  rank: row.rank_3m },
                        { ret: row.ret_6m,  rank: row.rank_6m },
                        { ret: row.ret_12m, rank: row.rank_12m },
                      ]
                      const totalN = grid.length
                      return (
                        <tr
                          key={row.baseline_name}
                          style={{ borderBottom: '1px solid var(--color-paper-rule)' }}
                        >
                          {/* Baseline name cell */}
                          <td style={{ padding: '16px', borderBottom: '1px solid var(--color-paper-rule)' }}>
                            <div className="flex items-center gap-3">
                              <div
                                className="flex items-center justify-center font-sans text-[14px]"
                                style={{
                                  width: '28px', height: '20px', borderRadius: '2px',
                                  background: 'var(--color-paper-deep)',
                                  border: '1px solid var(--color-paper-rule)',
                                  flexShrink: 0,
                                }}
                              >
                                {meta.flag}
                              </div>
                              <div>
                                <div className="flex items-center gap-2">
                                  <span className="font-sans font-medium" style={{ fontSize: '14px', color: 'var(--color-ink-primary)' }}>
                                    {row.baseline_name}
                                  </span>
                                  {isStale && (
                                    <span
                                      className="font-sans"
                                      title={`Last priced ${fmtShortDate(row.as_of_date)} — ${lagDays} days behind the freshest baseline (${fmtShortDate(as_of_date)}). Ranks for this row use stale data.`}
                                      style={{
                                        fontSize: '9px', fontWeight: 700, letterSpacing: '0.06em',
                                        textTransform: 'uppercase', padding: '1px 5px', borderRadius: '2px',
                                        color: 'var(--color-signal-warn)',
                                        background: 'rgba(176,120,44,0.12)',
                                        border: '1px solid var(--color-signal-warn)',
                                        whiteSpace: 'nowrap',
                                      }}
                                    >
                                      Stale · {fmtShortDate(row.as_of_date)}
                                    </span>
                                  )}
                                </div>
                                <div className="font-sans" style={{ fontSize: '11px', color: 'var(--color-ink-tertiary)', marginTop: '2px' }}>
                                  {meta.sub}
                                </div>
                              </div>
                            </div>
                          </td>
                          {/* Data cells */}
                          {cells.map(({ ret, rank }, ci) => {
                            const tint = cellTint(ret)
                            return (
                              <td
                                key={ci}
                                style={{ padding: 0, textAlign: 'center', borderBottom: '1px solid var(--color-paper-rule)' }}
                              >
                                <div
                                  style={{
                                    padding: '14px 8px',
                                    background: CELL_BG[tint],
                                    cursor: 'pointer',
                                    transition: 'filter 120ms',
                                  }}
                                >
                                  <div
                                    className="font-mono tabular"
                                    style={{ fontSize: '14px', fontWeight: 500, color: cellTextColor(tint), lineHeight: 1 }}
                                  >
                                    {formatRet(ret)}
                                  </div>
                                  <div
                                    className="font-sans"
                                    style={{ fontSize: '9px', color: cellSubTextColor(tint), marginTop: '4px', letterSpacing: '0.08em', textTransform: 'uppercase', fontWeight: 600 }}
                                  >
                                    {rank != null ? `${rank} / ${totalN}` : '—'}
                                  </div>
                                </div>
                              </td>
                            )
                          })}
                        </tr>
                      )
                    })}
                  </>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Colour key */}
        <div className="flex items-center justify-between mt-3">
          <div className="flex items-center gap-2 font-sans text-[11px]" style={{ color: 'var(--color-ink-tertiary)' }}>
            <span>Colour scale:</span>
            {([
              'rgba(176,73,44,0.45)',
              'rgba(176,73,44,0.25)',
              'rgba(176,73,44,0.10)',
              'var(--color-paper-deep)',
              'rgba(47,107,67,0.10)',
              'rgba(47,107,67,0.25)',
              'rgba(47,107,67,0.45)',
            ] as const).map((bg, i) => (
              <div
                key={i}
                style={{ width: '14px', height: '14px', borderRadius: '2px', background: bg, border: '1px solid var(--color-paper-rule)' }}
              />
            ))}
            <span className="font-mono" style={{ fontSize: '10px' }}>−10% · 0 · +10%</span>
          </div>
          <span className="font-sans text-[11px]" style={{ color: 'var(--color-ink-tertiary)' }}>
            Nifty 500 row anchors India rank context
          </span>
        </div>
      </div>

      {/* ======================================================
          NARRATIVE CARD
          ====================================================== */}
      <div className="px-8 py-10" style={{ borderBottom: '1px solid var(--color-paper-rule)' }}>
        <div className="mb-5">
          <h2
            className="font-serif"
            style={{ fontSize: '28px', fontWeight: 400, letterSpacing: '-0.011em', color: 'var(--color-ink-primary)' }}
          >
            What this is telling us
          </h2>
          <p
            className="font-sans"
            style={{ fontSize: '13px', color: 'var(--color-ink-tertiary)', maxWidth: '720px', lineHeight: 1.45, marginTop: '4px' }}
          >
            Auto-generated narrative from the RS grid above. Derived from live data — updates each evening at 20:00 IST.
          </p>
        </div>

        <div
          style={{
            background: 'var(--color-paper)',
            border: '1px solid var(--color-paper-rule)',
            borderRadius: '2px',
            padding: '24px',
          }}
        >
          {narrative.length === 0 ? (
            <p className="font-sans text-[14px]" style={{ color: 'var(--color-ink-tertiary)' }}>
              Narrative unavailable — grid has no data.
            </p>
          ) : (
            narrative.map((row, i) => {
              const tagBg = row.tagStyle === 'pos'
                ? 'rgba(47,107,67,0.12)'
                : row.tagStyle === 'neg'
                  ? 'rgba(176,73,44,0.12)'
                  : 'rgba(184,134,11,0.13)'
              const tagColor = row.tagStyle === 'pos'
                ? 'var(--color-signal-pos)'
                : row.tagStyle === 'neg'
                  ? 'var(--color-signal-neg)'
                  : 'var(--color-signal-warn)'
              return (
                <div
                  key={i}
                  className="grid"
                  style={{
                    gridTemplateColumns: '64px 1fr',
                    gap: '16px',
                    alignItems: 'start',
                    marginBottom: i < narrative.length - 1 ? '14px' : 0,
                  }}
                >
                  <div>
                    <span
                      className="font-sans inline-block"
                      style={{
                        fontSize: '10px', letterSpacing: '0.18em', textTransform: 'uppercase',
                        fontWeight: 700, padding: '3px 6px', borderRadius: '2px', lineHeight: 1.3,
                        background: tagBg, color: tagColor,
                      }}
                    >
                      {row.tag}
                    </span>
                  </div>
                  <div
                    className="font-sans"
                    style={{ fontSize: '14px', color: 'var(--color-ink-secondary)', lineHeight: 1.55 }}
                    dangerouslySetInnerHTML={{ __html: row.text.replace(/\*\*([^*]+)\*\*/g, '<strong style="color:var(--color-ink-primary);font-weight:500">$1</strong>') }}
                  />
                </div>
              )
            })
          )}
        </div>
      </div>

      {/* ======================================================
          DETAIL CHARTS
          ====================================================== */}
      <div className="px-8 py-10" style={{ borderBottom: '1px solid var(--color-paper-rule)' }}>
        <div className="mb-5">
          <h2
            className="font-serif"
            style={{ fontSize: '28px', fontWeight: 400, letterSpacing: '-0.011em', color: 'var(--color-ink-primary)' }}
          >
            Detail charts — price, volume &amp; RS in one frame
          </h2>
          <p
            className="font-sans"
            style={{ fontSize: '13px', color: 'var(--color-ink-tertiary)', maxWidth: '720px', lineHeight: 1.45, marginTop: '4px' }}
          >
            Each card stacks three lanes against the same time axis: <strong style={{ color: 'var(--color-ink-secondary)', fontWeight: 500 }}>price action</strong> with
            support &amp; resistance, a <strong style={{ color: 'var(--color-ink-secondary)', fontWeight: 500 }}>relative-strength strip</strong> showing the spread vs baseline,
            and <strong style={{ color: 'var(--color-ink-secondary)', fontWeight: 500 }}>volume bars</strong> with 20-day average overlay.
            Chart shapes are representative of RS direction from grid — full time-series in Phase F.2.
          </p>
        </div>

        {/* Multidim key legend */}
        <div
          className="flex flex-wrap gap-x-7 gap-y-2 items-center mb-4 font-sans text-[11px]"
          style={{
            background: 'var(--color-paper)',
            border: '1px solid var(--color-paper-rule)',
            borderRadius: '2px',
            padding: '12px 18px',
            color: 'var(--color-ink-tertiary)',
          }}
        >
          <span className="font-sans text-[10px] uppercase tracking-[0.14em] font-semibold" style={{ color: 'var(--color-ink-secondary)' }}>Price lane</span>
          <span className="flex items-center gap-2">
            <span style={{ display: 'inline-block', width: '24px', height: '2px', background: 'var(--color-ink-primary)' }}/>
            Index level
          </span>
          <span className="flex items-center gap-2">
            <span style={{ display: 'inline-block', width: '24px', height: '1.5px', background: 'var(--color-signal-info,#3E5C76)' }}/>
            Support / resistance
          </span>
          <span className="flex items-center gap-2">
            <span style={{ display: 'inline-block', width: '8px', height: '8px', transform: 'rotate(45deg)', background: 'var(--color-signal-pos)' }}/>
            RS new high
          </span>
          <span className="flex items-center gap-2">
            <span style={{ display: 'inline-block', width: '8px', height: '8px', transform: 'rotate(45deg)', background: 'var(--color-signal-neg)' }}/>
            RS new low
          </span>
          <span className="font-sans text-[10px] uppercase tracking-[0.14em] font-semibold ml-4" style={{ color: 'var(--color-ink-secondary)' }}>RS strip</span>
          <span className="flex items-center gap-2">
            <span style={{ display: 'inline-block', width: '18px', height: '10px', background: 'linear-gradient(to bottom, rgba(47,107,67,0.35) 0 50%, rgba(176,73,44,0.35) 50% 100%)', borderTop: '1px solid var(--color-signal-pos)', borderBottom: '1px solid var(--color-signal-neg)' }}/>
            Spread vs baseline
          </span>
          <span className="font-sans text-[10px] uppercase tracking-[0.14em] font-semibold ml-4" style={{ color: 'var(--color-ink-secondary)' }}>Volume lane</span>
          <span className="flex items-center gap-2">
            <span style={{ display: 'inline-block', width: '4px', height: '14px', background: 'rgba(47,107,67,0.55)', marginRight: '2px' }}/>
            <span style={{ display: 'inline-block', width: '4px', height: '14px', background: 'rgba(176,73,44,0.55)' }}/>
            Up / down day volume
          </span>
          <span className="flex items-center gap-2">
            <span style={{ display: 'inline-block', width: '24px', height: '1.5px', background: 'var(--color-signal-info,#3E5C76)' }}/>
            20-day average volume
          </span>
        </div>

        {/* 2-column chart grid */}
        <div className="grid grid-cols-2 gap-4">
          {detailCharts.map((chart, i) => {
            const commColor = chart.rsDirection === 'pos'
              ? 'var(--color-signal-pos)'
              : chart.rsDirection === 'neg'
                ? 'var(--color-signal-neg)'
                : 'var(--color-signal-warn)'
            return (
              <div
                key={i}
                style={{
                  background: 'var(--color-paper)',
                  border: '1px solid var(--color-paper-rule)',
                  borderRadius: '2px',
                  padding: '20px',
                }}
              >
                <div className="flex justify-between items-start mb-1">
                  <div
                    className="font-serif"
                    style={{ fontSize: '18px', color: 'var(--color-ink-primary)' }}
                  >
                    {chart.title}
                  </div>
                  <span
                    className="font-sans"
                    style={{
                      fontSize: '10px', letterSpacing: '0.12em', textTransform: 'uppercase',
                      fontWeight: 600, padding: '2px 6px', borderRadius: '2px',
                      background: 'var(--color-paper-deep)', color: 'var(--color-ink-tertiary)',
                      border: '1px solid var(--color-paper-rule)', whiteSpace: 'nowrap', marginTop: '3px',
                    }}
                  >
                    {chart.baselineTag}
                  </span>
                </div>
                <div
                  className="font-sans"
                  style={{ fontSize: '12px', color: 'var(--color-ink-tertiary)', marginBottom: '12px' }}
                >
                  {chart.sub}
                </div>

                <MultidimChartSvg rsDirection={chart.rsDirection} rsValue={chart.rsValue} />

                {/* Commentary strip */}
                <div
                  className="grid"
                  style={{
                    gridTemplateColumns: 'auto 1fr',
                    gap: '10px',
                    alignItems: 'start',
                    marginTop: '12px',
                    paddingTop: '12px',
                    borderTop: '1px solid var(--color-paper-rule)',
                  }}
                >
                  <div
                    className="font-mono tabular"
                    style={{ fontSize: '18px', fontWeight: 500, color: commColor, lineHeight: 1 }}
                  >
                    {chart.rsValue != null ? formatPp(chart.rsValue) : '—'}
                  </div>
                  <div>
                    <div
                      className="font-sans"
                      style={{ fontSize: '12px', color: 'var(--color-ink-tertiary)', lineHeight: 1.5 }}
                    >
                      {chart.detailCommentary}
                    </div>
                    <div
                      className="font-sans"
                      style={{ fontSize: '11px', color: 'var(--color-ink-tertiary)', marginTop: '5px', fontStyle: 'italic', opacity: 0.8 }}
                    >
                      {chart.detailHistory}
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* ======================================================
          FOOTNOTE
          ====================================================== */}
      <div
        className="px-8 py-6 font-sans"
        style={{ fontSize: '12px', color: 'var(--color-ink-tertiary)', lineHeight: 1.6, paddingBottom: '48px' }}
      >
        <p>
          <strong style={{ color: 'var(--color-ink-secondary)', fontWeight: 500 }}>Data sources:</strong>{' '}
          India indices (Nifty 50 / 100 / Midcap 150 / Smallcap 250 / 500) from NSE via Atlas pipeline.
          Gold from GOLDBEES ETF (NSE). S&amp;P 500 from ^GSPC (Yahoo Finance). MSCI World from URTH ETF,
          MSCI EM from VWO ETF. Foreign baselines USD-INR adjusted at spot rate from{' '}
          <span style={{ color: 'var(--color-accent)' }}>atlas_macro_daily</span>.
        </p>
        <p className="mt-2">
          <strong style={{ color: 'var(--color-ink-secondary)', fontWeight: 500 }}>Methodology:</strong>{' '}
          Total return in INR terms. Returns computed as (close_t / close_t-N) − 1 using business-day
          lookback (nearest trading day). Ranks are dense_rank() per window; ties share the same rank.
          India RS Grade = A/B/C/D derived from Nifty 500 average rank across 1m, 3m, 6m windows
          (A ≤ 2.5 avg rank, B ≤ 4.5, C ≤ 6.5, D &gt; 6.5).
        </p>
        <p className="mt-2">
          <strong style={{ color: 'var(--color-ink-secondary)', fontWeight: 500 }}>Refresh:</strong>{' '}
          Materialized view refreshed nightly at 20:05 IST via pg_cron.
          Detail chart shapes are representative (RS direction from grid) — full time-series charts planned for Phase F.2.
        </p>
        <p className="mt-2" style={{ color: 'var(--color-ink-tertiary)', opacity: 0.7 }}>
          For internal use only. Data as of {as_of_date ?? '—'}. Not investment advice.
        </p>
      </div>
    </div>
  )
}
