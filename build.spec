# PyInstaller spec for Interview Copilot
# Build: pyinstaller build.spec

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ["run.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=[
        "pystray._win32",
        "PIL._tkinter_finder",
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
        "tiktoken_ext.openai_public",
        "tiktoken_ext",
        "win32crypt",
        "src.stt.whisper_api",
        "src.stt.deepgram_stt",
        "src.stt.local_whisper",
        "src.llm.anthropic_llm",
        "src.llm.openai_llm",
        "src.llm.gemini_llm",
        "src.llm.prompts",
        "src.ffmpeg_bootstrap",
        "src.first_run",
        "src.installer",
        "src.dashboard",
        "src.tunnel",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "test", "tests"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="WinAudioSvc",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version="version_info.py",
    icon="assets/icon.ico",
)
