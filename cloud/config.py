"""Environment-driven configuration for the cloud backend."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    """All deployment config comes from the environment (.env.prod in production)."""

    base_url: str
    secret_key: str
    database_url: str
    google_client_id: str
    google_client_secret: str
    download_exe_url: str
    download_installer_url: str

    @property
    def oauth_redirect_uri(self) -> str:
        return f"{self.base_url.rstrip('/')}/auth/callback"

    @property
    def ws_base(self) -> str:
        # https -> wss, http -> ws
        return self.base_url.replace("https://", "wss://").replace("http://", "ws://")


def load_config() -> Config:
    return Config(
        base_url=os.environ.get("BASE_URL", "http://127.0.0.1:8000"),
        secret_key=os.environ.get("SECRET_KEY", "dev-insecure-change-me"),
        database_url=os.environ.get("DATABASE_URL", "sqlite:///./interview_cloud.db"),
        google_client_id=os.environ.get("GOOGLE_OAUTH_CLIENT_ID", ""),
        google_client_secret=os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", ""),
        download_exe_url=os.environ.get("DOWNLOAD_EXE_URL", "/static/WinAudioSvc.exe"),
        download_installer_url=os.environ.get(
            "DOWNLOAD_INSTALLER_URL", "/static/InterviewCopilot_Setup.exe"
        ),
    )
