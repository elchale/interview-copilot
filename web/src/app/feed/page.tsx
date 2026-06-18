import { redirect } from "next/navigation";
import { auth } from "@/auth";
import Feed from "./Feed";

export default async function FeedPage() {
  const session = await auth();
  if (!session?.user) redirect("/api/auth/signin?callbackUrl=/feed");
  return <Feed />;
}
