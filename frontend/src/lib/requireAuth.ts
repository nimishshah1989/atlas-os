// Shared fail-closed gate for write routes (middleware.ts is a deliberate no-op —
// the board is internal, but anything that mutates the FM's book is reachable on
// the public domain and must check. Mirrors app/api/desk/orders/route.ts.)
import 'server-only'
import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'

/** Returns a 401 response when the caller is not logged in, otherwise null. */
export async function requireAuth(what: string): Promise<NextResponse | null> {
  const pass = process.env.ATLAS_PASSWORD
  const cookie = (await cookies()).get('atlas_auth')?.value
  if (!pass || cookie !== pass) {
    return NextResponse.json(
      { error_code: 'unauthorized', message: `log in at /login to ${what}` },
      { status: 401 },
    )
  }
  return null
}
