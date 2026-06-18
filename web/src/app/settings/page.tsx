import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { prisma } from "@/lib/prisma";
import SettingsForm from "./SettingsForm";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const session = await auth();
  const uid = session?.user?.id;
  if (!uid) redirect("/api/auth/signin?callbackUrl=/settings");

  const user = await prisma.user.findUnique({
    where: { id: uid },
    select: { systemPrompt: true },
  });

  return (
    <>
      <div className="topbar">
        <a className="brand" href="/">Interview Copilot</a>
        <div>
          <a href="/feed">Open feed</a>{" "}&nbsp;
          <a href="/api/auth/signout">Log out</a>
        </div>
      </div>
      <div className="wrap">
        <h1>Copilot system prompt</h1>
        <p className="muted">
          Tell the copilot who you are and how it should answer for you — your background,
          experience, projects, the kind of role you&apos;re interviewing for, and any style
          preferences. This is woven into every answer and into the context notes. It applies the
          next time you start a call.
        </p>
        <SettingsForm initial={user?.systemPrompt ?? ""} />
      </div>
    </>
  );
}
