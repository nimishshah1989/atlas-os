// Phase C — Validator Admin Page
// Shows nightly frontend accuracy scan results: run history + P0/P1/P2 findings.
export const dynamic = 'force-dynamic'

import { getRecentValidatorRuns, getLatestFrontendFindings } from '@/lib/queries/validator'

function fmtDate(d: Date | string | null): string {
  if (!d) return '—'
  const date = typeof d === 'string' ? new Date(d) : d
  return date.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Kolkata',
  })
}

function fmtDelta(pct: string | null): string {
  if (!pct) return '—'
  const n = parseFloat(pct) * 100
  return isNaN(n) ? pct : `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`
}

function SeverityPill({ severity }: { severity: string }) {
  const cls =
    severity === 'P0'
      ? 'bg-signal-neg/10 text-signal-neg border-signal-neg/30'
      : severity === 'P1'
      ? 'bg-signal-warn/10 text-signal-warn border-signal-warn/30'
      : 'bg-ink-tertiary/10 text-ink-secondary border-ink-tertiary/30'
  return (
    <span className={`inline-block px-1.5 py-0.5 rounded border text-[10px] font-mono font-medium ${cls}`}>
      {severity}
    </span>
  )
}

function StatusPill({ status }: { status: string }) {
  const cls =
    status === 'success'
      ? 'bg-teal/10 text-teal border-teal/30'
      : status === 'failed'
      ? 'bg-signal-neg/10 text-signal-neg border-signal-neg/30'
      : 'bg-ink-tertiary/10 text-ink-secondary border-ink-tertiary/30'
  return (
    <span className={`inline-block px-1.5 py-0.5 rounded border text-[10px] font-mono font-medium ${cls}`}>
      {status}
    </span>
  )
}

export default async function ValidatorAdminPage() {
  const [runs, findings] = await Promise.all([
    getRecentValidatorRuns(20),
    getLatestFrontendFindings(100),
  ])

  const p0 = findings.filter(f => f.severity === 'P0').length
  const p1 = findings.filter(f => f.severity === 'P1').length
  const p2 = findings.filter(f => f.severity === 'P2').length

  const latestRun = runs.find(r => r.scope === 'frontend_diff')

  return (
    <main className="min-h-screen bg-paper px-8 py-6 max-w-7xl mx-auto">
      <header className="mb-6">
        <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">
          Atlas · Admin · Validator
        </div>
        <h1 className="font-serif text-2xl text-ink-primary mt-1">
          Frontend Accuracy Validator
        </h1>
        <p className="font-sans text-xs text-ink-secondary mt-1">
          Phase C nightly Playwright crawler. Diffs DOM values against SQL source-of-truth.
          Runs after MV refresh. Zero LLM tokens — purely deterministic.
        </p>
        {latestRun && (
          <p className="font-sans text-[11px] text-ink-tertiary mt-2">
            Last run: {fmtDate(latestRun.started_at)} IST — {latestRun.n_findings ?? 0} finding(s) &nbsp;·&nbsp;
            <StatusPill status={latestRun.status} />
          </p>
        )}
      </header>

      {/* Summary row */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        {[
          { label: 'P0 — Critical', count: p0, cls: 'border-signal-neg/40 bg-signal-neg/5' },
          { label: 'P1 — High', count: p1, cls: 'border-signal-warn/40 bg-signal-warn/5' },
          { label: 'P2 — Medium', count: p2, cls: 'border-ink-tertiary/30 bg-paper' },
        ].map(item => (
          <div key={item.label} className={`border rounded-sm p-4 ${item.cls}`}>
            <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">{item.label}</div>
            <div className="font-mono text-2xl text-ink-primary mt-1">{item.count}</div>
          </div>
        ))}
      </div>

      {/* Findings table */}
      <section className="mb-8">
        <h2 className="font-sans text-sm font-semibold text-ink-primary mb-3">
          Frontend Diffs (latest run)
        </h2>

        {findings.length === 0 ? (
          <div className="border border-paper-rule rounded-sm bg-white p-6">
            <p className="font-sans text-sm text-ink-secondary">No frontend diffs found — all values within tolerance.</p>
          </div>
        ) : (
          <div className="border border-paper-rule rounded-sm overflow-hidden">
            <table className="w-full font-sans text-xs">
              <thead>
                <tr className="bg-paper-rule/30 border-b border-paper-rule text-ink-tertiary text-[10px] uppercase tracking-wider">
                  <th className="px-3 py-2 text-left">Sev</th>
                  <th className="px-3 py-2 text-left">Surface</th>
                  <th className="px-3 py-2 text-left">Route</th>
                  <th className="px-3 py-2 text-left">Identifier</th>
                  <th className="px-3 py-2 text-right">Expected</th>
                  <th className="px-3 py-2 text-right">Actual</th>
                  <th className="px-3 py-2 text-right">Δ%</th>
                  <th className="px-3 py-2 text-right">Last seen</th>
                </tr>
              </thead>
              <tbody>
                {findings.map((f, i) => (
                  <tr
                    key={f.id}
                    className={`border-b border-paper-rule last:border-0 ${i % 2 === 0 ? 'bg-white' : 'bg-paper'}`}
                  >
                    <td className="px-3 py-2"><SeverityPill severity={f.severity} /></td>
                    <td className="px-3 py-2 font-mono text-ink-primary">{f.surface}</td>
                    <td className="px-3 py-2 text-ink-secondary">{f.route ?? '—'}</td>
                    <td className="px-3 py-2 text-ink-tertiary max-w-[200px] truncate">{f.identifier}</td>
                    <td className="px-3 py-2 text-right font-mono text-ink-secondary">{f.expected_value}</td>
                    <td className="px-3 py-2 text-right font-mono text-signal-neg">{f.actual_value}</td>
                    <td className="px-3 py-2 text-right font-mono text-ink-tertiary">{fmtDelta(f.delta_pct)}</td>
                    <td className="px-3 py-2 text-right text-ink-tertiary">{fmtDate(f.last_seen)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Run history table */}
      <section>
        <h2 className="font-sans text-sm font-semibold text-ink-primary mb-3">
          Run History (all scopes)
        </h2>
        <div className="border border-paper-rule rounded-sm overflow-hidden">
          <table className="w-full font-sans text-xs">
            <thead>
              <tr className="bg-paper-rule/30 border-b border-paper-rule text-ink-tertiary text-[10px] uppercase tracking-wider">
                <th className="px-3 py-2 text-left">Started (IST)</th>
                <th className="px-3 py-2 text-left">Scope</th>
                <th className="px-3 py-2 text-left">Status</th>
                <th className="px-3 py-2 text-right">Findings</th>
                <th className="px-3 py-2 text-right">Completed</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r, i) => (
                <tr
                  key={r.id}
                  className={`border-b border-paper-rule last:border-0 ${i % 2 === 0 ? 'bg-white' : 'bg-paper'}`}
                >
                  <td className="px-3 py-2 font-mono text-ink-secondary">{fmtDate(r.started_at)}</td>
                  <td className="px-3 py-2 text-ink-primary">{r.scope}</td>
                  <td className="px-3 py-2"><StatusPill status={r.status} /></td>
                  <td className="px-3 py-2 text-right font-mono text-ink-primary">{r.n_findings ?? '—'}</td>
                  <td className="px-3 py-2 text-right text-ink-tertiary">{fmtDate(r.completed_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  )
}
