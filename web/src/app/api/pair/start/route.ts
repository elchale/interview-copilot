import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { newToken } from "@/lib/tokens";

export const runtime = "nodejs";

// Called by the local agent (no auth) to begin pairing.
export async function POST(req: NextRequest) {
  const deviceCode = newToken(24);
  await prisma.pairCode.create({ data: { deviceCode } });
  const origin = req.nextUrl.origin;
  return NextResponse.json({
    device_code: deviceCode,
    verify_url: `${origin}/pair?code=${deviceCode}`,
    poll_url: `${origin}/api/pair/poll?code=${deviceCode}`,
  });
}
