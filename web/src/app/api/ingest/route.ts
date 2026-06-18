import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export const runtime = "nodejs";

type IncomingEvent = { kind?: unknown; payload?: unknown };

// The local agent POSTs batched feed events here, authenticated by its device token.
export async function POST(req: NextRequest) {
  const header = req.headers.get("authorization") ?? "";
  const token = header.startsWith("Bearer ") ? header.slice(7) : "";
  if (!token) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const device = await prisma.device.findUnique({ where: { token } });
  if (!device) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const body = (await req.json().catch(() => null)) as { events?: IncomingEvent[] } | null;
  const events = Array.isArray(body?.events) ? body!.events : [];
  if (events.length) {
    await prisma.event.createMany({
      data: events.slice(0, 500).map((e) => ({
        userId: device.userId,
        kind: String(e.kind ?? ""),
        payload: (e.payload ?? {}) as object,
      })),
    });
  }
  return NextResponse.json({ ok: true, count: events.length });
}
