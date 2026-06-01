# Interview Copilot

A stealth Windows background process that continuously records system audio and
microphone, and on-demand transcribes + generates AI-powered interview answers —
served live through a built-in web dashboard.

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

## Quick Start (Development)

```powershell
cd interviewer_v2
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
# Set your API keys in .env or via the control menu (Ctrl+Right Shift)
python -m src.main
```

The dashboard opens at [http://127.0.0.1:7123](http://127.0.0.1:7123).

## Build Executable

```powershell
pip install pyinstaller
pyinstaller build.spec
# Output: dist/WinAudioSvc.exe
```

## Auto-Start at Boot

```powershell
# Install (after building the exe)
powershell -ExecutionPolicy Bypass -File scripts/install_autostart.ps1

# Uninstall
powershell -ExecutionPolicy Bypass -File scripts/uninstall_autostart.ps1
```

## Supported Providers

### STT (Speech-to-Text)
- **OpenAI Whisper API** — best quality, handles noisy audio (default)
- **Deepgram Nova-3** — fastest, streaming-capable
- **Local Whisper** — offline, no API key needed (requires whisper.cpp)

### LLM (Answer Generation)
- **Anthropic Claude** — Sonnet 4.6 default (recommended)
- **OpenAI GPT-4o**
- **Google Gemini 2.5 Pro**

## Configuration

Settings are stored in `%LOCALAPPDATA%\WinAudioSvc\settings.json`. API keys are
encrypted with Windows DPAPI (tied to your user account). You can also set keys
via environment variables or `.env` file.

## Storage

Audio batches are stored in `%LOCALAPPDATA%\WinAudioSvc\batches\` and auto-deleted
after the retention period (default 48 hours). At ~25 MB/hour, a full 8-hour
interview day uses ~200 MB.

## Architecture

```
src/
├── main.py              # Entry point — starts all subsystems
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

- Windows 10/11 (WASAPI loopback for system audio capture)
- Python 3.11+ (for development)
- ffmpeg on PATH (for Opus encoding)
- At least one API key (OpenAI, Anthropic, Deepgram, or Gemini)
