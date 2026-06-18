import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";
import { prisma } from "@/lib/prisma";

export const runtime = "nodejs";

const MAX_LEN = 8000;

// The signed-in user reads/writes their own copilot system prompt.
export async function GET() {
  const session = await auth();
  const uid = session?.user?.id;
  if (!uid) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const user = await prisma.user.findUnique({
    where: { id: uid },
    select: { systemPrompt: true },
  });
  return NextResponse.json({ systemPrompt: user?.systemPrompt ?? "" });
}

export async function POST(req: NextRequest) {
  const session = await auth();
  const uid = session?.user?.id;
  if (!uid) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const body = (await req.json().catch(() => null)) as { systemPrompt?: unknown } | null;
  const raw = typeof body?.systemPrompt === "string" ? body.systemPrompt : "";
  const systemPrompt = raw.slice(0, MAX_LEN);

  await prisma.user.update({ where: { id: uid }, data: { systemPrompt } });
  return NextResponse.json({ ok: true, systemPrompt });
}
