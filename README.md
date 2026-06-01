# Interview Copilot

A stealth Windows background process that continuously records system audio and
microphone, and on-demand transcribes + generates AI-powered interview answers —
served live through a built-in web dashboard.

## Download & Install

**Option A — Installer (recommended):**
Go to [Releases](https://github.com/elchale/interview-copilot/releases), download
`InterviewCopilot_Setup_x.x.x.exe`, and run it. It installs the app, creates a
Start Menu shortcut, and optionally starts it at boot.

**Option B — Portable exe:**
Download `WinAudioSvc.exe` from Releases and run it directly — no installation needed.
Settings are stored in `%LOCALAPPDATA%\WinAudioSvc\`.

On first launch a setup wizard asks for your API key. That's it — no Python, no
ffmpeg, no config files. ffmpeg is auto-downloaded on first use (~80 MB, one-time).

## How It Works

1. **Always running** — the process starts at boot and silently records system
   audio (WASAPI loopback — the interviewer's voice) and your microphone into
   compressed Opus batches (~25 MB/hour).
2. **Ctrl+,** — grabs the last 3 minutes of audio, transcribes it, and streams
   an AI-generated answer to the dashboard.
3. **Ctrl+Right Shift** — opens the control menu to configure API keys,
   providers, hotkeys, answer mode, and persona.
4. **Dashboard** — a built-in web server shows the live transcript and streaming
   answers at `http://127.0.0.1:7123`. Optional cloudflared tunnel for a public URL.

## Hotkeys

| Keys | Action |
|---|---|
| **Ctrl + ,** | Answer the latest question |
| **Ctrl + Right Shift** | Open/close the control menu |
| **Ctrl + .** | Pause / resume recording |

All hotkeys are editable in the control menu.

## Supported Providers

### STT (Speech-to-Text)
- **OpenAI Whisper API** — best quality, handles noisy audio (default)
- **Deepgram Nova-3** — fastest, streaming-capable
- **Local Whisper** — offline, no API key needed (requires whisper.cpp)

### LLM (Answer Generation)
- **Anthropic Claude** — Sonnet 4.6 default (recommended)
- **OpenAI GPT-4o**
- **Google Gemini 2.5 Pro**

## Development

```powershell
cd interviewer_v2
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
python -m src.main
```

The dashboard opens at [http://127.0.0.1:7123](http://127.0.0.1:7123).

### Build executable

```powershell
pyinstaller build.spec
# → dist/WinAudioSvc.exe (47 MB, self-contained)
```

### Build installer

Requires [Inno Setup](https://jrsoftware.org/isinfo.php):
```powershell
pyinstaller build.spec
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
# → installer_output/InterviewCopilot_Setup_1.0.0.exe
```

### Automated builds

Push a tag to trigger the GitHub Actions workflow:
```powershell
git tag v1.0.0
git push origin v1.0.0
```
This builds the exe + installer and creates a GitHub Release with both files attached.

## Configuration

Settings are stored in `%LOCALAPPDATA%\WinAudioSvc\settings.json`. API keys are
encrypted with Windows DPAPI (tied to your user account). You can also set keys
via the control menu (Ctrl+Right Shift), environment variables, or a `.env` file.

## Storage

Audio batches are stored in `%LOCALAPPDATA%\WinAudioSvc\batches\` and auto-deleted
after the retention period (default 48 hours). At ~25 MB/hour, a full 8-hour
interview day uses ~200 MB.

## Architecture

```
src/
├── main.py              # Entry point — starts all subsystems
├── ffmpeg_bootstrap.py  # Auto-downloads ffmpeg on first run
├── first_run.py         # Setup wizard for first launch
├── recorder.py          # WASAPI loopback + mic capture
├── batch_manager.py     # Opus encoding, rolling storage, cleanup
├── engine.py            # Orchestrates STT → LLM on hotkey trigger
├── settings.py          # Config with DPAPI-encrypted key storage
├── hotkeys.py           # Global hotkey listener (right-shift aware)
├── server.py            # FastAPI + SSE dashboard server
├── dashboard.py         # Embedded HTML/CSS/JS dashboard
├── menu.py              # Tkinter settings panel
├── tray.py              # System tray icon
├── tunnel.py            # Optional cloudflared public URL
├── stt/                 # Pluggable STT providers
│   ├── whisper_api.py
│   ├── deepgram_stt.py
│   └── local_whisper.py
└── llm/                 # Pluggable LLM providers
    ├── anthropic_llm.py
    ├── openai_llm.py
    ├── gemini_llm.py
    └── prompts.py
```

## Requirements

For end users: **just Windows 10/11 and an API key.** Everything else is bundled.

For developers: Python 3.11+, ffmpeg on PATH.
