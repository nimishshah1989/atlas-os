import { NextRequest, NextResponse } from "next/server";
import fs from "fs";
import path from "path";

const ALLOWED_BASE = process.env.SIGNAL_SCREENSHOT_DIR ?? "/data/signals/screenshots";

export async function GET(req: NextRequest) {
  const filePath = req.nextUrl.searchParams.get("path");
  if (!filePath) {
    return NextResponse.json({ error: "path required" }, { status: 400 });
  }

  // Security: ensure the path is within the allowed base directory
  const resolved = path.resolve(filePath);
  if (!resolved.startsWith(path.resolve(ALLOWED_BASE))) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  if (!fs.existsSync(resolved)) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }

  const buffer = fs.readFileSync(resolved);
  return new NextResponse(buffer, {
    headers: { "Content-Type": "image/png", "Cache-Control": "public, max-age=86400" },
  });
}
