// TEMP mockup route — two graphical "score derivation tree" variants for design sign-off.
// Real data (rule #0): real stock's lens scores + deciles + sub-components + actual values
// via the same queries the stock detail page uses. Remove once the design is chosen.
//   /mockup/score-tree            → defaults to RELIANCE
//   /mockup/score-tree?s=TCS      → any symbol
import { getStockDecile, getStockEvidence } from '@/lib/queries/v6/stock_lens'
import { stockToLadder } from '@/components/v4/adapters/stockToLadder'
import { ScoreTreeMock } from '@/components/v6/mockup/ScoreTreeMock'

export const dynamic = 'force-dynamic'

export default async function Page({ searchParams }: { searchParams: Promise<{ s?: string }> }) {
  const symbol = ((await searchParams)?.s ?? 'RELIANCE').toUpperCase()
  const [decile, ev] = await Promise.all([getStockDecile(symbol), getStockEvidence(symbol)])
  if (!decile) {
    return <div className="mx-auto max-w-[900px] px-6 py-12 font-sans text-txt-2">No scored data for {symbol}. Try ?s=TCS / ?s=INFY.</div>
  }
  const ladder = stockToLadder(decile, ev)
  return (
    <ScoreTreeMock
      symbol={symbol}
      name={decile.name}
      strength={ladder.strength}
      leadership={ladder.leadership}
      lenses={ladder.lenses}
    />
  )
}
