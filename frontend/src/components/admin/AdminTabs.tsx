// allow-large: full admin dashboard — 3 tabs (Customization · Activity · Health) with flywheel explainers + live data widgets
'use client'
import { useState } from 'react'
import Link from 'next/link'

type SummaryRow = { label: string; value: string; sub?: string }

type Props = {
  custSummary:    SummaryRow[]
  actSummary:     SummaryRow[]
  healthSummary:  SummaryRow[]
  proposals: Array<{ tier: string; status: string; predicted_ic_delta: string | null; created_at: string }>
  findings:  Array<{ severity: string; finding_class: string; table_name: string | null; message: string; created_at: string }>
  healthRows: Array<{
    table_name: string; schema_name: string; category: string; status: string;
    last_data_date: string | null; freshness_days_lag: number | null;
    null_rate_critical: string | null; notes: string | null
  }>
  healthCheckDate?: string | null
}

const TABS = [
  { key: 'setup',    label: 'Setup & Customization' },
  { key: 'activity', label: 'Engine Activity' },
  { key: 'health',   label: 'Data Health' },
]

function StatusChip({ status }: { status: string }) {
  const cls = status === 'GREEN'  ? 'bg-signal-pos/15 text-signal-pos'
            : status === 'YELLOW' ? 'bg-signal-warn/15 text-signal-warn'
            : status === 'RED'    ? 'bg-signal-neg/15 text-signal-neg'
            : status === 'P0'     ? 'bg-signal-neg/15 text-signal-neg'
            : status === 'P1'     ? 'bg-signal-warn/15 text-signal-warn'
            : status === 'P2'     ? 'bg-paper-rule/30 text-ink-tertiary'
            : status === 'APPROVED' ? 'bg-signal-pos/15 text-signal-pos'
            : status === 'PENDING'  ? 'bg-signal-warn/15 text-signal-warn'
            : status === 'REJECTED' ? 'bg-signal-neg/15 text-signal-neg'
            : 'bg-paper-rule/30 text-ink-tertiary'
  return <span className={`px-2 py-0.5 rounded-[2px] font-mono text-[10px] font-semibold ${cls}`}>{status}</span>
}

function SummaryGrid({ rows }: { rows: SummaryRow[] }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-6">
      {rows.map(r => (
        <div key={r.label} className="bg-paper-soft border-l-4 border-l-teal p-4 rounded-r-[2px]">
          <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-1">{r.label}</div>
          <div className="font-mono text-[24px] font-semibold text-ink-primary leading-none">{r.value}</div>
          {r.sub && <div className="font-sans text-[11px] text-ink-tertiary leading-[1.4] mt-1">{r.sub}</div>}
        </div>
      ))}
    </div>
  )
}

// ============================================================================
// TAB 1: SETUP & CUSTOMIZATION
// ============================================================================

function SetupTab({ summary }: { summary: SummaryRow[] }) {
  return (
    <div className="px-8 py-8">
      <div className="bg-paper-soft border-l-4 border-l-teal p-5 rounded-r-[2px] mb-6">
        <div className="font-serif text-[18px] font-medium text-ink-primary mb-2">The setup → engine → conviction loop</div>
        <p className="font-sans text-[14px] text-ink-secondary leading-[1.6]">
          The numbers on Atlas are the output of three things working together: <strong className="text-ink-primary">thresholds</strong> (what counts as a leader vs laggard), <strong className="text-ink-primary">signal weights</strong> (how to blend 15 raw signals into one composite score), and <strong className="text-ink-primary">auto-approval rules</strong> (when the engine is allowed to retune itself without you).
          When the rules are right, conviction sharpens; when they&apos;re wrong, the engine reverts. That&apos;s the flywheel.
        </p>
      </div>

      <SummaryGrid rows={summary} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-paper-soft border border-paper-rule p-5 rounded-[2px]">
          <div className="font-serif text-[16px] font-medium text-ink-primary mb-1">Thresholds (regime + cell classifiers)</div>
          <p className="font-sans text-[12px] text-ink-secondary leading-[1.55] mb-3">
            These set the bar for what counts as Risk-On vs Risk-Off, Overweight vs Underweight, BUY vs WATCH. Stored in <code className="font-mono text-[10px] bg-paper px-1">atlas_thresholds</code>; loaded daily by the regime classifier. Every change is logged in <code className="font-mono text-[10px] bg-paper px-1">atlas_threshold_history</code> for audit.
          </p>
          <Link href="/admin/thresholds" className="font-sans text-[12px] text-teal hover:underline">→ Edit thresholds</Link>
        </div>

        <div className="bg-paper-soft border border-paper-rule p-5 rounded-[2px]">
          <div className="font-serif text-[16px] font-medium text-ink-primary mb-1">Signal weights (composite score recipe)</div>
          <p className="font-sans text-[12px] text-ink-secondary leading-[1.55] mb-3">
            Composite score = w₁·RS_1m + w₂·RS_3m + ... + w₁₅·factor. Each weight set is tier-specific (T1-T5). When auto-tuning suggests a better recipe, it proposes a candidate set with predicted IC improvement.
          </p>
          <Link href="/admin/weight-performance" className="font-sans text-[12px] text-teal hover:underline">→ Open weight monitoring</Link>
        </div>

        <div className="bg-paper-soft border border-paper-rule p-5 rounded-[2px] lg:col-span-2">
          <div className="font-serif text-[16px] font-medium text-ink-primary mb-1">Auto-approval policy</div>
          <p className="font-sans text-[12px] text-ink-secondary leading-[1.55] mb-3">
            Default: <strong className="text-ink-primary">DRY mode</strong> — Atlas proposes weight changes, you see them in the Activity tab, but they don&apos;t auto-apply until you confirm. Once a tier has 60+ days of live IC data validating the candidate <strong>and</strong> the Bayesian-smoothed predicted-IC delta is ≥0.02, the system can move to <strong className="text-ink-primary">AUTO-APPLY</strong> mode with a 30-day drift-revert safety net.
          </p>
          <div className="flex flex-wrap gap-2">
            <span className="font-mono text-[10px] px-2 py-1 rounded-[2px] bg-signal-warn/15 text-signal-warn">CURRENT: DRY · all proposals require your approval</span>
            <Link href="/admin/composite-proposals" className="font-sans text-[12px] text-teal hover:underline">→ See pending proposals</Link>
          </div>
        </div>
      </div>
    </div>
  )
}

// ============================================================================
// TAB 2: ENGINE ACTIVITY
// ============================================================================

function ActivityTab({ summary, proposals, findings }: { summary: SummaryRow[]; proposals: Props['proposals']; findings: Props['findings'] }) {
  return (
    <div className="px-8 py-8">
      <div className="bg-paper-soft border-l-4 border-l-teal p-5 rounded-r-[2px] mb-6">
        <div className="font-serif text-[18px] font-medium text-ink-primary mb-2">Last 30 days · what the engine did + why</div>
        <p className="font-sans text-[14px] text-ink-secondary leading-[1.6]">
          Every weight proposal here was generated automatically by the nightly cron, then either auto-applied (if it passed the bar) or held for your review.
          Every validator finding is a thing the engine wants you to be aware of — null rates above tolerance, schema drift, sensibility violations.
          Read across this tab to know <strong className="text-ink-primary">what Atlas changed</strong> and <strong className="text-ink-primary">why each change makes the engine sharper</strong>.
        </p>
      </div>

      <SummaryGrid rows={summary} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Weight proposals */}
        <div className="bg-paper-soft border border-paper-rule rounded-[2px] overflow-hidden">
          <div className="px-4 py-3 border-b border-paper-rule">
            <div className="font-serif text-[15px] font-medium text-ink-primary">Recent weight proposals</div>
            <p className="font-sans text-[11px] text-ink-tertiary mt-1 leading-[1.5]">
              For each conviction tier, Atlas tested an alternative weight set. <strong>Predicted Δ IC</strong> = the candidate would predict outcomes this much better. Positive = better; needs &gt;0.02 to be considered.
            </p>
          </div>
          {proposals.length === 0 ? (
            <div className="px-4 py-6 text-center font-sans text-[12px] text-ink-tertiary">No proposals in the last 30 days.</div>
          ) : (
            <table className="w-full font-sans text-[12px]">
              <thead className="bg-paper">
                <tr className="text-left">
                  <th className="px-3 py-2 font-mono text-[10px] text-ink-tertiary uppercase tracking-wider">Tier</th>
                  <th className="px-3 py-2 font-mono text-[10px] text-ink-tertiary uppercase tracking-wider">Status</th>
                  <th className="px-3 py-2 font-mono text-[10px] text-ink-tertiary uppercase tracking-wider text-right">Predicted Δ IC</th>
                  <th className="px-3 py-2 font-mono text-[10px] text-ink-tertiary uppercase tracking-wider">Created</th>
                </tr>
              </thead>
              <tbody>
                {proposals.map((p, i) => {
                  const delta = p.predicted_ic_delta ? parseFloat(p.predicted_ic_delta) : null
                  return (
                    <tr key={i} className="border-t border-paper-rule/60">
                      <td className="px-3 py-2 font-mono text-[12px] text-ink-primary">{p.tier}</td>
                      <td className="px-3 py-2"><StatusChip status={p.status} /></td>
                      <td className={`px-3 py-2 font-mono text-[12px] text-right ${delta != null && delta > 0.02 ? 'text-signal-pos' : delta != null && delta < 0 ? 'text-signal-neg' : 'text-ink-secondary'}`}>
                        {delta != null ? (delta > 0 ? '+' : '') + delta.toFixed(4) : '—'}
                      </td>
                      <td className="px-3 py-2 font-mono text-[11px] text-ink-tertiary">{p.created_at?.slice(0, 10)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Validator findings */}
        <div className="bg-paper-soft border border-paper-rule rounded-[2px] overflow-hidden">
          <div className="px-4 py-3 border-b border-paper-rule">
            <div className="font-serif text-[15px] font-medium text-ink-primary">Recent validator findings</div>
            <p className="font-sans text-[11px] text-ink-tertiary mt-1 leading-[1.5]">
              The validator runs nightly checking data quality, schema integrity, and sensibility (e.g., &quot;is yesterday&apos;s NAV within 20σ of recent history?&quot;). P0 = block, P1 = warn, P2 = note.
            </p>
          </div>
          {findings.length === 0 ? (
            <div className="px-4 py-6 text-center font-sans text-[12px] text-ink-tertiary">No findings in the last 14 days.</div>
          ) : (
            <div className="max-h-[440px] overflow-y-auto">
              <table className="w-full font-sans text-[12px]">
                <thead className="bg-paper sticky top-0">
                  <tr className="text-left">
                    <th className="px-3 py-2 font-mono text-[10px] text-ink-tertiary uppercase tracking-wider">Sev</th>
                    <th className="px-3 py-2 font-mono text-[10px] text-ink-tertiary uppercase tracking-wider">Class</th>
                    <th className="px-3 py-2 font-mono text-[10px] text-ink-tertiary uppercase tracking-wider">Table</th>
                    <th className="px-3 py-2 font-mono text-[10px] text-ink-tertiary uppercase tracking-wider">Message</th>
                  </tr>
                </thead>
                <tbody>
                  {findings.map((f, i) => (
                    <tr key={i} className="border-t border-paper-rule/60">
                      <td className="px-3 py-2"><StatusChip status={f.severity} /></td>
                      <td className="px-3 py-2 font-mono text-[11px] text-ink-secondary">{f.finding_class}</td>
                      <td className="px-3 py-2 font-mono text-[11px] text-ink-secondary">{f.table_name ?? '—'}</td>
                      <td className="px-3 py-2 text-ink-secondary leading-[1.45]" title={f.message}>{f.message?.slice(0, 120)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ============================================================================
// TAB 3: DATA HEALTH
// ============================================================================

function HealthTab({ summary, rows, checkDate }: { summary: SummaryRow[]; rows: Props['healthRows']; checkDate?: string | null }) {
  const [filter, setFilter] = useState<'ALL' | 'RED' | 'YELLOW' | 'GREEN'>('ALL')
  const filtered = filter === 'ALL' ? rows : rows.filter(r => r.status === filter)

  return (
    <div className="px-8 py-8">
      <div className="bg-paper-soft border-l-4 border-l-teal p-5 rounded-r-[2px] mb-6">
        <div className="flex items-baseline justify-between gap-4 mb-2">
          <div className="font-serif text-[18px] font-medium text-ink-primary">Pipeline health · check this if a number looks wrong</div>
          {checkDate && (
            <span className="font-mono text-[11px] text-ink-tertiary shrink-0">
              Last snapshot: <strong className="text-ink-secondary">{checkDate}</strong>
            </span>
          )}
        </div>
        <p className="font-sans text-[14px] text-ink-secondary leading-[1.6]">
          Every night Atlas writes a freshness + null-rate snapshot for every critical table into <code className="font-mono text-[11px] bg-paper px-1">atlas_data_health</code>. GREEN = current and clean; YELLOW = minor lag or null spike; RED = stale or empty (investigate). If any table shows RED, the corresponding page may show stale or missing data.
        </p>
      </div>

      <SummaryGrid rows={summary} />

      <div className="bg-paper-soft border border-paper-rule rounded-[2px] overflow-hidden">
        <div className="px-4 py-3 border-b border-paper-rule flex items-center justify-between">
          <div className="font-serif text-[15px] font-medium text-ink-primary">Today&apos;s health snapshot</div>
          <div className="flex gap-1">
            {(['ALL', 'RED', 'YELLOW', 'GREEN'] as const).map(f => (
              <button key={f} onClick={() => setFilter(f)}
                className={`font-mono text-[10px] px-2 py-1 rounded-[2px] ${filter === f ? 'bg-ink-primary text-paper' : 'text-ink-secondary border border-paper-rule hover:bg-paper'}`}>
                {f}
              </button>
            ))}
          </div>
        </div>
        {filtered.length === 0 ? (
          <div className="px-4 py-6 text-center font-sans text-[12px] text-ink-tertiary">No rows match.</div>
        ) : (
          <div className="max-h-[600px] overflow-y-auto">
            <table className="w-full font-sans text-[12px]">
              <thead className="bg-paper sticky top-0">
                <tr className="text-left">
                  <th className="px-3 py-2 font-mono text-[10px] text-ink-tertiary uppercase tracking-wider">Status</th>
                  <th className="px-3 py-2 font-mono text-[10px] text-ink-tertiary uppercase tracking-wider">Table</th>
                  <th className="px-3 py-2 font-mono text-[10px] text-ink-tertiary uppercase tracking-wider">Cat</th>
                  <th className="px-3 py-2 font-mono text-[10px] text-ink-tertiary uppercase tracking-wider">Last data</th>
                  <th className="px-3 py-2 font-mono text-[10px] text-ink-tertiary uppercase tracking-wider text-right">Lag (d)</th>
                  <th className="px-3 py-2 font-mono text-[10px] text-ink-tertiary uppercase tracking-wider text-right">Null %</th>
                  <th className="px-3 py-2 font-mono text-[10px] text-ink-tertiary uppercase tracking-wider">Notes</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r, i) => (
                  <tr key={i} className="border-t border-paper-rule/60">
                    <td className="px-3 py-2"><StatusChip status={r.status} /></td>
                    <td className="px-3 py-2 font-mono text-[11px] text-ink-primary"><span className="text-ink-tertiary">{r.schema_name}.</span>{r.table_name}</td>
                    <td className="px-3 py-2 font-mono text-[10px] text-ink-tertiary uppercase">{r.category}</td>
                    <td className="px-3 py-2 font-mono text-[11px] text-ink-secondary">{r.last_data_date ?? '—'}</td>
                    <td className="px-3 py-2 font-mono text-[11px] text-ink-secondary text-right">{r.freshness_days_lag ?? '—'}</td>
                    <td className="px-3 py-2 font-mono text-[11px] text-ink-secondary text-right">{r.null_rate_critical ? `${(parseFloat(r.null_rate_critical) * 100).toFixed(1)}%` : '—'}</td>
                    <td className="px-3 py-2 text-ink-tertiary text-[11px] leading-[1.45]">{r.notes ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

// ============================================================================
// Top-level
// ============================================================================

export default function AdminTabs(props: Props) {
  const [tab, setTab] = useState<'setup' | 'activity' | 'health'>('health')

  return (
    <div>
      {/* Tab strip */}
      <div className="px-8 pt-6 pb-0 border-b border-paper-rule bg-paper-soft">
        <div className="flex gap-1">
          {TABS.map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key as 'setup' | 'activity' | 'health')}
              className={`px-4 py-2 font-sans text-[13px] font-medium rounded-t-[2px] transition-all ${
                tab === t.key
                  ? 'bg-paper text-ink-primary border-x border-t border-paper-rule'
                  : 'text-ink-tertiary hover:text-ink-primary'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {tab === 'setup'    && <SetupTab    summary={props.custSummary} />}
      {tab === 'activity' && <ActivityTab summary={props.actSummary} proposals={props.proposals} findings={props.findings} />}
      {tab === 'health'   && <HealthTab   summary={props.healthSummary} rows={props.healthRows} checkDate={props.healthCheckDate} />}
    </div>
  )
}
