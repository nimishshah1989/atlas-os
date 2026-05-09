// src/app/login/page.tsx
import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ from?: string; error?: string }>
}) {
  const { from, error } = await searchParams

  async function login(formData: FormData) {
    'use server'
    const password = formData.get('password') as string
    if (!password || password !== process.env.ATLAS_PASSWORD) {
      const params = new URLSearchParams({ error: '1' })
      if (from) params.set('from', from)
      redirect(`/login?${params.toString()}`)
    }
    const cookieStore = await cookies()
    cookieStore.set('atlas_auth', password, {
      httpOnly: true,
      sameSite: 'lax',
      path: '/',
      maxAge: 60 * 60 * 24 * 7,
    })
    redirect(from ?? '/')
  }

  return (
    <div className="min-h-screen bg-paper flex items-center justify-center">
      <div className="border border-paper-rule rounded-[2px] p-8 w-80">
        <h1 className="font-serif text-xl text-ink-primary mb-1">Atlas-OS</h1>
        <p className="font-sans text-xs text-ink-tertiary mb-6">Javeri Securities</p>
        {error && (
          <p className="font-sans text-xs text-signal-neg mb-3">Incorrect password.</p>
        )}
        <form action={login} className="flex flex-col gap-3">
          <input
            type="password"
            name="password"
            placeholder="Password"
            autoFocus
            required
            className="border border-paper-rule rounded-[2px] px-3 py-2 text-sm font-sans bg-paper text-ink-primary placeholder:text-ink-tertiary focus:outline-none focus:border-accent"
          />
          <button
            type="submit"
            className="bg-accent text-paper font-sans text-sm py-2 rounded-[2px] hover:opacity-90 transition-opacity"
          >
            Sign in
          </button>
        </form>
      </div>
    </div>
  )
}
