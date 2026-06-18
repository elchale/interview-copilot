# PyInstaller spec for the Interview Copilot cloud capture agent.
# Build: pyinstaller build_agent.spec  ->  dist/InterviewCopilot.exe

block_cipher = None

a = Analysis(
    ["run_agent.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=[
        "win32crypt",
        "pynput.keyboard._win32",
        "pynput.mouse._win32",
        "pystray._win32",
        "PIL._tkinter_finder",
        "src.hotkeys",
        "cloud.agent",
        "cloud.remote_publisher",
        "src.live_session",
        "src.recorder",
        "src.settings",
        "src.stt.deepgram_stream",
        "src.llm.gate",
        "src.llm.anthropic_llm",
        "src.llm.prompts",
        "anthropic",
        "httpx",
        "websockets",
        "dotenv",
        "numpy",
        "pyaudiowpatch",
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
    name="InterviewCopilot",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # windowless background app (logs go to %LOCALAPPDATA%\WinAudioSvc\logs\agent.log)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico",
)
