// The editor's in-progress row shape. Mirrors CallRow but carries the asset-class
// selector the autocomplete needs, and no server ids (a draft is replaced wholesale).
import type { Call } from '@/lib/confirmations'

export type DraftCall = Omit<Call, 'weightPct'> & {
  weightPct: number
  triggerPrice: number | null
  stopPrice: number | null
  hasImage: boolean
  assetClass: 'stock' | 'etf'
}

export type DraftEvidence = {
  position: number
  title: string
  comment: string
  hasImage: boolean
  evidenceId: number | null
}
