import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { prisma } from "@/lib/prisma";
import { newToken, isExpired } from "@/lib/tokens";

export const runtime = "nodejs";

// Browser lands here from the agent. After Google login, bind the pairing code
// to the user, mint the agent token, and tell the user to go back to the app.
export default async function PairPage({
  searchParams,
}: {
  searchParams: Promise<{ code?: string }>;
}) {
  const { code = "" } = await searchParams;
  const session = await auth();
  if (!session?.user) {
    redirect(`/api/auth/signin?callbackUrl=${encodeURIComponent(`/pair?code=${code}`)}`);
  }
  const uid = session.user.id;

  let ok = false;
  const pc = await prisma.pairCode.findUnique({ where: { deviceCode: code } });
  if (pc && pc.status === "pending" && !isExpired(pc.createdAt)) {
    const token = newToken();
    await prisma.device.create({ data: { userId: uid, token } });
    await prisma.pairCode.update({
      where: { deviceCode: code },
      data: { status: "claimed", userId: uid, agentToken: token },
    });
    ok = true;
  }

  return (
    <div className="wrap">
      {ok ? (
        <div className="card" style={{ textAlign: "center", borderColor: "#2e7d32" }}>
          <h1>✓ All set</h1>
          <p>Your app is connected. You can go back to the app — opening your live feed now…</p>
          <p style={{ marginTop: 14 }}><a className="btn" href="/feed">Open feed</a></p>
          <meta httpEquiv="refresh" content="2; url=/feed" />
        </div>
      ) : (
        <div className="card">
          <h1>Pairing failed</h1>
          <p className="muted">That pairing link is invalid or expired. Restart the app to try again.</p>
        </div>
      )}
    </div>
  );
}
