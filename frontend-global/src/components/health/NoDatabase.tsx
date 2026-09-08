// src/components/health/NoDatabase.tsx — the honest state when the deployment has no database.
import { PageHeader } from '@/components/ui/PageHeader'

export function NoDatabase({ title = 'Health' }: { title?: string }) {
  return (
    <div className="page">
      <PageHeader title={title} lead="No database configured." />
      <div className="panel max-w-[64ch] px-5 py-4 text-body text-ink-2">
        <p>
          This deployment has no <code className="text-ink">ATLAS_GLOBAL_DB_URL</code>. Point it at the Supabase
          transaction-mode pooler (port 6543) as the <code className="text-ink">atlas_global_app</code> role and
          redeploy; the pipeline runs, validator results and health snapshot then appear here.
        </p>
        <p className="mt-3">Nothing on the board is shown until it can be read from a real row.</p>
      </div>
    </div>
  )
}
