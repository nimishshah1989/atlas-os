'use client'
// Controls for /funds/compare. State lives in the URL so the page stays shareable and
// printable; native select/date inputs so there is no picker dependency.
import { useRouter, useSearchParams } from 'next/navigation'
import type { CategoryOption } from '@/lib/queries/fund_category_curve'

const PERIOD_OPTIONS = [
  { v: '1m', l: '1 month' }, { v: '3m', l: '3 months' }, { v: '6m', l: '6 months' },
  { v: '1y', l: '1 year' }, { v: '2y', l: '2 years' }, { v: '3y', l: '3 years' },
  { v: '5y', l: '5 years' }, { v: 'max', l: 'Max' }, { v: 'custom', l: 'Custom range' },
]

const cleanCat = (c: string): string =>
  c.replace(/^India\s+Fund\s*[-–—]?\s*/i, '').trim() || c

const label = 'font-num text-[9px] uppercase tracking-[0.14em] text-txt-3'
const field =
  'rounded-tile border border-edge-hair bg-surface-panel px-2.5 py-1.5 font-sans text-[13px] text-txt-1'

export function CategoryCompareControls({
  options,
  staleBefore,
}: {
  options: CategoryOption[]
  /** Any category whose last NAV predates this is labelled stale in the picker. */
  staleBefore: string
}) {
  const router = useRouter()
  const params = useSearchParams()

  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    next.set(key, value)
    router.push(`/funds/compare?${next}`)
  }

  const period = params.get('period') ?? '3y'
  const view = params.get('view') ?? 'growth'

  return (
    <div className="print:hidden flex flex-wrap items-end gap-3">
      <div className="flex flex-col gap-1">
        <label className={label} htmlFor="cat">Category</label>
        <select id="cat" className={`${field} min-w-[280px]`}
                value={params.get('cat') ?? 'India Fund Flexi Cap'}
                onChange={(e) => set('cat', e.target.value)}>
          {options.map((o) => (
            <option key={o.category} value={o.category}>
              {cleanCat(o.category)} · {o.nFunds} funds
              {o.lastNav && o.lastNav < staleBefore ? ` · stale to ${o.lastNav}` : ''}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1">
        <label className={label} htmlFor="period">Period</label>
        <select id="period" className={field} value={period}
                onChange={(e) => set('period', e.target.value)}>
          {PERIOD_OPTIONS.map((p) => <option key={p.v} value={p.v}>{p.l}</option>)}
        </select>
      </div>

      {period === 'custom' && (
        <>
          <div className="flex flex-col gap-1">
            <label className={label} htmlFor="from">From</label>
            <input id="from" type="date" className={field} value={params.get('from') ?? ''}
                   onChange={(e) => set('from', e.target.value)} />
          </div>
          <div className="flex flex-col gap-1">
            <label className={label} htmlFor="to">To</label>
            <input id="to" type="date" className={field} value={params.get('to') ?? ''}
                   onChange={(e) => set('to', e.target.value)} />
          </div>
        </>
      )}

      <div className="flex flex-col gap-1">
        <label className={label} htmlFor="view">View</label>
        <select id="view" className={field} value={view}
                onChange={(e) => set('view', e.target.value)}>
          <option value="growth">Growth of ₹100</option>
          <option value="rolling">Rolling returns</option>
        </select>
      </div>

      {view === 'rolling' && (
        <div className="flex flex-col gap-1">
          <label className={label} htmlFor="window">Rolling window</label>
          <select id="window" className={field} value={params.get('window') ?? '3y'}
                  onChange={(e) => set('window', e.target.value)}>
            <option value="1y">1 year</option>
            <option value="3y">3 years</option>
            <option value="5y">5 years</option>
          </select>
        </div>
      )}
    </div>
  )
}
