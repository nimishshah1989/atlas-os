// allow-large: Admin landing — unified dashboard surfacing all 7 admin features via 3 explainer tabs (Customization · Engine Activity · Data Health)
export const dynamic = 'force-dynamic'

import Link from 'next/link'
import sql from '@/lib/db'
import AdminTabs from '@/components/admin/AdminTabs'

type SummaryRow = { label: string; value: string; sub?: string }

async function getCustomizationSummary(): Promise<SummaryRow[]> {
  const rows = await sql<Array<{ thresholds_n: number; weights_n: number; live_perf_n: number }>>`
    SELECT
      (SELECT COUNT(*) FROM atlas.atlas_thresholds)::int AS thresholds_n,
      (SELECT COUNT(*) FROM atlas.atlas_signal_weights)::int AS weights_n,
      (SELECT COUNT(*) FROM atlas.atlas_signal_weights_live_perf)::int AS live_perf_n
  `
  const r = rows[0]
  return [
    { label: 'Active thresholds', value: String(r.thresholds_n), sub: 'config values driving regime + cell classifiers' },
    { label: 'Active signal weights', value: String(r.weights_n), sub: 'per-tier weights blending ~15 signals into composite score' },
    { label: 'Live-IC data points', value: String(r.live_perf_n), sub: 'rolling performance per weight set' },
  ]
}

async function getActivitySummary(): Promise<SummaryRow[]> {
  const rows = await sql<Array<{ proposals_30d: number; findings_30d: number; ic_recent: number }>>`
    SELECT
      (SELECT COUNT(*) FROM atlas.atlas_weight_proposals WHERE created_at > now() - interval '30 days')::int AS proposals_30d,
      (SELECT COUNT(*) FROM atlas.atlas_validator_findings WHERE created_at > now() - interval '30 days')::int AS findings_30d,
      (SELECT COUNT(*) FROM atlas.atlas_signal_ic_rolling WHERE computed_at > now() - interval '7 days')::int AS ic_recent
  `
  const r = rows[0]
  return [
    { label: 'Weight proposals (30d)', value: String(r.proposals_30d), sub: 'auto-generated; bayesian-smoothed candidates per tier' },
    { label: 'Validator findings (30d)', value: String(r.findings_30d), sub: 'data quality + schema + sensibility checks' },
    { label: 'IC readings (7d)', value: String(r.ic_recent), sub: 'rolling Information Coefficient per signal' },
  ]
}

async function getHealthSummary(): Promise<SummaryRow[]> {
  const rows = await sql<Array<{ green: number; yellow: number; red: number }>>`
    SELECT
      COUNT(*) FILTER (WHERE status = 'GREEN')::int  AS green,
      COUNT(*) FILTER (WHERE status = 'YELLOW')::int AS yellow,
      COUNT(*) FILTER (WHERE status = 'RED')::int    AS red
    FROM atlas.atlas_data_health
    WHERE check_date = (SELECT MAX(check_date) FROM atlas.atlas_data_health)
  `
  const r = rows[0] ?? { green: 0, yellow: 0, red: 0 }
  return [
    { label: 'GREEN tables', value: String(r.green), sub: 'fresh + within tolerance' },
    { label: 'YELLOW tables', value: String(r.yellow), sub: 'minor lag or null-rate above tolerance' },
    { label: 'RED tables',    value: String(r.red),    sub: 'stale or empty — investigate' },
  ]
}

async function getRecentProposals(): Promise<Array<{ tier: string; status: string; predicted_ic_delta: string | null; created_at: string }>> {
  return sql<Array<{ tier: string; status: string; predicted_ic_delta: string | null; created_at: string }>>`
    SELECT
      tier::text,
      status::text,
      predicted_ic_delta::text,
      created_at::text
    FROM atlas.atlas_weight_proposals
    ORDER BY created_at DESC
    LIMIT 12
  `
}

async function getRecentFindings(): Promise<Array<{ severity: string; finding_class: string; table_name: string | null; message: string; created_at: string }>> {
  return sql<Array<{ severity: string; finding_class: string; table_name: string | null; message: string; created_at: string }>>`
    SELECT severity::text, finding_class::text, table_name, message, created_at::text
    FROM atlas.atlas_validator_findings
    WHERE created_at > now() - interval '14 days'
    ORDER BY
      CASE severity::text WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 ELSE 2 END,
      created_at DESC
    LIMIT 12
  `
}

async function getHealthRows(): Promise<Array<{
  table_name: string; schema_name: string; category: string; status: string;
  last_data_date: string | null; freshness_days_lag: number | null;
  null_rate_critical: string | null; notes: string | null
}>> {
  return sql<Array<{
    table_name: string; schema_name: string; category: string; status: string;
    last_data_date: string | null; freshness_days_lag: number | null;
    null_rate_critical: string | null; notes: string | null
  }>>`
    SELECT
      table_name, schema_name, category, status,
      last_data_date::text, freshness_days_lag,
      null_rate_critical::text, notes
    FROM atlas.atlas_data_health
    WHERE check_date = (SELECT MAX(check_date) FROM atlas.atlas_data_health)
    ORDER BY
      CASE status WHEN 'RED' THEN 0 WHEN 'YELLOW' THEN 1 ELSE 2 END,
      freshness_days_lag DESC NULLS LAST,
      table_name
  `
}

async function getHealthCheckDate(): Promise<string | null> {
  const rows = await sql<Array<{ d: string | null }>>`
    SELECT MAX(check_date)::text AS d FROM atlas.atlas_data_health
  `
  return rows[0]?.d ?? null
}

export default async function AdminPage() {
  const [custSummary, actSummary, healthSummary, proposals, findings, healthRows, healthCheckDate] = await Promise.all([
    getCustomizationSummary().catch(() => []),
    getActivitySummary().catch(() => []),
    getHealthSummary().catch(() => []),
    getRecentProposals().catch(() => []),
    getRecentFindings().catch(() => []),
    getHealthRows().catch(() => []),
    getHealthCheckDate().catch(() => null),
  ])

  return (
    <main className="min-h-screen bg-surface-base">
      {/* Hero */}
      <section className="px-8 py-10 border-b border-edge-hair">
        <div className="font-num text-[10px] text-txt-3 uppercase tracking-[0.14em] mb-2">Atlas · Admin</div>
        <h1 className="font-display text-[34px] font-semibold tracking-tight text-txt-1 leading-tight mb-3">
          Engine control + activity + health
        </h1>
        <p className="font-sans text-[15px] text-txt-2 leading-[1.55] max-w-[820px]">
          Atlas auto-tunes itself every day. This page lets you see <strong>what changed</strong>, <strong>why</strong>, and <strong>what improved</strong> — without needing to click-approve every adjustment. Three tabs:
        </p>
        <ul className="font-sans text-[13px] text-txt-3 leading-[1.6] mt-3 ml-4 max-w-[820px] list-disc">
          <li><strong className="text-txt-2">Setup &amp; Customization</strong> — the thresholds + weights + auto-approval rules driving the engine right now.</li>
          <li><strong className="text-txt-2">Engine Activity</strong> — last 30 days of auto-changes with the math that triggered them. The flywheel in action.</li>
          <li><strong className="text-txt-2">Data Health</strong> — every critical table&apos;s freshness + null-rate at a glance. If a number on the site looks wrong, start here.</li>
        </ul>

        {/* Admin sub-pages — Methodology · Data Health · Thresholds · IC Optimization */}
        <nav className="mt-6 flex flex-wrap gap-2 font-sans text-[12px] font-medium">
          <Link href="/methodology" className="rounded-tile border border-edge-hair bg-surface-panel px-3 py-1.5 text-txt-2 shadow-tile transition-colors hover:border-edge-strong hover:text-txt-1">Methodology</Link>
          <Link href="/health" className="rounded-tile border border-edge-hair bg-surface-panel px-3 py-1.5 text-txt-2 shadow-tile transition-colors hover:border-edge-strong hover:text-txt-1">Data Health</Link>
          <Link href="/admin/thresholds" className="rounded-tile border border-edge-hair bg-surface-panel px-3 py-1.5 text-txt-2 shadow-tile transition-colors hover:border-edge-strong hover:text-txt-1">Thresholds</Link>
          <Link href="/admin/composite-proposals" className="rounded-tile border border-edge-hair bg-surface-panel px-3 py-1.5 text-txt-2 shadow-tile transition-colors hover:border-edge-strong hover:text-txt-1">IC Optimization</Link>
        </nav>
      </section>

      <AdminTabs
        custSummary={custSummary}
        actSummary={actSummary}
        healthSummary={healthSummary}
        proposals={proposals}
        findings={findings}
        healthRows={healthRows}
        healthCheckDate={healthCheckDate}
      />

      <section className="px-8 py-8 bg-surface-panel border-t border-edge-hair">
        <div className="font-num text-[11px] text-txt-3 uppercase tracking-wider mb-2">Direct access (drill-down pages)</div>
        <div className="flex flex-wrap gap-3 text-[13px]">
          <Link href="/admin/thresholds"            className="text-brand hover:underline">→ Thresholds editor</Link>
          <Link href="/admin/composite-proposals"   className="text-brand hover:underline">→ Signal proposals</Link>
          <Link href="/admin/weight-performance"    className="text-brand hover:underline">→ Weight monitoring</Link>
          <Link href="/admin/validator"             className="text-brand hover:underline">→ Validator</Link>
          <Link href="/health"                      className="text-brand hover:underline">→ Data health (full)</Link>
          <Link href="/methodology"                 className="text-brand hover:underline">→ Methodology</Link>
        </div>
      </section>
    </main>
  )
}
