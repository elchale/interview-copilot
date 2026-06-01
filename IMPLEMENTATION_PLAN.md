# Interviewer V2 — Implementation Plan

## What it is

A **single Windows executable** that runs 24/7 as a background process. It continuously
records system audio (WASAPI loopback = interviewer's voice) and microphone (your voice),
stores compressed batches locally. On **Ctrl+,** it transcribes recent audio via AI,
analyzes the conversation, and generates interview answers — served live on a URL anyone
can open. A control menu (**Ctrl+Right Shift**) lets you configure API keys, providers,
hotkeys, and view status.

## Key differences from V1

| V1 (interview/) | V2 (interviewer_v2/) |
|---|---|
| Separate Python agent + Next.js web app + Neon Postgres | Single self-contained .exe |
| Live Deepgram streaming STT | Batch recording → on-demand transcription |
| Requires Neon DB + Vercel deploy | Everything local, no external infra |
| Hardcoded Anthropic provider | Configurable provider (Claude / OpenAI / Gemini) |
| localhost:3000 only | Built-in web server with shareable tunnel URL |
| Visible "python" process | Stealthy process name in Task Manager |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    WinAudioSvc.exe                          │
│                                                             │
│  ┌──────────┐  ┌───────────┐  ┌───────────┐  ┌──────────┐ │
│  │ Recorder  │  │ Batch     │  │ AI Engine │  │ Web      │ │
│  │ (WASAPI + │→ │ Storage   │→ │ (STT +    │→ │ Server   │ │
│  │  Mic)     │  │ (Opus)    │  │  LLM)     │  │ (FastAPI)│ │
│  └──────────┘  └───────────┘  └───────────┘  └──────────┘ │
│                                                             │
│  ┌──────────┐  ┌───────────┐                               │
│  │ Hotkey   │  │ System    │                               │
│  │ Listener │  │ Tray Icon │                               │
│  └──────────┘  └───────────┘                               │
└─────────────────────────────────────────────────────────────┘
```

### Components

1. **Recorder** — PyAudioWPatch (WASAPI loopback for system audio, standard input for mic).
   Two parallel streams → separate channels. Runs continuously while "listening" is on.

2. **Batch Storage** — Audio saved in rolling 60-second Opus/OGG files (~7 KB/s at 16 kbps
   mono speech = **~25 MB/hour**, ~400 MB for a full 16-hour day). Stored in
   `%LOCALAPPDATA%\WinAudioSvc\batches\`. Auto-cleanup: delete batches older than
   configurable retention (default 48 hours).

3. **AI Engine** — Triggered on Ctrl+,:
   - **STT**: Transcribe last N minutes of batches. Provider-configurable:
     - OpenAI Whisper API (`whisper-1`) — best quality, handles bad audio
     - Deepgram Nova-3 — fastest, streaming capable
     - Local Whisper (whisper.cpp) — offline, no API key needed
   - **LLM**: Send transcript → get interview answer. Provider-configurable:
     - Anthropic Claude (Sonnet 4.6 default, Opus available)
     - OpenAI GPT-4o
     - Google Gemini 2.5 Pro
   - Streams the answer token-by-token to the web server.

4. **Web Server** — FastAPI + uvicorn on a local port (default 7123).
   - SSE endpoint streams transcript + answers live
   - Simple HTML/CSS/JS dashboard (no build step — single-file served)
   - **Shareable URL options:**
     - Local network: `http://<your-ip>:7123` (shown in menu)
     - Tunnel: optional cloudflared/ngrok integration for a public URL

5. **Hotkey Listener** — pynput custom combination listener (same approach as V1):
   - **Ctrl+,** → trigger AI analysis of recent audio
   - **Ctrl+Right Shift** → toggle control menu
   - **Ctrl+.** → pause/resume recording

6. **System Tray** — pystray icon in notification area. Right-click menu:
   - Open dashboard (launches browser to the URL)
   - Open control menu
   - Status indicator (recording / idle / analyzing)
   - Quit

7. **Control Menu** — Tkinter window (appears on Ctrl+Right Shift):
   - API provider selector (Claude / OpenAI / Gemini / Local)
   - API key input (masked)
   - STT provider selector (Whisper API / Deepgram / Local Whisper)
   - STT API key input
   - Hotkey configuration (answer, menu, toggle)
   - Recording settings (retention hours, batch duration, answer window)
   - Answer mode (CODING / BEHAVIORAL / SYSTEM_DESIGN / MATH / GENERAL)
   - Persona/context field
   - Web server port
   - Tunnel toggle (cloudflared)
   - Status display (disk usage, recording duration, server URL)

---

## Process Stealth

- **Executable name**: `WinAudioSvc.exe` (looks like a Windows audio service)
- **Process description** (PE metadata): "Windows Audio Device Service"
- **Window**: No console, no taskbar entry. Only system tray icon.
- **Startup**: Task Scheduler task (more reliable than Startup folder, runs at logon,
  shows as "Windows Audio Device Service" in Task Manager details)
- **Data directory**: `%LOCALAPPDATA%\WinAudioSvc\` (blends with Windows services)

---

## Storage Format

```
%LOCALAPPDATA%\WinAudioSvc\
├── settings.json          # all config (API keys encrypted with DPAPI)
├── batches/
│   ├── sys_20260601_143000.opus    # system audio batch
│   ├── mic_20260601_143000.opus    # mic audio batch
│   ├── sys_20260601_143100.opus
│   └── ...
├── sessions/
│   ├── session_abc123.json         # transcript + answers
│   └── ...
└── logs/
    └── service.log                 # rotating log, max 5 MB
```

### Opus encoding

- **Bitrate**: 16 kbps mono (speech-optimized) → ~7.2 KB/s → 25.9 MB/hour
- **Batch duration**: 60 seconds (configurable)
- **Channels**: Separate files for system/mic (simpler, can transcribe independently)
- **Format**: OGG container with Opus codec (native Python via `opuslib` or subprocess
  to bundled `opusenc.exe` from opus-tools — more reliable on Windows)

---

## Tech Stack

| Component | Technology | Why |
|---|---|---|
| Language | Python 3.13 | Same ecosystem, PyAudio, fast iteration |
| Packaging | PyInstaller `--onefile --noconsole` | Single .exe, no Python install needed |
| Audio capture | PyAudioWPatch | WASAPI loopback (system audio), proven in V1 |
| Audio compression | ffmpeg (bundled) or opusenc | Opus codec, tiny footprint |
| STT | OpenAI Whisper API / Deepgram / local whisper.cpp | Configurable quality vs cost |
| LLM | Anthropic / OpenAI / Google SDKs | User picks provider |
| Web server | FastAPI + uvicorn | Async, SSE native, lightweight |
| Dashboard | Single HTML file (vanilla JS + SSE) | No build step, served by FastAPI |
| Hotkeys | pynput | Global hotkeys, proven in V1 |
| System tray | pystray + Pillow | Native Windows notification area |
| Settings UI | Tkinter | No extra deps, ships with Python |
| Tunnel | cloudflared (optional, bundled) | Free, no signup for quick tunnels |
| Key storage | Windows DPAPI (win32crypt) | Encrypt API keys at rest |
| Autostart | Windows Task Scheduler | Reliable, admin-level persistence |

---

## Data Flow

### Continuous Recording (always on)
```
WASAPI loopback ──→ PCM int16 frames ──→ Opus encoder ──→ batches/sys_*.opus
Microphone      ──→ PCM int16 frames ──→ Opus encoder ──→ batches/mic_*.opus
                                                           (60s rolling files)
```

### On Ctrl+, (answer trigger)
```
1. Gather batches from last N minutes (default: 3 min, configurable)
2. Decode Opus → PCM → send to STT provider
   ├── OpenAI Whisper: POST /v1/audio/transcriptions (file upload)
   ├── Deepgram: POST /v1/listen (streaming or file)
   └── Local: whisper.cpp subprocess
3. Receive transcript text
4. Send to LLM with system prompt (mode-aware: coding/behavioral/etc.)
   ├── Anthropic: client.messages.stream()
   ├── OpenAI: client.chat.completions.create(stream=True)
   └── Google: model.generate_content(stream=True)
5. Stream answer tokens → SSE → dashboard
6. Save session (transcript + answer) to sessions/ JSON
```

### Dashboard (web)
```
Browser ──GET /──→ FastAPI serves index.html (embedded)
Browser ──GET /api/stream──→ SSE connection
  ← event: status    {recording: true, analyzing: false}
  ← event: transcript {text: "...", source: "system"}
  ← event: answer.start {id: "..."}
  ← event: answer.delta {id: "...", text: "..."}
  ← event: answer.done  {id: "...", latencyMs: 340}
Browser ──GET /api/sessions──→ JSON list of past sessions
Browser ──GET /api/sessions/:id──→ JSON session detail
```

---

## Build Phases

### Phase 1: Core Recording + Storage (Day 1)
- [ ] Project scaffold (pyproject.toml, src/ layout)
- [ ] Audio recorder (WASAPI loopback + mic, dual-stream)
- [ ] Opus batch encoder (ffmpeg subprocess, 60s segments)
- [ ] Batch manager (rolling storage, auto-cleanup, disk usage tracking)
- [ ] Settings manager (JSON + DPAPI encryption for API keys)
- [ ] Basic logging

### Phase 2: AI Engine (Day 1-2)
- [ ] STT abstraction layer (provider interface)
- [ ] OpenAI Whisper provider
- [ ] Deepgram provider
- [ ] LLM abstraction layer (provider interface)
- [ ] Anthropic Claude provider (streaming)
- [ ] OpenAI GPT provider (streaming)
- [ ] Answer prompt system (mode-aware, persona-aware)
- [ ] Session persistence (transcript + answers → JSON)

### Phase 3: Web Dashboard (Day 2)
- [ ] FastAPI server with uvicorn
- [ ] SSE endpoint for live streaming
- [ ] REST endpoints (sessions list, session detail, status)
- [ ] Single-file HTML dashboard (dark theme, split view: transcript | answer)
- [ ] Live streaming display (partial transcript, token-by-token answer)
- [ ] Session history view
- [ ] Auto-scroll, code block rendering

### Phase 4: Hotkeys + UI (Day 2-3)
- [ ] pynput combination listener (Ctrl+, / Ctrl+Right Shift / Ctrl+.)
- [ ] Tkinter control menu (all settings, status display)
- [ ] pystray system tray icon (status indicator, quick actions)
- [ ] Cross-thread coordination (hotkey → engine → UI updates)

### Phase 5: Packaging + Stealth (Day 3)
- [ ] PyInstaller spec file (bundle ffmpeg, icon, metadata)
- [ ] PE metadata (description: "Windows Audio Device Service")
- [ ] Custom icon (generic Windows-style)
- [ ] Task Scheduler install/uninstall scripts
- [ ] First-run wizard (set API key, test audio, choose provider)

### Phase 6: Polish + Tunnel (Day 3-4)
- [ ] cloudflared tunnel integration (optional public URL)
- [ ] Google Gemini LLM provider
- [ ] Local Whisper STT provider (whisper.cpp bundled)
- [ ] Error recovery (recording restart, API retry)
- [ ] Bandwidth/latency optimization
- [ ] End-to-end testing

---

## Latency Budget (Ctrl+, → first answer token)

| Step | Target | Notes |
|---|---|---|
| Gather + decode batches | < 500 ms | Local disk, ffmpeg decode |
| Upload to STT | < 1s | 3 min audio ≈ 1.4 MB Opus |
| STT transcription | 2-4s | Whisper API for 3 min audio |
| LLM first token | 1-2s | Streaming, prompt-cached system prompt |
| **Total** | **~5-8s** | From hotkey press to first answer token |

For faster response: reduce answer window (1 min instead of 3), or use Deepgram
streaming STT (~1s for same audio).

---

## Security Considerations

- API keys encrypted at rest with Windows DPAPI (tied to user account)
- Web server binds to 0.0.0.0 only if tunnel/LAN sharing is enabled; otherwise 127.0.0.1
- No data leaves the machine except API calls to configured providers
- Audio batches are local-only, auto-deleted after retention period
- Settings file permissions restricted to current user (ACL)
- Tunnel URL is random, unguessable (cloudflared generates unique subdomain)

---

## File Structure

```
interviewer_v2/
├── IMPLEMENTATION_PLAN.md
├── README.md
├── pyproject.toml
├── requirements.txt
├── build.spec                    # PyInstaller spec
├── assets/
│   └── icon.ico                  # Tray icon
├── src/
│   ├── __init__.py
│   ├── main.py                   # Entry point: starts all subsystems
│   ├── recorder.py               # WASAPI + mic capture
│   ├── batch_manager.py          # Opus encoding, storage, cleanup
│   ├── settings.py               # Config + DPAPI key encryption
│   ├── engine.py                 # Orchestrates STT → LLM on trigger
│   ├── hotkeys.py                # pynput combination listener
│   ├── tray.py                   # pystray system tray
│   ├── menu.py                   # Tkinter control menu
│   ├── server.py                 # FastAPI + uvicorn + SSE
│   ├── dashboard.py              # Embedded HTML string for the dashboard
│   ├── stt/
│   │   ├── __init__.py           # STT provider interface
│   │   ├── whisper_api.py        # OpenAI Whisper
│   │   ├── deepgram.py           # Deepgram Nova-3
│   │   └── local_whisper.py      # whisper.cpp subprocess
│   ├── llm/
│   │   ├── __init__.py           # LLM provider interface
│   │   ├── anthropic.py          # Claude
│   │   ├── openai_llm.py         # GPT-4o
│   │   └── gemini.py             # Gemini 2.5 Pro
│   └── tunnel.py                 # cloudflared integration
├── scripts/
│   ├── install_autostart.ps1     # Task Scheduler setup
│   └── uninstall_autostart.ps1   # Remove scheduled task
└── .env.example
```

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| PyInstaller .exe flagged by antivirus | Sign with a code-signing cert; add exclusion instructions to README |
| WASAPI loopback unavailable (remote desktop, etc.) | Fallback to stereo mix; clear error message in menu |
| Large .exe size (bundled ffmpeg + Python) | Use UPX compression; ffmpeg-mini build (audio-only) |
| Opus encoding CPU usage | Use ffmpeg subprocess (native, fast); 16kbps mono is trivial |
| API rate limits | Exponential backoff; queue analysis requests; show status in tray |
| Tunnel reliability | Tunnel is optional; always works on localhost; auto-reconnect |
