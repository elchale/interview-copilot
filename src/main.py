"""Entry point: starts all subsystems and runs the Tkinter main loop."""

from __future__ import annotations

import asyncio
import logging
import logging.handlers
import os
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path

from dotenv import load_dotenv

from .engine import Engine
from .ffmpeg_bootstrap import ensure_ffmpeg
from .first_run import needs_first_run, run_wizard
from .hotkeys import CombinationListener
from .installer import needs_install, run_installer
from .menu import ControlMenu
from .server import start_server, new_session, update_status
from .settings import Settings, LOG_PATH, DATA_DIR
from .tray import TrayIcon
from .tunnel import Tunnel

logger = logging.getLogger(__name__)

__version__ = "1.0.0"


def _setup_logging() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    handlers: list[logging.Handler] = [
        logging.handlers.RotatingFileHandler(
            LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=2, encoding="utf-8",
        ),
    ]

    # sys.stdout is None under PyInstaller --noconsole; only log to console
    # when one actually exists (dev runs).
    if sys.stdout is not None:
        handlers.insert(0, logging.StreamHandler(sys.stdout))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )


def _start_async_loop() -> asyncio.AbstractEventLoop:
    """Start a background asyncio event loop and return it."""
    loop = asyncio.new_event_loop()

    def run() -> None:
        asyncio.set_event_loop(loop)
        loop.run_forever()

    t = threading.Thread(target=run, daemon=True, name="async-loop")
    t.start()
    return loop


def main() -> None:
    # Self-install on first double-click (exe only)
    if needs_install():
        installed = run_installer()
        if installed:
            sys.exit(0)  # Installed copy was launched
        else:
            sys.exit(1)  # User cancelled

    # Load .env from the source directory (dev) or next to the exe (prod)
    env_candidates = [
        Path(__file__).resolve().parent.parent / ".env",
        Path(sys.executable).parent / ".env",
    ]
    for env_path in env_candidates:
        if env_path.exists():
            load_dotenv(env_path)
            break

    _setup_logging()
    logger.info("Interview Copilot v%s starting (data: %s)", __version__, DATA_DIR)

    # Ensure ffmpeg is available (auto-downloads if needed)
    ffmpeg_path = ensure_ffmpeg()
    if ffmpeg_path:
        logger.info("ffmpeg ready: %s", ffmpeg_path)
    else:
        logger.warning("ffmpeg not available — audio stored as raw PCM")

    settings = Settings.load()

    # First-run wizard if no API keys configured
    if needs_first_run(settings):
        logger.info("No API keys found — launching setup wizard")
        run_wizard(settings, lambda s: None)
        settings = Settings.load()

    # Asyncio loop for AI operations
    loop = _start_async_loop()

    # Engine
    engine = Engine(settings)
    engine.set_event_loop(loop)

    # Web server
    server_thread = start_server(host=settings.bind_address, port=settings.server_port)
    dashboard_url = f"http://{settings.bind_address}:{settings.server_port}"
    logger.info("Dashboard: %s", dashboard_url)

    # Create initial session
    sid = new_session()
    logger.info("Session: %s", sid)

    # Optional tunnel
    tunnel = Tunnel(port=settings.server_port)
    if settings.enable_tunnel:
        tunnel_url = tunnel.start()
        if tunnel_url:
            logger.info("Public URL: %s", tunnel_url)

    # Hidden Tk root for the control menu
    root = tk.Tk()
    root.withdraw()

    def on_settings_save(new_settings: Settings) -> None:
        nonlocal settings
        settings = new_settings
        engine.settings = new_settings
        listener.update_bindings(_build_bindings(new_settings))
        logger.info("Settings updated")

    def on_quit() -> None:
        logger.info("Quit requested")
        engine.stop_listening()
        tunnel.stop()
        root.destroy()
        os._exit(0)

    menu = ControlMenu(
        root=root,
        settings=settings,
        on_save=on_settings_save,
        on_quit=on_quit,
    )

    # System tray
    tray = TrayIcon(
        on_open_menu=menu.toggle,
        on_open_dashboard=lambda: webbrowser.open(dashboard_url),
        on_quit=on_quit,
        dashboard_url=dashboard_url,
    )
    tray.start()

    def _build_bindings(s: Settings) -> dict:
        return {
            s.hotkey_answer: engine.answer_latest,
            s.hotkey_menu: menu.toggle,
            s.hotkey_toggle: engine.toggle_listening,
            s.hotkey_call: engine.toggle_call,
        }

    listener = CombinationListener(_build_bindings(settings))
    listener.start()

    # Start listening if continuous mode
    if settings.continuous_listening:
        engine.start_listening()

    logger.info(
        "Ready — Hotkeys: answer=%s, menu=%s, toggle=%s, call=%s",
        settings.hotkey_answer, settings.hotkey_menu, settings.hotkey_toggle, settings.hotkey_call,
    )

    # Tkinter main loop (must be on main thread)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        on_quit()


if __name__ == "__main__":
    main()
