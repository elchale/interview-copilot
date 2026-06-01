"""LLM provider abstraction layer."""

from __future__ import annotations

from typing import AsyncIterator, Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """All LLM providers must implement this interface."""

    @property
    def name(self) -> str: ...

    async def stream_answer(
        self,
        transcript: str,
        mode: str,
        persona: str,
    ) -> AsyncIterator[str]:
        """Stream answer tokens given a transcript, mode, and persona."""
        ...


def get_provider(provider_name: str, api_key: str, model: str | None = None) -> LLMProvider:
    """Factory: return an LLM provider instance by name."""
    if provider_name == "anthropic":
        from .anthropic_llm import AnthropicProvider
        return AnthropicProvider(api_key=api_key, model=model)
    elif provider_name == "openai":
        from .openai_llm import OpenAIProvider
        return OpenAIProvider(api_key=api_key, model=model)
    elif provider_name == "gemini":
        from .gemini_llm import GeminiProvider
        return GeminiProvider(api_key=api_key, model=model)
    raise ValueError(f"Unknown LLM provider: {provider_name}")
