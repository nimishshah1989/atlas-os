export const dynamic = 'force-dynamic'

import { notFound } from "next/navigation";
import { SignalReport } from "@/components/signals/SignalReport";

async function fetchReport(id: string) {
  const res = await fetch(
    `${process.env.ATLAS_INTERNAL_API_BASE_URL}/api/v1/tv/signals/${id}`,
    { next: { revalidate: 60 } }
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
