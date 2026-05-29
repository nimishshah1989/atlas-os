// frontend/src/lib/queries/v6/stock-detail.ts
const API_BASE = process.env.ATLAS_V1_API_BASE ?? 'http://localhost:8002'

export interface RSRatioPoint {
  date: string
  ratio: number
}

export interface RSRatiosData {
  symbol: string
  sector: string | null
  sector_index_code: string
  vs_sector: RSRatioPoint[]
  vs_sector_resistance: number
  vs_sector_status: 'BREAKING_OUT' | 'AT_RESISTANCE' | 'BELOW_RESISTANCE'
  vs_nifty50: RSRatioPoint[]
  vs_nifty50_resistance: number
  vs_nifty50_status: 'BREAKING_OUT' | 'AT_RESISTANCE' | 'BELOW_RESISTANCE'
}

export async function getRSRatios(symbol: string): Promise<RSRatiosData | null> {
  try {
    const res = await fetch(
      `${API_BASE}/v1/stocks/${encodeURIComponent(symbol)}/rs-ratios?days=252`,
      { next: { revalidate: 3600 } },
    )
    if (!res.ok) return null
    const json = await res.json()
    return (json.data ?? null) as RSRatiosData | null
  } catch {
    return null
  }
}

export interface PeerRow {
  symbol: string
  company_name: string
  is_parent: boolean
  stage: string
  conviction: string
  rs_vs_nifty: number | null
  ema20_slope: string
  volume: string
  ret_3m_pct: number | null
  extension_pct: number | null
}

export async function getPeerMatrix(symbol: string): Promise<PeerRow[]> {
  try {
    const res = await fetch(
      `${API_BASE}/v1/stocks/${encodeURIComponent(symbol)}/peer-matrix`,
      { next: { revalidate: 3600 } },
    )
    if (!res.ok) return []
    const json = await res.json()
    return (json.data?.peers ?? []) as PeerRow[]
  } catch {
    return []
  }
}
