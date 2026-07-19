// Desk board data — the glass-box view of atlas_foundation.desk_* tables.
// RULE #0: everything here is journaled engine output (agent replies validated
// + hard-filtered in code, outcomes stamped from stored prices); this file only
// joins and formats — no numbers are derived.
import 'server-only'

import sql from '@/lib/db'

type Json = Record<string, unknown>

export type DeskCard = {
  symbol: string
  side: string
  thesis: string
  invalidation: string
  conviction: number | null
  entryRef: number | null
  stop: number | null
  target: number | null
  rr: number | null
  planBasis: string | null
  reduced: boolean
  price: number | null
}

export type DeskCycle = {
  portfolioId: string
  name: string
  charter: string
  nav: number | null
  cycleDate: string
  applied: DeskCard[]
  queued: DeskCard[]
  proposals: { symbol: string; action: string; urgency: string; conviction: number | null; evidence: string[] }[]
  verdicts: { symbol: string; verdict: string; consensus: number | null; reduced: boolean; reason: string }[]
  pmNote: string | null
  errors: string[]
  cvar: { state: string; tail_avg?: number; n?: number } | null
  credibilityRows: number | null
}

const num = (v: unknown): number | null => (v === null || v === undefined ? null : Number(v))

function card(c: Json): DeskCard {
  return {
    symbol: String(c.symbol ?? ''),
    side: String(c.side ?? ''),
    thesis: String(c.thesis ?? ''),
    invalidation: String(c.invalidation ?? ''),
    conviction: num(c.conviction),
    entryRef: num(c.entry_ref),
    stop: num(c.stop),
    target: num(c.target),
    rr: num(c.rr),
    planBasis: c.plan_basis == null ? null : String(c.plan_basis),
    reduced: c.reduced === true,
    price: num(c.price),
  }
}

export async function getDeskCycles(): Promise<{ cycles: DeskCycle[]; regime: string | null }> {
  const rows = await sql`
    select distinct on (dj.portfolio_id)
           dj.portfolio_id::text as pid, m.name,
           coalesce(m.params->>'charter', 'sector_leaders') as charter,
           dj.cycle_date::text as cycle_date, dj.scout, dj.risk, dj.pm,
           dj.applied, dj.queued, dj.errors, dj.inputs_digest, n.nav
    from atlas_foundation.desk_journal dj
    join atlas_foundation.portfolio_master m using (portfolio_id)
    left join lateral (
        select nav from atlas_foundation.portfolio_nav_daily
        where portfolio_id = dj.portfolio_id and run_type = 'live'
        order by date desc limit 1) n on true
    where m.status = 'active' and m.params->>'desk' = 'true'
    order by dj.portfolio_id, dj.cycle_date desc, dj.ts desc`
  const regime = await sql`
    select regime_state from atlas_foundation.atlas_market_regime_daily
    order by date desc limit 1`
  const cycles = rows
    .map((r): DeskCycle => {
      const scout = (r.scout ?? {}) as Json
      const risk = (r.risk ?? {}) as Json
      const pm = (r.pm ?? {}) as Json
      const digest = (r.inputs_digest ?? {}) as Json
      return {
        portfolioId: String(r.pid),
        name: String(r.name),
        charter: String(r.charter),
        nav: num(r.nav),
        cycleDate: String(r.cycle_date),
        applied: ((r.applied ?? []) as Json[]).map(card),
        queued: ((r.queued ?? []) as Json[]).map(card),
        proposals: ((scout.proposals ?? []) as Json[]).map((p) => ({
          symbol: String(p.symbol ?? ''),
          action: String(p.action ?? ''),
          urgency: String(p.urgency ?? ''),
          conviction: num(p.conviction),
          evidence: ((p.evidence ?? []) as unknown[]).map(String),
        })),
        verdicts: ((risk.verdicts ?? []) as Json[]).map((v) => ({
          symbol: String(v.symbol ?? ''),
          verdict: String(v.verdict ?? ''),
          consensus: num(v.consensus),
          reduced: v.reduced === true,
          reason: String(v.reason ?? ''),
        })),
        pmNote: pm.note == null ? null : String(pm.note),
        errors: ((r.errors ?? []) as unknown[]).map(String),
        cvar: (digest.cvar as DeskCycle['cvar']) ?? null,
        credibilityRows: num(digest.credibility_rows),
      }
    })
    .sort((a, b) => a.name.localeCompare(b.name))
  return { cycles, regime: regime.length ? String(regime[0].regime_state) : null }
}

export type DeskIntel = {
  credibility: { dim: string; dimValue: string; n: number; hitRate: number; avgAlpha: number }[]
  lessons: { desk: string; layer: string; confidence: number; lesson: string; contrast: boolean }[]
  hypotheses: { ts: string; hypothesis: string; thresholdKey: string; proposedValue: number; verdict: string }[]
  audits: { ts: string; desk: string; jaccard: number }[]
  alerts: { date: string; symbol: string; kind: string; level: number; quote: number }[]
}

export async function getDeskIntel(): Promise<DeskIntel> {
  const [cred, lessons, hypos, audits, alerts] = await Promise.all([
    sql`select dim, dim_value, n, hit_rate, avg_alpha
        from atlas_foundation.desk_credibility order by dim, n desc`,
    sql`select m.name as desk, l.layer, l.confidence, l.lesson, (l.tags ? 'contrast') as contrast
        from atlas_foundation.desk_lessons l
        join atlas_foundation.portfolio_master m using (portfolio_id)
        where l.active order by l.confidence desc, l.ts desc limit 16`,
    sql`select ts::date::text as ts, hypothesis, threshold_key, proposed_value, verdict
        from atlas_foundation.desk_hypotheses order by ts desc limit 5`,
    sql`select a.ts::date::text as ts, m.name as desk, a.jaccard
        from atlas_foundation.desk_audit a
        join atlas_foundation.portfolio_master m using (portfolio_id)
        order by a.ts desc limit 6`,
    sql`select alert_date::text as date, symbol, kind, level, quote
        from atlas_foundation.desk_alerts order by created_at desc limit 10`,
  ])
  return {
    credibility: cred.map((r) => ({
      dim: String(r.dim),
      dimValue: String(r.dim_value),
      n: Number(r.n),
      hitRate: Number(r.hit_rate),
      avgAlpha: Number(r.avg_alpha),
    })),
    lessons: lessons.map((r) => ({
      desk: String(r.desk),
      layer: String(r.layer),
      confidence: Number(r.confidence),
      lesson: String(r.lesson),
      contrast: r.contrast === true,
    })),
    hypotheses: hypos.map((r) => ({
      ts: String(r.ts),
      hypothesis: String(r.hypothesis),
      thresholdKey: String(r.threshold_key),
      proposedValue: Number(r.proposed_value),
      verdict: String(r.verdict),
    })),
    audits: audits.map((r) => ({ ts: String(r.ts), desk: String(r.desk), jaccard: Number(r.jaccard) })),
    alerts: alerts.map((r) => ({
      date: String(r.date),
      symbol: String(r.symbol),
      kind: String(r.kind),
      level: Number(r.level),
      quote: Number(r.quote),
    })),
  }
}
