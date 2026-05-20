// frontend/src/components/ui/LinkedToken.tsx
import Link from 'next/link'

function dash() {
  return <span className="font-mono text-xs text-ink-tertiary">—</span>
}

export function LinkedTicker({ symbol, className = '' }: { symbol: string | null; className?: string }) {
  if (!symbol) return dash()
  return (
    <Link href={`/stocks/${encodeURIComponent(symbol)}`}
      className={`text-ink-primary hover:text-teal hover:underline transition-colors ${className}`}>
      {symbol}
    </Link>
  )
}

export function LinkedSector({ sector, className = '' }: { sector: string | null; className?: string }) {
  if (!sector) return dash()
  return (
    <Link href={`/sectors/${encodeURIComponent(sector)}`}
      className={`text-ink-secondary hover:text-teal hover:underline transition-colors ${className}`}>
      {sector}
    </Link>
  )
}

export function LinkedFund({ mstarId, name }: { mstarId: string | null; name: string | null }) {
  if (!mstarId || !name) return dash()
  return (
    <Link href={`/funds/${encodeURIComponent(mstarId)}`}
      className="text-ink-primary hover:text-teal hover:underline transition-colors">
      {name}
    </Link>
  )
}

export function LinkedETF({ ticker }: { ticker: string | null }) {
  if (!ticker) return dash()
  return (
    <Link href={`/etfs/${encodeURIComponent(ticker)}`}
      className="text-ink-primary hover:text-teal hover:underline transition-colors">
      {ticker}
    </Link>
  )
}

export function LinkedCountry({ ticker, name }: { ticker: string | null; name: string | null }) {
  if (!ticker || !name) return dash()
  return (
    <Link href={`/global/country/${encodeURIComponent(ticker)}`}
      className="text-ink-primary hover:text-teal hover:underline transition-colors">
      {name}
    </Link>
  )
}
