"""Verify the stored API keys are valid — free (no transcription/token cost).

Run:  .\.venv\Scripts\python verify_keys.py
Checks the keys saved by the app (DPAPI-encrypted in %LOCALAPPDATA%\\WinAudioSvc)
against each provider's free auth endpoint. Prints only masked keys, never the full value.
"""

from __future__ import annotations

import httpx
import anthropic

from src.settings import Settings


def mask(k: str) -> str:
    return f"{k[:6]}...{k[-4:]} (len {len(k)})" if k else "(EMPTY)"


def main() -> None:
    s = Settings.load()
    dg, an = s.deepgram_key, s.anthropic_key
    print("Deepgram key :", mask(dg))
    print("Anthropic key:", mask(an))
    print("-" * 40)

    if dg:
        try:
            r = httpx.get(
                "https://api.deepgram.com/v1/projects",
                headers={"Authorization": f"Token {dg}"},
                timeout=15,
            )
            print("Deepgram auth:", "VALID" if r.status_code == 200 else f"INVALID ({r.status_code})")
        except Exception as e:
            print("Deepgram check error:", e)
    else:
        print("Deepgram: no key stored")

    if an:
        try:
            anthropic.Anthropic(api_key=an).models.list(limit=1)
            print("Anthropic auth: VALID")
        except anthropic.AuthenticationError:
            print("Anthropic auth: INVALID")
        except Exception as e:
            print("Anthropic check error:", type(e).__name__, str(e)[:120])
    else:
        print("Anthropic: no key stored")


if __name__ == "__main__":
    main()
