"""Google OAuth (Authlib) setup, user upsert, and pairing-token helpers."""

from __future__ import annotations

import secrets

from authlib.integrations.starlette_client import OAuth

from .config import Config
from .db import Device, PairCode, User


def create_oauth(config: Config) -> OAuth:
    """Register Google as an OpenID Connect provider via discovery."""
    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=config.google_client_id,
        client_secret=config.google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    return oauth


def new_token() -> str:
    return secrets.token_urlsafe(32)


def upsert_user(session, userinfo: dict) -> User:
    """Find-or-create a user from Google's OIDC userinfo claims."""
    sub = userinfo.get("sub", "")
    user = session.query(User).filter_by(google_sub=sub).one_or_none()
    if user is None:
        user = User(google_sub=sub)
        session.add(user)
    user.email = userinfo.get("email", user.email or "")
    user.name = userinfo.get("name", user.name or "")
    user.picture = userinfo.get("picture", user.picture or "")
    session.commit()
    return user


def claim_pair_code(session, device_code: str, user_id: int) -> str:
    """Bind a pending pairing code to a user and mint the agent token. Returns token."""
    pc = session.query(PairCode).filter_by(device_code=device_code).one_or_none()
    if pc is None or pc.is_expired() or pc.status != "pending":
        raise ValueError("invalid_or_expired_code")
    token = new_token()
    device = Device(user_id=user_id, token=token, label="capture-agent")
    session.add(device)
    pc.status = "claimed"
    pc.user_id = user_id
    pc.agent_token = token
    session.commit()
    return token


def device_for_token(session, token: str) -> Device | None:
    if not token:
        return None
    return session.query(Device).filter_by(token=token).one_or_none()
