"""Self-installer and uninstaller for Interview Copilot."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import time
import tkinter as tk
from tkinter import ttk
from pathlib import Path

logger = logging.getLogger(__name__)

APP_NAME = "Interview Copilot"
EXE_NAME = "WinAudioSvc.exe"
INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Programs" / "InterviewCopilot"
INSTALLED_EXE = INSTALL_DIR / EXE_NAME
DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "WinAudioSvc"
REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REGISTRY_VALUE = "WinAudioSvc"


def is_running_from_install_dir() -> bool:
    if not getattr(sys, "frozen", False):
        return True
    try:
        return Path(sys.executable).resolve() == INSTALLED_EXE.resolve()
    except OSError:
        return False


def is_installed() -> bool:
    return INSTALLED_EXE.exists()


def needs_install() -> bool:
    if not getattr(sys, "frozen", False):
        return False
    return not is_running_from_install_dir()


def run_installer() -> bool:
    """Show install or uninstall wizard depending on current state.
    Returns True if the installed copy was launched (caller should exit)."""
    if is_installed():
        return _run_manage_wizard()
    return _run_install_wizard()


# ---------------------------------------------------------------------------
# Shared UI helpers
# ---------------------------------------------------------------------------

def _center(root: tk.Tk, w: int, h: int) -> None:
    root.update_idletasks()
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")


def _apply_styles() -> None:
    style = ttk.Style()
    style.theme_use("vista" if "vista" in style.theme_names() else "clam")
    style.configure("Main.TFrame", background="white")
    style.configure("Bottom.TFrame", background="#f0f0f0")
    style.configure("Main.TLabel", background="white", font=("Segoe UI", 9))
    style.configure("Title.TLabel", background="white", font=("Segoe UI", 14))
    style.configure("Bold.TLabel", background="white", font=("Segoe UI", 9, "bold"))
    style.configure("Status.TLabel", background="#f0f0f0", font=("Segoe UI", 8), foreground="#555")
    style.configure("Main.TCheckbutton", background="white", font=("Segoe UI", 9))
    style.configure("Main.TRadiobutton", background="white", font=("Segoe UI", 9))


def _make_bottom_bar(root: tk.Tk) -> tuple[ttk.Frame, tk.StringVar]:
    sep = ttk.Separator(root, orient="horizontal")
    sep.pack(fill="x")
    bottom = ttk.Frame(root, style="Bottom.TFrame", padding=(24, 10))
    bottom.pack(fill="x")
    status_var = tk.StringVar(value="")
    ttk.Label(bottom, textvariable=status_var, style="Status.TLabel").pack(side="left")
    return bottom, status_var


# ---------------------------------------------------------------------------
# Install wizard
# ---------------------------------------------------------------------------

def _run_install_wizard() -> bool:
    root = tk.Tk()
    root.title(f"{APP_NAME} Setup")
    root.resizable(False, False)
    root.configure(bg="white")
    _center(root, 500, 380)
    _apply_styles()

    main = ttk.Frame(root, style="Main.TFrame", padding=(24, 20, 24, 12))
    main.pack(fill="both", expand=True)

    ttk.Label(main, text=f"Welcome to {APP_NAME} Setup", style="Title.TLabel").pack(
        anchor="w", pady=(0, 12),
    )
    ttk.Label(
        main,
        text=(
            "This will install Interview Copilot on your computer.\n"
            "The program runs in the background and listens to your\n"
            "calls to help you with interview answers."
        ),
        style="Main.TLabel",
    ).pack(anchor="w", pady=(0, 16))

    ttk.Label(main, text="Install location:", style="Bold.TLabel").pack(anchor="w")
    path_entry = ttk.Entry(main, font=("Segoe UI", 9))
    path_entry.insert(0, str(INSTALL_DIR))
    path_entry.configure(state="readonly")
    path_entry.pack(fill="x", pady=(2, 12))

    v_autostart = tk.BooleanVar(value=True)
    ttk.Checkbutton(
        main, text="Start automatically with Windows",
        variable=v_autostart, style="Main.TCheckbutton",
    ).pack(anchor="w", pady=(0, 3))

    v_startmenu = tk.BooleanVar(value=True)
    ttk.Checkbutton(
        main, text="Create Start Menu shortcut",
        variable=v_startmenu, style="Main.TCheckbutton",
    ).pack(anchor="w", pady=(0, 3))

    v_desktop = tk.BooleanVar(value=False)
    ttk.Checkbutton(
        main, text="Create Desktop shortcut",
        variable=v_desktop, style="Main.TCheckbutton",
    ).pack(anchor="w", pady=(0, 3))

    bottom, status_var = _make_bottom_bar(root)
    result = {"done": False}

    def do_install() -> None:
        install_btn.configure(state="disabled")
        cancel_btn.configure(state="disabled")

        try:
            status_var.set("Copying files...")
            root.update()
            _copy_exe()
        except Exception as e:
            logger.exception("Failed to copy exe")
            status_var.set(f"Error: {e}")
            install_btn.configure(state="normal")
            cancel_btn.configure(state="normal")
            return

        if v_autostart.get():
            status_var.set("Setting up autostart...")
            root.update()
            _safe(_set_autostart, True)

        if v_startmenu.get():
            status_var.set("Creating Start Menu shortcut...")
            root.update()
            _safe(_create_shortcut, "start_menu")

        if v_desktop.get():
            status_var.set("Creating Desktop shortcut...")
            root.update()
            _safe(_create_shortcut, "desktop")

        status_var.set("Installation complete!")
        root.update()
        result["done"] = True
        root.after(600, root.destroy)

    cancel_btn = ttk.Button(bottom, text="Cancel", command=root.destroy, width=10)
    cancel_btn.pack(side="right", padx=(6, 0))
    install_btn = ttk.Button(bottom, text="Install", command=do_install, width=10)
    install_btn.pack(side="right")

    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()

    if result["done"]:
        _launch_installed()
        return True
    return False


# ---------------------------------------------------------------------------
# Manage / Uninstall wizard (shown when already installed)
# ---------------------------------------------------------------------------

def _run_manage_wizard() -> bool:
    root = tk.Tk()
    root.title(f"{APP_NAME} Setup")
    root.resizable(False, False)
    root.configure(bg="white")
    _center(root, 500, 340)
    _apply_styles()

    main = ttk.Frame(root, style="Main.TFrame", padding=(24, 20, 24, 12))
    main.pack(fill="both", expand=True)

    ttk.Label(main, text=f"{APP_NAME} is already installed", style="Title.TLabel").pack(
        anchor="w", pady=(0, 12),
    )
    ttk.Label(
        main,
        text=(
            f"Interview Copilot is installed at:\n{INSTALL_DIR}\n\n"
            "Choose what you would like to do:"
        ),
        style="Main.TLabel",
    ).pack(anchor="w", pady=(0, 16))

    v_action = tk.StringVar(value="reinstall")
    ttk.Radiobutton(
        main, text="Reinstall — replace with this version",
        variable=v_action, value="reinstall", style="Main.TRadiobutton",
    ).pack(anchor="w", pady=(0, 4))
    ttk.Radiobutton(
        main, text="Uninstall — remove Interview Copilot from this computer",
        variable=v_action, value="uninstall", style="Main.TRadiobutton",
    ).pack(anchor="w", pady=(0, 4))

    v_delete_data = tk.BooleanVar(value=False)
    data_cb = ttk.Checkbutton(
        main, text="Also delete recordings and settings",
        variable=v_delete_data, style="Main.TCheckbutton",
    )
    data_cb.pack(anchor="w", padx=(20, 0), pady=(0, 4))

    bottom, status_var = _make_bottom_bar(root)
    result = {"done": False, "launched": False}

    def do_action() -> None:
        action = v_action.get()
        ok_btn.configure(state="disabled")
        cancel_btn.configure(state="disabled")

        if action == "uninstall":
            _do_uninstall(root, status_var, v_delete_data.get())
            status_var.set("Uninstall complete.")
            root.update()
            result["done"] = True
            root.after(800, root.destroy)
        else:
            _do_reinstall(root, status_var)
            status_var.set("Reinstall complete!")
            root.update()
            result["done"] = True
            result["launched"] = True
            root.after(600, root.destroy)

    cancel_btn = ttk.Button(bottom, text="Cancel", command=root.destroy, width=10)
    cancel_btn.pack(side="right", padx=(6, 0))
    ok_btn = ttk.Button(bottom, text="OK", command=do_action, width=10)
    ok_btn.pack(side="right")

    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()

    if result.get("launched"):
        _launch_installed()
        return True
    return False


def _do_uninstall(root: tk.Tk, status_var: tk.StringVar, delete_data: bool) -> None:
    # Kill running instances first
    status_var.set("Stopping running instances...")
    root.update()
    _kill_running()
    time.sleep(0.5)

    status_var.set("Removing autostart...")
    root.update()
    _safe(_set_autostart, False)

    status_var.set("Removing shortcuts...")
    root.update()
    _safe(_remove_shortcut, "start_menu")
    _safe(_remove_shortcut, "desktop")

    status_var.set("Removing program files...")
    root.update()
    _safe(_remove_install_dir)

    if delete_data:
        status_var.set("Removing recordings and settings...")
        root.update()
        _safe(_remove_data_dir)


def _do_reinstall(root: tk.Tk, status_var: tk.StringVar) -> None:
    status_var.set("Stopping running instances...")
    root.update()
    _kill_running()
    time.sleep(0.5)

    status_var.set("Copying files...")
    root.update()
    _copy_exe()

    status_var.set("Updating autostart...")
    root.update()
    _safe(_set_autostart, True)


# ---------------------------------------------------------------------------
# Low-level operations
# ---------------------------------------------------------------------------

def _safe(fn, *args) -> None:
    try:
        fn(*args)
    except Exception as e:
        logger.warning("%s failed: %s", fn.__name__, e)


def _copy_exe() -> None:
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    src = Path(sys.executable).resolve()
    dst = INSTALLED_EXE.resolve()
    if src != dst:
        shutil.copy2(str(src), str(dst))
    if not INSTALLED_EXE.exists():
        raise FileNotFoundError(f"Copy verification failed — {INSTALLED_EXE} not found")
    logger.info("Installed exe to %s", INSTALLED_EXE)


def _set_autostart(enable: bool) -> None:
    import winreg
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, REGISTRY_KEY, 0,
        winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE,
    )
    try:
        if enable:
            winreg.SetValueEx(key, REGISTRY_VALUE, 0, winreg.REG_SZ, f'"{INSTALLED_EXE}"')
        else:
            try:
                winreg.DeleteValue(key, REGISTRY_VALUE)
            except FileNotFoundError:
                pass
    finally:
        winreg.CloseKey(key)


def _create_shortcut(location: str) -> None:
    folder = _get_known_folder(location)
    if not folder:
        return
    folder.mkdir(parents=True, exist_ok=True)
    lnk_path = folder / f"{APP_NAME}.lnk"

    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        try:
            shell = win32com.client.Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(str(lnk_path))
            shortcut.Targetpath = str(INSTALLED_EXE)
            shortcut.WorkingDirectory = str(INSTALL_DIR)
            shortcut.Description = APP_NAME
            shortcut.save()
        finally:
            pythoncom.CoUninitialize()
    except ImportError:
        _create_shortcut_powershell(lnk_path)


def _create_shortcut_powershell(lnk_path: Path) -> None:
    ps_exe = _find_powershell()
    if not ps_exe:
        return
    lnk_str = str(lnk_path).replace("'", "''")
    target_str = str(INSTALLED_EXE).replace("'", "''")
    workdir_str = str(INSTALL_DIR).replace("'", "''")
    ps_script = (
        f"$ws = New-Object -ComObject WScript.Shell; "
        f"$sc = $ws.CreateShortcut('{lnk_str}'); "
        f"$sc.TargetPath = '{target_str}'; "
        f"$sc.WorkingDirectory = '{workdir_str}'; "
        f"$sc.Description = '{APP_NAME}'; "
        f"$sc.Save()"
    )
    try:
        subprocess.run(
            [ps_exe, "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True, timeout=15, creationflags=0x08000000,
        )
    except Exception as e:
        logger.warning("PowerShell shortcut failed: %s", e)


def _remove_shortcut(location: str) -> None:
    folder = _get_known_folder(location)
    if folder:
        lnk = folder / f"{APP_NAME}.lnk"
        lnk.unlink(missing_ok=True)


def _kill_running() -> None:
    """Kill any running instances of WinAudioSvc.exe."""
    taskkill = _find_exe("taskkill.exe")
    if not taskkill:
        return
    try:
        subprocess.run(
            [taskkill, "/F", "/IM", EXE_NAME],
            capture_output=True, timeout=10,
            creationflags=0x08000000,
        )
    except Exception:
        pass


def _remove_install_dir() -> None:
    if INSTALL_DIR.exists():
        shutil.rmtree(str(INSTALL_DIR), ignore_errors=True)


def _remove_data_dir() -> None:
    if DATA_DIR.exists():
        shutil.rmtree(str(DATA_DIR), ignore_errors=True)


def _find_powershell() -> str | None:
    result = shutil.which("powershell.exe")
    if result:
        return result
    sys_root = os.environ.get("SystemRoot", r"C:\Windows")
    candidate = os.path.join(sys_root, r"System32\WindowsPowerShell\v1.0\powershell.exe")
    if os.path.isfile(candidate):
        return candidate
    return None


def _find_exe(name: str) -> str | None:
    result = shutil.which(name)
    if result:
        return result
    sys_root = os.environ.get("SystemRoot", r"C:\Windows")
    candidate = os.path.join(sys_root, "System32", name)
    if os.path.isfile(candidate):
        return candidate
    return None


def _get_known_folder(name: str) -> Path | None:
    if name == "start_menu":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    elif name == "desktop":
        profile = os.environ.get("USERPROFILE")
        if profile:
            return Path(profile) / "Desktop"
    return None


def _launch_installed() -> None:
    if not INSTALLED_EXE.exists():
        logger.error("Installed exe not found at %s", INSTALLED_EXE)
        return
    try:
        subprocess.Popen(
            [str(INSTALLED_EXE)],
            creationflags=0x00000008 | 0x00000200,
            close_fds=True,
            cwd=str(INSTALL_DIR),
        )
    except OSError as e:
        logger.error("Failed to launch: %s", e)
