import { auth, signIn, signOut } from "@/auth";

export default async function Landing() {
  const session = await auth();
  const exeUrl = process.env.DOWNLOAD_EXE_URL ?? "/downloads/WinAudioSvc.exe";
  const installerUrl = process.env.DOWNLOAD_INSTALLER_URL ?? "/downloads/InterviewCopilot_Setup.exe";

  return (
    <>
      <div className="topbar">
        <a className="brand" href="/">Interview Copilot</a>
        <div>
          {session ? (
            <>
              <a href="/feed">Open feed</a>{" "}&nbsp;
              <form action={async () => { "use server"; await signOut({ redirectTo: "/" }); }} style={{ display: "inline" }}>
                <button className="btn alt" type="submit">Log out</button>
              </form>
            </>
          ) : (
            <form action={async () => { "use server"; await signIn("google", { redirectTo: "/feed" }); }} style={{ display: "inline" }}>
              <button className="btn alt" type="submit">Log in</button>
            </form>
          )}
        </div>
      </div>

      <div className="wrap">
        <h1>Your AI copilot for live interviews.</h1>
        <p className="muted">
          Install the capture app on Windows. It listens to your call, detects every question,
          and generates answers — all on your machine. This site is your live viewer, on any
          device you&apos;re logged into. Your API keys and audio never leave your computer.
        </p>

        <div className="card">
          <h2>1 · Download</h2>
          <a className="btn" href={installerUrl}>Download installer (.exe)</a>
          <a className="btn alt" href={exeUrl}>Portable .exe</a>
          <p className="muted" style={{ marginTop: 10 }}>Windows 10/11. Everything is bundled.</p>
        </div>

        <div className="card">
          <h2>2 · How it works</h2>
          <ol>
            <li>Run the app. It opens this site to sign in with Google.</li>
            <li>After login it says <em>&quot;you can go back to the app&quot;</em> and opens your live feed.</li>
            <li>Start a call from the app — questions and answers appear here in real time.</li>
          </ol>
        </div>

        {!session && (
          <form action={async () => { "use server"; await signIn("google", { redirectTo: "/feed" }); }}>
            <button className="btn" type="submit">Sign in with Google →</button>
          </form>
        )}
      </div>
    </>
  );
}
