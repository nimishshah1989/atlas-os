// Coming soon — Phase C
// This route will be implemented as part of Phase C (page composites).

export default async function ETFDetailPage({
  params,
}: {
  params: Promise<{ iid: string }>;
}) {
  const { iid } = await params;
  return (
    <div className="min-h-screen bg-[#F8F4EC] p-6">
      <p className="text-sm text-[#6B5E4E]">Coming soon — Phase C</p>
      <p className="text-xs text-[#9E8E7E] mt-1">ETF: {iid}</p>
    </div>
  );
}
