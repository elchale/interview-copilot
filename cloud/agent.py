"""Local capture agent with a control window (the installed Windows app).

Double-clicking the exe opens a small control panel — not the website. From there
you set/verify your API keys and press Start Call, which connects to Deepgram and
streams the resulting transcript/answers to bebita.club (open the feed when you
want to read them). The full pipeline (capture + STT + LLM) runs locally with your
own keys; nothing connects until you press Start, so idle = free.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import ttk

import httpx
from dotenv import load_dotenv

from src.hotkeys import CombinationListener, _token
from src.live_session import LiveSession
from src.recorder import Recorder
from src.settings import DATA_DIR, Settings
from .remote_publisher import RemotePublisher

logger = logging.getLogger(__name__)

# Canonical host is www (apex 308-redirects to it).
BASE_URL = os.environ.get("CLOUD_BASE_URL", "https://www.bebita.club").rstrip("/")
TOKEN_PATH = Path(DATA_DIR) / "agent.json"


def _load() -> dict:
    try:
        return json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(data: dict) -> None:
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(json.dumps(data), encoding="utf-8")


def _check_keys(deepgram_key: str, anthropic_key: str) -> dict[str, str]:
    """Validate keys against the providers' free auth endpoints (no usage cost).

    Returns {"deepgram": status, "anthropic": status} with status
    "valid" | "invalid" | "error" (error = provider unreachable / offline).
    """
    out = {"deepgram": "error", "anthropic": "error"}
    try:
        r = httpx.get(
            "https://api.deepgram.com/v1/projects",
            headers={"Authorization": f"Token {deepgram_key}"},
            timeout=12,
        )
        out["deepgram"] = "valid" if r.status_code == 200 else "invalid"
    except Exception:
        out["deepgram"] = "error"
    try:
        import anthropic

        anthropic.Anthropic(api_key=anthropic_key).models.list(limit=1)
        out["anthropic"] = "valid"
    except Exception as e:
        import anthropic

        out["anthropic"] = "invalid" if isinstance(e, anthropic.AuthenticationError) else "error"
    return out


async def _pair() -> tuple[str, str]:
    """Browser pairing flow. Returns (token, ingest_url)."""
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        start = (await client.post(f"{BASE_URL}/pair/start")).json()
        webbrowser.open(start["verify_url"])
        for _ in range(150):  # ~5 min
            await asyncio.sleep(2)
            r = await client.get(start["poll_url"])
            if r.status_code == 404:
                raise RuntimeError("pairing code expired")
            data = r.json()
            if data.get("status") == "claimed":
                _save({"token": data["token"], "ingest_url": data["ingest_url"]})
                return data["token"], data["ingest_url"]
        raise RuntimeError("pairing timed out")


class Controller:
    """Owns the live pipeline; start/stop are scheduled onto the asyncio loop."""

    def __init__(self, loop: asyncio.AbstractEventLoop, on_status, on_recording=None) -> None:
        self._loop = loop
        self._status = on_status
        self._on_recording = on_recording or (lambda _: None)
        self._recorder: Recorder | None = None
        self._live: LiveSession | None = None
        self._publisher: RemotePublisher | None = None
        self._flusher: asyncio.Task | None = None
        self._heartbeat: asyncio.Task | None = None
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        asyncio.run_coroutine_threadsafe(self._start(), self._loop)

    def stop(self) -> None:
        asyncio.run_coroutine_threadsafe(self._stop(), self._loop)

    def toggle(self) -> None:
        (self.stop if self._running else self.start)()

    async def _start(self) -> None:
        if self._running:
            return
        s = Settings.load()
        if not s.deepgram_key or not s.anthropic_key:
            self._status("Add and verify your API keys first.")
            return

        saved = _load()
        token, ingest_url = saved.get("token", ""), saved.get("ingest_url", "")
        if not token or not ingest_url:
            self._status("Pairing — complete Google sign-in in your browser…")
            try:
                token, ingest_url = await _pair()
            except Exception as e:
                self._status(f"Pairing failed: {e}")
                return

        self._publisher = RemotePublisher(ingest_url, token)
        self._live = LiveSession(s, self._loop, publisher=self._publisher)
        self._recorder = Recorder(
            loopback_device_index=s.loopback_device_index,
            on_system_audio=self._live.feed_audio,
        )
        self._recorder.start()
        await self._live.start()
        self._flusher = asyncio.create_task(self._publisher.run_flusher())
        self._heartbeat = asyncio.create_task(self._beat())
        self._running = True
        self._on_recording(True)
        self._status("LIVE — recording. Open the feed to read suggestions.")

    async def _beat(self) -> None:
        """Periodic 'still recording' ping so the web auto-reverts if we die."""
        try:
            while True:
                await asyncio.sleep(5)
                if self._publisher:
                    self._publisher.update_status(listening=True, recording=True, call_active=True)
        except asyncio.CancelledError:
            raise

    async def _stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._heartbeat:
            self._heartbeat.cancel()
            self._heartbeat = None
        if self._live:
            await self._live.stop()  # buffers call_active=False
        if self._publisher:
            await self._publisher.flush_now()  # ensure the web sees "stopped"
        if self._flusher:
            self._flusher.cancel()
            self._flusher = None
        if self._recorder:
            self._recorder.stop()
        self._on_recording(False)
        self._status("Stopped — idle (no cost).")


def _sanitize_name(name: str) -> str:
    safe = "".join(c for c in name if c.isalnum() or c in ("-", "_", " ")).strip()
    return safe or "WinAudioSvc"


def _apply_process_name(name: str) -> str:
    """Persist the desired Task Manager name. When frozen, relaunch under
    <name>.exe (so Task Manager shows it). Returns a status string."""
    import sys

    name = _sanitize_name(name)
    s = Settings.load()
    s.process_name = name
    s.save()

    if not getattr(sys, "frozen", False):
        return f"Saved '{name}'. Takes effect as <{name}.exe> in the built app."

    import shutil
    import subprocess

    cur = Path(sys.executable)
    target = cur.with_name(f"{name}.exe")
    if target == cur:
        return f"Already running as {name}.exe."
    try:
        shutil.copy2(cur, target)
        subprocess.Popen([str(target)], close_fds=True)
        os._exit(0)  # quit this instance; the renamed one takes over
    except Exception as e:
        return f"Could not rename: {e}"
    return ""


def _record_combo(timeout: float = 8.0) -> str:
    """Capture the next key combination the user presses; return its spec string."""
    from pynput import keyboard

    held: set[str] = set()
    captured: set[str] = set()

    def on_press(key) -> None:
        tok = _token(key)
        if tok:
            held.add(tok)
            captured.clear()
            captured.update(held)

    def on_release(key) -> None:
        held.discard(_token(key))
        if captured:
            listener.stop()

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()
    listener.join(timeout=timeout)
    listener.stop()

    order = {"ctrl": 0, "alt": 1, "shift": 2, "shift_r": 2}
    return "+".join(sorted(captured, key=lambda t: (order.get(t, 9), t)))


def _start_loop() -> asyncio.AbstractEventLoop:
    loop = asyncio.new_event_loop()

    def run() -> None:
        asyncio.set_event_loop(loop)
        loop.run_forever()

    threading.Thread(target=run, daemon=True, name="agent-loop").start()
    return loop


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv()

    loop = _start_loop()
    settings = Settings.load()

    try:  # cosmetic: console window title (Task Manager name is set via Apply below)
        import ctypes

        ctypes.windll.kernel32.SetConsoleTitleW(settings.process_name)
    except Exception:
        pass

    root = tk.Tk()
    root.title("Interview Copilot")
    root.geometry("480x600")
    root.resizable(False, False)
    frm = ttk.Frame(root, padding=18)
    frm.pack(fill="both", expand=True)

    ttk.Label(frm, text="Interview Copilot", font=("Segoe UI", 14, "bold")).pack(anchor="w")
    rec_lbl = tk.Label(frm, text="○  Not recording", font=("Segoe UI", 12, "bold"), fg="#888")
    rec_lbl.pack(anchor="w", pady=(4, 2))
    status_var = tk.StringVar(value="Idle.")
    ttk.Label(frm, textvariable=status_var, foreground="#06c").pack(anchor="w", pady=(0, 12))

    # --- API keys ---
    ttk.Label(frm, text="Deepgram API key", font=("Segoe UI", 9, "bold")).pack(anchor="w")
    dg = tk.StringVar(value=settings.deepgram_key)
    ttk.Entry(frm, textvariable=dg, show="*").pack(fill="x", pady=(0, 6))
    ttk.Label(frm, text="Anthropic API key", font=("Segoe UI", 9, "bold")).pack(anchor="w")
    an = tk.StringVar(value=settings.anthropic_key)
    ttk.Entry(frm, textvariable=an, show="*").pack(fill="x", pady=(0, 6))
    key_msg = tk.StringVar()
    ttk.Label(frm, textvariable=key_msg).pack(anchor="w")

    def set_status(msg: str) -> None:
        root.after(0, lambda: status_var.set(msg))

    def set_recording(active: bool) -> None:
        def upd() -> None:
            if active:
                rec_lbl.configure(text="●  RECORDING", fg="#d33")
            else:
                rec_lbl.configure(text="○  Not recording", fg="#888")
        root.after(0, upd)

    ctrl = Controller(loop, set_status, set_recording)

    def verify_keys() -> None:
        d, a = dg.get().strip(), an.get().strip()
        if not d or not a:
            key_msg.set("Both keys are required.")
            return
        key_msg.set("Checking keys…")

        def work() -> None:
            st = _check_keys(d, a)
            bad = []
            if st["deepgram"] == "invalid":
                bad.append("Deepgram invalid")
            if st["anthropic"] == "invalid":
                bad.append("Anthropic invalid")
            if bad:
                root.after(0, lambda: key_msg.set(" / ".join(bad) + " — re-check."))
                return
            s = Settings.load()
            s.deepgram_key, s.anthropic_key = d, a
            s.save()
            root.after(0, lambda: key_msg.set("Keys saved and verified ✓"))

        threading.Thread(target=work, daemon=True).start()

    ttk.Button(frm, text="Save & verify keys", command=verify_keys).pack(anchor="w", pady=(2, 14))

    # --- Call controls (with hotkey indicator) ---
    hk_var = tk.StringVar(value=settings.hotkey_call)

    btns = ttk.Frame(frm)
    btns.pack(fill="x")
    start_btn = ttk.Button(btns, text="Start call", command=lambda: ctrl.start())
    start_btn.pack(side="left")
    stop_btn = ttk.Button(btns, text="Stop call", command=lambda: ctrl.stop())
    stop_btn.pack(side="left", padx=6)
    ttk.Button(btns, text="Open feed", command=lambda: webbrowser.open(f"{BASE_URL}/feed")).pack(side="left")

    def refresh_btn_labels() -> None:
        hk = hk_var.get()
        start_btn.configure(text=f"Start call  [{hk}]")
        stop_btn.configure(text=f"Stop call  [{hk}]")

    refresh_btn_labels()

    # Global toggle hotkey
    listener = CombinationListener({settings.hotkey_call: ctrl.toggle})
    listener.start()

    hk_frame = ttk.LabelFrame(frm, text="Start/Stop hotkey", padding=8)
    hk_frame.pack(fill="x", pady=(14, 0))
    ttk.Entry(hk_frame, textvariable=hk_var, width=18).pack(side="left")

    def apply_hotkey() -> None:
        combo = hk_var.get().strip()
        if not combo:
            return
        s = Settings.load()
        s.hotkey_call = combo
        s.save()
        listener.update_bindings({combo: ctrl.toggle})
        refresh_btn_labels()
        set_status(f"Hotkey set to [{combo}]")

    def record_hotkey() -> None:
        set_status("Press your key combo…")

        def work() -> None:
            combo = _record_combo()
            if combo:
                root.after(0, lambda: (hk_var.set(combo), set_status(f"Captured [{combo}] — click Apply")))
            else:
                root.after(0, lambda: set_status("No combo captured."))

        threading.Thread(target=work, daemon=True).start()

    ttk.Button(hk_frame, text="Record", command=record_hotkey).pack(side="left", padx=6)
    ttk.Button(hk_frame, text="Apply", command=apply_hotkey).pack(side="left")

    # --- Task Manager name ---
    pn_frame = ttk.LabelFrame(frm, text="Task Manager name", padding=8)
    pn_frame.pack(fill="x", pady=(12, 0))
    pn_var = tk.StringVar(value=settings.process_name)
    ttk.Entry(pn_frame, textvariable=pn_var, width=22).pack(side="left")

    def apply_name() -> None:
        set_status("Applying name…")
        set_status(_apply_process_name(pn_var.get()))

    ttk.Button(pn_frame, text="Apply (relaunch)", command=apply_name).pack(side="left", padx=6)

    ttk.Label(
        frm,
        text="Idle costs nothing — Start connects to Deepgram and begins capturing.\n"
        "The feed opens only when you click Open feed.",
        foreground="#666",
        justify="left",
    ).pack(anchor="w", pady=(12, 0))

    def on_close() -> None:
        try:
            listener.stop()
        except Exception:
            pass
        ctrl.stop()
        root.after(300, root.destroy)

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
