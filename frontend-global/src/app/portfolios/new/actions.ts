'use server'
// src/app/portfolios/new/actions.ts — create a basket. Validation is pure (src/lib/basketDraft.ts);
// the thresholds and the directory come from atlas_global; the write is ONE transaction
// (basket_master + basket_constituents). No Python is spawned and nothing is priced here — the
// fills and the first NAV are mark_baskets.py's, which the 5-minute worker runs for any basket
// without a NAV row; the detail page says "marking within 5 minutes" until then.
import { redirect } from 'next/navigation'
import { requireUser } from '@/lib/auth'
import { checkResolved, parseDraft, type DraftInput, type FormState, type Suggestion } from '@/lib/basketDraft'
import { dbAvailable } from '@/lib/db'
import { getBasketLimits, insertBasket, latestSession, resolveSymbols, searchInstruments } from '@/lib/queries/baskets'

const message = (e: unknown) => (e instanceof Error ? e.message : String(e))

function draftFromForm(formData: FormData): DraftInput {
  const str = (v: FormDataEntryValue | null) => (typeof v === 'string' ? v : '')
  const symbols = formData.getAll('symbol').map(str)
  const weights = formData.getAll('weight').map(str)
  return {
    name: str(formData.get('name')),
    kind: str(formData.get('kind')),
    capital: str(formData.get('capital')),
    rows: symbols.map((symbol, i) => ({ symbol, weightPct: weights[i] ?? '' })),
  }
}

export async function createBasket(_prev: FormState, formData: FormData): Promise<FormState> {
  const user = await requireUser()
  const values = draftFromForm(formData)
  const fail = (errors: string[]): FormState => ({ errors, notes: [], values })
  if (!dbAvailable) return fail(['This deployment has no database; nothing can be saved.'])

  let limits
  try {
    limits = await getBasketLimits()
  } catch (e) {
    return fail([message(e)])
  }
  const parsed = parseDraft(values, limits)
  if (!parsed.ok) return fail(parsed.errors)

  let checked
  try {
    checked = checkResolved(parsed.draft, await resolveSymbols(parsed.draft.rows.map((r) => r.symbol)))
  } catch (e) {
    return fail([`The directory could not be read: ${message(e)}`])
  }
  if (!checked.ok) return fail(checked.errors)

  let id: string
  try {
    id = await insertBasket(parsed.draft, checked.constituents, user.email, await latestSession())
  } catch (e) {
    return fail([`The database refused the basket: ${message(e)}`])
  }
  redirect(`/portfolios/${id}`)
}

/** The symbol box's suggestions. Signed in, bounded, and nothing is written. */
export async function suggestInstruments(q: string, kind: 'etf' | 'stock'): Promise<Suggestion[]> {
  await requireUser()
  if (!dbAvailable || (kind !== 'etf' && kind !== 'stock')) return []
  return searchInstruments(String(q ?? '').slice(0, 24), kind)
}
