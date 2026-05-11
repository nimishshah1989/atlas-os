// frontend/src/app/intelligence/page.tsx
// Morning dashboard — aggregates regime, brief, sector rotation, breakouts,
// RS leaders, and deterioration watch into a single scannable view.
// Server component. Layout: left col (regime + sectors + breakouts) |
//                           right col (brief + RS leaders + deterioration).
import Link from 'next/link'
import { TrendingUp, Minus, TrendingDown } from 'lucide-react'
import { getIntelligenceDashboard } from '@/lib/queries/intelligence'
import type {
  RegimeSummary,
  BriefSummary,
  SectorSnapshotRow,
  BreakoutRow,
  RSLeaderSnapshotRow,
} from '@/lib/queries/intelligence'

export const dynamic = 'force-dynamic'
export const revalidate = 0

// ── Formatters ───────────────────────────────────────────────────────────────

function fmtDate(d: Date | string): string {
  const date = typeof d === 'string' ? new Date(d) : d
  const day   = String(date.getUTCDate()).padStart(2, '0')
  const month = date.toLocaleString('en-IN', { month: 'short', timeZone: 'UTC' })
  return `${day}-${month}-${date.getUTCFullYear()}`
}

function fmtPct(v: string | null, multiply = true, digits = 1): string {
  if (v == null) return '—'
  const n = multiply ? parseFloat(v) * 100 : parseFloat(v)
  const sign = n > 0 ? '+' : ''
  return `${sign}${n.toFixed(digits)}%`
}

function fmtDeploy(v: string | null): string {
  if (v == null) return '—'
  return `${(parseFloat(v) * 100).toFixed(0)}%`
}

function narrativePreview(text: string): string {
  const sentences = text.match(/[^.!?]+[.!?]+/g) ?? []
  return sentences.slice(0, 3).join(' ').trim() || text.slice(0, 300)
}

// ── Sub-components ────────────────────────────────────────────────────────────

const REGIME_CFG: Record<string, { bg: string; border: string; text: string; Icon: typeof TrendingUp }> = {
  'Risk-On':  { bg: 'bg-signal-pos/5', border: 'border-signal-pos/20', text: 'text-signal-pos', Icon: TrendingUp },
  'Cautious': { bg: 'bg-signal-warn/5', border: 'border-signal-warn/20', text: 'text-signal-warn', Icon: Minus },
  'Risk-Off': { bg: 'bg-signal-neg/5', border: 'border-signal-neg/20', text: 'text-signal-neg', Icon: TrendingDown },
}

function RegimeHero({ regime }: { regime: RegimeSummary }) {
  const cfg = REGIME_CFG[regime.regime_state] ?? REGIME_CFG['Cautious']
  const { Icon } = cfg
  return (
    <div className={`rounded-sm border px-5 py-4 ${cfg.bg} ${cfg.border}`}>
      <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-2">
        Market Regime · {fmtDate(regime.date)}
      </div>
      <div className={`flex items-center gap-2 mb-3 ${cfg.text}`}>
        <Icon className="w-4 h-4" />
        <span className="font-serif text-xl font-semibold">{regime.regime_state}</span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-1.5">
        {[
          ['Deploy',    fmtDeploy(regime.deployment_multiplier)],
          ['VIX',       regime.india_vix ? parseFloat(regime.india_vix).toFixed(1) : '—'],
          ['Above EMA-50', fmtPct(regime.pct_above_ema_50)],
          ['A/D Ratio', regime.ad_ratio ? parseFloat(regime.ad_ratio).toFixed(2) : '—'],
          ['McClellan', regime.mcclellan_oscillator ? parseFloat(regime.mcclellan_oscillator).toFixed(0) : '—'],
          ['Net NH-NL', regime.net_new_highs != null ? String(regime.net_new_highs) : '—'],
        ].map(([label, val]) => (
          <div key={label} className="flex items-baseline gap-1.5">
            <span className="font-sans text-[10px] text-ink-tertiary">{label}</span>
            <span className="font-mono text-xs font-semibold text-ink-primary">{val}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

const QUAD_PILL: Record<string, string> = {
  Leading:   'bg-signal-pos/10 text-signal-pos border-signal-pos/30',
  Improving: 'bg-teal/10 text-teal border-teal/30',
  Weakening: 'bg-signal-warn/10 text-signal-warn border-signal-warn/30',
  Lagging:   'bg-signal-neg/10 text-signal-neg border-signal-neg/30',
}

function SectorRotation({ sectors }: { sectors: SectorSnapshotRow[] }) {
  const groups: Record<string, string[]> = { Leading: [], Improving: [], Weakening: [], Lagging: [] }
  for (const s of sectors) {
    if (s.rrg_quadrant && groups[s.rrg_quadrant]) {
      groups[s.rrg_quadrant].push(s.sector_name)
    }
  }
  const quads = Object.entries(groups).filter(([, names]) => names.length > 0)
  if (quads.length === 0) {
    return <p className="font-sans text-xs text-ink-tertiary">No sector data available.</p>
  }
  return (
    <div className="space-y-2">
      {quads.map(([quad, names]) => (
        <div key={quad} className="flex items-start gap-2">
          <span className={`mt-0.5 shrink-0 inline-flex px-2 py-0.5 border rounded-full font-sans text-[10px] font-semibold ${QUAD_PILL[quad] ?? ''}`}>
            {quad}
          </span>
          <span className="font-sans text-xs text-ink-secondary leading-relaxed">
            {names.slice(0, 5).join(', ')}{names.length > 5 ? ` +${names.length - 5}` : ''}
          </span>
        </div>
      ))}
    </div>
  )
}

function TransitionList({ rows, emptyMsg }: { rows: BreakoutRow[]; emptyMsg: string }) {
  if (rows.length === 0) {
    return <p className="font-sans text-xs text-ink-tertiary">{emptyMsg}</p>
  }
  return (
    <div className="space-y-1.5">
      {rows.map((r) => (
        <div key={r.symbol} className="flex items-baseline justify-between gap-4">
          <span className="font-mono text-xs font-semibold text-ink-primary">{r.symbol}</span>
          <span className="font-sans text-[11px] text-ink-tertiary truncate">{r.sector ?? '—'}</span>
          <span className="font-sans text-[11px] text-ink-secondary shrink-0">
            {r.prior_rs_state ?? '—'} → {r.new_rs_state ?? '—'}
          </span>
        </div>
      ))}
    </div>
  )
}

function RSLeadersList({ leaders }: { leaders: RSLeaderSnapshotRow[] }) {
  if (leaders.length === 0) {
    return <p className="font-sans text-xs text-ink-tertiary">No RS leaders today.</p>
  }
  return (
    <div className="space-y-1.5">
      {leaders.map((r) => (
        <div key={r.symbol} className="flex items-baseline justify-between gap-3">
          <span className="font-mono text-xs font-semibold text-ink-primary">{r.symbol}</span>
          <span className="font-sans text-[11px] text-ink-tertiary truncate flex-1 min-w-0">{r.sector ?? '—'}</span>
          <span className={`font-sans text-[10px] font-semibold shrink-0 ${r.rs_state === 'Leader' ? 'text-signal-pos' : 'text-teal'}`}>
            {r.rs_state}
          </span>
          <span className="font-mono text-[11px] text-ink-secondary shrink-0">
            {r.rs_pctile_3m ? `${(parseFloat(r.rs_pctile_3m) * 100).toFixed(0)}%ile` : '—'}
          </span>
        </div>
      ))}
    </div>
  )
}

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border border-paper-rule rounded-sm bg-white p-5">
      <h2 className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-3 pb-2 border-b border-paper-rule">
        {title}
      </h2>
      {children}
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default async function IntelligencePage() {
  const d = await getIntelligenceDashboard()

  return (
    <main className="max-w-[1200px] mx-auto px-4 sm:px-6 py-8 bg-white min-h-screen">
      <header className="mb-6">
        <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">Atlas · Intelligence</div>
        <h1 className="font-serif text-2xl text-ink-primary mt-1">Morning Dashboard</h1>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* ── Left column ── */}
        <div className="space-y-5">
          {/* 1. Hero strip */}
          {d.regime
            ? <RegimeHero regime={d.regime} />
            : <div className="rounded-sm border border-paper-rule px-5 py-4 font-sans text-xs text-ink-tertiary">Regime data unavailable.</div>
          }

          {/* 3. Sector Rotation */}
          <SectionCard title="Sector Rotation">
            <SectorRotation sectors={d.sectors} />
          </SectionCard>

          {/* 4. Breakouts today */}
          <SectionCard title="Breakouts Today">
            <TransitionList rows={d.breakouts} emptyMsg="No breakouts today." />
          </SectionCard>
        </div>

        {/* ── Right column ── */}
        <div className="space-y-5">
          {/* 2. Today's Brief card */}
          <SectionCard title="Today's Brief">
            {d.brief ? (
              <div>
                <div className="font-sans text-[10px] text-ink-tertiary mb-2">{fmtDate(d.brief.as_of_date)}</div>
                <p className="font-serif text-sm leading-relaxed text-ink-primary line-clamp-4">
                  {narrativePreview(d.brief.narrative)}
                </p>
                {d.brief.key_themes.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-3">
                    {d.brief.key_themes.slice(0, 3).map((t, i) => (
                      <span key={i} className="inline-flex px-2.5 py-0.5 bg-paper-rule/30 border border-paper-rule rounded-sm font-sans text-[10px] text-ink-primary">
                        {t}
                      </span>
                    ))}
                  </div>
                )}
                <div className="mt-3">
                  <Link href="/intelligence/daily-brief" className="font-sans text-xs text-teal hover:underline">
                    Read full brief →
                  </Link>
                </div>
              </div>
            ) : (
              <p className="font-sans text-xs text-ink-tertiary">No brief generated yet.</p>
            )}
          </SectionCard>

          {/* 6. Top RS Leaders */}
          <SectionCard title="Top RS Leaders">
            <RSLeadersList leaders={d.rsLeaders} />
          </SectionCard>

          {/* 5. Deterioration watch */}
          <SectionCard title="Deterioration Watch">
            <TransitionList rows={d.deterioration} emptyMsg="No deterioration signals today." />
          </SectionCard>
        </div>
      </div>
    </main>
  )
}
