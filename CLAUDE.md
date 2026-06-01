# CLAUDE.md — Interview Copilot V2

## Project Overview

Self-contained Windows executable (`WinAudioSvc.exe`) that runs as a stealth background
process. Continuously records system audio (WASAPI loopback) + microphone into compressed
Opus batches. On hotkey, transcribes and generates AI-powered interview answers served via
a built-in FastAPI web server.

## Architecture

- **Language**: Python 3.13, packaged via PyInstaller (`--onefile --noconsole`)
- **Audio**: PyAudioWPatch (WASAPI loopback + mic) → ffmpeg Opus encoding
- **STT**: Pluggable — OpenAI Whisper API, Deepgram Nova-3, or local whisper.cpp
- **LLM**: Pluggable — Anthropic Claude, OpenAI GPT, Google Gemini
- **Web**: FastAPI + uvicorn, single-file HTML dashboard with SSE
- **UI**: pystray (system tray) + Tkinter (control menu)
- **Hotkeys**: pynput custom combination listener
- **Storage**: `%LOCALAPPDATA%\WinAudioSvc\` — Opus batches, JSON sessions, encrypted settings

## Code Standards

- **Type hints everywhere** — all function signatures, return types, class attributes
- **Docstrings**: Google style, one-line for simple functions, multi-line only when non-obvious
- **Naming**: snake_case for functions/variables, PascalCase for classes, UPPER_SNAKE for constants
- **Imports**: stdlib → third-party → local, separated by blank lines
- **Error handling**: explicit exceptions, never bare `except:`
- **Async**: use `asyncio` for I/O-bound work, `threading` only for GUI/hotkey (Tkinter requirement)
- **No global mutable state** — pass dependencies explicitly or use dataclasses
- **Provider abstraction**: all STT/LLM providers implement a Protocol (ABC), selected at runtime

## Working Directory

All commands run from `C:\Users\Personal\Desktop\Carlos\Apps\Progress\interviewer_v2\`.

```powershell
# Dev
pip install -r requirements.txt
python -m src.main

# Build
pyinstaller build.spec

# Test
pytest tests/ -v
```

## File Layout

```
src/
├── main.py              # Entry point
├── recorder.py          # WASAPI + mic capture
├── batch_manager.py     # Opus encoding, storage, cleanup
├── settings.py          # Config + DPAPI encryption
├── engine.py            # Orchestrates STT → LLM
├── hotkeys.py           # pynput combination listener
├── tray.py              # pystray system tray
├── menu.py              # Tkinter control menu
├── server.py            # FastAPI + uvicorn + SSE
├── dashboard.py         # Embedded HTML dashboard
├── stt/                 # STT providers (Protocol-based)
├── llm/                 # LLM providers (Protocol-based)
└── tunnel.py            # cloudflared integration
```

## Key Constraints

- Process name in Task Manager must be `WinAudioSvc.exe` or similar innocuous name
- API keys encrypted at rest with Windows DPAPI
- Web server binds 127.0.0.1 by default; 0.0.0.0 only when tunnel/LAN enabled
- Audio batches auto-delete after retention period (default 48h)
- No external database — everything is local files
- Must work as both `python -m src.main` (dev) and as PyInstaller .exe (prod)
