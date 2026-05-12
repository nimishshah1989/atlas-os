'use client'
import type { FindingGroup, RouteSummary, DayTrend, ValidatorRun } from '@/lib/queries/validator'

// ── known routes with their labels + expected data-point counts ──────────────
const ROUTE_META: Record<string, { label: string; fields: string[]; count: string }> = {
  '/':            { label: 'Regime',      fields: ['regime_state', 'india_vix', 'deployment_multiplier'], count: '3' },
  '/etfs':        { label: 'ETFs',        fields: ['rs_pctile_3m', 'effort_ratio_63', 'above_30w_ma'],     count: '~34' },
  '/intelligence':{ label: 'Intelligence',fields: ['conviction_score', 'rs_pctile_3m'],                   count: '~23' },
  '/sectors':     { label: 'Sectors',     fields: ['sector_state'],                                        count: '24' },
  '/stocks':      { label: 'Stocks',      fields: ['rs_state', 'momentum_state', 'ret_1m', 'ret_3m', 'rs_pctile_3m'], count: '250' },
  '/funds':       { label: 'Funds',       fields: ['nav_state', 'composition_state', 'rs_pctile_3m'],      count: '~1161' },
}

// ── humanise the surface key into a brief explanation ─────────────────────────
const SURFACE_NOTES: Record<string, string> = {
  'fund.rs_pctile_3m':   'Fund has no 3M RS percentile data on the latest nav_date. Data pipeline gap — fund may not have been recomputed on the most recent date.',
  'stock.rs_state':      'RS state displayed by chip component (abbreviates e.g. "Average"→"Avg") differs from DB. Missing data-validator-raw attribute on the cell.',
  'stock.momentum_state':'Momentum state chip abbreviates text; raw attribute missing.',
  'fund.nav_state':      'NAV state chip abbreviates. Check data-validator-raw attribute on cell.',
  'fund.composition_state': 'Composition state chip abbreviates. Check data-validator-raw.',
}

function severity_cls(s: string) {
  if (s === 'P0') return 'text-signal-neg font-semibold'
  if (s === 'P1') return 'text-signal-warn'
  if (s === 'P2') return 'text-ink-secondary'
  return 'text-ink-tertiary'
}

function SeverityPill({ s }: { s: string }) {
  const cls =
    s === 'P0' ? 'bg-signal-neg/10 text-signal-neg border-signal-neg/30' :
    s === 'P1' ? 'bg-signal-warn/10 text-signal-warn border-signal-warn/30' :
    s === 'P2' ? 'bg-ink-tertiary/10 text-ink-secondary border-paper-rule' :
                 'bg-paper text-ink-tertiary border-paper-rule'
  return (
    <span className={`inline-block px-1.5 py-0.5 rounded border font-mono text-[10px] font-medium ${cls}`}>
      {s}
    </span>
  )
}

function fmtDate(d: Date | string | null): string {
  if (!d) return '—'
  const date = typeof d === 'string' ? new Date(d) : d
  return date.toLocaleString('en-IN', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
    timeZone: 'Asia/Kolkata',
  })
}

// Route health card — coloured by worst severity
function RouteCard({ route, summary }: { route: string; summary: RouteSummary | undefined }) {
  const meta = ROUTE_META[route]
  const p0 = summary?.p0 ?? 0
  const p1 = summary?.p1 ?? 0
  const isClean = !summary || (p0 === 0 && p1 === 0 && (summary.p2 ?? 0) === 0)
  const borderCls = p0 > 0 ? 'border-signal-neg/50 bg-signal-neg/5'
    : p1 > 0 ? 'border-signal-warn/40 bg-signal-warn/4'
    : 'border-paper-rule bg-paper'

  return (
    <div className={`border rounded-sm p-3 ${borderCls}`}>
      <div className="flex items-center justify-between mb-1.5">
        <span className="font-sans text-xs font-semibold text-ink-primary">{meta?.label ?? route}</span>
        {isClean
          ? <span className="font-mono text-[10px] text-teal">✓ clean</span>
          : p0 > 0
            ? <span className="font-mono text-[10px] text-signal-neg">{p0} P0</span>
            : <span className="font-mono text-[10px] text-signal-warn">{p1} P1</span>}
      </div>
      <div className="font-mono text-[10px] text-ink-tertiary">{route}</div>
      {meta && (
        <div className="font-sans text-[10px] text-ink-tertiary mt-1">
          {meta.count} pts · {meta.fields.join(', ')}
        </div>
      )}
    </div>
  )
}

// 7-day sparkline using inline bar charts (no external lib)
function TrendBar({ days }: { days: DayTrend[] }) {
  if (!days.length) return <p className="font-sans text-xs text-ink-tertiary">No trend data yet.</p>
  return (
    <div className="overflow-x-auto">
      <table className="w-full font-sans text-xs">
        <thead>
          <tr className="text-ink-tertiary text-[10px] uppercase tracking-wider border-b border-paper-rule">
            <th className="px-3 py-2 text-left">Date</th>
            <th className="px-3 py-2 text-right">P0</th>
            <th className="px-3 py-2 text-right">P1</th>
            <th className="px-3 py-2 text-right">P2</th>
            <th className="px-3 py-2 text-right">Total findings</th>
          </tr>
        </thead>
        <tbody>
          {days.map((d, i) => (
            <tr key={d.run_date} className={`border-b border-paper-rule ${i % 2 === 0 ? 'bg-white' : 'bg-paper'}`}>
              <td className="px-3 py-2 font-mono text-ink-secondary">{d.run_date}</td>
              <td className={`px-3 py-2 text-right font-mono ${Number(d.p0) > 0 ? 'text-signal-neg font-semibold' : 'text-ink-tertiary'}`}>{d.p0}</td>
              <td className={`px-3 py-2 text-right font-mono ${Number(d.p1) > 0 ? 'text-signal-warn' : 'text-ink-tertiary'}`}>{d.p1}</td>
              <td className="px-3 py-2 text-right font-mono text-ink-tertiary">{d.p2}</td>
              <td className="px-3 py-2 text-right font-mono text-ink-primary">{d.total}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

type Props = {
  runs: ValidatorRun[]
  groups: FindingGroup[]
  routeSummary: RouteSummary[]
  trend: DayTrend[]
}

export function ValidatorDashboard({ runs, groups, routeSummary, trend }: Props) {
  const latestRun = runs.find(r => r.scope === 'frontend_diff')
  const totalP0 = groups.filter(g => g.severity === 'P0').reduce((a, g) => a + Number(g.count), 0)
  const totalP1 = groups.filter(g => g.severity === 'P1').reduce((a, g) => a + Number(g.count), 0)
  const totalP2 = groups.filter(g => g.severity === 'P2').reduce((a, g) => a + Number(g.count), 0)

  const summaryByRoute: Record<string, RouteSummary> = {}
  for (const r of routeSummary) summaryByRoute[r.route] = r

  return (
    <div className="space-y-8">
      {/* Header */}
      <header>
        <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">Atlas · Admin · Validator</div>
        <h1 className="font-serif text-2xl text-ink-primary mt-1">Frontend Accuracy Validator</h1>
        <p className="font-sans text-xs text-ink-secondary mt-1 max-w-2xl">
          Phase C nightly Playwright scan — diffs DOM values against SQL source-of-truth across 6 routes and ~1,495 data points.
          Runs after the nightly compute pipeline. No LLM tokens — purely deterministic.
        </p>
        {latestRun && (
          <p className="font-sans text-[11px] text-ink-tertiary mt-2">
            Last run: <span className="text-ink-secondary">{fmtDate(latestRun.started_at)} IST</span>
            &nbsp;·&nbsp;{latestRun.n_findings ?? 0} finding(s)
            &nbsp;·&nbsp;
            <span className={latestRun.status === 'success' ? 'text-teal' : 'text-signal-neg'}>{latestRun.status}</span>
          </p>
        )}
      </header>

      {/* P0 alert banner */}
      {totalP0 > 0 ? (
        <div className="border border-signal-neg/40 bg-signal-neg/5 rounded-sm px-4 py-3">
          <p className="font-sans text-sm font-semibold text-signal-neg">
            ⚠ {totalP0} P0 finding{totalP0 > 1 ? 's' : ''} — data shown on Atlas does not match the DB
          </p>
          <p className="font-sans text-xs text-signal-neg/80 mt-1">
            P0 means the frontend value differs from the DB by more than 10× tolerance. These are incorrect numbers shown to users. Investigate immediately.
          </p>
        </div>
      ) : (
        <div className="border border-teal/30 bg-teal/5 rounded-sm px-4 py-3">
          <p className="font-sans text-sm font-semibold text-teal">✓ P0 clear — no critical data mismatches</p>
          <p className="font-sans text-xs text-teal/70 mt-0.5">
            All values on Atlas match their DB source within tolerance. {totalP1 > 0 && `${totalP1} P1 data gaps exist (see below).`}
          </p>
        </div>
      )}

      {/* Summary + Route health matrix */}
      <section>
        <h2 className="font-sans text-sm font-semibold text-ink-primary mb-3">Route health — latest run</h2>
        <div className="grid grid-cols-3 gap-3 mb-4">
          <div className={`border rounded-sm p-3 ${totalP0 > 0 ? 'border-signal-neg/40 bg-signal-neg/5' : 'border-paper-rule'}`}>
            <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">P0 · Critical</div>
            <div className={`font-mono text-3xl mt-1 ${totalP0 > 0 ? 'text-signal-neg' : 'text-ink-tertiary'}`}>{totalP0}</div>
            <div className="font-sans text-[10px] text-ink-tertiary mt-1">Wrong values shown to users</div>
          </div>
          <div className={`border rounded-sm p-3 ${totalP1 > 0 ? 'border-signal-warn/40 bg-signal-warn/4' : 'border-paper-rule'}`}>
            <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">P1 · Data gaps</div>
            <div className={`font-mono text-3xl mt-1 ${totalP1 > 0 ? 'text-signal-warn' : 'text-ink-tertiary'}`}>{totalP1}</div>
            <div className="font-sans text-[10px] text-ink-tertiary mt-1">Frontend shows null; DB has data</div>
          </div>
          <div className="border border-paper-rule rounded-sm p-3">
            <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">P2 · Minor</div>
            <div className="font-mono text-3xl mt-1 text-ink-tertiary">{totalP2}</div>
            <div className="font-sans text-[10px] text-ink-tertiary mt-1">Within tolerance but non-zero</div>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3">
          {Object.keys(ROUTE_META).map(route => (
            <RouteCard key={route} route={route} summary={summaryByRoute[route]} />
          ))}
        </div>
      </section>

      {/* Aggregated findings */}
      {groups.length > 0 && (
        <section>
          <h2 className="font-sans text-sm font-semibold text-ink-primary mb-3">
            Findings — aggregated by field
          </h2>
          <p className="font-sans text-[11px] text-ink-tertiary mb-3">
            Rows are grouped by (route · field · severity). Count shows how many instruments are affected.
            P0 = wrong value displayed. P1 = field absent on frontend but exists in DB.
          </p>
          <div className="border border-paper-rule rounded-sm overflow-hidden">
            <table className="w-full font-sans text-xs">
              <thead>
                <tr className="bg-paper-rule/30 border-b border-paper-rule text-ink-tertiary text-[10px] uppercase tracking-wider">
                  <th className="px-3 py-2 text-left w-14">Sev</th>
                  <th className="px-3 py-2 text-left">Route</th>
                  <th className="px-3 py-2 text-left">Field</th>
                  <th className="px-3 py-2 text-right w-16">Count</th>
                  <th className="px-3 py-2 text-right">Expected (sample)</th>
                  <th className="px-3 py-2 text-right">Actual (sample)</th>
                  <th className="px-3 py-2 text-left">What this means</th>
                </tr>
              </thead>
              <tbody>
                {groups.map((g, i) => {
                  const note = SURFACE_NOTES[g.surface] ?? ''
                  return (
                    <tr key={i} className={`border-b border-paper-rule last:border-0 ${i % 2 === 0 ? 'bg-white' : 'bg-paper'}`}>
                      <td className="px-3 py-2.5"><SeverityPill s={g.severity} /></td>
                      <td className="px-3 py-2.5 font-mono text-[10px] text-ink-tertiary">{g.route ?? '—'}</td>
                      <td className={`px-3 py-2.5 font-mono text-[10px] ${severity_cls(g.severity)}`}>{g.surface}</td>
                      <td className="px-3 py-2.5 text-right font-mono font-semibold text-ink-primary">{g.count}</td>
                      <td className="px-3 py-2.5 text-right font-mono text-ink-secondary text-[10px]">{g.sample_expected ?? '—'}</td>
                      <td className="px-3 py-2.5 text-right font-mono text-signal-neg text-[10px]">{g.sample_actual ?? '—'}</td>
                      <td className="px-3 py-2.5 text-ink-tertiary max-w-xs text-[10px] leading-relaxed">
                        {note || (g.severity === 'P1' ? 'Frontend shows null; DB has a value. Data not reaching this component.' : 'Value mismatch beyond tolerance.')}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {groups.length === 0 && (
        <section>
          <div className="border border-paper-rule rounded-sm p-8 text-center">
            <p className="font-sans text-sm text-teal">All data points match — no findings in latest run.</p>
          </div>
        </section>
      )}

      {/* 7-day trend */}
      <section>
        <h2 className="font-sans text-sm font-semibold text-ink-primary mb-3">7-day trend</h2>
        <div className="border border-paper-rule rounded-sm overflow-hidden">
          <TrendBar days={trend} />
        </div>
      </section>

      {/* Run history */}
      <section>
        <h2 className="font-sans text-sm font-semibold text-ink-primary mb-3">Run history</h2>
        <div className="border border-paper-rule rounded-sm overflow-hidden">
          <table className="w-full font-sans text-xs">
            <thead>
              <tr className="bg-paper-rule/30 border-b border-paper-rule text-ink-tertiary text-[10px] uppercase tracking-wider">
                <th className="px-3 py-2 text-left">Started (IST)</th>
                <th className="px-3 py-2 text-left">Scope</th>
                <th className="px-3 py-2 text-left">Status</th>
                <th className="px-3 py-2 text-right">Findings</th>
                <th className="px-3 py-2 text-right">Duration</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r, i) => {
                const dur = r.completed_at && r.started_at
                  ? Math.round((new Date(r.completed_at).getTime() - new Date(r.started_at).getTime()) / 1000)
                  : null
                return (
                  <tr key={r.id} className={`border-b border-paper-rule last:border-0 ${i % 2 === 0 ? 'bg-white' : 'bg-paper'}`}>
                    <td className="px-3 py-2 font-mono text-ink-secondary text-[10px]">{fmtDate(r.started_at)}</td>
                    <td className="px-3 py-2 text-ink-primary">{r.scope}</td>
                    <td className="px-3 py-2">
                      <span className={`font-mono text-[10px] ${r.status === 'success' ? 'text-teal' : 'text-signal-neg'}`}>
                        {r.status}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-ink-primary">{r.n_findings ?? '—'}</td>
                    <td className="px-3 py-2 text-right font-mono text-ink-tertiary text-[10px]">
                      {dur != null ? `${dur}s` : '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* Coverage callout */}
      <section className="border border-paper-rule rounded-sm p-4 bg-paper-rule/5">
        <h3 className="font-sans text-xs font-semibold text-ink-primary mb-2">Sampling coverage</h3>
        <div className="grid grid-cols-2 gap-x-8 gap-y-1 font-sans text-[11px] text-ink-secondary">
          <div>Stocks — 50/~750 per run · all rotated in ~15 days</div>
          <div>ETFs — all ~17 per run · 100% daily</div>
          <div>Funds — all ~387 per run · 100% daily</div>
          <div>Sectors — all 12 per run · 100% daily</div>
          <div>Regime — 1 row per run · 100% daily</div>
          <div>Intelligence — ~23 conviction rows · daily</div>
        </div>
        <p className="font-sans text-[10px] text-ink-tertiary mt-2">
          Within 30 days: 100% of stocks, ETFs, funds, sectors, and regime data will have been verified at least once.
        </p>
      </section>
    </div>
  )
}
