// frontend/src/app/api/health/route.ts
// Machine-readable health endpoint for monitoring / alerting.
// Returns HTTP 200 when healthy, 503 when critical anomalies or validator FAILs.

import { NextResponse } from 'next/server'
import {
  getHeaderStatus,
  getFreshness,
  getJipFreshness,
  getRecentRuns,
  lagThresholdDays,
  jipLagThresholdDays,
} from '@/lib/queries/health'

export const dynamic = 'force-dynamic'

export async function GET() {
  const [status, freshness, jipFreshness, recentRuns] = await Promise.all([
    getHeaderStatus(),
    getFreshness(),
    getJipFreshness(),
    getRecentRuns(10),
  ])

  const staleTables = freshness
    .filter((t) => t.lag_days != null && t.lag_days > lagThresholdDays(t.table_name))
    .map((t) => ({ table: t.table_name, lag_days: t.lag_days }))

  const jipStaleTables = jipFreshness
    .filter((t) => t.lag_days != null && t.lag_days > jipLagThresholdDays(t.table_name))
    .map((t) => ({ table: t.table_name, lag_days: t.lag_days }))

  const recentFailures = recentRuns
    .filter((r) => r.status === 'failed')
    .map((r) => ({
      script: r.script_name,
      started_at: r.started_at,
      error: r.error_message,
    }))

  const body = {
    status: status.level,
    message: status.message,
    checked_at: new Date().toISOString(),
    last_health_check: status.last_health_check,
    pipeline: {
      recent_failures: recentFailures,
    },
    freshness: {
      stale_tables: staleTables,
      jip_stale_tables: jipStaleTables,
    },
  }

  const httpStatus = status.level === 'red' ? 503 : 200
  return NextResponse.json(body, { status: httpStatus })
}
