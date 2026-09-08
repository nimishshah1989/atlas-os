// src/app/login/page.tsx — magic-link sign-in. Invite-only: the address must be on
// atlas_global.app_user. Without Supabase configured the page says so and never crashes.
import Link from 'next/link'
import { PageHeader } from '@/components/ui/PageHeader'
import { authRequired } from '@/lib/openAccess'
import { isSupabaseConfigured } from '@/lib/supabase/env'
import { safeNext } from '@/lib/supabase/paths'
import { sendMagicLink, signOut } from './actions'

export const metadata = { title: 'Sign in' }

type Search = { [key: string]: string | string[] | undefined }
const first = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v)

const ERRORS: Record<string, string> = {
  email: 'Enter a valid email address.',
  link: 'That sign-in link did not work. It may have expired or already been used; request a new one.',
  send: 'The sign-in email could not be sent. Try again in a minute; if it keeps failing, check the Supabase Auth settings.',
}

function AuthNotConfigured() {
  return (
    <div className="page">
      <PageHeader title="Sign in" lead="Auth is not configured for this deployment." />
      <div className="panel max-w-[64ch] px-5 py-4 text-body text-ink-2">
        <p>
          Set <code className="text-ink">NEXT_PUBLIC_SUPABASE_URL</code> and{' '}
          <code className="text-ink">NEXT_PUBLIC_SUPABASE_ANON_KEY</code> to the project’s public keys and
          redeploy. Until then the board is closed; only this page and the health page are reachable.
        </p>
      </div>
    </div>
  )
}

/** Nothing to sign in to. Shown rather than a form that would send a link nobody needs. */
function BoardIsOpen() {
  return (
    <div className="page">
      <PageHeader title="Sign in" lead="This board does not ask for one." />
      <div className="panel max-w-[64ch] px-5 py-4 text-body text-ink-2">
        <p>
          Global Atlas is open: everything on it — prices, returns, relative strength, one fund
          per country — is public market data. There are no accounts and no positions to guard.
          Sign-in returns with the first page that shows something private.
        </p>
        <p className="mt-3">
          <Link className="underline text-ink" href="/">
            Go to the board
          </Link>
        </p>
      </div>
    </div>
  )
}

export default async function LoginPage({ searchParams }: { searchParams: Promise<Search> }) {
  // Checked BEFORE the Supabase-configured branch: on an open board the reader needs neither
  // this form nor an explanation of a setting that has no bearing on getting in.
  if (!authRequired()) return <BoardIsOpen />
  if (!isSupabaseConfigured()) return <AuthNotConfigured />
  const sp = await searchParams
  const sent = first(sp.sent)
  const reason = first(sp.reason)
  const error = first(sp.error)
  const next = safeNext(first(sp.next))

  return (
    <div className="page">
      <PageHeader
        title="Sign in"
        lead="Enter the email address you were invited with. A link that signs you in on this device will follow."
      />
      <div className="panel max-w-[420px] px-6 py-5">
        {sent && (
          <p className="mb-4 text-body text-ink">
            A sign-in link is on its way to <span className="font-medium">{sent}</span>. It expires in an hour; open it
            on this device.
          </p>
        )}
        {(reason === 'not-invited' || reason === 'role' || reason === 'no-directory') && (
          <div className="mb-4 text-body text-ink">
            <p>
              {reason === 'role'
                ? 'This is a client account. The board is open to the FM and analysts only until client pages arrive.'
                : reason === 'no-directory'
                  ? // requireUser() could not reach the invite list, so nobody has been checked.
                    // Says what is wrong without naming the missing setting to a stranger.
                    'The board cannot reach its invite list, so it cannot let anyone in. This is a configuration fault, not your account — tell the FM.'
                  : 'This address is not on the invite list. Ask the FM to add it, then try again.'}
            </p>
            <form action={signOut} className="mt-2">
              <button type="submit" className="btn">
                Use a different account
              </button>
            </form>
          </div>
        )}
        {error && ERRORS[error] && <p className="mb-4 text-body text-neg">{ERRORS[error]}</p>}

        <form action={sendMagicLink} className="space-y-4">
          <input type="hidden" name="next" value={next} />
          <label className="block">
            <span className="mb-1 block text-meta text-ink-2">Email</span>
            <input className="field text-body" type="email" name="email" required autoComplete="email" placeholder="you@firm.com" />
          </label>
          <button type="submit" className="btn btn-primary text-body">
            Send sign-in link
          </button>
        </form>
      </div>
    </div>
  )
}
