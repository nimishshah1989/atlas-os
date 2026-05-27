'use server'

import { getTopPicksBySector, type TopPickRow } from '@/lib/queries/sector-deep-dive'

export async function getTopPicksAction(sectorName: string): Promise<TopPickRow[]> {
  if (!sectorName || typeof sectorName !== 'string') return []
  try {
    return await getTopPicksBySector(sectorName)
  } catch {
    return []
  }
}
