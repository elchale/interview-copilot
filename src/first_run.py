"""First-run setup wizard — shown when no API key is configured."""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk
from typing import Callable

from .recorder import loopback_devices
from .settings import Settings

logger = logging.getLogger(__name__)

LLM_PROVIDERS = {
    "anthropic": ("Anthropic Claude", "Best for coding interviews"),
    "openai": ("OpenAI GPT-4o", "Strong general purpose"),
    "gemini": ("Google Gemini", "Fast, large context"),
}

STT_PROVIDERS = {
    "whisper_api": ("OpenAI Whisper API", "Best accuracy — needs OpenAI key"),
    "deepgram": ("Deepgram Nova-3", "Fastest — needs Deepgram key"),
    "local": ("Local Whisper", "Free, offline — slower, needs whisper.cpp"),
}


def needs_first_run(settings: Settings) -> bool:
    """Return True if no LLM API key is configured."""
    return not any([
        settings.anthropic_key,
        settings.openai_key,
        settings.gemini_key,
    ])


def run_wizard(settings: Settings, on_complete: Callable[[Settings], None]) -> None:
    """Show the first-run setup wizard. Blocks until closed."""
    root = tk.Tk()
    root.title("Interview Copilot — Setup")
    root.geometry("560x640")
    root.resizable(False, False)
    root.configure(bg="#0f0f0f")
    root.attributes("-topmost", True)

    style = ttk.Style()
    style.theme_use("clam")
    style.configure("W.TFrame", background="#0f0f0f")
    style.configure("W.TLabel", background="#0f0f0f", foreground="#e0e0e0", font=("Segoe UI", 10))
    style.configure("Title.TLabel", background="#0f0f0f", foreground="#4fc3f7", font=("Segoe UI", 16, "bold"))
    style.configure("Sub.TLabel", background="#0f0f0f", foreground="#888", font=("Segoe UI", 9))
    style.configure("Section.TLabel", background="#0f0f0f", foreground="#66bb6a", font=("Segoe UI", 11, "bold"))
    style.configure("W.TEntry", fieldbackground="#1a1a1a", foreground="#e0e0e0", font=("Segoe UI", 10))
    style.configure("W.TButton", background="#4fc3f7", foreground="#0f0f0f", font=("Segoe UI", 11, "bold"))
    style.configure("W.TRadiobutton", background="#0f0f0f", foreground="#e0e0e0", font=("Segoe UI", 10))

    frame = ttk.Frame(root, style="W.TFrame", padding=24)
    frame.pack(fill="both", expand=True)

    row = 0

    # Title
    ttk.Label(frame, text="Interview Copilot", style="Title.TLabel").grid(
        row=row, column=0, columnspan=2, sticky="w", pady=(0, 4)
    )
    row += 1
    ttk.Label(
        frame,
        text="Quick setup — you only need one API key to get started.",
        style="Sub.TLabel",
    ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 16))
    row += 1

    # LLM Provider
    ttk.Label(frame, text="Answer Provider", style="Section.TLabel").grid(
        row=row, column=0, columnspan=2, sticky="w", pady=(8, 4)
    )
    row += 1
    v_llm = tk.StringVar(value=settings.llm_provider)
    for key, (name, desc) in LLM_PROVIDERS.items():
        rb = ttk.Radiobutton(
            frame, text=f"{name} — {desc}",
            variable=v_llm, value=key, style="W.TRadiobutton",
        )
        rb.grid(row=row, column=0, columnspan=2, sticky="w", padx=(12, 0))
        row += 1

    # API Key
    row += 1
    ttk.Label(frame, text="API Key", style="Section.TLabel").grid(
        row=row, column=0, columnspan=2, sticky="w", pady=(8, 4)
    )
    row += 1
    ttk.Label(
        frame,
        text="Enter the key for your chosen provider above:",
        style="Sub.TLabel",
    ).grid(row=row, column=0, columnspan=2, sticky="w")
    row += 1
    v_key = tk.StringVar()
    key_entry = ttk.Entry(frame, textvariable=v_key, width=52, style="W.TEntry", show="*")
    key_entry.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 0))
    row += 1

    # STT Provider
    row += 1
    ttk.Label(frame, text="Transcription", style="Section.TLabel").grid(
        row=row, column=0, columnspan=2, sticky="w", pady=(8, 4)
    )
    row += 1
    v_stt = tk.StringVar(value=settings.stt_provider)
    for key, (name, desc) in STT_PROVIDERS.items():
        rb = ttk.Radiobutton(
            frame, text=f"{name} — {desc}",
            variable=v_stt, value=key, style="W.TRadiobutton",
        )
        rb.grid(row=row, column=0, columnspan=2, sticky="w", padx=(12, 0))
        row += 1

    # STT Key (if different from LLM key)
    row += 1
    ttk.Label(
        frame,
        text="STT API Key (leave blank if same as above or using local):",
        style="Sub.TLabel",
    ).grid(row=row, column=0, columnspan=2, sticky="w")
    row += 1
    v_stt_key = tk.StringVar()
    ttk.Entry(frame, textvariable=v_stt_key, width=52, style="W.TEntry", show="*").grid(
        row=row, column=0, columnspan=2, sticky="ew", pady=(4, 0)
    )
    row += 1

    # Error label
    row += 1
    v_error = tk.StringVar()
    err_label = ttk.Label(frame, textvariable=v_error, foreground="#ef5350",
                          background="#0f0f0f", font=("Segoe UI", 9))
    err_label.grid(row=row, column=0, columnspan=2, sticky="w")
    row += 1

    frame.columnconfigure(0, weight=1)

    completed = False

    def finish() -> None:
        nonlocal completed
        api_key = v_key.get().strip()
        if not api_key:
            v_error.set("Please enter an API key to continue.")
            return

        provider = v_llm.get()
        if provider == "anthropic":
            settings.anthropic_key = api_key
        elif provider == "openai":
            settings.openai_key = api_key
        elif provider == "gemini":
            settings.gemini_key = api_key

        settings.llm_provider = provider
        settings.stt_provider = v_stt.get()

        stt_key = v_stt_key.get().strip()
        if stt_key:
            if v_stt.get() == "whisper_api":
                settings.openai_key = stt_key
            elif v_stt.get() == "deepgram":
                settings.deepgram_key = stt_key
        elif v_stt.get() == "whisper_api" and provider == "openai":
            pass  # Same key
        elif v_stt.get() == "whisper_api" and not settings.openai_key:
            settings.openai_key = api_key  # Use LLM key for Whisper too

        settings.save()
        completed = True
        root.destroy()

    # Start button
    btn = ttk.Button(frame, text="Start Interview Copilot", command=finish, style="W.TButton")
    btn.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(12, 0), ipady=6)

    key_entry.focus_set()
    root.bind("<Return>", lambda e: finish())

    root.mainloop()

    if completed:
        on_complete(settings)
    else:
        import sys
        sys.exit(0)
