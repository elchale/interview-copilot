import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export const runtime = "nodejs";

// The local agent polls this for new commands after `since` (the cursor),
// authenticated by its device token — same auth as /api/ingest and /api/config.
export async function GET(req: NextRequest) {
  const header = req.headers.get("authorization") ?? "";
  const token = header.startsWith("Bearer ") ? header.slice(7) : "";
  if (!token) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const device = await prisma.device.findUnique({ where: { token } });
  if (!device) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const since = Number(req.nextUrl.searchParams.get("since") ?? "0") || 0;
  const rows = await prisma.command.findMany({
    where: { userId: device.userId, id: { gt: since } },
    orderBy: { id: "asc" },
    take: 100,
  });
  const cursor = rows.length ? rows[rows.length - 1].id : since;
  return NextResponse.json({
    cursor,
    commands: rows.map((r) => ({ id: r.id, type: r.type, payload: r.payload })),
  });
}
