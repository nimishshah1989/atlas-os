// POST /api/portfolios/create — create a new FM basket from picked instruments, or
// add picks to an existing basket. Delegates ALL booking to portfolio_run.py (rule #0:
// the route never sizes a position or invents a price — Python owns the accounting).
//   { name: string,     picks: ["stock:SYMBOL" | "etf:SYMBOL" | "fund:MSTAR_ID", ...] }  → new basket
//   { basketId: string, picks: [...] }                                                   → add to existing
// New baskets are inited synchronously (inception trades at last EOD close); the
// 1/3/5y what-if backtest is kicked off fire-and-forget and appears on the detail
// page when it lands.
import { NextResponse } from 'next/server'
import { spawn } from 'node:child_process'
import path from 'node:path'
import { resolvePicks } from '@/lib/queries/portfolios'

export const dynamic = 'force-dynamic'
export const maxDuration = 300

const REPO_ROOT = path.resolve(process.cwd(), '..')
const ENGINE = 'scripts/foundation/portfolio_run.py'

function run(args: string[]): Promise<{ code: number; stdout: string; stderr: string }> {
  return new Promise((resolve) => {
    const proc = spawn('python3', [ENGINE, ...args], { cwd: REPO_ROOT, env: process.env })
    let stdout = ''
    let stderr = ''
    proc.stdout.on('data', (d) => (stdout += d.toString()))
    proc.stderr.on('data', (d) => (stderr += d.toString()))
    proc.on('close', (code) => resolve({ code: code ?? -1, stdout, stderr }))
    proc.on('error', (e) => resolve({ code: -1, stdout, stderr: String(e) }))
  })
}

const lastJson = (stdout: string): Record<string, unknown> => {
  try {
    return JSON.parse(stdout.trim().split('\n').filter(Boolean).pop() ?? '{}')
  } catch {
    return {}
  }
}

const err = (status: number, message: string) =>
  NextResponse.json({ error_code: 'basket_failed', message }, { status })

type Holding = { key: string; weightPct: number }

export async function POST(req: Request) {
  let body: {
    name?: string
    basketId?: string
    picks?: string[]
    holdings?: Holding[]
    capital?: number
  }
  try {
    body = await req.json()
  } catch {
    return err(400, 'invalid JSON body')
  }

  // weighted builder path: { name, capital, holdings:[{key, weightPct}] }
  if (Array.isArray(body.holdings)) return createWeighted(body)

  const picks = Array.isArray(body.picks) ? body.picks.filter((p) => typeof p === 'string') : []
  if (!picks.length || !picks.every((p) => /^(stock|etf|fund):.+$/.test(p)))
    return err(400, 'picks must be ["stock:SYMBOL" | "etf:SYMBOL" | "fund:MSTAR_ID", ...]')
  const { resolved, unknown } = await resolvePicks(picks)
  if (unknown.length) return err(400, `unknown instruments: ${unknown.join(', ')}`)

  // add to an existing basket: one manual buy per pick, at last EOD close
  if (body.basketId) {
    const results: { pick: string; ok: boolean; detail: string }[] = []
    for (const key of resolved) {
      const r = await run(['trade', '--portfolio-id', body.basketId, '--side', 'buy', '--key', key])
      results.push({
        pick: key,
        ok: r.code === 0,
        detail: r.code === 0 ? JSON.stringify(lastJson(r.stdout)) : r.stderr.trim().split('\n').pop() ?? 'failed',
      })
    }
    return NextResponse.json({ data: { basketId: body.basketId, results } })
  }

  // new basket: create (picks in params) → init → fire-and-forget backtest
  const name = (body.name ?? '').trim()
  if (!name) return err(400, 'name is required for a new basket')
  const classes = [...new Set(resolved.map((p) => p.split(':', 1)[0]))]
  const created = await run([
    'create', '--name', name, '--kind', 'basket',
    '--params', JSON.stringify({ picks: resolved }),
    '--asset-classes', ...classes,
  ])
  if (created.code !== 0)
    return err(500, created.stderr.trim().split('\n').pop() ?? 'create failed')
  const portfolioId = String(lastJson(created.stdout).portfolio_id ?? '')
  if (!portfolioId) return err(500, 'engine returned no portfolio_id')

  const inited = await run(['init', '--portfolio-id', portfolioId])
  if (inited.code !== 0)
    return err(500, inited.stderr.trim().split('\n').pop() ?? 'init failed')

  // what-if backtest lands asynchronously; the detail page shows it when stored
  spawn('python3', [ENGINE, 'backtest', '--portfolio-id', portfolioId], {
    cwd: REPO_ROOT, env: process.env, detached: true, stdio: 'ignore',
  }).unref()

  return NextResponse.json({
    data: { portfolioId, init: lastJson(inited.stdout), backtest: 'queued' },
  })
}

// A hand-built weighted basket: each holding sized to its own % of capital, priced
// at the last EOD close by the engine. Weights may sum to <=100% (remainder = cash).
async function createWeighted(body: {
  name?: string
  capital?: number
  holdings?: Holding[]
}) {
  const name = (body.name ?? '').trim()
  if (name.length < 2) return err(400, 'name is required')
  const capital = Number(body.capital)
  if (!Number.isFinite(capital) || capital < 100000 || capital > 1e9)
    return err(400, 'capital must be between 1,00,000 and 1,00,00,00,000')
  const holdings = (body.holdings ?? []).filter(
    (h) => typeof h?.key === 'string' && Number.isFinite(h?.weightPct),
  )
  if (!holdings.length) return err(400, 'add at least one instrument')
  if (!holdings.every((h) => /^(stock|etf|fund):.+$/.test(h.key)))
    return err(400, 'each holding needs a valid instrument')
  if (holdings.some((h) => h.weightPct <= 0)) return err(400, 'every weight must be > 0%')
  const total = holdings.reduce((s, h) => s + h.weightPct, 0)
  if (total > 100.0001) return err(400, `weights sum to ${total.toFixed(1)}% — must be ≤ 100%`)

  const keys = holdings.map((h) => h.key)
  const { resolved, unknown } = await resolvePicks(keys)
  if (unknown.length) return err(400, `unknown instruments: ${unknown.join(', ')}`)
  // resolvePicks preserves order and (since unknown is empty) is 1:1 with input
  const weights: Record<string, number> = {}
  holdings.forEach((h, i) => (weights[resolved[i]] = h.weightPct / 100))
  const classes = [...new Set(resolved.map((p) => p.split(':', 1)[0]))]
  // the basket's position cap = its largest declared weight, so the nightly cap gate
  // stays a real guard (a weighted book has no uniform cap — sizing is explicit)
  const maxWeight = Math.min(1, Math.max(...holdings.map((h) => h.weightPct)) / 100)

  const created = await run([
    'create', '--name', name, '--kind', 'basket',
    '--params', JSON.stringify({ picks: resolved, weights }),
    '--asset-classes', ...classes,
    '--capital', String(Math.round(capital)),
    '--cap-pct', String(maxWeight),
  ])
  if (created.code !== 0) return err(500, created.stderr.trim().split('\n').pop() ?? 'create failed')
  const portfolioId = String(lastJson(created.stdout).portfolio_id ?? '')
  if (!portfolioId) return err(500, 'engine returned no portfolio_id')

  const inited = await run(['init', '--portfolio-id', portfolioId])
  if (inited.code !== 0) return err(500, inited.stderr.trim().split('\n').pop() ?? 'init failed')

  spawn('python3', [ENGINE, 'backtest', '--portfolio-id', portfolioId], {
    cwd: REPO_ROOT, env: process.env, detached: true, stdio: 'ignore',
  }).unref()

  return NextResponse.json({ data: { portfolioId, init: lastJson(inited.stdout), backtest: 'queued' } })
}
