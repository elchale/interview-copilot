"""First-run setup wizard — shown when no API key is configured."""

from __future__ import annotations

import logging
import sys
import tkinter as tk
from tkinter import ttk

from .settings import Settings

logger = logging.getLogger(__name__)

LLM_PROVIDERS = {
    "anthropic": "Anthropic Claude (recommended)",
    "openai": "OpenAI GPT-4o",
    "gemini": "Google Gemini",
}

STT_PROVIDERS = {
    "whisper_api": "OpenAI Whisper API (best accuracy)",
    "deepgram": "Deepgram Nova-3 (fastest)",
    "local": "Local Whisper (free, offline)",
}


def needs_first_run(settings: Settings) -> bool:
    """Return True if no LLM API key is configured."""
    return not any([
        settings.anthropic_key,
        settings.openai_key,
        settings.gemini_key,
    ])


def run_wizard(settings: Settings, on_complete) -> None:
    """Show the first-run setup wizard. Blocks until closed."""
    root = tk.Tk()
    root.title("Interview Copilot — Initial Setup")
    root.geometry("480x440")
    root.resizable(False, False)
    root.configure(bg="white")

    root.update_idletasks()
    x = (root.winfo_screenwidth() - 480) // 2
    y = (root.winfo_screenheight() - 440) // 2
    root.geometry(f"480x440+{x}+{y}")

    style = ttk.Style()
    style.theme_use("vista" if "vista" in style.theme_names() else "clam")

    BG = "#f0f0f0"
    WHITE = "white"

    style.configure("W.TFrame", background=WHITE)
    style.configure("Bottom.TFrame", background=BG)
    style.configure("W.TLabel", background=WHITE, font=("Segoe UI", 9))
    style.configure("Title.TLabel", background=WHITE, font=("Segoe UI", 14))
    style.configure("Bold.TLabel", background=WHITE, font=("Segoe UI", 9, "bold"))
    style.configure("Error.TLabel", background=WHITE, font=("Segoe UI", 8), foreground="#c00")
    style.configure("Status.TLabel", background=BG, font=("Segoe UI", 8), foreground="#555")
    style.configure("W.TRadiobutton", background=WHITE, font=("Segoe UI", 9))

    # --- Main area ---
    main = ttk.Frame(root, style="W.TFrame", padding=(24, 20, 24, 8))
    main.pack(fill="both", expand=True)

    ttk.Label(main, text="Configure Your API Key", style="Title.TLabel").pack(anchor="w", pady=(0, 8))
    ttk.Label(
        main,
        text="Interview Copilot needs an API key to generate answers.\nYou only need one key to get started.",
        style="W.TLabel",
    ).pack(anchor="w", pady=(0, 14))

    # Provider selection
    ttk.Label(main, text="Answer provider:", style="Bold.TLabel").pack(anchor="w", pady=(0, 4))
    v_llm = tk.StringVar(value=settings.llm_provider)
    for key, label in LLM_PROVIDERS.items():
        ttk.Radiobutton(
            main, text=label, variable=v_llm, value=key, style="W.TRadiobutton",
        ).pack(anchor="w", padx=(12, 0))

    # API key
    ttk.Label(main, text="API key:", style="Bold.TLabel").pack(anchor="w", pady=(14, 4))
    v_key = tk.StringVar()
    key_entry = ttk.Entry(main, textvariable=v_key, show="*", font=("Segoe UI", 9))
    key_entry.pack(fill="x", pady=(0, 2))

    # STT
    ttk.Label(main, text="Transcription provider:", style="Bold.TLabel").pack(anchor="w", pady=(14, 4))
    v_stt = tk.StringVar(value=settings.stt_provider)
    for key, label in STT_PROVIDERS.items():
        ttk.Radiobutton(
            main, text=label, variable=v_stt, value=key, style="W.TRadiobutton",
        ).pack(anchor="w", padx=(12, 0))

    # Error label
    v_error = tk.StringVar()
    ttk.Label(main, textvariable=v_error, style="Error.TLabel").pack(anchor="w", pady=(8, 0))

    # --- Bottom bar ---
    sep = ttk.Separator(root, orient="horizontal")
    sep.pack(fill="x")

    bottom = ttk.Frame(root, style="Bottom.TFrame", padding=(24, 10))
    bottom.pack(fill="x")

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

        # If STT is whisper_api and user picked openai, same key works
        if v_stt.get() == "whisper_api" and not settings.openai_key:
            settings.openai_key = api_key

        settings.save()
        completed = True
        root.destroy()

    ttk.Button(bottom, text="Cancel", command=root.destroy, width=10).pack(side="right", padx=(6, 0))
    ttk.Button(bottom, text="Finish", command=finish, width=10).pack(side="right")

    key_entry.focus_set()
    root.bind("<Return>", lambda e: finish())
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()

    if completed:
        on_complete(settings)
    else:
        sys.exit(0)
