import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { isExpired } from "@/lib/tokens";

export const runtime = "nodejs";

// The agent polls this until the browser login claims the code.
export async function GET(req: NextRequest) {
  const code = req.nextUrl.searchParams.get("code") ?? "";
  const pc = await prisma.pairCode.findUnique({ where: { deviceCode: code } });
  if (!pc || isExpired(pc.createdAt)) {
    return NextResponse.json({ status: "expired" }, { status: 404 });
  }
  if (pc.status === "claimed") {
    return NextResponse.json({
      status: "claimed",
      token: pc.agentToken,
      ingest_url: `${req.nextUrl.origin}/api/ingest`,
    });
  }
  return NextResponse.json({ status: "pending" });
}
