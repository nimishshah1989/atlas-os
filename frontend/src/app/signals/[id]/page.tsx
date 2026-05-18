export const dynamic = 'force-dynamic'

import { notFound } from "next/navigation";
import { SignalReport } from "@/components/signals/SignalReport";

async function fetchReport(id: string) {
  const base = process.env.ATLAS_TV_API_BASE_URL ?? process.env.ATLAS_INTERNAL_API_BASE_URL;
  const res = await fetch(
    `${base}/api/v1/tv/signals/${id}`,
    {
      headers: { Authorization: `Bearer ${process.env.ATLAS_INTERNAL_SECRET ?? ""}` },
      next: { revalidate: 60 },
    }
  );
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Report fetch failed: ${res.status}`);
  return res.json();
}

export default async function SignalReportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const report = await fetchReport(id);
  if (!report) notFound();
  return (
    <div className="px-4 py-8">
      <SignalReport report={report} />
    </div>
  );
}
