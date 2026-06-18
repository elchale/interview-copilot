import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export const runtime = "nodejs";

// The local agent fetches the paired user's configuration (system prompt) here,
// authenticated by its device token — same auth as /api/ingest.
export async function GET(req: NextRequest) {
  const header = req.headers.get("authorization") ?? "";
  const token = header.startsWith("Bearer ") ? header.slice(7) : "";
  if (!token) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const device = await prisma.device.findUnique({
    where: { token },
    include: { user: { select: { systemPrompt: true } } },
  });
  if (!device) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  return NextResponse.json({ systemPrompt: device.user.systemPrompt ?? "" });
}
