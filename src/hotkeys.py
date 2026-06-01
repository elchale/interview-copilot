"""Global hotkey listener using pynput with right-shift discrimination."""

from __future__ import annotations

import logging
import threading
from typing import Callable

from pynput import keyboard

logger = logging.getLogger(__name__)

_ALIASES: dict[str, str] = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "shift": "shift",
    "shift_r": "shift_r",
}

_VK_TOKEN: dict[int, str] = {
    188: ",",  # VK_OEM_COMMA
    190: ".",  # VK_OEM_PERIOD
    191: "/",
    186: ";",
    222: "'",
    219: "[",
    221: "]",
    220: "\\",
    189: "-",
    187: "=",
    192: "`",
}


def _token(key: keyboard.Key | keyboard.KeyCode | None) -> str | None:
    """Normalize a key event into a matchable token string."""
    if key is None:
        return None

    if isinstance(key, keyboard.Key):
        name = key.name
        if name in ("ctrl_l", "ctrl_r"):
            return "ctrl"
        if name == "shift_r":
            return "shift_r"
        if name in ("shift", "shift_l"):
            return "shift"
        if name in ("alt_l", "alt_r", "alt_gr"):
            return "alt"
        return name

    if isinstance(key, keyboard.KeyCode):
        if key.vk and key.vk in _VK_TOKEN:
            return _VK_TOKEN[key.vk]
        if key.char:
            return key.char.lower()
        if key.vk:
            if 0x41 <= key.vk <= 0x5A:
                return chr(key.vk).lower()
            if 0x30 <= key.vk <= 0x39:
                return chr(key.vk)
        return None

    return None


def _parse(spec: str) -> frozenset[str]:
    """Parse a hotkey spec like 'ctrl+,' into a frozenset of tokens."""
    parts = spec.lower().strip().split("+")
    tokens: set[str] = set()
    for p in parts:
        p = p.strip()
        tokens.add(_ALIASES.get(p, p))
    return frozenset(tokens)


def _satisfied(token: str, held: set[str]) -> bool:
    """Check if a required token is satisfied by the held set."""
    if token == "shift":
        return bool(held & {"shift", "shift_l", "shift_r"})
    return token in held


class CombinationListener:
    """Listen for custom key combinations with right-shift discrimination."""

    def __init__(self, bindings: dict[str, Callable[[], None]]) -> None:
        self._combos: list[tuple[frozenset[str], Callable[[], None]]] = [
            (_parse(spec), action) for spec, action in bindings.items()
        ]
        self._held: set[str] = set()
        self._fired: set[frozenset[str]] = set()
        self._listener: keyboard.Listener | None = None

    def start(self) -> None:
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.daemon = True
        self._listener.start()
        logger.info("Hotkey listener started with %d bindings", len(self._combos))

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None

    def update_bindings(self, bindings: dict[str, Callable[[], None]]) -> None:
        self._combos = [
            (_parse(spec), action) for spec, action in bindings.items()
        ]
        self._fired.clear()
        logger.info("Hotkey bindings updated: %d bindings", len(self._combos))

    def _on_press(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        tok = _token(key)
        if tok is None:
            return
        self._held.add(tok)

        for combo, action in self._combos:
            if combo in self._fired:
                continue
            if all(_satisfied(t, self._held) for t in combo):
                self._fired.add(combo)
                threading.Thread(target=action, daemon=True).start()

    def _on_release(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        tok = _token(key)
        if tok is None:
            return
        self._held.discard(tok)

        release_combos = set()
        for combo, _ in self._combos:
            if combo in self._fired:
                if not all(_satisfied(t, self._held) for t in combo):
                    release_combos.add(combo)
        self._fired -= release_combos
