// Data layer for the Monday confirmations (see lib/confirmations.ts for the rules).
// Publishing is the only write that touches the book: it folds this week's calls
// onto the last published book and stores the snapshot on the row.
import 'server-only'

import sql from '@/lib/db'
import {
  foldBook,
  isoDate,
  validateCalls,
  type BookPosition,
  type Call,
  type PortfolioCode,
  type Problem,
} from '@/lib/confirmations'

export type EvidenceSection = {
  position: number
  title: string
  comment: string
  hasImage: boolean
  evidenceId: number | null
}

export type CallRow = Call & {
  callId: number | null
  triggerPrice: number | null
  stopPrice: number | null
  hasImage: boolean
  position: number
}

export type Confirmation = {
  confirmationId: number
  portfolioCode: PortfolioCode
  weekOf: string
  status: 'draft' | 'published'
  publishedAt: string | null
  calls: CallRow[]
  evidence: EvidenceSection[]
  /** The book this week starts from — the last published book before it. */
  openingBook: BookPosition[]
  /** Stored at publish; for a draft this is the live preview of the fold. */
  resultingBook: BookPosition[]
}

const num = (v: unknown): number | null => (v == null ? null : Number(v))

const toCall = (r: Record<string, unknown>): CallRow => ({
  callId: Number(r.call_id),
  side: r.side as 'buy' | 'sell',
  key: String(r.instrument_key),
  symbol: String(r.symbol),
  name: String(r.name ?? ''),
  sector: r.sector == null ? null : String(r.sector),
  weightPct: Number(r.weight_pct),
  triggerPrice: num(r.trigger_price),
  stopPrice: num(r.stop_price),
  reasons: (r.reasons as string[] | null) ?? [],
  comment: String(r.comment ?? ''),
  hasImage: Boolean(r.has_image),
  position: Number(r.position ?? 0),
})

/**
 * The portfolio as it stands: the most recent published book, ignoring drafts
 * and (when publishing week W) anything dated W or later.
 */
export async function getOpeningBook(code: PortfolioCode, before?: string): Promise<BookPosition[]> {
  const rows = await sql<Array<{ resulting_book: BookPosition[] }>>`
    SELECT resulting_book
    FROM atlas_foundation.mpf_confirmation
    WHERE portfolio_code = ${code}
      AND status = 'published'
      ${before ? sql`AND week_of < ${before}` : sql``}
    ORDER BY week_of DESC
    LIMIT 1`
  return rows[0]?.resulting_book ?? []
}

export type ConfirmationSummary = {
  weekOf: string
  status: 'draft' | 'published'
  publishedAt: string | null
  buys: number
  sells: number
}

/** Report history for a book — the UI shows the most recent few. */
export async function listConfirmations(code: PortfolioCode, limit = 3): Promise<ConfirmationSummary[]> {
  const rows = await sql<Array<Record<string, unknown>>>`
    SELECT c.week_of, c.status, c.published_at,
           count(*) FILTER (WHERE k.side = 'buy')  AS buys,
           count(*) FILTER (WHERE k.side = 'sell') AS sells
    FROM atlas_foundation.mpf_confirmation c
    LEFT JOIN atlas_foundation.mpf_call k USING (confirmation_id)
    WHERE c.portfolio_code = ${code}
    GROUP BY c.confirmation_id, c.week_of, c.status, c.published_at
    ORDER BY c.week_of DESC
    LIMIT ${limit}`
  return rows.map((r) => ({
    weekOf: isoDate(r.week_of as Date | string),
    status: r.status as 'draft' | 'published',
    publishedAt: r.published_at ? new Date(r.published_at as string).toISOString() : null,
    buys: Number(r.buys),
    sells: Number(r.sells),
  }))
}

/** Load one week. Returns null when that week has never been started. */
export async function getConfirmation(code: PortfolioCode, weekOf: string): Promise<Confirmation | null> {
  const head = await sql<Array<Record<string, unknown>>>`
    SELECT confirmation_id, portfolio_code, week_of, status, published_at, resulting_book
    FROM atlas_foundation.mpf_confirmation
    WHERE portfolio_code = ${code} AND week_of = ${weekOf}`
  if (head.length === 0) return null
  const h = head[0]
  const id = Number(h.confirmation_id)

  const [calls, evidence, openingBook] = await Promise.all([
    sql<Array<Record<string, unknown>>>`
      SELECT call_id, side, instrument_key, symbol, name, sector, weight_pct,
             trigger_price, stop_price, reasons, comment, position,
             (chart_image IS NOT NULL) AS has_image
      FROM atlas_foundation.mpf_call
      WHERE confirmation_id = ${id}
      ORDER BY side, position, call_id`,
    sql<Array<Record<string, unknown>>>`
      SELECT evidence_id, position, title, comment, (image IS NOT NULL) AS has_image
      FROM atlas_foundation.mpf_evidence
      WHERE confirmation_id = ${id}
      ORDER BY position, evidence_id`,
    getOpeningBook(code, weekOf),
  ])

  const callRows = calls.map(toCall)
  return {
    confirmationId: id,
    portfolioCode: code,
    weekOf: isoDate(h.week_of as Date | string),
    status: h.status as 'draft' | 'published',
    publishedAt: h.published_at ? new Date(h.published_at as string).toISOString() : null,
    calls: callRows,
    evidence: evidence.map((r) => ({
      evidenceId: Number(r.evidence_id),
      position: Number(r.position),
      title: String(r.title ?? ''),
      comment: String(r.comment ?? ''),
      hasImage: Boolean(r.has_image),
    })),
    openingBook,
    resultingBook: (h.resulting_book as BookPosition[] | null) ?? foldBook(openingBook, callRows),
  }
}

export type DraftInput = {
  calls: Array<Omit<CallRow, 'callId' | 'hasImage'>>
  evidence: Array<Omit<EvidenceSection, 'hasImage' | 'evidenceId'>>
}

/**
 * Replace a draft's rows wholesale, in one transaction. Images are keyed to the
 * instrument (not the row id), so re-saving a draft keeps attached charts.
 */
export async function saveDraft(
  code: PortfolioCode,
  weekOf: string,
  input: DraftInput,
): Promise<{ confirmationId: number }> {
  return sql.begin(async (tx) => {
    const head = await tx<Array<{ confirmation_id: number; status: string }>>`
      INSERT INTO atlas_foundation.mpf_confirmation (portfolio_code, week_of)
      VALUES (${code}, ${weekOf})
      ON CONFLICT (portfolio_code, week_of)
        DO UPDATE SET updated_at = now()
      RETURNING confirmation_id, status`
    const id = Number(head[0].confirmation_id)
    if (head[0].status === 'published') {
      throw new Error('published_immutable')
    }

    // Carry attached images across the replace.
    const kept = await tx<Array<{ instrument_key: string; chart_image: Buffer; chart_mime: string }>>`
      SELECT instrument_key, chart_image, chart_mime
      FROM atlas_foundation.mpf_call
      WHERE confirmation_id = ${id} AND chart_image IS NOT NULL`
    const images = new Map(kept.map((r) => [r.instrument_key, r]))

    await tx`DELETE FROM atlas_foundation.mpf_call WHERE confirmation_id = ${id}`
    for (const [i, c] of input.calls.entries()) {
      const img = images.get(c.key)
      try {
        await tx`
          INSERT INTO atlas_foundation.mpf_call
            (confirmation_id, side, instrument_key, symbol, name, sector, weight_pct,
             trigger_price, stop_price, reasons, comment, position, chart_image, chart_mime)
          VALUES (${id}, ${c.side}, ${c.key}, ${c.symbol}, ${c.name}, ${c.sector},
                  ${c.weightPct}, ${c.triggerPrice}, ${c.stopPrice}, ${c.reasons},
                  ${c.comment}, ${i}, ${img?.chart_image ?? null}, ${img?.chart_mime ?? null})`
      } catch (e) {
        // UNIQUE(confirmation_id, instrument_key) — the name is already on the
        // other side. Report it as the rule it is, not as a database error.
        if (typeof e === 'object' && e !== null && (e as { code?: string }).code === '23505') {
          throw new Error(`duplicate_instrument:${c.symbol}`)
        }
        throw e
      }
    }

    const keptEvidence = await tx<Array<{ position: number; image: Buffer; mime: string }>>`
      SELECT position, image, mime FROM atlas_foundation.mpf_evidence
      WHERE confirmation_id = ${id} AND image IS NOT NULL`
    const evidenceImages = new Map(keptEvidence.map((r) => [r.position, r]))

    await tx`DELETE FROM atlas_foundation.mpf_evidence WHERE confirmation_id = ${id}`
    for (const [i, e] of input.evidence.entries()) {
      const img = evidenceImages.get(e.position)
      await tx`
        INSERT INTO atlas_foundation.mpf_evidence
          (confirmation_id, position, title, comment, image, mime)
        VALUES (${id}, ${i}, ${e.title}, ${e.comment}, ${img?.image ?? null}, ${img?.mime ?? null})`
    }
    return { confirmationId: id }
  })
}

/**
 * Validate against the stored book and freeze the result. Returns the problems
 * instead of throwing when the week is not publishable — the caller shows them.
 */
export async function publish(
  code: PortfolioCode,
  weekOf: string,
): Promise<{ ok: true; book: BookPosition[] } | { ok: false; problems: Problem[] }> {
  const current = await getConfirmation(code, weekOf)
  if (!current) return { ok: false, problems: [{ code: 'not_found', message: 'nothing to publish' }] }
  if (current.status === 'published') {
    return { ok: false, problems: [{ code: 'already_published', message: 'this week is already published' }] }
  }
  if (current.calls.length === 0) {
    return { ok: false, problems: [{ code: 'empty', message: 'add at least one buy or sell' }] }
  }

  const problems = validateCalls(current.openingBook, current.calls)
  if (problems.length > 0) return { ok: false, problems }

  const book = foldBook(current.openingBook, current.calls)
  await sql`
    UPDATE atlas_foundation.mpf_confirmation
    SET status = 'published', published_at = now(), resulting_book = ${sql.json(book)}, updated_at = now()
    WHERE confirmation_id = ${current.confirmationId} AND status = 'draft'`
  return { ok: true, book }
}

export async function saveCallImage(
  confirmationId: number,
  instrumentKey: string,
  bytes: Buffer,
  mime: string,
): Promise<boolean> {
  const rows = await sql`
    UPDATE atlas_foundation.mpf_call
    SET chart_image = ${bytes}, chart_mime = ${mime}
    WHERE confirmation_id = ${confirmationId} AND instrument_key = ${instrumentKey}
    RETURNING call_id`
  return rows.length > 0
}

export async function saveEvidenceImage(
  confirmationId: number,
  position: number,
  bytes: Buffer,
  mime: string,
): Promise<boolean> {
  const rows = await sql`
    UPDATE atlas_foundation.mpf_evidence
    SET image = ${bytes}, mime = ${mime}
    WHERE confirmation_id = ${confirmationId} AND position = ${position}
    RETURNING evidence_id`
  return rows.length > 0
}

export async function getCallImage(callId: number): Promise<{ bytes: Buffer; mime: string } | null> {
  const rows = await sql<Array<{ chart_image: Buffer | null; chart_mime: string | null }>>`
    SELECT chart_image, chart_mime FROM atlas_foundation.mpf_call WHERE call_id = ${callId}`
  const r = rows[0]
  if (!r?.chart_image) return null
  return { bytes: r.chart_image, mime: r.chart_mime ?? 'image/png' }
}

export async function getEvidenceImage(evidenceId: number): Promise<{ bytes: Buffer; mime: string } | null> {
  const rows = await sql<Array<{ image: Buffer | null; mime: string | null }>>`
    SELECT image, mime FROM atlas_foundation.mpf_evidence WHERE evidence_id = ${evidenceId}`
  const r = rows[0]
  if (!r?.image) return null
  return { bytes: r.image, mime: r.mime ?? 'image/png' }
}
