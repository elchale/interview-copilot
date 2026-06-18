"""Application settings with DPAPI-encrypted API key storage."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

APP_NAME = "WinAudioSvc"
DATA_DIR = Path(os.environ.get("LOCALAPPDATA", "~")) / APP_NAME
SETTINGS_PATH = DATA_DIR / "settings.json"
BATCHES_DIR = DATA_DIR / "batches"
SESSIONS_DIR = DATA_DIR / "sessions"
LOG_PATH = DATA_DIR / "logs" / "service.log"


def _ensure_dirs() -> None:
    for d in [DATA_DIR, BATCHES_DIR, SESSIONS_DIR, LOG_PATH.parent]:
        d.mkdir(parents=True, exist_ok=True)


def _dpapi_encrypt(plaintext: str) -> str:
    """Encrypt a string using Windows DPAPI. Returns hex-encoded ciphertext."""
    try:
        import win32crypt
        blob = win32crypt.CryptProtectData(
            plaintext.encode("utf-8"), None, None, None, None, 0
        )
        return blob.hex()
    except ImportError:
        logger.warning("pywin32 not available — storing key in plaintext")
        return f"plain:{plaintext}"


def _dpapi_decrypt(ciphertext: str) -> str:
    """Decrypt a DPAPI-encrypted hex string."""
    if not ciphertext:
        return ""
    if ciphertext.startswith("plain:"):
        return ciphertext[6:]
    try:
        import win32crypt
        _, plaintext_bytes = win32crypt.CryptUnprotectData(
            bytes.fromhex(ciphertext), None, None, None, 0
        )
        return plaintext_bytes.decode("utf-8")
    except (ImportError, Exception):
        return ""


@dataclass
class Settings:
    """Runtime settings — persisted to JSON."""

    # Hotkeys
    hotkey_answer: str = "ctrl+,"
    hotkey_menu: str = "ctrl+shift_r"
    hotkey_toggle: str = "ctrl+."
    hotkey_call: str = "ctrl+;"  # start / stop a live call

    # Providers
    stt_provider: str = "whisper_api"
    llm_provider: str = "anthropic"
    llm_model: str = ""

    # Encrypted API keys (stored as DPAPI hex)
    _openai_key_enc: str = field(default="", repr=False)
    _anthropic_key_enc: str = field(default="", repr=False)
    _deepgram_key_enc: str = field(default="", repr=False)
    _gemini_key_enc: str = field(default="", repr=False)

    # Recording
    answer_mode: str = "CODING"
    answer_window_seconds: int = 180
    batch_duration_seconds: int = 60
    retention_hours: int = 48
    loopback_device_index: int | None = None
    continuous_listening: bool = True

    # Live call mode (streaming STT + auto question detection)
    live_gate_model: str = "claude-haiku-4-5"
    enable_web_search: bool = True
    live_context_utterances: int = 12

    # Server
    server_port: int = 7123
    bind_address: str = "127.0.0.1"
    enable_tunnel: bool = False

    # Persona
    persona: str = ""

    # Key getters/setters
    @property
    def openai_key(self) -> str:
        return os.environ.get("OPENAI_API_KEY") or _dpapi_decrypt(self._openai_key_enc)

    @openai_key.setter
    def openai_key(self, value: str) -> None:
        self._openai_key_enc = _dpapi_encrypt(value) if value else ""

    @property
    def anthropic_key(self) -> str:
        return os.environ.get("ANTHROPIC_API_KEY") or _dpapi_decrypt(self._anthropic_key_enc)

    @anthropic_key.setter
    def anthropic_key(self, value: str) -> None:
        self._anthropic_key_enc = _dpapi_encrypt(value) if value else ""

    @property
    def deepgram_key(self) -> str:
        return os.environ.get("DEEPGRAM_API_KEY") or _dpapi_decrypt(self._deepgram_key_enc)

    @deepgram_key.setter
    def deepgram_key(self, value: str) -> None:
        self._deepgram_key_enc = _dpapi_encrypt(value) if value else ""

    @property
    def gemini_key(self) -> str:
        return os.environ.get("GEMINI_API_KEY") or _dpapi_decrypt(self._gemini_key_enc)

    @gemini_key.setter
    def gemini_key(self, value: str) -> None:
        self._gemini_key_enc = _dpapi_encrypt(value) if value else ""

    def stt_api_key(self) -> str:
        """Return the API key for the active STT provider."""
        if self.stt_provider == "whisper_api":
            return self.openai_key
        elif self.stt_provider == "deepgram":
            return self.deepgram_key
        return ""

    def llm_api_key(self) -> str:
        """Return the API key for the active LLM provider."""
        mapping = {
            "anthropic": self.anthropic_key,
            "openai": self.openai_key,
            "gemini": self.gemini_key,
        }
        return mapping.get(self.llm_provider, "")

    def save(self) -> None:
        _ensure_dirs()
        data = asdict(self)
        SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("Settings saved to %s", SETTINGS_PATH)

    @classmethod
    def load(cls) -> Settings:
        _ensure_dirs()
        if not SETTINGS_PATH.exists():
            s = cls()
            s.save()
            return s

        try:
            raw: dict[str, Any] = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
            filtered = {k: v for k, v in raw.items() if k in valid_fields}
            return cls(**filtered)
        except Exception as e:
            logger.error("Failed to load settings, using defaults: %s", e)
            return cls()
