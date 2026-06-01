"""STT provider abstraction layer."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class STTProvider(Protocol):
    """All STT providers must implement this interface."""

    @property
    def name(self) -> str: ...

    async def transcribe(self, audio_path: str) -> str:
        """Transcribe an audio file and return the text."""
        ...


def get_provider(provider_name: str, api_key: str) -> STTProvider:
    """Factory: return an STT provider instance by name."""
    if provider_name == "whisper_api":
        from .whisper_api import WhisperAPIProvider
        return WhisperAPIProvider(api_key=api_key)
    elif provider_name == "deepgram":
        from .deepgram_stt import DeepgramProvider
        return DeepgramProvider(api_key=api_key)
    elif provider_name == "local":
        from .local_whisper import LocalWhisperProvider
        return LocalWhisperProvider()
    raise ValueError(f"Unknown STT provider: {provider_name}")
