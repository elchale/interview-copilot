import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";
import { prisma } from "@/lib/prisma";

export const runtime = "nodejs";

// The viewer polls this for new feed events after `since` (the cursor).
export async function GET(req: NextRequest) {
  const session = await auth();
  const uid = session?.user?.id;
  if (!uid) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const since = Number(req.nextUrl.searchParams.get("since") ?? "0") || 0;
  const rows = await prisma.event.findMany({
    where: { userId: uid, id: { gt: since } },
    orderBy: { id: "asc" },
    take: 500,
  });
  const cursor = rows.length ? rows[rows.length - 1].id : since;
  return NextResponse.json({
    cursor,
    events: rows.map((r) => ({ id: r.id, kind: r.kind, payload: r.payload })),
  });
}
