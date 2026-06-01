"""System tray icon using pystray."""

from __future__ import annotations

import logging
import threading
import webbrowser
from typing import Callable

logger = logging.getLogger(__name__)


def _create_default_icon():
    """Create a simple icon image — a green circle on transparent background."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([8, 8, 56, 56], fill=(76, 175, 80, 255))
    draw.ellipse([22, 22, 42, 42], fill=(255, 255, 255, 200))
    return img


class TrayIcon:
    """System tray icon with quick actions."""

    def __init__(
        self,
        on_open_menu: Callable[[], None],
        on_open_dashboard: Callable[[], None],
        on_quit: Callable[[], None],
        dashboard_url: str = "http://127.0.0.1:7123",
    ) -> None:
        self._on_menu = on_open_menu
        self._on_dashboard = on_open_dashboard
        self._on_quit = on_quit
        self._url = dashboard_url
        self._icon = None

    def start(self) -> None:
        try:
            import pystray
        except ImportError:
            logger.warning("pystray not installed — tray icon disabled")
            return

        icon_image = _create_default_icon()
        menu = pystray.Menu(
            pystray.MenuItem("Open Dashboard", self._dashboard_action),
            pystray.MenuItem("Settings", self._menu_action),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit_action),
        )

        self._icon = pystray.Icon(
            name="WinAudioSvc",
            icon=icon_image,
            title="Interview Copilot",
            menu=menu,
        )

        thread = threading.Thread(target=self._icon.run, daemon=True, name="tray")
        thread.start()
        logger.info("Tray icon started")

    def stop(self) -> None:
        if self._icon:
            self._icon.stop()

    def _dashboard_action(self) -> None:
        webbrowser.open(self._url)

    def _menu_action(self) -> None:
        self._on_menu()

    def _quit_action(self) -> None:
        self._on_quit()
