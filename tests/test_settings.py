"""Tests for settings module."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from src.settings import Settings


class TestSettings:
    def test_defaults(self):
        s = Settings()
        assert s.hotkey_answer == "ctrl+,"
        assert s.hotkey_menu == "ctrl+shift_r"
        assert s.stt_provider == "whisper_api"
        assert s.llm_provider == "anthropic"
        assert s.answer_mode == "CODING"
        assert s.server_port == 7123

    def test_save_and_load(self, tmp_path: Path):
        settings_file = tmp_path / "settings.json"
        with patch("src.settings.SETTINGS_PATH", settings_file), \
             patch("src.settings.DATA_DIR", tmp_path), \
             patch("src.settings._ensure_dirs"):
            s = Settings()
            s.answer_mode = "MATH"
            s.server_port = 9999
            s.save()

            loaded = Settings.load()
            assert loaded.answer_mode == "MATH"
            assert loaded.server_port == 9999

    def test_env_override_for_keys(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key-123"}):
            s = Settings()
            assert s.anthropic_key == "test-key-123"

    def test_stt_api_key_routing(self):
        s = Settings()
        s.stt_provider = "whisper_api"
        with patch.dict("os.environ", {"OPENAI_API_KEY": "oai-key"}):
            assert s.stt_api_key() == "oai-key"

    def test_llm_api_key_routing(self):
        s = Settings()
        s.llm_provider = "anthropic"
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "ant-key"}):
            assert s.llm_api_key() == "ant-key"
