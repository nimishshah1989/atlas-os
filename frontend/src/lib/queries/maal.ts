// Data layer for the MaaL Process (see lib/maal.ts for the rules).
// Publishing is the only write that touches the book: it folds this week's calls
// onto the last published book and stores the snapshot on the row.
import 'server-only'

import sql from '@/lib/db'
import {
  foldBook,
  isoDate,
  round1,
  validateCalls,
  type BookPosition,
  type Call,
  type MaalCode,
  type Problem,
} from '@/lib/maal'

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
  portfolioCode: MaalCode
  weekOf: string
  status: 'draft' | 'published'
  publishedAt: string | null
  calls: CallRow[]
  evidence: EvidenceSection[]
  /** The book this week starts from — the last published book before it. */
  openingBook: BookPosition[]
  /** Stored at publish; for a draft this is the live preview of the fold. */
  resultingBook: BookPosition[]
  /** Max position cap % for this book; 0 = unset, so nothing pre-fills the sell side. */
  maxCapPct: number
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
/** Max position cap % for a book, from atlas_thresholds. 0 means the FM has not set one. */
export async function getMaxCap(code: MaalCode): Promise<number> {
  const rows = await sql<Array<{ threshold_value: string }>>`
    SELECT threshold_value FROM atlas_foundation.atlas_thresholds
    WHERE threshold_key = ${`maal_max_cap.${code}`} AND is_active`
  return rows[0] ? round1(Number(rows[0].threshold_value)) : 0
}

/** Clamped to [0, 100] server-side — the route never trusts the posted number. */
export async function setMaxCap(code: MaalCode, capPct: number): Promise<number> {
  const clamped = round1(Math.min(100, Math.max(0, capPct)))
  await sql`
    UPDATE atlas_foundation.atlas_thresholds
    SET threshold_value = ${clamped}, last_modified_by = 'maal', last_modified_at = now()
    WHERE threshold_key = ${`maal_max_cap.${code}`}`
  return clamped
}

/**
 * The book this week starts from: the latest synced snapshot of the REAL portfolio,
 * priced with Atlas's own close.
 *
 * NOT a fold of prior recommendations. The FM's calls are a superset of what actually
 * executes, so a folded book drifts from the real portfolio every week it compounds —
 * see ADR 0005. `resulting_book` still freezes what a published report SAID, for report
 * fidelity; it is no longer what the next week opens from.
 *
 * `before` selects the newest snapshot taken strictly before that week, so a historical
 * report opens from the book as it stood then rather than as it stands today.
 */
export async function getOpeningBook(code: MaalCode, before?: string): Promise<BookPosition[]> {
  const rows = await sql<Array<Record<string, unknown>>>`
    WITH latest AS (
      -- max(as_of), NOT max(source_as_of). as_of is unique per look; source_as_of is
      -- shared by every look at the same unmoved CPP data, so keying on it matched
      -- several snapshots at once and rendered the book DOUBLED.
      SELECT max(as_of) AS a
      FROM atlas_foundation.maal_holding_snapshot
      WHERE maal_code = ${code}
        ${before ? sql`AND source_as_of < ${before}` : sql``}
    ),
    priced AS (
      SELECT s.instrument_key, s.source_symbol, s.asset_class,
             im.name AS company_name, im.sector,
             s.quantity * coalesce(st.close, et.close) AS value
      FROM atlas_foundation.maal_holding_snapshot s
      JOIN latest ON latest.a = s.as_of
      JOIN atlas_foundation.instrument_master im ON im.isin = s.isin
      -- Prices live in two tables: stocks in ohlcv_stock (keyed by symbol), ETFs in
      -- ohlcv_etf (keyed by TICKER — its isin column is mostly NULL). Reading only
      -- ohlcv_stock silently dropped every ETF, which on Leaders is GOLDBEES,
      -- NIFTYBEES, SILVERBEES and HDFCSML250 — 43% of the book by weight.
      LEFT JOIN LATERAL (
        SELECT close FROM atlas_foundation.ohlcv_stock x
        WHERE x.symbol = im.symbol ORDER BY x.date DESC LIMIT 1
      ) st ON true
      LEFT JOIN LATERAL (
        SELECT close FROM atlas_foundation.ohlcv_etf y
        WHERE y.ticker = im.symbol ORDER BY y.date DESC LIMIT 1
      ) et ON true
      WHERE s.maal_code = ${code}
        AND s.instrument_key IS NOT NULL
        -- CASH-class rows (LIQUIDBEES/LIQUIDCASE/LIQUIDETF) are cash, not positions.
        -- They belong in the cash line, never in the holdings list.
        AND s.asset_class <> 'CASH'
        AND coalesce(st.close, et.close) IS NOT NULL
    )
    SELECT instrument_key, source_symbol, company_name, sector,
           value / nullif(sum(value) OVER (), 0) AS share
    FROM priced
    ORDER BY share DESC`

  // Weights are a share of TOTAL portfolio value, so they sum to (100 − cash), not to
  // 100. That keeps the long-standing contract that cash is the remainder — cashPct(),
  // the over-allocation check and the report all keep working unchanged — while making
  // the remainder the REAL cash from the synced NAV instead of an artefact of the fold.
  // Normalising to 100 here would report 0% cash on a book genuinely holding 33%.
  const { cashPct: cash } = await getBookCash(code)
  const invested = Math.max(0, 100 - cash)

  return rows.map((r) => ({
    key: String(r.instrument_key),
    symbol: String(r.source_symbol),
    name: String(r.company_name ?? r.source_symbol),
    sector: r.sector == null ? null : String(r.sector),
    weightPct: round1(Number(r.share) * invested),
  }))
}

/**
 * The book's cash and the date its positions are actually from.
 *
 * Cash is NOT `100 − Σ weights` any more: it comes from the synced NAV row, which counts
 * the liquid-ETF sleeve as cash per the FM's rule. `sourceAsOf` is the day CPP's data is
 * from, not the day we looked — a document that does not state which day its positions
 * are from is the exact problem this phase exists to fix.
 */
export async function getBookCash(
  code: MaalCode,
): Promise<{ cashPct: number; navDate: string | null }> {
  const rows = await sql<Array<Record<string, unknown>>>`
    SELECT n.date::text AS d,
           n.cash / nullif(n.nav, 0) * 100 AS cash_pct
    FROM atlas_foundation.portfolio_nav_daily n
    JOIN atlas_foundation.portfolio_master m USING (portfolio_id)
    WHERE m.params->>'source' = 'cpp'
      AND m.params->>'maal_code' = ${code}
      AND n.run_type = 'live'
    ORDER BY n.date DESC
    LIMIT 1`
  const r = rows[0]
  if (!r) return { cashPct: 0, navDate: null }
  return { cashPct: round1(Number(r.cash_pct)), navDate: r.d ? String(r.d) : null }
}

export type ConfirmationSummary = {
  weekOf: string
  status: 'draft' | 'published'
  publishedAt: string | null
  buys: number
  sells: number
}

/** Report history for a book — the UI shows the most recent few. */
export async function listConfirmations(code: MaalCode, limit = 3): Promise<ConfirmationSummary[]> {
  const rows = await sql<Array<Record<string, unknown>>>`
    SELECT c.week_of, c.status, c.published_at,
           count(*) FILTER (WHERE k.side = 'buy')  AS buys,
           count(*) FILTER (WHERE k.side = 'sell') AS sells
    FROM atlas_foundation.maal_confirmation c
    LEFT JOIN atlas_foundation.maal_call k USING (confirmation_id)
    WHERE c.maal_code = ${code}
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
export async function getConfirmation(code: MaalCode, weekOf: string): Promise<Confirmation | null> {
  const head = await sql<Array<Record<string, unknown>>>`
    SELECT confirmation_id, maal_code, week_of, status, published_at, resulting_book
    FROM atlas_foundation.maal_confirmation
    WHERE maal_code = ${code} AND week_of = ${weekOf}`
  if (head.length === 0) return null
  const h = head[0]
  const id = Number(h.confirmation_id)

  const [calls, evidence, openingBook, maxCapPct] = await Promise.all([
    sql<Array<Record<string, unknown>>>`
      SELECT call_id, side, instrument_key, symbol, name, sector, weight_pct,
             trigger_price, stop_price, reasons, comment, position,
             (chart_image IS NOT NULL) AS has_image
      FROM atlas_foundation.maal_call
      WHERE confirmation_id = ${id}
      ORDER BY side, position, call_id`,
    sql<Array<Record<string, unknown>>>`
      SELECT evidence_id, position, title, comment, (image IS NOT NULL) AS has_image
      FROM atlas_foundation.maal_evidence
      WHERE confirmation_id = ${id}
      ORDER BY position, evidence_id`,
    getOpeningBook(code, weekOf),
    getMaxCap(code),
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
    maxCapPct,
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
  code: MaalCode,
  weekOf: string,
  input: DraftInput,
): Promise<{ confirmationId: number }> {
  return sql.begin(async (tx) => {
    const head = await tx<Array<{ confirmation_id: number; status: string }>>`
      INSERT INTO atlas_foundation.maal_confirmation (maal_code, week_of)
      VALUES (${code}, ${weekOf})
      ON CONFLICT (maal_code, week_of)
        DO UPDATE SET updated_at = now()
      RETURNING confirmation_id, status`
    const id = Number(head[0].confirmation_id)
    if (head[0].status === 'published') {
      throw new Error('published_immutable')
    }

    // Carry attached images across the replace.
    const kept = await tx<Array<{ instrument_key: string; chart_image: Buffer; chart_mime: string }>>`
      SELECT instrument_key, chart_image, chart_mime
      FROM atlas_foundation.maal_call
      WHERE confirmation_id = ${id} AND chart_image IS NOT NULL`
    const images = new Map(kept.map((r) => [r.instrument_key, r]))

    await tx`DELETE FROM atlas_foundation.maal_call WHERE confirmation_id = ${id}`
    for (const [i, c] of input.calls.entries()) {
      const img = images.get(c.key)
      try {
        await tx`
          INSERT INTO atlas_foundation.maal_call
            (confirmation_id, side, instrument_key, symbol, name, sector, weight_pct,
             trigger_price, stop_price, reasons, comment, position, chart_image, chart_mime)
          VALUES (${id}, ${c.side}, ${c.key}, ${c.symbol}, ${c.name}, ${c.sector},
                  ${round1(c.weightPct)}, ${c.triggerPrice}, ${c.stopPrice}, ${c.reasons},
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
      SELECT position, image, mime FROM atlas_foundation.maal_evidence
      WHERE confirmation_id = ${id} AND image IS NOT NULL`
    const evidenceImages = new Map(keptEvidence.map((r) => [r.position, r]))

    await tx`DELETE FROM atlas_foundation.maal_evidence WHERE confirmation_id = ${id}`
    for (const [i, e] of input.evidence.entries()) {
      const img = evidenceImages.get(e.position)
      await tx`
        INSERT INTO atlas_foundation.maal_evidence
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
  code: MaalCode,
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
    UPDATE atlas_foundation.maal_confirmation
    SET status = 'published', published_at = now(), resulting_book = ${sql.json(book)}, updated_at = now()
    WHERE confirmation_id = ${current.confirmationId} AND status = 'draft'`
  return { ok: true, book }
}

/**
 * Reopen a published week for editing (FM, 2026-08-01).
 *
 * ADR 0003 made publish one-way so a circulated report would render identically
 * forever. That still holds for an untouched report — but the FM needs to correct a
 * mistake without waiting a week, so reopening is now possible AS AN EXPLICIT ACT.
 * It flips the row back to draft and clears published_at, so the document stops
 * claiming to be published while it is being changed, and the report re-renders
 * marked DRAFT until it is published again.
 *
 * The tradeoff, stated plainly: a report already sent to the group can now diverge
 * from the copy people are holding. Republishing is what makes it authoritative again.
 */
export async function reopenConfirmation(code: MaalCode, weekOf: string): Promise<boolean> {
  const rows = await sql`
    UPDATE atlas_foundation.maal_confirmation
    SET status = 'draft', published_at = NULL, updated_at = now()
    WHERE maal_code = ${code} AND week_of = ${weekOf} AND status = 'published'
    RETURNING confirmation_id`
  return rows.length > 0
}

export async function saveCallImage(
  confirmationId: number,
  instrumentKey: string,
  bytes: Buffer,
  mime: string,
): Promise<boolean> {
  const rows = await sql`
    UPDATE atlas_foundation.maal_call
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
    UPDATE atlas_foundation.maal_evidence
    SET image = ${bytes}, mime = ${mime}
    WHERE confirmation_id = ${confirmationId} AND position = ${position}
    RETURNING evidence_id`
  return rows.length > 0
}

/**
 * Detach a chart. Clears the bytes rather than deleting the row — the call itself
 * still stands; only its evidence is being replaced or withdrawn.
 */
export async function clearCallImage(
  confirmationId: number,
  instrumentKey: string,
): Promise<boolean> {
  const rows = await sql`
    UPDATE atlas_foundation.maal_call
    SET chart_image = NULL, chart_mime = NULL
    WHERE confirmation_id = ${confirmationId} AND instrument_key = ${instrumentKey}
    RETURNING call_id`
  return rows.length > 0
}

export async function clearEvidenceImage(
  confirmationId: number,
  position: number,
): Promise<boolean> {
  const rows = await sql`
    UPDATE atlas_foundation.maal_evidence
    SET image = NULL, mime = NULL
    WHERE confirmation_id = ${confirmationId} AND position = ${position}
    RETURNING evidence_id`
  return rows.length > 0
}

export async function getCallImage(callId: number): Promise<{ bytes: Buffer; mime: string } | null> {
  const rows = await sql<Array<{ chart_image: Buffer | null; chart_mime: string | null }>>`
    SELECT chart_image, chart_mime FROM atlas_foundation.maal_call WHERE call_id = ${callId}`
  const r = rows[0]
  if (!r?.chart_image) return null
  return { bytes: r.chart_image, mime: r.chart_mime ?? 'image/png' }
}

export async function getEvidenceImage(evidenceId: number): Promise<{ bytes: Buffer; mime: string } | null> {
  const rows = await sql<Array<{ image: Buffer | null; mime: string | null }>>`
    SELECT image, mime FROM atlas_foundation.maal_evidence WHERE evidence_id = ${evidenceId}`
  const r = rows[0]
  if (!r?.image) return null
  return { bytes: r.image, mime: r.mime ?? 'image/png' }
}
