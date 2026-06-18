import { NextResponse } from "next/server";
import { auth } from "@/auth";
import { prisma } from "@/lib/prisma";

export const runtime = "nodejs";

// Wipes the signed-in user's feed history (transcript, answers, context).
export async function POST() {
  const session = await auth();
  const uid = session?.user?.id;
  if (!uid) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { count } = await prisma.event.deleteMany({ where: { userId: uid } });
  return NextResponse.json({ ok: true, deleted: count });
}
