// Presentational sub-components for /v6/regime.
// Server components; no client interactivity.

import type { CellFavored, ConvictionStock, ConvictionFund, ConvictionEtf } from '@/lib/queries/v6/market-regime'

function actionTint(action: string): string {
  if (action === 'POSITIVE') return 'text-signal-pos'
  if (action === 'NEGATIVE') return 'text-signal-neg'
  return 'text-ink-secondary'
}

function actionLabel(action: string): string {
  if (action === 'POSITIVE') return 'BUY'
  if (action === 'NEGATIVE') return 'AVOID'
  return 'WATCH'
}

export function CellFavoredCard({ cell }: { cell: CellFavored }) {
  return (
    <div className="border border-paper-rule p-5 rounded-sm">
      <div className="flex items-baseline justify-between mb-2">
        <div className="font-serif text-lg text-ink">{cell.display_name}</div>
        <div className={`text-[10px] uppercase tracking-widest font-semibold ${actionTint(cell.action)}`}>
          {actionLabel(cell.action)}
        </div>
      </div>
      <div className="text-xs text-ink-secondary mb-3 leading-relaxed">
        {cell.explain_text ?? '—'}
      </div>
      <div className="flex items-center gap-4 text-xs font-mono text-ink-tertiary">
        <span>{cell.stocks_firing_today} firing</span>
        <span>·</span>
        <span>{cell.confidence}</span>
        {cell.predicted_excess != null && (
          <>
            <span>·</span>
            <span className={actionTint(cell.action)}>
              {(cell.predicted_excess * 100).toFixed(1)}pp pred
            </span>
          </>
        )}
      </div>
    </div>
  )
}

export function ConvictionStocksColumn({ rows }: { rows: ConvictionStock[] }) {
  return (
    <div>
      <h2 className="font-serif text-xl text-ink mb-3">Top stocks</h2>
      {rows.length === 0 ? (
        <p className="text-sm text-ink-tertiary">No conviction stocks today.</p>
      ) : (
        <ul className="space-y-2">
          {rows.slice(0, 8).map(s => (
            <li key={s.symbol} className="flex items-baseline justify-between border-b border-paper-rule pb-2">
              <div>
                <div className="font-mono text-sm text-ink">{s.symbol}</div>
                <div className="text-[11px] text-ink-tertiary">{s.sector ?? '—'}</div>
              </div>
              <div className={`text-xs font-mono ${actionTint(s.action)}`}>
                {s.predicted_excess != null ? `${(s.predicted_excess * 100).toFixed(1)}pp` : '—'}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function ConvictionFundsColumn({ rows }: { rows: ConvictionFund[] }) {
  return (
    <div>
      <h2 className="font-serif text-xl text-ink mb-3">Top funds</h2>
      {rows.length === 0 ? (
        <p className="text-sm text-ink-tertiary">No conviction funds today.</p>
      ) : (
        <ul className="space-y-2">
          {rows.slice(0, 8).map(f => (
            <li key={f.scheme_code} className="border-b border-paper-rule pb-2">
              <div className="text-sm text-ink">{f.fund_name}</div>
              <div className="flex items-baseline justify-between mt-1">
                <div className="text-[11px] text-ink-tertiary">{f.category ?? '—'}</div>
                <div className="text-xs font-mono text-ink">
                  {f.composite != null ? f.composite.toFixed(1) : '—'} · {f.quartile ?? '—'}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function ConvictionEtfsColumn({ rows }: { rows: ConvictionEtf[] }) {
  return (
    <div>
      <h2 className="font-serif text-xl text-ink mb-3">Top ETFs</h2>
      {rows.length === 0 ? (
        <p className="text-sm text-ink-tertiary">No conviction ETFs today.</p>
      ) : (
        <ul className="space-y-2">
          {rows.slice(0, 8).map(e => (
            <li key={e.ticker} className="border-b border-paper-rule pb-2">
              <div className="flex items-baseline justify-between">
                <div className="font-mono text-sm text-ink">{e.ticker}</div>
                <div className={`text-xs font-mono ${actionTint(e.action)}`}>
                  {e.composite != null ? e.composite.toFixed(1) : '—'}
                </div>
              </div>
              <div className="text-[11px] text-ink-tertiary">{e.etf_name}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
