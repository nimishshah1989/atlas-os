// StockRSMatrix — the always-visible RS matrix for the v4 stock detail page.
// Rows {Nifty 50, Nifty 500, Sector} × cols {1D,1W,1M,3M,6M,12M}, color-scaled
// (green positive / red negative pp), "—" for null. Native foundation_staging
// (technical_daily) via getStockRSMatrix(). Server component.
// Color-scale mirrors RSWindowsTable so the whole app reads the same.
import type { RSMatrix } from '@/lib/queries/v6/stock_lens'
import { TermInfo } from '@/components/v6/shared/TermInfo'

const COLS = ['1D', '1W', '1M', '3M', '6M', '12M']

const HM_STYLES: Record<string, React.CSSProperties> = {
  'pos-strong': { background: 'rgba(47,107,67,0.45)', color: '#F8F4EC', fontWeight: 600 },
  'pos':        { background: 'rgba(47,107,67,0.25)' },
  'pos-weak':   { background: 'rgba(47,107,67,0.10)' },
  'flat':       { background: '#FBF8F1' },
  'neg-weak':   { background: 'rgba(176,73,44,0.10)' },
  'neg':        { background: 'rgba(176,73,44,0.25)' },
  'neg-strong': { background: 'rgba(176,73,44,0.45)', color: '#F8F4EC', fontWeight: 600 },
}
function hmCls(pp: number | null): string {
  if (pp == null) return 'flat'
  if (pp >= 10)  return 'pos-strong'
  if (pp >= 5)   return 'pos'
  if (pp >= 2)   return 'pos-weak'
  if (pp >= -2)  return 'flat'
  if (pp >= -5)  return 'neg-weak'
  if (pp >= -10) return 'neg'
  return 'neg-strong'
}

function RSCell({ value }: { value: number | null }) {
  const style = HM_STYLES[hmCls(value)] ?? {}
  const text = value != null ? `${value >= 0 ? '+' : ''}${value.toFixed(1)}pp` : '—'
  return (
    <td style={{ padding: 0, textAlign: 'center', borderBottom: '1px solid #F1ECDF' }}>
      <div
        style={{ padding: '12px 8px', fontFamily: "'JetBrains Mono', Consolas, monospace", fontSize: 13, fontWeight: 500, color: '#1A1714', ...style }}
        aria-label={text}
      >
        {value != null ? text : <span className="text-txt-3">—</span>}
      </div>
    </td>
  )
}

const ROW_SUB: Record<string, string> = {
  'Nifty 50': 'Large-cap anchor',
  'Nifty 500': 'Broad-market baseline',
  'Sector': 'Own-sector index',
}

export function StockRSMatrix({ matrix }: { matrix: RSMatrix }) {
  const thStyle: React.CSSProperties = {
    textAlign: 'center', padding: '11px 14px', fontFamily: 'Inter, sans-serif', fontSize: 9,
    letterSpacing: '0.18em', textTransform: 'uppercase', color: '#6B6157', fontWeight: 600,
    background: '#FBF8F1', borderBottom: '1px solid #DDD3BF',
  }
  // Index cells by window for fast lookup (Sector row only has 1M..12M).
  const cellFor = (row: RSMatrix['rows'][number], col: string) =>
    row.cells.find(c => c.window === col) ?? null

  return (
    <section className="px-8 py-9 border-b border-edge-hair" aria-label="Relative strength matrix">
      <div className="mb-[18px]">
        <h2 className="font-display text-[26px] font-normal tracking-tight text-txt-1">Relative strength · always on<TermInfo term="rs" /></h2>
        <p className="font-sans text-[13px] text-txt-3 max-w-[760px] leading-[1.45] mt-1">
          Percentage-point spread vs each baseline across six windows. Green = outperforming, red = lagging.
          {matrix.as_of && <> Data as of <span className="font-num text-txt-2">{matrix.as_of}</span>.</>}
        </p>
      </div>
      <div className="bg-surface-panel border border-edge-hair rounded-tile overflow-hidden" data-testid="stock-rs-matrix">
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              <th style={{ ...thStyle, textAlign: 'left', width: '26%', paddingLeft: 16 }}>Baseline<TermInfo term="baseline" /></th>
              {COLS.map(c => <th key={c} style={thStyle}>{c}</th>)}
            </tr>
          </thead>
          <tbody>
            {matrix.rows.map(row => (
              <tr key={row.baseline}>
                <td style={{ padding: '14px 16px', textAlign: 'left', fontFamily: 'Inter, sans-serif', borderBottom: '1px solid #F1ECDF' }}>
                  <div className="font-medium text-txt-1 text-[13px]">{row.baseline}</div>
                  <div className="text-[10px] text-txt-3 mt-[1px]">{ROW_SUB[row.baseline] ?? ''}</div>
                </td>
                {COLS.map(col => <RSCell key={col} value={cellFor(row, col)?.v ?? null} />)}
              </tr>
            ))}
          </tbody>
        </table>
        <div className="px-4 py-2 border-t border-edge-hair bg-surface-panel">
          <p className="font-sans text-[11px] text-txt-3">
            From <strong className="text-txt-2">foundation_staging.technical_daily</strong>. Sector row covers 1M–12M (1D/1W not stored).
          </p>
        </div>
      </div>
    </section>
  )
}
