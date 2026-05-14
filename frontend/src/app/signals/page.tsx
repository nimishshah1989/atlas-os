export const dynamic = 'force-dynamic'

import { SignalCard } from "@/components/signals/SignalCard";

interface SignalReport {
  id: string;
  ticker: string;
  company_name?: string;
  condition_label: string;
  condition_tier: number;
  confirmation_level: string;
  verdict: string;
  conviction_score?: number;
  triggered_at: string;
}

async function fetchSignals(): Promise<{ reports: SignalReport[]; total: number }> {
  const base = process.env.ATLAS_TV_API_BASE_URL ?? process.env.ATLAS_INTERNAL_API_BASE_URL;
  const res = await fetch(
    `${base}/api/v1/tv/signals?limit=50`,
    {
      headers: { Authorization: `Bearer ${process.env.ATLAS_INTERNAL_SECRET ?? ""}` },
      next: { revalidate: 30 },
    }
  );
  if (!res.ok) return { reports: [], total: 0 };
  return res.json();
}

export default async function SignalsPage() {
  const { reports, total } = await fetchSignals();

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Signal Feed</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            TradingView Pine Script triggers — dual-confirmed with Atlas intelligence
          </p>
        </div>
        <span className="text-sm text-gray-400">{total} total</span>
      </div>

      {reports.length === 0 ? (
        <div className="text-center py-16 text-gray-400 text-sm">
          No signals yet. TV alerts will appear here when Pine conditions fire.
        </div>
      ) : (
        <div className="space-y-3">
          {reports.map((r) => (
            <SignalCard
              key={r.id}
              id={r.id}
              ticker={r.ticker}
              companyName={r.company_name}
              conditionLabel={r.condition_label}
              conditionTier={r.condition_tier}
              confirmationLevel={r.confirmation_level}
              verdict={r.verdict}
              convictionScore={r.conviction_score}
              triggeredAt={r.triggered_at}
            />
          ))}
        </div>
      )}
    </div>
  );
}
