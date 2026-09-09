// src/components/portfolios/BasketDetailView.tsx — one basket, glass-box: the stored NAV
// against SPY as growth of 100, the risk/return windows, the holdings as the trades made them,
// and the trade log. Every figure is a stored row (mark_baskets.py) or arithmetic over one;
// the chart series and the window metrics are the only floats, and they are display.
import { computeWindowMetrics, maxDrawdown } from '@/lib/basketMetrics'
import { formatDecimal, formatIsoDate, formatPct, formatUsd } from '@/lib/format'
import type { BasketDetail } from '@/lib/queries/baskets'
import { PageHeader } from '@/components/ui/PageHeader'
import { Section } from '@/components/ui/Section'
import { BasketChart } from './BasketChart'
import { KIND_LABEL, tone } from './BasketCards'

const pctNum = (v: number | null) => (v == null ? '—' : formatPct(v, 2, { sign: true }))
const toneNum = (v: number | null) => (v == null ? 'text-ink-3' : v < 0 ? 'text-neg' : v > 0 ? 'text-pos' : 'text-ink-2')

function Tile({ label, value, className = 'text-ink' }: { label: string; value: string; className?: string }) {
  return (
    <div className="tile">
      <div className="text-meta text-ink-3">{label}</div>
      <div className={`num mt-1 text-lead font-medium ${className}`}>{value}</div>
    </div>
  )
}

export function BasketDetailView({ d }: { d: BasketDetail }) {
  const { summary: s, nav, holdings, constituents, trades } = d
  const marked = nav.length > 0
  const dd = maxDrawdown(nav)
  const windows = [1, 3, 5].map((y) => ({ y, m: computeWindowMetrics(nav, y) }))
  return (
    <div className="page">
      <PageHeader
        title={s.name}
        lead={
          <>
            {KIND_LABEL[s.kind]} · {s.n_constituents} name{s.n_constituents === 1 ? '' : 's'} · capital{' '}
            {formatUsd(s.initial_capital, 0)}
            {s.inception_date && <> · inception {formatIsoDate(s.inception_date)}</>}
            {s.created_by && <> · by {s.created_by}</>}
          </>
        }
        aside={
          marked ? (
            <p className="text-body text-ink-2">
              Marked at <span className="text-ink">{formatIsoDate(s.nav_date!)}</span>, the latest session
            </p>
          ) : undefined
        }
      />

      {!marked && (
        <div className="notice" data-marking="pending">
          <span className="dot bg-warn" aria-hidden="true" />
          <p className="text-body">
            Not marked yet — the basket is booked at the last session close by the next mark, within five minutes of
            saving. If it is still unmarked after ten, the worker log or /health says why (a name with no recent
            print, or a weight outside the thresholds).
          </p>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Tile label="NAV" value={s.nav ? formatUsd(s.nav) : '—'} />
        <Tile label="Since inception" value={formatPct(s.since_inception, 2, { sign: true })} className={tone(s.since_inception)} />
        <Tile label="SPY, same span" value={formatPct(s.spy_since_inception, 2, { sign: true })} className={tone(s.spy_since_inception)} />
        <Tile label="vs SPY (relative)" value={formatPct(s.vs_spy, 2, { sign: true })} className={tone(s.vs_spy)} />
        <Tile label="Max drawdown" value={dd == null ? '—' : formatPct(dd, 2)} className={dd != null && dd < 0 ? 'text-neg' : 'text-ink'} />
        {windows.map(({ y, m }) => (
          <Tile key={y} label={`${y}Y CAGR · Max DD · Calmar`} value={`${pctNum(m.cagr)} · ${pctNum(m.maxDd)} · ${m.calmar == null ? '—' : m.calmar.toFixed(2)}`} className={toneNum(m.cagr)} />
        ))}
      </div>
      <p className="mt-2 text-meta text-ink-3">
        vs SPY is the board&rsquo;s relative form, (1+r)/(1+r<sub>SPY</sub>) − 1, both on total return. A window shows
        &ldquo;—&rdquo; until the record covers its full span — no 3Y number invented from months of data.
      </p>

      {marked && (
        <Section title="Growth of 100 vs SPY" note="total return; SPY on close_tr">
          <div className="panel p-3">
            <BasketChart d={d} />
          </div>
        </Section>
      )}

      <Section title={holdings.length ? 'Holdings' : 'Constituents'} note={holdings.length ? 'as the trades made them' : `target weights, v${s.current_version}`}>
        <div className="panel overflow-x-auto">
          <table className="tbl">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Name</th>
                <th className="r">Target</th>
                {holdings.length > 0 && (
                  <>
                    <th className="r">Qty</th>
                    <th className="r">Fill</th>
                    <th className="r">Last</th>
                    <th className="r">Value</th>
                    <th className="r">Since entry</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody>
              {holdings.length > 0
                ? holdings.map((h) => (
                    <tr key={h.instrument_id} data-holding={h.symbol}>
                      <td className="text-ink">{h.symbol}</td>
                      <td className="text-ink-2">{h.name ?? '—'}</td>
                      <td className="num r">{formatPct(h.target_weight_frac, 2)}</td>
                      <td className="num r">{formatDecimal(h.qty, 6)}</td>
                      <td className="num r">{formatUsd(h.fill_price)}</td>
                      <td className="num r">
                        {formatUsd(h.last_price)}
                        {h.last_date && <span className="text-ink-3"> {formatIsoDate(h.last_date)}</span>}
                      </td>
                      <td className="num r text-ink">{formatUsd(h.value)}</td>
                      <td className={`num r ${tone(h.ret_since_entry)}`}>{formatPct(h.ret_since_entry, 2, { sign: true })}</td>
                    </tr>
                  ))
                : constituents.map((c) => (
                    <tr key={c.instrument_id} data-constituent={c.symbol}>
                      <td className="text-ink">{c.symbol}</td>
                      <td className="text-ink-2">{c.name ?? '—'}</td>
                      <td className="num r">{formatPct(c.target_weight_frac, 2)}</td>
                    </tr>
                  ))}
            </tbody>
          </table>
        </div>
        {holdings.length > 0 && (
          <p className="mt-2 text-meta text-ink-3">
            Qty and Fill are the real fractional shares at the split-adjusted close of the fill date. Value grows the
            fill by total return since entry (dividends reinvested), which is what the NAV carries — so Value can exceed
            Qty × Last by the dividends paid.
          </p>
        )}
      </Section>

      <Section title="Trades" note={`${trades.length} row${trades.length === 1 ? '' : 's'}`}>
        <div className="panel overflow-x-auto">
          <table className="tbl">
            <thead>
              <tr>
                <th>Date</th>
                <th>Symbol</th>
                <th>Side</th>
                <th className="r">Qty</th>
                <th className="r">Price</th>
                <th className="r">Value</th>
                <th className="r">Cost</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {trades.length === 0 && (
                <tr>
                  <td colSpan={8} className="text-ink-3">
                    No trades yet — the inception fills land with the first mark.
                  </td>
                </tr>
              )}
              {trades.map((t, i) => (
                <tr key={i}>
                  <td className="num">{formatIsoDate(t.date)}</td>
                  <td className="text-ink">{t.symbol}</td>
                  <td className={t.side === 'buy' ? 'text-pos' : 'text-neg'}>{t.side}</td>
                  <td className="num r">{formatDecimal(t.qty, 6)}</td>
                  <td className="num r">{formatUsd(t.price)}</td>
                  <td className="num r text-ink">{formatUsd(t.value)}</td>
                  <td className="num r">{formatUsd(t.cost)}</td>
                  <td className="max-w-[48ch] text-ink-2" title={t.rationale ?? undefined}>
                    {t.reason}
                    {t.rationale && <span className="block text-meta text-ink-3">{t.rationale}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>
    </div>
  )
}
