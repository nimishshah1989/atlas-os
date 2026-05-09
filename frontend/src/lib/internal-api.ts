// src/lib/internal-api.ts
import 'server-only'

const INTERNAL_BASE_URL =
  process.env.ATLAS_INTERNAL_API_BASE_URL ?? 'http://13.206.34.214:8002'

export type RecomputeResponse =
  | { ok: true; compute_run_id: string; milestone: string; log_file: string }
  | { ok: false; error_code: string; message: string; existing_run_id?: string }

export async function triggerRecompute(
  milestone: 'm3' | 'm4' | 'm5' | 'all',
): Promise<RecomputeResponse> {
  const secret = process.env.ATLAS_INTERNAL_SECRET
  if (!secret) {
    return {
      ok: false,
      error_code: 'config_missing',
      message: 'ATLAS_INTERNAL_SECRET not set on server',
    }
  }

  let res: Response
  try {
    res = await fetch(`${INTERNAL_BASE_URL}/internal/recompute/${milestone}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${secret}` },
      cache: 'no-store',
    })
  } catch (err) {
    return {
      ok: false,
      error_code: 'network_error',
      message: err instanceof Error ? err.message : String(err),
    }
  }

  // The Python endpoint returns: { "data": { compute_run_id, milestone, status, log_file }, "meta": {...} }
  // Error shape: { "detail": { "error_code", "message", "context": { "run_id"? } } }
  const body = await res.json().catch(() => null)

  if (res.status === 202 && body?.data) {
    return {
      ok: true,
      compute_run_id: body.data.compute_run_id,
      milestone: body.data.milestone,
      log_file: body.data.log_file,
    }
  }

  if (res.status === 409 && body?.detail) {
    return {
      ok: false,
      error_code: 'already_running',
      message: 'A recompute is already in progress',
      existing_run_id: body.detail.context?.run_id,
    }
  }

  return {
    ok: false,
    error_code: body?.detail?.error_code ?? 'unknown',
    message: body?.detail?.message ?? `Unexpected status ${res.status}`,
  }
}
