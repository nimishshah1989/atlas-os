// GET /api/instruments/search?q=<text>&class=stock|etf|fund — type-ahead for the
// portfolio builder. Returns up to 10 matches with a display price (last real close /
// NAV). RULE #0: price is the stored close, informational only — the actual booking
// price is set by the Python engine at init, never invented here.
import { NextResponse } from 'next/server'
import sql from '@/lib/db'

export const dynamic = 'force-dynamic'

type Hit = { key: string; label: string; sublabel: string; assetClass: string; price: number | null }

export async function GET(req: Request) {
  const url = new URL(req.url)
  const q = (url.searchParams.get('q') ?? '').trim()
  const cls = url.searchParams.get('class') ?? 'stock'
  if (q.length < 2) return NextResponse.json({ hits: [] })
  const like = `%${q}%`
  const prefix = `${q}%`

  if (cls === 'fund') {
    const rows = await sql<Array<Record<string, unknown>>>`
      SELECT f.mstar_id, f.scheme_name, f.category_name,
             (SELECT nav FROM atlas_foundation.de_mf_nav_daily n
              WHERE n.mstar_id = f.mstar_id ORDER BY nav_date DESC LIMIT 1) AS price
      FROM atlas_foundation.atlas_universe_funds f
      WHERE f.scheme_name ILIKE ${like}
      ORDER BY (f.scheme_name ILIKE ${prefix}) DESC, f.scheme_name
      LIMIT 10`
    const hits: Hit[] = rows.map((r) => ({
      key: `fund:${r.mstar_id}`,
      label: String(r.scheme_name),
      sublabel: String(r.category_name ?? 'Fund'),
      assetClass: 'fund',
      price: r.price != null ? Number(r.price) : null,
    }))
    return NextResponse.json({ hits })
  }

  if (cls !== 'stock' && cls !== 'etf') return NextResponse.json({ hits: [] })
  // last close: stocks keyed by instrument_id, ETFs by ticker (=symbol) — mirrors load_prices
  const priceExpr =
    cls === 'etf'
      ? sql`(SELECT close_adj FROM atlas_foundation.ohlcv_etf o WHERE o.ticker = i.symbol AND o.close_adj > 0 ORDER BY o.date DESC LIMIT 1)`
      : sql`(SELECT close_adj FROM atlas_foundation.ohlcv_stock o WHERE o.instrument_id = i.instrument_id AND o.close_adj > 0 ORDER BY o.date DESC LIMIT 1)`
  const rows = await sql<Array<Record<string, unknown>>>`
    SELECT i.symbol, i.name, i.sector, ${priceExpr} AS price
    FROM atlas_foundation.instrument_master i
    WHERE i.is_active AND i.asset_class = ${cls} AND i.kite_token IS NOT NULL
      AND (i.symbol ILIKE ${prefix} OR i.name ILIKE ${like})
    ORDER BY (i.symbol ILIKE ${prefix}) DESC, i.symbol
    LIMIT 10`
  const hits: Hit[] = rows.map((r) => ({
    key: `${cls}:${r.symbol}`,
    label: String(r.symbol),
    sublabel: String(r.name ?? cls),
    assetClass: cls,
    price: r.price != null ? Number(r.price) : null,
  }))
  return NextResponse.json({ hits })
}
