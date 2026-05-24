import { NextRequest, NextResponse } from "next/server";

const TV_API_BASE =
  process.env.ATLAS_TV_API_BASE_URL ?? process.env.ATLAS_INTERNAL_API_BASE_URL ?? "";
const SECRET = process.env.ATLAS_INTERNAL_SECRET ?? "";

export async function GET(req: NextRequest) {
  const filePath = req.nextUrl.searchParams.get("path");
  if (!filePath) {
    return NextResponse.json({ error: "path required" }, { status: 400 });
  }

  const upstream = `${TV_API_BASE}/api/v1/tv/screenshot?path=${encodeURIComponent(filePath)}`;

  try {
    const res = await fetch(upstream, {
      headers: { "X-Internal-Secret": SECRET },
      next: { revalidate: 86400 },
    });

    if (!res.ok) {
      return NextResponse.json({ error: "screenshot unavailable" }, { status: res.status });
    }

    const buffer = await res.arrayBuffer();
    return new NextResponse(buffer, {
      headers: {
        "Content-Type": "image/png",
        "Cache-Control": "public, max-age=86400",
      },
    });
  } catch {
    return NextResponse.json({ error: "upstream unreachable" }, { status: 502 });
  }
}
