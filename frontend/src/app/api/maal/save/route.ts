// POST /api/maal/save — replace a draft's rows. Deliberately permissive:
// a half-typed Friday draft must save. Publishing is where the rules bite.
import { NextResponse } from 'next/server'

import { MAAL_CODES, type MaalCode } from '@/lib/maal'
import { requireAuth } from '@/lib/requireAuth'
import { saveDraft, type CallRow, type EvidenceSection } from '@/lib/queries/maal'

export const dynamic = 'force-dynamic'

type Body = {
  code?: unknown
  week?: unknown
  calls?: unknown
  evidence?: unknown
}

const str = (v: unknown, fallback = '') => (typeof v === 'string' ? v : fallback)
const numOrNull = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : null)

export async function POST(req: Request) {
  const denied = await requireAuth('save a confirmation')
  if (denied) return denied

  let body: Body = {}
  try {
    body = await req.json()
  } catch {
    // fall through to validation
  }
  const code = body.code
  const week = body.week
  if (typeof code !== 'string' || !(MAAL_CODES as readonly string[]).includes(code)) {
    return NextResponse.json({ error_code: 'bad_request', message: 'unknown portfolio code' }, { status: 400 })
  }
  if (typeof week !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(week)) {
    return NextResponse.json({ error_code: 'bad_request', message: 'week must be YYYY-MM-DD' }, { status: 400 })
  }
  if (!Array.isArray(body.calls) || !Array.isArray(body.evidence)) {
    return NextResponse.json({ error_code: 'bad_request', message: 'calls and evidence must be arrays' }, { status: 400 })
  }

  const calls: Array<Omit<CallRow, 'callId' | 'hasImage'>> = []
  for (const raw of body.calls as Array<Record<string, unknown>>) {
    const key = str(raw.key)
    const side = raw.side === 'sell' ? 'sell' : 'buy'
    if (!key) continue // an empty row the FM has not filled in yet
    calls.push({
      side,
      key,
      symbol: str(raw.symbol, key.split(':')[1] ?? key),
      name: str(raw.name),
      sector: raw.sector == null ? null : str(raw.sector),
      weightPct: numOrNull(raw.weightPct) ?? 0,
      triggerPrice: numOrNull(raw.triggerPrice),
      stopPrice: numOrNull(raw.stopPrice),
      reasons: Array.isArray(raw.reasons) ? raw.reasons.filter((r): r is string => typeof r === 'string') : [],
      comment: str(raw.comment),
      position: calls.length,
    })
  }

  const evidence: Array<Omit<EvidenceSection, 'hasImage' | 'evidenceId'>> = (
    body.evidence as Array<Record<string, unknown>>
  ).map((raw, i) => ({ position: i, title: str(raw.title), comment: str(raw.comment) }))

  try {
    const { confirmationId } = await saveDraft(code as MaalCode, week, { calls, evidence })
    return NextResponse.json({ confirmationId, saved: calls.length })
  } catch (e) {
    if (e instanceof Error && e.message === 'published_immutable') {
      return NextResponse.json(
        { error_code: 'published', message: 'this week is published — start the next week instead' },
        { status: 409 },
      )
    }
    if (e instanceof Error && e.message.startsWith('duplicate_instrument:')) {
      const symbol = e.message.split(':')[1]
      return NextResponse.json(
        {
          error_code: 'both_sides',
          message: `${symbol} is on both the buy and the sell side — an instrument can appear only once`,
        },
        { status: 409 },
      )
    }
    throw e
  }
}
