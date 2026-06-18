"""At-rest encryption for users' BYO API keys.

DPAPI (used by the local app) is Windows-only, so server-side we use Fernet with
a key deterministically derived from ``SECRET_KEY`` — one secret to manage.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


def _fernet(secret_key: str) -> Fernet:
    digest = hashlib.sha256(secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(secret_key: str, plaintext: str) -> str:
    """Encrypt a value for storage. Empty input stays empty."""
    if not plaintext:
        return ""
    return _fernet(secret_key).encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(secret_key: str, token: str) -> str:
    """Decrypt a stored value. Returns "" on empty or tampered input."""
    if not token:
        return ""
    try:
        return _fernet(secret_key).decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""
