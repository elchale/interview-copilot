"""Tests for the hotkey combination listener."""

from __future__ import annotations

from unittest.mock import MagicMock

from pynput.keyboard import Key, KeyCode

from src.hotkeys import _token, _parse, CombinationListener


class TestTokenization:
    def test_ctrl_l(self):
        assert _token(Key.ctrl_l) == "ctrl"

    def test_ctrl_r(self):
        assert _token(Key.ctrl_r) == "ctrl"

    def test_shift_r(self):
        assert _token(Key.shift_r) == "shift_r"

    def test_shift_l(self):
        assert _token(Key.shift) == "shift"

    def test_comma_vk(self):
        assert _token(KeyCode.from_vk(188)) == ","

    def test_period_vk(self):
        assert _token(KeyCode.from_vk(190)) == "."

    def test_letter_a(self):
        assert _token(KeyCode.from_char("a")) == "a"

    def test_none_key(self):
        assert _token(None) is None


class TestParse:
    def test_ctrl_comma(self):
        assert _parse("ctrl+,") == frozenset({"ctrl", ","})

    def test_ctrl_shift_r(self):
        assert _parse("ctrl+shift_r") == frozenset({"ctrl", "shift_r"})

    def test_ctrl_period(self):
        assert _parse("ctrl+.") == frozenset({"ctrl", "."})

    def test_aliases(self):
        assert _parse("control+,") == frozenset({"ctrl", ","})


class TestCombinationListener:
    def test_fires_on_correct_combo(self):
        action = MagicMock()
        listener = CombinationListener({"ctrl+,": action})

        listener._on_press(Key.ctrl_l)
        listener._on_press(KeyCode.from_vk(188))

        action.assert_called_once()

    def test_does_not_fire_on_partial(self):
        action = MagicMock()
        listener = CombinationListener({"ctrl+,": action})

        listener._on_press(KeyCode.from_vk(188))

        action.assert_not_called()

    def test_right_shift_only(self):
        menu_action = MagicMock()
        listener = CombinationListener({"ctrl+shift_r": menu_action})

        # Left shift should NOT fire
        listener._on_press(Key.ctrl_l)
        listener._on_press(Key.shift)
        menu_action.assert_not_called()

        listener._on_release(Key.shift)
        listener._on_release(Key.ctrl_l)

        # Right shift SHOULD fire
        listener._on_press(Key.ctrl_l)
        listener._on_press(Key.shift_r)
        menu_action.assert_called_once()

    def test_fires_only_once_until_release(self):
        action = MagicMock()
        listener = CombinationListener({"ctrl+,": action})

        listener._on_press(Key.ctrl_l)
        listener._on_press(KeyCode.from_vk(188))
        listener._on_press(KeyCode.from_vk(188))

        assert action.call_count == 1

        listener._on_release(KeyCode.from_vk(188))
        listener._on_press(KeyCode.from_vk(188))

        assert action.call_count == 2
