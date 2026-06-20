import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";
import { prisma } from "@/lib/prisma";

export const runtime = "nodejs";

// The viewer enqueues a command for the local agent (e.g. re-answer a question).
export async function POST(req: NextRequest) {
  const session = await auth();
  const uid = session?.user?.id;
  if (!uid) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const body = (await req.json().catch(() => null)) as
    | { type?: unknown; payload?: unknown }
    | null;
  const type = String(body?.type ?? "");
  if (type !== "reanswer") {
    return NextResponse.json({ error: "bad type" }, { status: 400 });
  }

  const cmd = await prisma.command.create({
    data: { userId: uid, type, payload: (body?.payload ?? {}) as object },
  });
  return NextResponse.json({ ok: true, id: cmd.id });
}
