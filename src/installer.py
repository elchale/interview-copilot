"""Self-installer: on first run, installs the app and sets up autostart."""

from __future__ import annotations

import logging
import os
import shutil
import sys
import tkinter as tk
from tkinter import ttk
from pathlib import Path

logger = logging.getLogger(__name__)

APP_NAME = "Interview Copilot"
EXE_NAME = "WinAudioSvc.exe"
INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Programs" / "InterviewCopilot"
INSTALLED_EXE = INSTALL_DIR / EXE_NAME
REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REGISTRY_VALUE = "WinAudioSvc"


def is_running_from_install_dir() -> bool:
    """Check if the current exe is running from the install directory."""
    if not getattr(sys, "frozen", False):
        return True
    try:
        current = Path(sys.executable).resolve()
        target = INSTALLED_EXE.resolve()
        return current == target
    except OSError:
        return False


def needs_install() -> bool:
    """Return True if we should show the installer."""
    if not getattr(sys, "frozen", False):
        return False
    return not is_running_from_install_dir()


def run_installer() -> bool:
    """Show install wizard. Returns True if installed and launched, False if cancelled."""
    root = tk.Tk()
    root.title(f"{APP_NAME} Setup")
    root.geometry("500x380")
    root.resizable(False, False)
    root.configure(bg="white")

    # Center on screen
    root.update_idletasks()
    x = (root.winfo_screenwidth() - 500) // 2
    y = (root.winfo_screenheight() - 380) // 2
    root.geometry(f"500x380+{x}+{y}")

    style = ttk.Style()
    style.theme_use("vista" if "vista" in style.theme_names() else "clam")

    # Standard Windows-like colors
    BG = "#f0f0f0"
    WHITE = "white"
    BLUE = "#0078d4"

    style.configure("Main.TFrame", background=WHITE)
    style.configure("Bottom.TFrame", background=BG)
    style.configure("Main.TLabel", background=WHITE, font=("Segoe UI", 9))
    style.configure("Title.TLabel", background=WHITE, font=("Segoe UI", 14))
    style.configure("Bold.TLabel", background=WHITE, font=("Segoe UI", 9, "bold"))
    style.configure("Status.TLabel", background=BG, font=("Segoe UI", 8), foreground="#555")
    style.configure("Main.TCheckbutton", background=WHITE, font=("Segoe UI", 9))
    style.configure("Install.TButton", font=("Segoe UI", 9))
    style.configure("Cancel.TButton", font=("Segoe UI", 9))

    # --- Top white area ---
    main_frame = ttk.Frame(root, style="Main.TFrame", padding=(24, 20, 24, 12))
    main_frame.pack(fill="both", expand=True)

    ttk.Label(
        main_frame, text=f"Welcome to {APP_NAME} Setup", style="Title.TLabel",
    ).pack(anchor="w", pady=(0, 12))

    ttk.Label(
        main_frame,
        text=(
            "This will install Interview Copilot on your computer.\n"
            "The program runs in the background and listens to your\n"
            "calls to help you with interview answers."
        ),
        style="Main.TLabel",
    ).pack(anchor="w", pady=(0, 16))

    ttk.Label(main_frame, text="Install location:", style="Bold.TLabel").pack(anchor="w")
    path_frame = ttk.Frame(main_frame, style="Main.TFrame")
    path_frame.pack(fill="x", pady=(2, 12))
    path_entry = ttk.Entry(path_frame, font=("Segoe UI", 9))
    path_entry.insert(0, str(INSTALL_DIR))
    path_entry.configure(state="readonly")
    path_entry.pack(fill="x")

    # Options
    v_autostart = tk.BooleanVar(value=True)
    ttk.Checkbutton(
        main_frame, text="Start automatically with Windows",
        variable=v_autostart, style="Main.TCheckbutton",
    ).pack(anchor="w", pady=(0, 3))

    v_startmenu = tk.BooleanVar(value=True)
    ttk.Checkbutton(
        main_frame, text="Create Start Menu shortcut",
        variable=v_startmenu, style="Main.TCheckbutton",
    ).pack(anchor="w", pady=(0, 3))

    v_desktop = tk.BooleanVar(value=False)
    ttk.Checkbutton(
        main_frame, text="Create Desktop shortcut",
        variable=v_desktop, style="Main.TCheckbutton",
    ).pack(anchor="w", pady=(0, 3))

    # --- Bottom gray bar ---
    sep = ttk.Separator(root, orient="horizontal")
    sep.pack(fill="x")

    bottom = ttk.Frame(root, style="Bottom.TFrame", padding=(24, 10))
    bottom.pack(fill="x")

    status_var = tk.StringVar(value="")
    status_label = ttk.Label(bottom, textvariable=status_var, style="Status.TLabel")
    status_label.pack(side="left")

    result = {"installed": False}

    def do_install() -> None:
        install_btn.configure(state="disabled")
        cancel_btn.configure(state="disabled")

        errors: list[str] = []

        # Step 1: Copy exe
        status_var.set("Copying files...")
        root.update()
        try:
            _copy_exe()
        except Exception as e:
            logger.exception("Failed to copy exe")
            errors.append(f"Copy failed: {e}")

        if errors:
            status_var.set(errors[0])
            install_btn.configure(state="normal")
            cancel_btn.configure(state="normal")
            return

        # Step 2: Autostart
        if v_autostart.get():
            status_var.set("Setting up autostart...")
            root.update()
            try:
                _set_autostart(True)
            except Exception as e:
                logger.warning("Autostart setup failed: %s", e)

        # Step 3: Shortcuts
        if v_startmenu.get():
            status_var.set("Creating Start Menu shortcut...")
            root.update()
            try:
                _create_shortcut("start_menu")
            except Exception as e:
                logger.warning("Start Menu shortcut failed: %s", e)

        if v_desktop.get():
            status_var.set("Creating Desktop shortcut...")
            root.update()
            try:
                _create_shortcut("desktop")
            except Exception as e:
                logger.warning("Desktop shortcut failed: %s", e)

        status_var.set("Installation complete!")
        root.update()
        result["installed"] = True
        root.after(600, root.destroy)

    cancel_btn = ttk.Button(bottom, text="Cancel", command=root.destroy, style="Cancel.TButton", width=10)
    cancel_btn.pack(side="right", padx=(6, 0))

    install_btn = ttk.Button(bottom, text="Install", command=do_install, style="Install.TButton", width=10)
    install_btn.pack(side="right")

    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()

    if result["installed"]:
        _launch_installed()
        return True
    return False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _copy_exe() -> None:
    """Copy the running exe to the install directory."""
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    src = Path(sys.executable).resolve()
    dst = INSTALLED_EXE.resolve()
    if src != dst:
        shutil.copy2(str(src), str(dst))
    if not INSTALLED_EXE.exists():
        raise FileNotFoundError(f"Copy failed — {INSTALLED_EXE} does not exist after copy")
    logger.info("Installed exe to %s", INSTALLED_EXE)


def _set_autostart(enable: bool) -> None:
    """Set or remove the Run registry key for autostart."""
    import winreg
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, REGISTRY_KEY, 0,
        winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE,
    )
    try:
        if enable:
            winreg.SetValueEx(key, REGISTRY_VALUE, 0, winreg.REG_SZ, f'"{INSTALLED_EXE}"')
            logger.info("Autostart enabled in registry")
        else:
            try:
                winreg.DeleteValue(key, REGISTRY_VALUE)
                logger.info("Autostart removed from registry")
            except FileNotFoundError:
                pass
    finally:
        winreg.CloseKey(key)


def _create_shortcut(location: str) -> None:
    """Create a Windows .lnk shortcut using COM via ctypes (no PowerShell needed)."""
    if location == "start_menu":
        folder = _get_known_folder("start_menu")
    elif location == "desktop":
        folder = _get_known_folder("desktop")
    else:
        return

    if not folder or not folder.exists():
        logger.warning("Could not find %s folder", location)
        return

    lnk_path = folder / f"{APP_NAME}.lnk"

    try:
        # Use pythoncom/win32com if available (pywin32)
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
            logger.info("Shortcut created: %s", lnk_path)
        finally:
            pythoncom.CoUninitialize()
    except ImportError:
        # Fallback: use PowerShell with full path
        _create_shortcut_powershell(lnk_path)


def _create_shortcut_powershell(lnk_path: Path) -> None:
    """Fallback shortcut creation via PowerShell."""
    import subprocess

    # Find powershell.exe explicitly
    ps_exe = _find_powershell()
    if not ps_exe:
        logger.warning("PowerShell not found — skipping shortcut creation")
        return

    # Escape backslashes for PowerShell
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
        result = subprocess.run(
            [ps_exe, "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True, timeout=15, creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
        if result.returncode == 0:
            logger.info("Shortcut created via PowerShell: %s", lnk_path)
        else:
            logger.warning(
                "PowerShell shortcut failed (rc=%d): %s",
                result.returncode, result.stderr.decode(errors="replace")[:200],
            )
    except Exception as e:
        logger.warning("PowerShell shortcut failed: %s", e)


def _find_powershell() -> str | None:
    """Find powershell.exe by checking known locations."""
    candidates = [
        shutil.which("powershell.exe"),
        shutil.which("powershell"),
    ]
    # Explicit paths as fallback
    sys_root = os.environ.get("SystemRoot", r"C:\Windows")
    for name in ("powershell.exe",):
        for subdir in (
            r"System32\WindowsPowerShell\v1.0",
            r"SysWOW64\WindowsPowerShell\v1.0",
        ):
            p = os.path.join(sys_root, subdir, name)
            candidates.append(p)

    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None


def _get_known_folder(name: str) -> Path | None:
    """Get a Windows known folder path."""
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
    """Launch the installed exe as a detached process."""
    import subprocess
    if not INSTALLED_EXE.exists():
        logger.error("Cannot launch — installed exe not found at %s", INSTALLED_EXE)
        return
    try:
        subprocess.Popen(
            [str(INSTALLED_EXE)],
            creationflags=0x00000008 | 0x00000200,  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
            close_fds=True,
            cwd=str(INSTALL_DIR),
        )
        logger.info("Launched installed copy")
    except OSError as e:
        logger.error("Failed to launch installed exe: %s", e)


def uninstall() -> None:
    """Remove the app: autostart, shortcuts."""
    try:
        _set_autostart(False)
    except Exception:
        pass

    for name in ("start_menu", "desktop"):
        folder = _get_known_folder(name)
        if folder:
            lnk = folder / f"{APP_NAME}.lnk"
            try:
                lnk.unlink(missing_ok=True)
            except OSError:
                pass

    logger.info("Uninstalled")
