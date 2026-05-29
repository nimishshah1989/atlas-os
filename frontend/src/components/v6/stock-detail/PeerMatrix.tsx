// frontend/src/components/v6/stock-detail/PeerMatrix.tsx
import Link from 'next/link'
import type { PeerRow } from '@/lib/queries/v6/stock-detail'

interface PeerMatrixProps { peers: PeerRow[] }

function stageColor(s: string): string {
  if (s.includes('2a') || s.includes('2b')) return 'text-signal-pos'
  if (s.includes('2c') || s.includes('3')) return 'text-signal-warn'
  if (s.includes('4') || s.includes('uninv')) return 'text-signal-neg'
  return 'text-ink-3'
}

function stageLabel(s: string): string {
  return s.replace('stage_', 'S').replace('_', '').replace('uninvestable', 'UNINV').toUpperCase()
}

function convColor(v: string): string {
  if (v === 'Bullish') return 'text-signal-pos'
  if (v === 'Bearish') return 'text-signal-neg'
  return 'text-ink-3'
}

function slopeColor(v: string): string {
  if (v === 'Rising' || v === 'Expanding') return 'text-signal-pos'
  if (v === 'Declining' || v === 'Fading') return 'text-signal-neg'
  return 'text-ink-3'
}

function numColor(v: number | null): string {
  if (v == null) return 'text-ink-3'
  return v > 0 ? 'text-signal-pos' : v < 0 ? 'text-signal-neg' : 'text-ink-3'
}

function fmtPct(v: number | null): string {
  if (v == null) return '—'
  return `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`
}

function fmtRs(v: number | null): string {
  if (v == null) return '—'
  return Math.round(v).toString()
}

const HEADERS = ['Stock', 'Stage', 'Conviction', 'RS Rank', 'EMA20 Slope', 'Volume', '3M Return', 'Extension']

export function PeerMatrix({ peers }: PeerMatrixProps) {
  if (peers.length === 0) return null
  return (
    <section className="px-6 py-6 border-b border-paper-rule">
      <p className="font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-4">Peer Matrix — How does this stock stack up in its sector?</p>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-[12px]">
          <thead>
            <tr className="border-b border-paper-rule">
              {HEADERS.map(h => <th key={h} className="text-left py-2 px-2 font-mono text-[9px] uppercase tracking-wider text-ink-3 font-normal whitespace-nowrap">{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {peers.map(peer => (
              <tr key={peer.symbol} className={['border-b border-paper-rule last:border-0', peer.is_parent ? 'bg-[rgba(29,158,117,0.08)] border-l-2 border-teal' : 'hover:bg-paper-deep/50'].join(' ')}>
                <td className="py-2 px-2 whitespace-nowrap">
                  <Link href={`/stocks/${peer.symbol}`} className="font-mono text-accent hover:text-teal hover:underline">{peer.symbol}</Link>
                  {peer.company_name && <span className="block font-sans text-[10px] text-ink-3 truncate max-w-[120px]">{peer.company_name}</span>}
                </td>
                <td className={`py-2 px-2 font-mono whitespace-nowrap ${stageColor(peer.stage)} ${peer.is_parent ? 'font-semibold' : ''}`}>{stageLabel(peer.stage)}</td>
                <td className={`py-2 px-2 font-mono whitespace-nowrap ${convColor(peer.conviction)} ${peer.is_parent ? 'font-semibold' : ''}`}>{peer.conviction || '—'}</td>
                <td className={`py-2 px-2 font-mono text-right whitespace-nowrap ${numColor(peer.rs_vs_nifty)} ${peer.is_parent ? 'font-semibold' : ''}`}>{fmtRs(peer.rs_vs_nifty)}</td>
                <td className={`py-2 px-2 font-mono whitespace-nowrap ${slopeColor(peer.ema20_slope)} ${peer.is_parent ? 'font-semibold' : ''}`}>{peer.ema20_slope || '—'}</td>
                <td className={`py-2 px-2 font-mono whitespace-nowrap ${slopeColor(peer.volume)} ${peer.is_parent ? 'font-semibold' : ''}`}>{peer.volume || '—'}</td>
                <td className={`py-2 px-2 font-mono text-right whitespace-nowrap ${numColor(peer.ret_3m_pct)} ${peer.is_parent ? 'font-semibold' : ''}`}>{fmtPct(peer.ret_3m_pct)}</td>
                <td className={`py-2 px-2 font-mono text-right whitespace-nowrap ${numColor(peer.extension_pct)} ${peer.is_parent ? 'font-semibold' : ''}`}>{fmtPct(peer.extension_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
