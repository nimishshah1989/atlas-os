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
  const cls = status === 'GREEN'  ? 'bg-sig-pos/15 text-sig-pos'
            : status === 'YELLOW' ? 'bg-sig-warn/15 text-sig-warn'
            : status === 'RED'    ? 'bg-sig-neg/15 text-sig-neg'
            : status === 'P0'     ? 'bg-sig-neg/15 text-sig-neg'
            : status === 'P1'     ? 'bg-sig-warn/15 text-sig-warn'
            : status === 'P2'     ? 'bg-surface-inset text-txt-3'
            : status === 'APPROVED' ? 'bg-sig-pos/15 text-sig-pos'
            : status === 'PENDING'  ? 'bg-sig-warn/15 text-sig-warn'
            : status === 'REJECTED' ? 'bg-sig-neg/15 text-sig-neg'
            : 'bg-surface-inset text-txt-3'
  return <span className={`px-2 py-0.5 rounded-tile font-num text-[10px] font-semibold tabular-nums ${cls}`}>{status}</span>
}

function SummaryGrid({ rows }: { rows: SummaryRow[] }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-6">
      {rows.map(r => (
        <div key={r.label} className="bg-surface-raised border-l-4 border-l-brand p-4 rounded-r-tile">
          <div className="font-num text-[10px] text-txt-3 uppercase tracking-wider mb-1">{r.label}</div>
          <div className="font-display text-[24px] font-semibold text-txt-1 leading-none tabular-nums">{r.value}</div>
          {r.sub && <div className="font-sans text-[11px] text-txt-3 leading-[1.4] mt-1">{r.sub}</div>}
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
      <div className="bg-surface-raised border-l-4 border-l-brand p-5 rounded-r-tile mb-6">
        <div className="font-display text-[18px] font-medium text-txt-1 mb-2">The setup → engine → conviction loop</div>
        <p className="font-sans text-[14px] text-txt-2 leading-[1.6]">
          The numbers on Atlas are the output of three things working together: <strong className="text-txt-1">thresholds</strong> (what counts as a leader vs laggard), <strong className="text-txt-1">signal weights</strong> (how to blend 15 raw signals into one composite score), and <strong className="text-txt-1">auto-approval rules</strong> (when the engine is allowed to retune itself without you).
          When the rules are right, conviction sharpens; when they&apos;re wrong, the engine reverts. That&apos;s the flywheel.
        </p>
      </div>

      <SummaryGrid rows={summary} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-surface-panel border border-edge-hair p-5 rounded-tile shadow-tile">
          <div className="font-display text-[16px] font-medium text-txt-1 mb-1">Thresholds (regime + cell classifiers)</div>
          <p className="font-sans text-[12px] text-txt-2 leading-[1.55] mb-3">
            These set the bar for what counts as Risk-On vs Risk-Off, Overweight vs Underweight, BUY vs WATCH. Stored in <code className="font-num text-[10px] bg-surface-inset px-1">atlas_thresholds</code>; loaded daily by the regime classifier. Every change is logged in <code className="font-num text-[10px] bg-surface-inset px-1">atlas_threshold_history</code> for audit.
          </p>
          <Link href="/admin/thresholds" className="font-sans text-[12px] text-brand hover:underline">→ Edit thresholds</Link>
        </div>

        <div className="bg-surface-panel border border-edge-hair p-5 rounded-tile shadow-tile">
          <div className="font-display text-[16px] font-medium text-txt-1 mb-1">Signal weights (composite score recipe)</div>
          <p className="font-sans text-[12px] text-txt-2 leading-[1.55] mb-3">
            Composite score = w₁·RS_1m + w₂·RS_3m + ... + w₁₅·factor. Each weight set is tier-specific (T1-T5). When auto-tuning suggests a better recipe, it proposes a candidate set with predicted IC improvement.
          </p>
          <Link href="/admin/weight-performance" className="font-sans text-[12px] text-brand hover:underline">→ Open weight monitoring</Link>
        </div>

        <div className="bg-surface-panel border border-edge-hair p-5 rounded-tile shadow-tile lg:col-span-2">
          <div className="font-display text-[16px] font-medium text-txt-1 mb-1">Auto-approval policy</div>
          <p className="font-sans text-[12px] text-txt-2 leading-[1.55] mb-3">
            Default: <strong className="text-txt-1">DRY mode</strong> — Atlas proposes weight changes, you see them in the Activity tab, but they don&apos;t auto-apply until you confirm. Once a tier has 60+ days of live IC data validating the candidate <strong>and</strong> the Bayesian-smoothed predicted-IC delta is ≥0.02, the system can move to <strong className="text-txt-1">AUTO-APPLY</strong> mode with a 30-day drift-revert safety net.
          </p>
          <div className="flex flex-wrap gap-2">
            <span className="font-num text-[10px] px-2 py-1 rounded-tile bg-sig-warn/15 text-sig-warn">CURRENT: DRY · all proposals require your approval</span>
            <Link href="/admin/composite-proposals" className="font-sans text-[12px] text-brand hover:underline">→ See pending proposals</Link>
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
      <div className="bg-surface-raised border-l-4 border-l-brand p-5 rounded-r-tile mb-6">
        <div className="font-display text-[18px] font-medium text-txt-1 mb-2">Last 30 days · what the engine did + why</div>
        <p className="font-sans text-[14px] text-txt-2 leading-[1.6]">
          Every weight proposal here was generated automatically by the nightly cron, then either auto-applied (if it passed the bar) or held for your review.
          Every validator finding is a thing the engine wants you to be aware of — null rates above tolerance, schema drift, sensibility violations.
          Read across this tab to know <strong className="text-txt-1">what Atlas changed</strong> and <strong className="text-txt-1">why each change makes the engine sharper</strong>.
        </p>
      </div>

      <SummaryGrid rows={summary} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Weight proposals */}
        <div className="bg-surface-panel border border-edge-hair rounded-panel shadow-panel overflow-hidden">
          <div className="px-4 py-3 border-b border-edge-hair">
            <div className="font-display text-[15px] font-medium text-txt-1">Recent weight proposals</div>
            <p className="font-sans text-[11px] text-txt-3 mt-1 leading-[1.5]">
              For each conviction tier, Atlas tested an alternative weight set. <strong>Predicted Δ IC</strong> = the candidate would predict outcomes this much better. Positive = better; needs &gt;0.02 to be considered.
            </p>
          </div>
          {proposals.length === 0 ? (
            <div className="px-4 py-6 text-center font-sans text-[12px] text-txt-3">No proposals in the last 30 days.</div>
          ) : (
            <table className="w-full font-sans text-[12px]">
              <thead className="bg-surface-raised">
                <tr className="text-left">
                  <th className="px-3 py-2 font-num text-[10px] text-txt-3 uppercase tracking-wider">Tier</th>
                  <th className="px-3 py-2 font-num text-[10px] text-txt-3 uppercase tracking-wider">Status</th>
                  <th className="px-3 py-2 font-num text-[10px] text-txt-3 uppercase tracking-wider text-right">Predicted Δ IC</th>
                  <th className="px-3 py-2 font-num text-[10px] text-txt-3 uppercase tracking-wider">Created</th>
                </tr>
              </thead>
              <tbody>
                {proposals.map((p, i) => {
                  const delta = p.predicted_ic_delta ? parseFloat(p.predicted_ic_delta) : null
                  return (
                    <tr key={i} className="border-t border-edge-hair">
                      <td className="px-3 py-2 font-num text-[12px] text-txt-1">{p.tier}</td>
                      <td className="px-3 py-2"><StatusChip status={p.status} /></td>
                      <td className={`px-3 py-2 font-num text-[12px] text-right tabular-nums ${delta != null && delta > 0.02 ? 'text-sig-pos' : delta != null && delta < 0 ? 'text-sig-neg' : 'text-txt-2'}`}>
                        {delta != null ? (delta > 0 ? '+' : '') + delta.toFixed(4) : '—'}
                      </td>
                      <td className="px-3 py-2 font-num text-[11px] text-txt-3 tabular-nums">{p.created_at?.slice(0, 10)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Validator findings */}
        <div className="bg-surface-panel border border-edge-hair rounded-panel shadow-panel overflow-hidden">
          <div className="px-4 py-3 border-b border-edge-hair">
            <div className="font-display text-[15px] font-medium text-txt-1">Recent validator findings</div>
            <p className="font-sans text-[11px] text-txt-3 mt-1 leading-[1.5]">
              The validator runs nightly checking data quality, schema integrity, and sensibility (e.g., &quot;is yesterday&apos;s NAV within 20σ of recent history?&quot;). P0 = block, P1 = warn, P2 = note.
            </p>
          </div>
          {findings.length === 0 ? (
            <div className="px-4 py-6 text-center font-sans text-[12px] text-txt-3">No findings in the last 14 days.</div>
          ) : (
            <div className="max-h-[440px] overflow-y-auto">
              <table className="w-full font-sans text-[12px]">
                <thead className="bg-surface-raised sticky top-0">
                  <tr className="text-left">
                    <th className="px-3 py-2 font-num text-[10px] text-txt-3 uppercase tracking-wider">Sev</th>
                    <th className="px-3 py-2 font-num text-[10px] text-txt-3 uppercase tracking-wider">Class</th>
                    <th className="px-3 py-2 font-num text-[10px] text-txt-3 uppercase tracking-wider">Table</th>
                    <th className="px-3 py-2 font-num text-[10px] text-txt-3 uppercase tracking-wider">Message</th>
                  </tr>
                </thead>
                <tbody>
                  {findings.map((f, i) => (
                    <tr key={i} className="border-t border-edge-hair">
                      <td className="px-3 py-2"><StatusChip status={f.severity} /></td>
                      <td className="px-3 py-2 font-num text-[11px] text-txt-2">{f.finding_class}</td>
                      <td className="px-3 py-2 font-num text-[11px] text-txt-2">{f.table_name ?? '—'}</td>
                      <td className="px-3 py-2 text-txt-2 leading-[1.45]" title={f.message}>{f.message?.slice(0, 120)}</td>
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
      <div className="bg-surface-raised border-l-4 border-l-brand p-5 rounded-r-tile mb-6">
        <div className="flex items-baseline justify-between gap-4 mb-2">
          <div className="font-display text-[18px] font-medium text-txt-1">Pipeline health · check this if a number looks wrong</div>
          {checkDate && (
            <span className="font-num text-[11px] text-txt-3 shrink-0 tabular-nums">
              Last snapshot: <strong className="text-txt-2">{checkDate}</strong>
            </span>
          )}
        </div>
        <p className="font-sans text-[14px] text-txt-2 leading-[1.6]">
          Every night Atlas writes a freshness + null-rate snapshot for every critical table into <code className="font-num text-[11px] bg-surface-inset px-1">atlas_data_health</code>. GREEN = current and clean; YELLOW = minor lag or null spike; RED = stale or empty (investigate). If any table shows RED, the corresponding page may show stale or missing data.
        </p>
      </div>

      <SummaryGrid rows={summary} />

      <div className="bg-surface-panel border border-edge-hair rounded-panel shadow-panel overflow-hidden">
        <div className="px-4 py-3 border-b border-edge-hair flex items-center justify-between">
          <div className="font-display text-[15px] font-medium text-txt-1">Today&apos;s health snapshot</div>
          <div className="flex gap-1">
            {(['ALL', 'RED', 'YELLOW', 'GREEN'] as const).map(f => (
              <button key={f} onClick={() => setFilter(f)}
                className={`font-num text-[10px] px-2 py-1 rounded-tile ${filter === f ? 'bg-txt-1 text-surface-panel' : 'text-txt-2 border border-edge-hair hover:border-edge-strong'}`}>
                {f}
              </button>
            ))}
          </div>
        </div>
        {filtered.length === 0 ? (
          <div className="px-4 py-6 text-center font-sans text-[12px] text-txt-3">No rows match.</div>
        ) : (
          <div className="max-h-[600px] overflow-y-auto">
            <table className="w-full font-sans text-[12px]">
              <thead className="bg-surface-raised sticky top-0">
                <tr className="text-left">
                  <th className="px-3 py-2 font-num text-[10px] text-txt-3 uppercase tracking-wider">Status</th>
                  <th className="px-3 py-2 font-num text-[10px] text-txt-3 uppercase tracking-wider">Table</th>
                  <th className="px-3 py-2 font-num text-[10px] text-txt-3 uppercase tracking-wider">Cat</th>
                  <th className="px-3 py-2 font-num text-[10px] text-txt-3 uppercase tracking-wider">Last data</th>
                  <th className="px-3 py-2 font-num text-[10px] text-txt-3 uppercase tracking-wider text-right">Lag (d)</th>
                  <th className="px-3 py-2 font-num text-[10px] text-txt-3 uppercase tracking-wider text-right">Null %</th>
                  <th className="px-3 py-2 font-num text-[10px] text-txt-3 uppercase tracking-wider">Notes</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r, i) => (
                  <tr key={i} className="border-t border-edge-hair">
                    <td className="px-3 py-2"><StatusChip status={r.status} /></td>
                    <td className="px-3 py-2 font-num text-[11px] text-txt-1"><span className="text-txt-3">{r.schema_name}.</span>{r.table_name}</td>
                    <td className="px-3 py-2 font-num text-[10px] text-txt-3 uppercase">{r.category}</td>
                    <td className="px-3 py-2 font-num text-[11px] text-txt-2 tabular-nums">{r.last_data_date ?? '—'}</td>
                    <td className="px-3 py-2 font-num text-[11px] text-txt-2 text-right tabular-nums">{r.freshness_days_lag ?? '—'}</td>
                    <td className="px-3 py-2 font-num text-[11px] text-txt-2 text-right tabular-nums">{r.null_rate_critical ? `${(parseFloat(r.null_rate_critical) * 100).toFixed(1)}%` : '—'}</td>
                    <td className="px-3 py-2 text-txt-3 text-[11px] leading-[1.45]">{r.notes ?? '—'}</td>
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
      <div className="px-8 pt-6 pb-0 border-b border-edge-hair bg-surface-base">
        <div className="flex gap-1">
          {TABS.map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key as 'setup' | 'activity' | 'health')}
              className={`px-4 py-2 font-sans text-[13px] font-medium rounded-t-tile transition-all ${
                tab === t.key
                  ? 'bg-surface-panel text-txt-1 border-x border-t border-edge-hair'
                  : 'text-txt-3 hover:text-txt-1'
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
