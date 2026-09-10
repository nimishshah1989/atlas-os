// src/app/sectors/[id]/page.tsx — one sector. Logic lives in components/sectors.
import { notFound } from 'next/navigation'
import { NoDatabase } from '@/components/health/NoDatabase'
import { SectorView } from '@/components/sectors/SectorView'
import { PageHeader } from '@/components/ui/PageHeader'
import { QueryFailed } from '@/components/ui/Section'
import { requireUser } from '@/lib/auth'
import { dbAvailable } from '@/lib/db'
import { getSector } from '@/lib/queries/sectors'
import { attempt } from '@/lib/result'

type Params = { params: Promise<{ id: string }> }

const idOf = async ({ params }: Params): Promise<string> => {
  const { id } = await params
  try {
    return decodeURIComponent(id)
  } catch {
    return id
  }
}

export async function generateMetadata(props: Params) {
  return { title: await idOf(props) }
}

export default async function SectorPage(props: Params) {
  await requireUser()
  const id = await idOf(props)
  if (!dbAvailable) return <NoDatabase title="Sectors" />
  const detail = await attempt(getSector(id))
  if (!detail.ok) {
    return (
      <div className="page">
        <PageHeader title={id} />
        <QueryFailed error={detail.error} />
      </div>
    )
  }
  if (!detail.value) notFound()
  return <SectorView detail={detail.value} />
}
