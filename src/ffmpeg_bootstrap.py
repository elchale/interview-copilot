"""Auto-download a minimal ffmpeg binary on first run if not on PATH."""

from __future__ import annotations

import io
import logging
import os
import shutil
import sys
import zipfile
from pathlib import Path
from urllib.request import urlopen, Request

from .settings import DATA_DIR

logger = logging.getLogger(__name__)

FFMPEG_DIR = DATA_DIR / "ffmpeg"
FFMPEG_EXE = FFMPEG_DIR / "ffmpeg.exe"

FFMPEG_URL = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/"
    "latest/ffmpeg-master-latest-win64-gpl.zip"
)


def ensure_ffmpeg() -> str:
    """Return path to ffmpeg, downloading it if necessary."""
    # 1. Already on PATH?
    existing = shutil.which("ffmpeg")
    if existing:
        logger.info("ffmpeg found on PATH: %s", existing)
        return existing

    # 2. Already downloaded to our data dir?
    if FFMPEG_EXE.exists():
        _add_to_path(FFMPEG_DIR)
        logger.info("Using bundled ffmpeg: %s", FFMPEG_EXE)
        return str(FFMPEG_EXE)

    # 3. Bundled with the PyInstaller exe?
    if getattr(sys, "frozen", False):
        bundle_dir = Path(sys._MEIPASS)  # type: ignore[attr-defined]
        bundled = bundle_dir / "ffmpeg.exe"
        if bundled.exists():
            logger.info("Using PyInstaller-bundled ffmpeg: %s", bundled)
            return str(bundled)

    # 4. Download it
    logger.info("ffmpeg not found — downloading (~80 MB, one-time)...")
    return _download_ffmpeg()


def _download_ffmpeg() -> str:
    """Download ffmpeg from GitHub and extract just the binary."""
    FFMPEG_DIR.mkdir(parents=True, exist_ok=True)

    try:
        req = Request(FFMPEG_URL, headers={"User-Agent": "InterviewCopilot/1.0"})
        with urlopen(req, timeout=120) as resp:
            data = resp.read()

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for name in zf.namelist():
                if name.endswith("/ffmpeg.exe"):
                    with zf.open(name) as src, open(FFMPEG_EXE, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    break
            else:
                raise FileNotFoundError("ffmpeg.exe not found in downloaded archive")

        _add_to_path(FFMPEG_DIR)
        logger.info("ffmpeg downloaded to %s", FFMPEG_EXE)
        return str(FFMPEG_EXE)

    except Exception as e:
        logger.error("Failed to download ffmpeg: %s", e)
        logger.warning("Audio will be stored as uncompressed PCM (larger files)")
        return ""


def _add_to_path(directory: Path) -> None:
    """Add a directory to the current process PATH."""
    dir_str = str(directory)
    if dir_str not in os.environ.get("PATH", ""):
        os.environ["PATH"] = dir_str + os.pathsep + os.environ.get("PATH", "")
