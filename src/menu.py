"""Tkinter control menu — settings panel opened by Ctrl+Right Shift."""

from __future__ import annotations

import logging
import os
import tkinter as tk
from tkinter import ttk
from typing import Callable

from .recorder import loopback_devices
from .settings import Settings

logger = logging.getLogger(__name__)

ANSWER_MODES = ["CODING", "BEHAVIORAL", "SYSTEM_DESIGN", "MATH", "GENERAL"]
STT_PROVIDERS = ["whisper_api", "deepgram", "local"]
LLM_PROVIDERS = ["anthropic", "openai", "gemini"]


class ControlMenu:
    """Settings panel as a Tkinter Toplevel window."""

    def __init__(
        self,
        root: tk.Tk,
        settings: Settings,
        on_save: Callable[[Settings], None],
        on_quit: Callable[[], None],
        get_status: Callable[[], dict] | None = None,
    ) -> None:
        self._root = root
        self._settings = settings
        self._on_save = on_save
        self._on_quit = on_quit
        self._get_status = get_status
        self._win: tk.Toplevel | None = None

    def toggle(self) -> None:
        """Show or hide the control menu. Thread-safe via root.after."""
        self._root.after(0, self._toggle_on_main)

    def _toggle_on_main(self) -> None:
        if self._win and self._win.winfo_exists():
            self._win.destroy()
            self._win = None
        else:
            self._show()

    def _show(self) -> None:
        self._win = win = tk.Toplevel(self._root)
        win.title("Interview Copilot — Settings")
        win.geometry("520x720")
        win.resizable(False, True)
        win.configure(bg="#1a1a1a")
        win.attributes("-topmost", True)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Dark.TFrame", background="#1a1a1a")
        style.configure("Dark.TLabel", background="#1a1a1a", foreground="#e0e0e0", font=("Segoe UI", 10))
        style.configure("Dark.TEntry", fieldbackground="#2a2a2a", foreground="#e0e0e0")
        style.configure("Header.TLabel", background="#1a1a1a", foreground="#4fc3f7", font=("Segoe UI", 11, "bold"))
        style.configure("Dark.TButton", background="#2a2a2a", foreground="#e0e0e0", font=("Segoe UI", 10))
        style.configure("Dark.TCheckbutton", background="#1a1a1a", foreground="#e0e0e0")

        frame = ttk.Frame(win, style="Dark.TFrame", padding=16)
        frame.pack(fill="both", expand=True)

        row = 0

        def section(text: str) -> None:
            nonlocal row
            ttk.Label(frame, text=text, style="Header.TLabel").grid(
                row=row, column=0, columnspan=2, sticky="w", pady=(12, 4)
            )
            row += 1

        def field(label: str, var: tk.Variable, show: str = "") -> None:
            nonlocal row
            ttk.Label(frame, text=label, style="Dark.TLabel").grid(row=row, column=0, sticky="w", padx=(0, 8))
            e = ttk.Entry(frame, textvariable=var, width=36, style="Dark.TEntry")
            if show:
                e.configure(show=show)
            e.grid(row=row, column=1, sticky="ew")
            row += 1

        def dropdown(label: str, var: tk.StringVar, values: list[str]) -> None:
            nonlocal row
            ttk.Label(frame, text=label, style="Dark.TLabel").grid(row=row, column=0, sticky="w", padx=(0, 8))
            cb = ttk.Combobox(frame, textvariable=var, values=values, state="readonly", width=34)
            cb.grid(row=row, column=1, sticky="ew")
            row += 1

        frame.columnconfigure(1, weight=1)

        # --- API Keys ---
        section("API Keys")
        self._v_openai = tk.StringVar(value="")
        self._v_anthropic = tk.StringVar(value="")
        self._v_deepgram = tk.StringVar(value="")
        self._v_gemini = tk.StringVar(value="")
        field("OpenAI Key", self._v_openai, show="*")
        field("Anthropic Key", self._v_anthropic, show="*")
        field("Deepgram Key", self._v_deepgram, show="*")
        field("Gemini Key", self._v_gemini, show="*")

        # --- Providers ---
        section("Providers")
        self._v_stt = tk.StringVar(value=self._settings.stt_provider)
        self._v_llm = tk.StringVar(value=self._settings.llm_provider)
        self._v_model = tk.StringVar(value=self._settings.llm_model)
        dropdown("STT Provider", self._v_stt, STT_PROVIDERS)
        dropdown("LLM Provider", self._v_llm, LLM_PROVIDERS)
        field("LLM Model (optional)", self._v_model)

        # --- Hotkeys ---
        section("Hotkeys")
        self._v_hk_answer = tk.StringVar(value=self._settings.hotkey_answer)
        self._v_hk_menu = tk.StringVar(value=self._settings.hotkey_menu)
        self._v_hk_toggle = tk.StringVar(value=self._settings.hotkey_toggle)
        field("Answer", self._v_hk_answer)
        field("Menu", self._v_hk_menu)
        field("Toggle Listen", self._v_hk_toggle)

        # --- Recording ---
        section("Recording")
        self._v_mode = tk.StringVar(value=self._settings.answer_mode)
        self._v_window = tk.StringVar(value=str(self._settings.answer_window_seconds))
        self._v_retention = tk.StringVar(value=str(self._settings.retention_hours))
        self._v_continuous = tk.BooleanVar(value=self._settings.continuous_listening)
        dropdown("Answer Mode", self._v_mode, ANSWER_MODES)
        field("Answer Window (sec)", self._v_window)
        field("Retention (hours)", self._v_retention)
        ttk.Checkbutton(
            frame, text="Continuous listening on start",
            variable=self._v_continuous, style="Dark.TCheckbutton",
        ).grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1

        # --- Device ---
        section("Audio Device")
        devices = loopback_devices()
        dev_labels = [f"[{i}] {name}" for i, name in devices]
        self._v_device = tk.StringVar(value="Auto-detect")
        if self._settings.loopback_device_index is not None:
            for i, name in devices:
                if i == self._settings.loopback_device_index:
                    self._v_device.set(f"[{i}] {name}")
                    break
        dropdown("Loopback Device", self._v_device, ["Auto-detect"] + dev_labels)

        # --- Server ---
        section("Web Server")
        self._v_port = tk.StringVar(value=str(self._settings.server_port))
        self._v_bind = tk.StringVar(value=self._settings.bind_address)
        field("Port", self._v_port)
        field("Bind Address", self._v_bind)

        # --- Persona ---
        section("Persona / Context")
        self._persona_text = tk.Text(frame, height=4, bg="#2a2a2a", fg="#e0e0e0",
                                      font=("Segoe UI", 10), insertbackground="#e0e0e0",
                                      relief="flat", wrap="word")
        self._persona_text.insert("1.0", self._settings.persona)
        self._persona_text.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        row += 1

        # --- Buttons ---
        btn_frame = ttk.Frame(frame, style="Dark.TFrame")
        btn_frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Button(btn_frame, text="Save", command=self._save, style="Dark.TButton").pack(side="left", padx=(0, 8))
        ttk.Button(btn_frame, text="Quit App", command=self._quit, style="Dark.TButton").pack(side="right")

    def _save(self) -> None:
        s = self._settings

        # Keys — only update if the user typed something (field not blank)
        if self._v_openai.get().strip():
            s.openai_key = self._v_openai.get().strip()
        if self._v_anthropic.get().strip():
            s.anthropic_key = self._v_anthropic.get().strip()
        if self._v_deepgram.get().strip():
            s.deepgram_key = self._v_deepgram.get().strip()
        if self._v_gemini.get().strip():
            s.gemini_key = self._v_gemini.get().strip()

        s.stt_provider = self._v_stt.get()
        s.llm_provider = self._v_llm.get()
        s.llm_model = self._v_model.get().strip()

        s.hotkey_answer = self._v_hk_answer.get().strip()
        s.hotkey_menu = self._v_hk_menu.get().strip()
        s.hotkey_toggle = self._v_hk_toggle.get().strip()

        s.answer_mode = self._v_mode.get()
        try:
            s.answer_window_seconds = int(self._v_window.get())
        except ValueError:
            pass
        try:
            s.retention_hours = int(self._v_retention.get())
        except ValueError:
            pass
        s.continuous_listening = self._v_continuous.get()

        dev = self._v_device.get()
        if dev == "Auto-detect":
            s.loopback_device_index = None
        else:
            try:
                s.loopback_device_index = int(dev.split("]")[0].strip("["))
            except (ValueError, IndexError):
                s.loopback_device_index = None

        try:
            s.server_port = int(self._v_port.get())
        except ValueError:
            pass
        s.bind_address = self._v_bind.get().strip()
        s.persona = self._persona_text.get("1.0", "end-1c").strip()

        s.save()
        self._on_save(s)
        if self._win:
            self._win.destroy()
            self._win = None
        logger.info("Settings saved from menu")

    def _quit(self) -> None:
        if self._win:
            self._win.destroy()
        self._on_quit()
