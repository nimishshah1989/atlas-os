import { redirect } from 'next/navigation'

export default function USStocksPage() {
  redirect('/us?tab=Stocks')
}
