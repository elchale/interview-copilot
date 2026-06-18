"""Database models: users (with encrypted BYO keys), agent devices, pairing codes."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    google_sub: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320), default="")
    name: Mapped[str] = mapped_column(String(200), default="")
    picture: Mapped[str] = mapped_column(String(512), default="")

    # BYO API keys, Fernet-encrypted at rest
    enc_deepgram_key: Mapped[str] = mapped_column(String(512), default="")
    enc_anthropic_key: Mapped[str] = mapped_column(String(512), default="")

    # Live preferences
    answer_mode: Mapped[str] = mapped_column(String(32), default="GENERAL")
    persona: Mapped[str] = mapped_column(String(4000), default="")
    enable_web_search: Mapped[bool] = mapped_column(default=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Device(Base):
    """A paired local agent. ``token`` authenticates the agent's audio WebSocket."""

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class PairCode(Base):
    """Short-lived device-pairing handshake between the agent and a browser login."""

    __tablename__ = "pair_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|claimed
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    agent_token: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    def is_expired(self, ttl_seconds: int = 600) -> bool:
        created = self.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=dt.timezone.utc)
        return (_utcnow() - created).total_seconds() > ttl_seconds


_SessionLocal: sessionmaker | None = None


def init_engine(database_url: str) -> None:
    """Create the engine + tables. Call once at startup."""
    global _SessionLocal
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args, future=True)
    Base.metadata.create_all(engine)
    _SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def get_session():
    if _SessionLocal is None:
        raise RuntimeError("DB not initialized — call init_engine() first")
    return _SessionLocal()
