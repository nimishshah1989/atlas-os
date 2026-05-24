// frontend/src/app/v6/funds/page.tsx
// v6 funds — ConvictionTape + StyleBox.

import { getScreenFunds } from '@/lib/api/v1'
import { ConvictionTape } from '@/components/v6/ConvictionTape'
import { DataSourceBanner } from '@/components/v6/DataSourceBanner'
import { StyleBox } from '@/components/v6/StyleBox'
import { LinkedFund } from '@/components/ui/LinkedToken'
import { StateBadge } from '@/components/ui/StateBadge'
import { formatINR } from '@/lib/format-inr'
import type { ScreenFund, StyleSize, StyleAxis } from '@/lib/api/v1'

export const dynamic = 'force-dynamic'

function pctSigned(v: number | null) {
  if (v == null) return { text: '—', cls: 'text-ink-tertiary' }
  const pct = v * 100
  const sign = pct >= 0 ? '+' : ''
  return { text: `${sign}${pct.toFixed(1)}%`, cls: pct >= 0 ? 'text-signal-pos' : 'text-signal-neg' }
}

function styleBoxFromFunds(funds: ScreenFund[]) {
  const counts = new Map<string, number>()
  for (const f of funds) {
    if (!f.style_box) continue
    const k = `${f.style_box.size}-${f.style_box.style}`
    counts.set(k, (counts.get(k) ?? 0) + 1)
  }
  const sizes: StyleSize[] = ['Large', 'Mid', 'Small']
  const styles: StyleAxis[] = ['Value', 'Blend', 'Growth']
  const cells: { size: StyleSize; style: StyleAxis; count: number }[] = []
  for (const size of sizes) {
    for (const style of styles) {
      cells.push({ size, style, count: counts.get(`${size}-${style}`) ?? 0 })
    }
  }
  return cells
}

export default async function V6FundsPage() {
  const { data: funds, meta, source_kind } = await getScreenFunds()
  const styleCells = styleBoxFromFunds(funds)

  return (
    <div className="max-w-[1400px] mx-auto">
      <div className="px-6 py-4 border-b border-paper-rule">
        <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-1">
          Funds · v6
        </div>
        <h1 className="font-serif text-2xl lg:text-3xl font-semibold text-ink-primary">
          Funds Discovery
        </h1>
        <p className="font-sans text-sm text-ink-secondary leading-relaxed mt-2 max-w-[760px]">
          {funds.length} funds with Morningstar-style style box + conviction tape derived
          from holdings. Click any fund to see lens panels.
        </p>
      </div>

      <DataSourceBanner source={source_kind} asOf={meta.data_as_of} />

      <div className="px-6 py-5 border-b border-paper-rule flex gap-8 flex-wrap">
        <StyleBox cells={styleCells} />
        <div className="flex-1 min-w-[280px]">
          <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-2">
            About the style box
          </h2>
          <p className="font-sans text-sm text-ink-secondary leading-relaxed">
            Morningstar-style 3 × 3 grid: rows = capitalisation (Large / Mid / Small),
            columns = investment style (Value / Blend / Growth). The number shows how many
            funds in our universe sit in each slot. The style classification for Indian
            funds is v6.1 work — placeholder cells until the migration lands.
          </p>
        </div>
      </div>

      <div className="overflow-x-auto border border-paper-rule rounded-[2px] mx-6 my-4">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-paper-rule bg-paper">
              <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-left">Fund</th>
              <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-left">Category</th>
              <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-right">AUM</th>
              <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-left">Style</th>
              <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-left">Conviction</th>
              <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-left">RS</th>
              <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-right">1M</th>
              <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-right">3M</th>
              <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-right">12M</th>
            </tr>
          </thead>
          <tbody>
            {funds.map((f, i) => {
              const r1 = pctSigned(f.ret_1m)
              const r3 = pctSigned(f.ret_3m)
              const r12 = pctSigned(f.ret_12m)
              return (
                <tr key={f.iid} className={`border-b border-paper-rule hover:bg-paper-rule/20 transition-colors ${i % 2 === 0 ? '' : 'bg-paper-rule/5'}`}>
                  <td className="px-3 py-2.5">
                    <LinkedFund mstarId={f.code} name={f.name} />
                  </td>
                  <td className="px-3 py-2.5 font-sans text-[11px] text-ink-tertiary whitespace-nowrap">{f.category}</td>
                  <td className="px-3 py-2.5 font-mono text-xs tabular-nums text-right whitespace-nowrap">{formatINR(f.aum_inr)}</td>
                  <td className="px-3 py-2.5 font-sans text-[11px] text-ink-secondary whitespace-nowrap">
                    {f.style_box ? `${f.style_box.size} · ${f.style_box.style}` : '—'}
                  </td>
                  <td className="px-3 py-2.5 whitespace-nowrap">
                    {f.conviction_tape ? <ConvictionTape tape={f.conviction_tape} compact /> : <span className="font-mono text-xs text-ink-tertiary">—</span>}
                  </td>
                  <td className="px-3 py-2.5 whitespace-nowrap">
                    {f.rs_state ? <StateBadge state={f.rs_state} size="sm" /> : <span className="font-mono text-xs text-ink-tertiary">—</span>}
                  </td>
                  <td className={`px-3 py-2.5 font-mono text-xs tabular-nums text-right whitespace-nowrap ${r1.cls}`}>{r1.text}</td>
                  <td className={`px-3 py-2.5 font-mono text-xs tabular-nums text-right whitespace-nowrap ${r3.cls}`}>{r3.text}</td>
                  <td className={`px-3 py-2.5 font-mono text-xs tabular-nums text-right whitespace-nowrap ${r12.cls}`}>{r12.text}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
