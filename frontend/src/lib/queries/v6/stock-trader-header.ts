// frontend/src/lib/queries/v6/stock-trader-header.ts
//
// Reads atlas.mv_stock_landscape_trader for the trader-view header on
// /stocks/[symbol]. Exposes verdict + source + tracking columns; the
// rest of the stock detail page continues to read mv_stock_deepdive.
//
// Spec: docs/superpowers/specs/2026-05-28-trader-view-redesign.html §4 + §8
// View: migration 116 (DROP + CREATE with verdict_source axis)

import 'server-only'
import sql from '@/lib/db'
import type { Verdict } from '@/components/v6/trader-view'

export type StockTraderHeader = {
  symbol: string
  cap_tier: string | null
  conviction_score: number | null
  conviction_tier: string | null
  composite_score: number | null
  combined_verdict: Verdict | string | null
  verdict_reason: string | null
  verdict_source: 'signal_call' | 'composite_score' | 'no_data' | null
  first_called_at: string | null
  since_call_return: number | null
  cell_action: string | null
  cell_tenure: string | null
  cell_predicted_excess: number | null
  cell_ic: number | null
  close_price: number | null
}

type Row = {
  symbol: string
  cap_tier: string | null
  conviction_score: string | null
  conviction_tier: string | null
  composite_score: string | null
  combined_verdict: string | null
  verdict_reason: string | null
  verdict_source: string | null
  first_called_at: string | null
  since_call_return: string | null
  cell_action: string | null
  cell_tenure: string | null
  cell_predicted_excess: string | null
  cell_ic: string | null
  close_price: string | null
}

function toNumber(s: string | number | null | undefined): number | null {
  if (s == null) return null
  const n = typeof s === 'number' ? s : Number(s)
  return Number.isFinite(n) ? n : null
}

export async function getStockTraderHeader(symbol: string): Promise<StockTraderHeader | null> {
  const rows = await sql<Row[]>`
    SELECT
      symbol,
      cap_tier::text                  AS cap_tier,
      conviction_score::text          AS conviction_score,
      conviction_tier,
      composite_score::text           AS composite_score,
      combined_verdict,
      verdict_reason,
      verdict_source,
      first_called_at::text           AS first_called_at,
      since_call_return::text         AS since_call_return,
      cell_action::text               AS cell_action,
      cell_tenure::text               AS cell_tenure,
      cell_predicted_excess::text     AS cell_predicted_excess,
      cell_ic::text                   AS cell_ic,
      close_price::text               AS close_price
    FROM atlas.mv_stock_landscape_trader
    WHERE symbol = ${symbol}
    LIMIT 1
  `
  const r = rows[0]
  if (!r) return null

  return {
    symbol: r.symbol,
    cap_tier: r.cap_tier,
    conviction_score: toNumber(r.conviction_score),
    conviction_tier: r.conviction_tier,
    composite_score: toNumber(r.composite_score),
    combined_verdict: r.combined_verdict,
    verdict_reason: r.verdict_reason,
    verdict_source: r.verdict_source as StockTraderHeader['verdict_source'],
    first_called_at: r.first_called_at,
    since_call_return: toNumber(r.since_call_return),
    cell_action: r.cell_action,
    cell_tenure: r.cell_tenure,
    cell_predicted_excess: toNumber(r.cell_predicted_excess),
    cell_ic: toNumber(r.cell_ic),
    close_price: toNumber(r.close_price),
  }
}
