# Interview Copilot — Cloud (bebita.club)

Hosted dashboard + local capture agent. The website handles Google login, holds
each user's **encrypted BYO API keys**, and runs the STT→gate→LLM pipeline. The
installed Windows app only captures audio and streams it up; suggestions appear
on the website's live feed.

```
Windows agent ──PCM/WSS──▶ FastAPI (bebita.club) ──SSE──▶ your browser
   (capture)               OAuth · per-user keys · relay      (live feed)
```

## Architecture

- `config.py` — env-driven config.
- `crypto.py` — Fernet encryption for stored keys (key derived from `SECRET_KEY`).
- `db.py` — SQLAlchemy models: `User` (encrypted keys + prefs), `Device` (agent token), `PairCode`.
- `auth.py` — Authlib Google OAuth + device-pairing token helpers.
- `publisher.py` — per-user `Hub`: agent audio → reused `LiveSession` → browser SSE (`BrowserPublisher`).
- `app.py` — routes: landing, OAuth, settings (BYO keys), `/app` feed (SSE), `/ws/agent` ingest, pairing.
- `pages.py` — landing / settings / pair-success HTML; the feed reuses `src/dashboard.py`.
- `agent.py` — local capture agent (pairs, then streams audio).

## The pairing / OAuth flow (what the user sees)

1. User downloads + runs the app (`cloud/agent.py`, packaged as the .exe).
2. App calls `POST /pair/start`, opens the browser to `bebita.club/pair?code=…`.
3. Browser → Google login → `/auth/callback` → back to `/pair?code=…`, which binds
   the code to the user and mints an agent token.
4. The page shows **"✓ All set — you can go back to the app"** and redirects to `/app` (the feed).
5. The app polls `/pair/poll`, gets the token, connects `wss://bebita.club/ws/agent`,
   and starts streaming audio. Suggestions stream onto `/app`.

## Deploy

1. Fill secrets: `cloud/.env.prod` already has the Google OAuth client (copied from
   the eccomerce project) and a generated `SECRET_KEY`. Set `DATABASE_URL` (SQLite
   volume or Postgres). **`.env.prod` is gitignored — keep it that way.**
2. In Google Cloud Console, add **`https://bebita.club/auth/callback`** to the OAuth
   client's *Authorized redirect URIs* (the eccomerce client won't have it yet).
3. Put the built `WinAudioSvc.exe` / installer in `cloud/static/` (or set
   `DOWNLOAD_*_URL` to wherever you host them).
4. Build & run:
   ```bash
   docker build -f cloud/Dockerfile -t interview-cloud .
   docker run --env-file cloud/.env.prod -p 8000:8000 -v interview_data:/data interview-cloud
   ```
   Terminate TLS for `bebita.club` at your proxy/load balancer (Caddy, nginx, Fly, etc.).

## Local dev

```bash
pip install -r cloud/requirements.txt
set -a; . cloud/.env.prod; set +a   # or use .env.example with BASE_URL=http://127.0.0.1:8000
uvicorn cloud.app:app --reload --port 8000
```
For local OAuth, also add `http://127.0.0.1:8000/auth/callback` to the Google client.

## Notes / caveats

- **BYO keys:** users paste their Deepgram + Anthropic keys in `/settings`; stored
  Fernet-encrypted. Rotating `SECRET_KEY` invalidates all stored keys and sessions.
- Changing keys takes effect on the next agent (re)connect.
- The server image installs **no audio libraries** — the agent uses the project's
  root `requirements.txt` on Windows.
- One agent + multiple browser tabs per user are supported; the hub stops the live
  session when the last agent disconnects.
