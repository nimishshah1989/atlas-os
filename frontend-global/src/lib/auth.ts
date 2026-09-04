// src/lib/auth.ts — who is looking at the board.
// Identity comes from Supabase Auth; permission comes from the atlas_global.app_user allowlist
// (invite-only; roles fm | analyst | client). A page calls requireUser() first thing.
import 'server-only'
import { redirect } from 'next/navigation'
import { db, dbAvailable } from '@/lib/db'
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

/**
 * The signed-in, invited user — or a redirect to /login. Without auth configured nobody is
 * signed in; without a database the allowlist is not checked and the role is unknown.
 */
export async function requireUser(): Promise<AppUser> {
  if (!isSupabaseConfigured()) redirect('/login')
  const supabase = await createServerSupabase()
  const { data } = await supabase.auth.getUser()
  const email = data.user?.email?.toLowerCase()
  if (!email) redirect('/login')
  if (!dbAvailable) return { email, role: null, display_name: null, allowlist_checked: false }
  const row = await allowlistRow(email)
  if (!row) redirect('/login?reason=not-invited')
  return { email: row.email, role: row.role, display_name: row.display_name, allowlist_checked: true }
}
