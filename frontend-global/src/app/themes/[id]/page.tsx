// src/app/themes/[id]/page.tsx — one theme. Logic lives in components/themes.
import { notFound } from 'next/navigation'
import { NoDatabase } from '@/components/health/NoDatabase'
import { ThemeView } from '@/components/themes/ThemeView'
import { PageHeader } from '@/components/ui/PageHeader'
import { QueryFailed } from '@/components/ui/Section'
import { requireUser } from '@/lib/auth'
import { dbAvailable } from '@/lib/db'
import { getTheme, peerGroupMinMembers } from '@/lib/queries/themes'
import { attempt } from '@/lib/result'

type Params = { params: Promise<{ id: string }> }

const idOf = async ({ params }: Params) => decodeURIComponent((await params).id)

export async function generateMetadata(props: Params) {
  const id = await idOf(props)
  const detail = dbAvailable ? await getTheme(id) : null
  return { title: detail?.row.name ?? id }
}

export default async function ThemePage(props: Params) {
  await requireUser()
  const id = await idOf(props)
  if (!dbAvailable) return <NoDatabase title="Themes" />

  const [detail, min] = await Promise.all([attempt(getTheme(id)), attempt(peerGroupMinMembers())])
  if (!detail.ok) {
    return (
      <div className="page">
        <PageHeader title={id} />
        <QueryFailed error={detail.error} />
      </div>
    )
  }
  if (!detail.value) notFound()
  if (!min.ok) {
    return (
      <div className="page">
        <PageHeader title={detail.value.row.name} />
        <QueryFailed error={min.error} />
      </div>
    )
  }
  return <ThemeView detail={detail.value} minMembers={min.value} />
}
