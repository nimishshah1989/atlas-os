// POST /api/thresholds/save — persist FM threshold edits to atlas_foundation.atlas_thresholds.
// Each value is validated/clamped server-side against its own min/max (authoritative); the body
// is { edits: [{key, value}], modifiedBy? }. Does NOT recompute — that's a separate explicit step.
import { NextResponse } from 'next/server'
import { updateThresholds, type ThresholdEdit } from '@/lib/queries/thresholds'

export const dynamic = 'force-dynamic'

export async function POST(req: Request) {
  let body: { edits?: ThresholdEdit[]; modifiedBy?: string }
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error_code: 'bad_json', message: 'Invalid JSON body' }, { status: 400 })
  }
  const edits = Array.isArray(body.edits) ? body.edits : []
  if (edits.length === 0) {
    return NextResponse.json({ error_code: 'no_edits', message: 'No edits supplied' }, { status: 400 })
  }
  const result = await updateThresholds(edits, body.modifiedBy ?? 'fm-panel')
  return NextResponse.json({ data: result })
}
