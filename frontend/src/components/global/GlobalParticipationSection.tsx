'use client'
import { Users } from 'lucide-react'
import { SectionHeader } from '@/components/regime/SectionHeader'
import { CategorySummary } from '@/components/regime/CategorySummary'
import type { GlobalRegimeRow, CountryRow } from '@/lib/queries/global'

type Props = {
  current: GlobalRegimeRow
  countries: CountryRow[]
}

const POS = '#22c55e'
const NEG = '#ef4444'
const WARN = '#f59e0b'
const TEAL = '#14b8a6'

function getQBarColor(q: number): string {
  if (q === 1) return POS
  if (q === 2) return TEAL
  if (q === 3) return WARN
  if (q === 4) return '#f97316'
  return NEG
}

export function GlobalParticipationSection({ current, countries }: Props) {
  const total = countries.length || 1

  // Signal 1: countries with q_3m_vt <= 2 (Q1/Q2 = strong) / total > 0.35
  const q1q2Count = countries.filter((c) => (c.q_3m_vt ?? 99) <= 2).length
  const sig1 = q1q2Count / total > 0.35

  // Signal 2: DM countries with q_3m_vt <= 2 / DM total > 0.40
  const dmCountries   = countries.filter((c) => c.is_developed_market)
  const dmQ1Q2Count   = dmCountries.filter((c) => (c.q_3m_vt ?? 99) <= 2).length
  const sig2 = dmCountries.length > 0 && dmQ1Q2Count / dmCountries.length > 0.40

  // Signal 3: countries with above_30w_ma = true / countries with above_30w_ma not null > 0.5
  const maValid   = countries.filter((c) => c.above_30w_ma !== null)
  const maAbove   = maValid.filter((c) => c.above_30w_ma === true).length
  const maDenom   = maValid.length || 1
  const sig3 = maAbove / maDenom > 0.5

  const bullishSignals = [sig1, sig2, sig3]
  const bullishCount = bullishSignals.filter(Boolean).length
  const totalCount   = bullishSignals.length

  const emCountries   = countries.filter((c) => !c.is_developed_market)
  const emQ1Q2Count   = emCountries.filter((c) => (c.q_3m_vt ?? 99) <= 2).length

  const partLabel =
    bullishCount === 3 ? 'PARTICIPATION IS STRONG' :
    bullishCount === 2 ? 'PARTICIPATION IS MIXED' :
    'PARTICIPATION IS WEAK'

  const partSummary =
    `${q1q2Count} of ${total} country ETFs are in Q1/Q2 (strong) vs VT on a 3-month basis. ` +
    `DM: ${dmQ1Q2Count} of ${dmCountries.length} in Q1/Q2. EM: ${emQ1Q2Count} of ${emCountries.length} in Q1/Q2. ` +
    `${maAbove} of ${maDenom} countries above their 30-week MA. ` +
    (bullishCount === 3
      ? 'Leadership is sufficiently broad to support the global advance.'
      : bullishCount === 2
        ? 'Mixed participation — DM/EM split or MA breadth thinning.'
        : 'Participation is too thin — global rally quality is suspect.')

  // Q distribution for the visual bar
  const qCounts = [1, 2, 3, 4, 5].map((q) => ({
    q,
    count: countries.filter((c) => c.q_3m_vt === q).length,
  }))
  const qNullCount = countries.filter((c) => c.q_3m_vt == null).length

  // Above/below 30W MA breakdown
  const maBelowCount = maValid.filter((c) => c.above_30w_ma === false).length

  // Region-level participation
  const regions = Array.from(new Set(countries.map((c) => c.region))).sort()
  const regionStats = regions.map((region) => {
    const inRegion = countries.filter((c) => c.region === region)
    const strongInRegion = inRegion.filter((c) => (c.q_3m_vt ?? 99) <= 2).length
    return { region, total: inRegion.length, strong: strongInRegion }
  })

  return (
    <section className="border-b border-paper-rule">
      <SectionHeader
        icon={<Users className="w-4 h-4" strokeWidth={2} />}
        title="Participation"
        description="Participation quality tells us whether the global advance is broad or concentrated. When the majority of country ETFs are in Q1/Q2 (outperforming VT on 3M) and above their 30-week moving average, the global rally has genuine depth. Narrow participation — only a few mega-market countries driving VT — is historically fragile and a leading indicator of eventual reversal."
        bullishCount={bullishCount}
        totalCount={totalCount}
      />

      <CategorySummary
        bullishCount={bullishCount}
        totalCount={totalCount}
        headline={partLabel}
        summary={partSummary}
      />

      <div className="px-6 pb-6 space-y-4">
        {/* Q Distribution bar */}
        <div className="border border-paper-rule rounded-sm p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="font-sans text-xs font-semibold uppercase tracking-wide text-ink-secondary">
              Quintile Distribution vs VT (3M)
            </span>
            <span
              className="font-sans text-[10px] font-medium"
              style={{ color: q1q2Count / total > 0.5 ? POS : q1q2Count / total > 0.35 ? WARN : NEG }}
            >
              {q1q2Count}/{total} in Q1/Q2
            </span>
          </div>
          <p className="font-sans text-xs text-ink-tertiary mb-4 leading-relaxed">
            Each bar shows how many country ETFs fall in each RS quintile versus VT on a 3-month basis. Q1 = top outperformers; Q5 = worst underperformers. A left-skewed distribution (most in Q1/Q2) signals strong global participation.
          </p>

          {/* Stacked bar representation */}
          <div className="flex gap-[2px] h-8 mb-3 rounded overflow-hidden">
            {qCounts.map(({ q, count }) => {
              const pct = (count / total) * 100
              if (pct === 0) return null
              return (
                <div
                  key={q}
                  className="h-full flex items-center justify-center transition-all"
                  style={{ width: `${pct}%`, backgroundColor: getQBarColor(q), opacity: 0.75 }}
                  title={`Q${q}: ${count} countries (${pct.toFixed(0)}%)`}
                />
              )
            })}
            {qNullCount > 0 && (
              <div
                className="h-full bg-paper-rule"
                style={{ width: `${(qNullCount / total) * 100}%` }}
                title={`No data: ${qNullCount} countries`}
              />
            )}
          </div>

          {/* Legend */}
          <div className="flex items-center gap-4 flex-wrap">
            {qCounts.map(({ q, count }) => (
              <div key={q} className="flex items-center gap-1.5">
                <span
                  className="inline-block w-2.5 h-2.5 rounded-sm"
                  style={{ backgroundColor: getQBarColor(q), opacity: 0.75 }}
                />
                <span className="font-sans text-[11px] text-ink-tertiary">
                  Q{q}: <span className="font-medium text-ink-secondary">{count}</span>
                </span>
              </div>
            ))}
            {qNullCount > 0 && (
              <div className="flex items-center gap-1.5">
                <span className="inline-block w-2.5 h-2.5 rounded-sm bg-paper-rule" />
                <span className="font-sans text-[11px] text-ink-tertiary">
                  N/A: <span className="font-medium text-ink-secondary">{qNullCount}</span>
                </span>
              </div>
            )}
          </div>
        </div>

        {/* 2-column: MA status + Region breakdown */}
        <div className="grid grid-cols-2 gap-4">
          {/* 30-Week MA status */}
          <div className="border border-paper-rule rounded-sm p-4">
            <span className="font-sans text-xs font-semibold uppercase tracking-wide text-ink-secondary block mb-3">
              30-Week MA Participation
            </span>
            <p className="font-sans text-xs text-ink-tertiary mb-4 leading-relaxed">
              Weinstein Stage 2 proxy — a country ETF above its rising 30-week MA is in a structural uptrend. Above 50% = healthy global participation.
            </p>
            <div className="flex items-center gap-3 mb-3">
              <div className="flex-1 text-center p-3 rounded-sm" style={{ backgroundColor: `${POS}12` }}>
                <div className="font-mono text-2xl font-semibold" style={{ color: POS }}>{maAbove}</div>
                <div className="font-sans text-[10px] text-ink-tertiary mt-0.5">Above 30W MA</div>
              </div>
              <div className="flex-1 text-center p-3 rounded-sm" style={{ backgroundColor: `${NEG}12` }}>
                <div className="font-mono text-2xl font-semibold" style={{ color: NEG }}>{maBelowCount}</div>
                <div className="font-sans text-[10px] text-ink-tertiary mt-0.5">Below 30W MA</div>
              </div>
            </div>
            {/* MA bar */}
            <div className="h-1.5 rounded-full overflow-hidden bg-paper-rule">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${(maAbove / maDenom) * 100}%`,
                  backgroundColor: maAbove / maDenom > 0.5 ? POS : maAbove / maDenom > 0.35 ? WARN : NEG,
                }}
              />
            </div>
            <div className="flex items-center justify-between mt-1">
              <span className="font-sans text-[10px] text-ink-tertiary">0%</span>
              <span
                className="font-mono text-[10px] font-medium"
                style={{ color: maAbove / maDenom > 0.5 ? POS : WARN }}
              >
                {((maAbove / maDenom) * 100).toFixed(0)}%
              </span>
              <span className="font-sans text-[10px] text-ink-tertiary">100%</span>
            </div>
          </div>

          {/* Region breakdown */}
          <div className="border border-paper-rule rounded-sm p-4">
            <span className="font-sans text-xs font-semibold uppercase tracking-wide text-ink-secondary block mb-3">
              Participation by Region
            </span>
            <p className="font-sans text-xs text-ink-tertiary mb-3 leading-relaxed">
              Share of countries in Q1/Q2 vs VT within each geographic region.
            </p>
            <div className="space-y-2.5">
              {regionStats.map(({ region, total: rTotal, strong }) => {
                const pct = rTotal > 0 ? (strong / rTotal) * 100 : 0
                const color = pct >= 60 ? POS : pct >= 40 ? TEAL : pct >= 25 ? WARN : NEG
                return (
                  <div key={region}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-sans text-[11px] text-ink-secondary">{region}</span>
                      <span className="font-mono text-[11px] tabular-nums" style={{ color }}>
                        {strong}/{rTotal}
                      </span>
                    </div>
                    <div className="h-1 rounded-full overflow-hidden bg-paper-rule">
                      <div
                        className="h-full rounded-full"
                        style={{ width: `${pct}%`, backgroundColor: color }}
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
