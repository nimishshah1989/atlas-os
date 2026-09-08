// src/lib/auth.ts — who is looking at the board.
// Identity comes from Supabase Auth; permission comes from the atlas_global.app_user allowlist
// (invite-only; roles fm | analyst | client). A page calls requireUser() first thing.
import 'server-only'
import { redirect } from 'next/navigation'
import { db, dbAvailable } from '@/lib/db'
import { e2eBypassEmail } from '@/lib/e2e'
import { isSupabaseConfigured } from '@/lib/supabase/env'
import { createServerSupabase } from '@/lib/supabase/server'

export type Role = 'fm' | 'analyst' | 'client'

export type AppUser = {
  email: string
  /** null when the allowlist could not be consulted (no database in this deployment). */
  role: Role | null
  display_name: string | null
  allowlist_checked: boolean
}

type AppUserRow = { email: string; role: Role; display_name: string | null }

async function allowlistRow(email: string): Promise<AppUserRow | null> {
  const rows = await db()<AppUserRow[]>`
    SELECT email, role, display_name
    FROM atlas_global.app_user
    WHERE email = ${email} AND is_active
    LIMIT 1
  `
  return rows[0] ?? null
}

/** True when the address is on the active allowlist. Requires a database. */
export async function isInvited(email: string): Promise<boolean> {
  return (await allowlistRow(email.toLowerCase())) !== null
}

/** The signed-in address, or a redirect to /login. Without auth configured nobody is signed in. */
async function sessionEmail(): Promise<string> {
  if (!isSupabaseConfigured()) redirect('/login')
  const supabase = await createServerSupabase()
  const { data } = await supabase.auth.getUser()
  const email = data.user?.email?.toLowerCase()
  if (!email) redirect('/login')
  return email
}

/**
 * The signed-in, invited user holding one of `roles` — or a redirect to /login. Every board page
 * is for the FM and analysts until client pages arrive in M2 (docs/global/phase1.md, P1-G), so
 * that is the default. Without a database the allowlist is not checked and the role is unknown.
 * The smoke's dev-only bypass (src/lib/e2e.ts) replaces the session step and nothing else.
 */
const BOARD_ROLES: readonly Role[] = ['fm', 'analyst']

export async function requireUser(): Promise<AppUser> {
  const email = e2eBypassEmail() ?? (await sessionEmail())
  // No directory, no entry. The allowlist is the ONLY thing standing between a valid Supabase
  // session and this board, so a run that cannot read it has not authorised anyone — it has
  // merely failed to check. In production that must close, not open: `dbAvailable` is only
  // `Boolean(url)`, so a pm2 process started without ATLAS_GLOBAL_DB_URL in its environment
  // would otherwise serve every page to anyone holding any Supabase account. Outside
  // production the unchecked path stays, so a laptop or a preview with no database still
  // builds and renders its honest "not configured" state — the same dev-only shape as
  // e2eBypassEmail(), which `next build` compiles to a constant.
  if (!dbAvailable) {
    if (process.env.NODE_ENV === 'production') redirect('/login?reason=no-directory')
    return { email, role: null, display_name: null, allowlist_checked: false }
  }
  const row = await allowlistRow(email)
  if (!row) redirect('/login?reason=not-invited')
  if (!BOARD_ROLES.includes(row.role)) redirect('/login?reason=role')
  return { email: row.email, role: row.role, display_name: row.display_name, allowlist_checked: true }
}
