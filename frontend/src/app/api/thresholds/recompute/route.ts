// POST /api/thresholds/recompute — re-blend the composite from cached lens sub-scores using the
// CURRENT saved weights, in foundation_staging. Two modes via { apply?: boolean }:
//   apply=false (default) → preview: how many composites/tiers would shift (no write).
//   apply=true            → verify-gated single in-DB UPDATE of the latest snapshot.
// Delegates to scripts/foundation/recompute_composite_fast.py so the math stays the ONE canonical
// scorer (rule #0) — the route never re-implements scoring. Latest snapshot only → seconds.
import { NextResponse } from 'next/server'
import { spawn } from 'node:child_process'
import path from 'node:path'

export const dynamic = 'force-dynamic'
export const maxDuration = 120

const REPO_ROOT = path.resolve(process.cwd(), '..') // frontend/ → repo root

function runEngine(args: string[]): Promise<{ code: number; stdout: string; stderr: string }> {
  return new Promise((resolve) => {
    const proc = spawn('python3', ['scripts/foundation/recompute_composite_fast.py', ...args, '--json'], {
      cwd: REPO_ROOT,
      env: process.env,
    })
    let stdout = ''
    let stderr = ''
    proc.stdout.on('data', (d) => (stdout += d.toString()))
    proc.stderr.on('data', (d) => (stderr += d.toString()))
    proc.on('close', (code) => resolve({ code: code ?? -1, stdout, stderr }))
    proc.on('error', (e) => resolve({ code: -1, stdout, stderr: String(e) }))
  })
}

export async function POST(req: Request) {
  let apply = false
  try {
    const body = await req.json()
    apply = body?.apply === true
  } catch {
    // no body → preview
  }

  const { code, stdout, stderr } = await runEngine(apply ? ['--apply'] : [])
  if (code !== 0) {
    return NextResponse.json(
      { error_code: 'recompute_failed', message: stderr.trim().split('\n').slice(-3).join(' ') || 'engine error' },
      { status: 500 },
    )
  }
  // The engine prints one JSON line (last line of stdout).
  const line = stdout.trim().split('\n').filter(Boolean).pop() ?? '{}'
  let data: unknown
  try {
    data = JSON.parse(line)
  } catch {
    return NextResponse.json({ error_code: 'bad_engine_output', message: line.slice(0, 200) }, { status: 500 })
  }
  return NextResponse.json({ data: { mode: apply ? 'applied' : 'preview', ...(data as object) } })
}
