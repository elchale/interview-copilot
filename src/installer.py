"""Self-installer: on first run, installs the app and sets up autostart."""

from __future__ import annotations

import ctypes
import logging
import os
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

logger = logging.getLogger(__name__)

APP_NAME = "Interview Copilot"
EXE_NAME = "WinAudioSvc.exe"
INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA", "~")) / "Programs" / "InterviewCopilot"
INSTALLED_EXE = INSTALL_DIR / EXE_NAME
REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REGISTRY_VALUE = "WinAudioSvc"


def is_installed() -> bool:
    """Check if the app is already installed."""
    return INSTALLED_EXE.exists()


def is_running_from_install_dir() -> bool:
    """Check if the current exe is running from the install directory."""
    if not getattr(sys, "frozen", False):
        return True  # Dev mode — skip install
    current = Path(sys.executable).resolve()
    target = INSTALLED_EXE.resolve()
    return current == target


def needs_install() -> bool:
    """Return True if we should show the installer."""
    if not getattr(sys, "frozen", False):
        return False  # Dev mode
    return not is_running_from_install_dir()


def run_installer() -> bool:
    """Show install wizard. Returns True if installed, False if cancelled."""
    root = tk.Tk()
    root.title(f"Install {APP_NAME}")
    root.geometry("480x400")
    root.resizable(False, False)
    root.configure(bg="#0f0f0f")
    root.attributes("-topmost", True)

    style = ttk.Style()
    style.theme_use("clam")
    style.configure("I.TFrame", background="#0f0f0f")
    style.configure("I.TLabel", background="#0f0f0f", foreground="#e0e0e0", font=("Segoe UI", 10))
    style.configure("Title.TLabel", background="#0f0f0f", foreground="#4fc3f7", font=("Segoe UI", 18, "bold"))
    style.configure("Sub.TLabel", background="#0f0f0f", foreground="#888", font=("Segoe UI", 9))
    style.configure("Path.TLabel", background="#1a1a1a", foreground="#aaa", font=("Consolas", 9),
                     padding=8, borderwidth=1, relief="solid")
    style.configure("I.TCheckbutton", background="#0f0f0f", foreground="#e0e0e0", font=("Segoe UI", 10))
    style.configure("Install.TButton", font=("Segoe UI", 12, "bold"))
    style.configure("Cancel.TButton", font=("Segoe UI", 10))

    frame = ttk.Frame(root, style="I.TFrame", padding=32)
    frame.pack(fill="both", expand=True)

    ttk.Label(frame, text="Interview Copilot", style="Title.TLabel").pack(anchor="w")
    ttk.Label(frame, text="Stealth interview assistant", style="Sub.TLabel").pack(anchor="w", pady=(0, 20))

    ttk.Label(frame, text="This will install the app to:", style="I.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Label(frame, text=str(INSTALL_DIR), style="Path.TLabel").pack(fill="x", pady=(0, 16))

    v_autostart = tk.BooleanVar(value=True)
    ttk.Checkbutton(
        frame, text="Start automatically when Windows boots",
        variable=v_autostart, style="I.TCheckbutton",
    ).pack(anchor="w", pady=(0, 4))

    v_shortcut = tk.BooleanVar(value=True)
    ttk.Checkbutton(
        frame, text="Create Start Menu shortcut",
        variable=v_shortcut, style="I.TCheckbutton",
    ).pack(anchor="w", pady=(0, 4))

    v_desktop = tk.BooleanVar(value=False)
    ttk.Checkbutton(
        frame, text="Create Desktop shortcut",
        variable=v_desktop, style="I.TCheckbutton",
    ).pack(anchor="w", pady=(0, 20))

    result = {"installed": False}

    progress_var = tk.StringVar(value="")
    progress_label = ttk.Label(frame, textvariable=progress_var, style="Sub.TLabel")
    progress_label.pack(anchor="w", pady=(0, 8))

    def do_install() -> None:
        install_btn.configure(state="disabled")
        cancel_btn.configure(state="disabled")

        try:
            progress_var.set("Copying files...")
            root.update()
            _copy_exe()

            if v_autostart.get():
                progress_var.set("Setting up autostart...")
                root.update()
                _set_autostart(True)

            if v_shortcut.get():
                progress_var.set("Creating Start Menu shortcut...")
                root.update()
                _create_shortcut("start_menu")

            if v_desktop.get():
                progress_var.set("Creating Desktop shortcut...")
                root.update()
                _create_shortcut("desktop")

            progress_var.set("Installation complete!")
            root.update()

            result["installed"] = True
            root.after(500, root.destroy)

        except Exception as e:
            logger.exception("Installation failed")
            progress_var.set(f"Error: {e}")
            install_btn.configure(state="normal")
            cancel_btn.configure(state="normal")

    btn_frame = ttk.Frame(frame, style="I.TFrame")
    btn_frame.pack(fill="x", side="bottom")

    cancel_btn = ttk.Button(btn_frame, text="Cancel", command=root.destroy, style="Cancel.TButton")
    cancel_btn.pack(side="left")

    install_btn = ttk.Button(btn_frame, text="Install", command=do_install, style="Install.TButton")
    install_btn.pack(side="right", ipady=4, ipadx=16)

    root.mainloop()

    if result["installed"]:
        # Launch the installed copy and exit this one
        subprocess.Popen([str(INSTALLED_EXE)], creationflags=0x00000008)  # DETACHED_PROCESS
        return True

    return False


def _copy_exe() -> None:
    """Copy the running exe to the install directory."""
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    src = Path(sys.executable)
    if src.resolve() != INSTALLED_EXE.resolve():
        shutil.copy2(src, INSTALLED_EXE)
    logger.info("Installed to %s", INSTALLED_EXE)


def _set_autostart(enable: bool) -> None:
    """Set or remove the Run registry key for autostart."""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY, 0, winreg.KEY_SET_VALUE)
        if enable:
            winreg.SetValueEx(key, REGISTRY_VALUE, 0, winreg.REG_SZ, f'"{INSTALLED_EXE}"')
        else:
            try:
                winreg.DeleteValue(key, REGISTRY_VALUE)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        logger.error("Failed to set autostart: %s", e)


def _create_shortcut(location: str) -> None:
    """Create a Windows shortcut (.lnk) using PowerShell."""
    if location == "start_menu":
        folder = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    elif location == "desktop":
        folder = Path(os.environ.get("USERPROFILE", "")) / "Desktop"
    else:
        return

    folder.mkdir(parents=True, exist_ok=True)
    lnk_path = folder / f"{APP_NAME}.lnk"

    ps_script = f"""
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut("{lnk_path}")
$sc.TargetPath = "{INSTALLED_EXE}"
$sc.WorkingDirectory = "{INSTALL_DIR}"
$sc.Description = "{APP_NAME}"
$sc.Save()
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        capture_output=True,
        timeout=10,
    )
    logger.info("Shortcut created: %s", lnk_path)


def uninstall() -> None:
    """Remove the app: autostart, shortcuts, install dir."""
    _set_autostart(False)

    # Remove shortcuts
    for loc in ["start_menu", "desktop"]:
        if loc == "start_menu":
            lnk = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / f"{APP_NAME}.lnk"
        else:
            lnk = Path(os.environ.get("USERPROFILE", "")) / "Desktop" / f"{APP_NAME}.lnk"
        lnk.unlink(missing_ok=True)

    logger.info("Uninstalled")
