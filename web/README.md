# Interview Copilot — Web Viewer (Vercel)

Next.js (App Router) + Auth.js (Google) + Prisma/Postgres. The browser is a **thin
viewer**: the Windows agent runs the whole pipeline locally (capture + STT + LLM,
keys never leave the machine) and POSTs feed events here; the viewer **polls** the
DB. No WebSockets — fully Vercel-serverless-compatible.

```
Windows agent ──POST /api/ingest──▶ Postgres ◀──GET /api/events?since=N── browser (polls)
 (capture+STT+LLM, local keys)     (event feed)        Google login (Auth.js)
```

## Routes

- `/` landing + download buttons · `/feed` gated polling viewer · `/pair` claims a device after login
- `POST /api/pair/start` → device code · `GET /api/pair/poll` → token when claimed
- `POST /api/ingest` (agent, Bearer device token) · `GET /api/events?since=` (viewer, session)
- `GET|POST /api/auth/[...nextauth]` (Auth.js)

## Deploy to Vercel

1. **Import the repo** in Vercel; set **Root Directory = `web`**. Build command `npm run build`
   (runs `prisma generate` then `next build`); install runs `prisma generate` via postinstall.
2. **Add a Postgres DB** (Vercel Postgres / Neon) → it sets `DATABASE_URL`.
3. **Env vars** (paste from `web/.env.prod`, which already has the Google client + a generated
   `AUTH_SECRET`): `DATABASE_URL`, `AUTH_SECRET`, `AUTH_URL=https://bebita.club`,
   `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `DOWNLOAD_*`.
4. **Google Cloud Console** → add redirect URI: **`https://bebita.club/api/auth/callback/google`**.
5. **Run migrations** against the prod DB once: `DATABASE_URL=... npm run db:deploy`
   (or `npm run db:push` for no migration history).
6. Put the built `WinAudioSvc.exe` / installer in `web/public/downloads/` (or set `DOWNLOAD_*`
   to external URLs).

## Local dev

```bash
cd web
cp .env.example .env.local   # fill DATABASE_URL, AUTH_SECRET (npx auth secret), Google creds
npm install
npm run db:push              # create tables in your dev DB
npm run dev                  # http://localhost:3000
```
Add `http://localhost:3000/api/auth/callback/google` to the Google client for local login.

## The agent (Python, ships as the .exe)

`cloud/agent.py` (project root) pairs, then runs the local pipeline and publishes via
`cloud/remote_publisher.py`. Point it at the site with `CLOUD_BASE_URL=https://bebita.club`.
It reads the user's Deepgram/Anthropic keys from the **local** app settings (DPAPI) — they
never reach the server.

## Notes

- **Latency = poll interval.** Transcript ~1s; the viewer polls every 400 ms while an answer
  is streaming, 1 s when idle. The agent batches event uploads every ~400 ms.
- This **supersedes** the server-side `cloud/` FastAPI relay (that design ran STT/LLM in the
  cloud and needed WebSockets). With the viewer model, only the agent + this Next.js app are used.
