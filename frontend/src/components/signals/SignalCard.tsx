"use client";

import Link from "next/link";

interface SignalCardProps {
  id: string;
  ticker: string;
  companyName?: string;
  conditionLabel: string;
  conditionTier: number;
  confirmationLevel: string;
  verdict: string;
  convictionScore?: number;
  triggeredAt: string;
}

const TIER_STYLES: Record<number, { bg: string; label: string }> = {
  1: { bg: "bg-red-100 text-red-800 border-red-200", label: "T1 Critical" },
  2: { bg: "bg-orange-100 text-orange-800 border-orange-200", label: "T2 High" },
  3: { bg: "bg-yellow-100 text-yellow-800 border-yellow-200", label: "T3 Medium" },
  4: { bg: "bg-gray-100 text-gray-600 border-gray-200", label: "T4 Low" },
  5: { bg: "bg-purple-100 text-purple-800 border-purple-200", label: "T5 Sell" },
};

export function SignalCard({
  id, ticker, companyName, conditionLabel, conditionTier,
  confirmationLevel, verdict, convictionScore, triggeredAt,
}: SignalCardProps) {
  const tierStyle = TIER_STYLES[conditionTier] ?? TIER_STYLES[4];
  const isDual = confirmationLevel === "dual";
  const verdictColor = verdict === "bullish" ? "text-emerald-600" : verdict === "bearish" ? "text-red-600" : "text-yellow-600";

  return (
    <Link href={`/signals/${id}`} className="block">
      <div className="border border-gray-200 rounded-lg p-4 hover:border-teal-300 hover:shadow-sm transition-all bg-white">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 mb-1">
              <span className="font-semibold text-gray-900 text-sm">{ticker}</span>
              {companyName && (
                <span className="text-gray-500 text-xs truncate">{companyName}</span>
              )}
            </div>
            <p className="text-sm text-gray-700 leading-snug">{conditionLabel}</p>
          </div>
          <div className="flex flex-col items-end gap-1.5 shrink-0">
            <span className={`text-xs font-medium px-2 py-0.5 rounded border ${tierStyle.bg}`}>
              {tierStyle.label}
            </span>
            {isDual && (
              <span className="text-xs font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded">
                DUAL ✓
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center justify-between mt-3 pt-2 border-t border-gray-100">
          <div className="flex items-center gap-3">
            <span className={`text-xs font-semibold uppercase ${verdictColor}`}>{verdict}</span>
            {convictionScore != null && (
              <span className="text-xs text-gray-500">
                Conviction {Number(convictionScore).toFixed(1)}/10
              </span>
            )}
          </div>
          <span className="text-xs text-gray-400">
            {new Date(triggeredAt).toLocaleString("en-IN", {
              day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
            })}
          </span>
        </div>
      </div>
    </Link>
  );
}
