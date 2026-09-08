// e2e/global-setup.ts — the board suite's sign-in row. With ATLAS_GLOBAL_DB_URL and
// ATLAS_E2E_BYPASS set, the bypass address is put on the allowlist of THAT database (role
// analyst, invited by this file) so requireUser() takes its normal path. Without them, nothing
// happens and the board suite skips itself. Never run against production: the bypass is dev-only
// (src/lib/e2e.ts) and a production allowlist is the FM's to edit.
import postgres from 'postgres'

export default async function globalSetup() {
  const url = process.env.ATLAS_GLOBAL_DB_URL
  const email = process.env.ATLAS_E2E_BYPASS?.trim().toLowerCase()
  if (!url || !email) return
  const sql = postgres(url, { max: 1, prepare: false })
  try {
    await sql`
      INSERT INTO atlas_global.app_user (email, role, display_name, invited_by)
      VALUES (${email}, 'analyst', 'Playwright smoke', 'frontend-global/e2e/global-setup.ts')
      ON CONFLICT (email) DO NOTHING
    `
  } finally {
    await sql.end()
  }
}
