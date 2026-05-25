// Coming soon — Phase D
// This route will be implemented as part of Phase D (FM-critic new components).

export default async function CellDetailPage({
  params,
}: {
  params: Promise<{ cell_id: string }>;
}) {
  const { cell_id } = await params;
  return (
    <div className="min-h-screen bg-[#F8F4EC] p-6">
      <p className="text-sm text-[#6B5E4E]">Coming soon — Phase D</p>
      <p className="text-xs text-[#9E8E7E] mt-1">Cell: {cell_id}</p>
    </div>
  );
}
