"""
Aksi desktop Windows: volume (pycaw), buka aplikasi (App Paths / ShellExecute),
tutup jendela (WM_CLOSE), buka file/folder (os.startfile).
Isinya dipindah tanpa perubahan perilaku dari core/system_control.py.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from config import ALLOWED_APPS
from .app_search import AppEntry

try:
    import pyautogui
except Exception:
    pyautogui = None

# Nama proses (tanpa .exe) yang tidak boleh dimatikan lewat close_application
PROTECTED_PROCESSES = {
    "system", "smss", "csrss", "wininit", "winlogon", "services", "lsass",
    "svchost", "dwm", "explorer", "python", "pythonw", "ollama",
}

# Alias nama aplikasi -> nama proses (tanpa .exe)
PROCESS_ALIASES = {
    "google chrome": "chrome",
    "browser": "chrome",
    "edge": "msedge",
    "microsoft edge": "msedge",
    "word": "winword",
    "powerpoint": "powerpnt",
    "vscode": "code",
    "visual studio code": "code",
    "kalkulator": "calculatorapp",
    "calculator": "calculatorapp",
}

# Skema URI minimal 2 karakter, jadi drive letter "C:" tidak dianggap URI
URI_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]+:")

WM_CLOSE = 0x0010

USER_DIRS = {
    "desktop": "Desktop",
    "downloads": "Downloads",
    "documents": "Documents",
    "pictures": "Pictures",
    "music": "Music",
    "videos": "Videos",
}


def user_dir(name: str) -> Path:
    """Folder user (desktop, downloads, ...)."""
    return Path.home() / USER_DIRS.get(name, name)


def _start_menu_dirs() -> List[Path]:
    dirs = []
    for env, default in (("ProgramData", r"C:\ProgramData"), ("APPDATA", "")):
        base = os.environ.get(env) or default
        if base:
            dirs.append(Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    return dirs


def _start_apps() -> List[dict]:
    """Daftar aplikasi Start Menu (termasuk aplikasi Store): [{"Name", "AppID"}]."""
    script = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json -Compress"
    result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                            capture_output=True, timeout=20,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    data = json.loads(result.stdout.decode("utf-8", errors="replace") or "[]")
    return data if isinstance(data, list) else [data]


class WindowsDesktop:
    name = "windows"
    protected_processes = PROTECTED_PROCESSES

    def __init__(self):
        self._volume_interface = None

    # ── Audio ──

    def init_audio(self):
        try:
            import comtypes
            comtypes.CoInitialize()
        except Exception:
            pass

        try:
            from pycaw.pycaw import AudioUtilities
            devices = AudioUtilities.GetSpeakers()
            self._volume_interface = devices.EndpointVolume
            print("[SystemControl] Audio initialized successfully")
        except Exception as e:
            print(f"[SystemControl] Audio init failed: {e}")
            self._volume_interface = None

    def get_volume(self) -> int:
        if self._volume_interface:
            try:
                return int(self._volume_interface.GetMasterVolumeLevelScalar() * 100)
            except Exception as e:
                print(f"[SystemControl] Error getting volume: {e}")
        return -1

    def set_volume(self, level: int) -> Tuple[bool, str]:
        if self._volume_interface:
            try:
                self._volume_interface.SetMasterVolumeLevelScalar(level / 100.0, None)
                return True, f"Volume diatur ke {level}%"
            except Exception as e:
                return False, f"Error setting volume: {e}"
        return False, "Audio interface not available"

    def set_mute(self, mute: bool) -> Tuple[bool, str]:
        if not self._volume_interface:
            return False, "Audio interface not available"
        try:
            self._volume_interface.SetMute(mute, None)
            return True, f"Audio {'dimute' if mute else 'di-unmute'}"
        except Exception as e:
            return False, f"Error: {e}"

    def is_muted(self) -> bool:
        if not self._volume_interface:
            return False
        try:
            return bool(self._volume_interface.GetMute())
        except Exception:
            return False

    # ── Aplikasi ──

    def launch(self, app_name: str) -> Tuple[bool, str, Optional[int]]:
        """Buka aplikasi dari whitelist ALLOWED_APPS: (sukses, pesan, PID bila diketahui)."""
        app_lower = app_name.lower().strip()
        command = ALLOWED_APPS.get(app_lower)
        if not command:
            for key, cmd in ALLOWED_APPS.items():
                if app_lower in key or key in app_lower:
                    command = cmd
                    break
        if not command:
            return False, f"Aplikasi '{app_name}' tidak dikenali", None

        target = command[len("start "):].strip() if command.startswith("start ") else command
        print(f"[SystemControl] Launching: {target}")

        # Tanpa shell=True. Command berasal dari whitelist ALLOWED_APPS.
        try:
            if URI_SCHEME.match(target):
                os.startfile(target)
                return True, f"Membuka {app_name}...", None

            resolved = shutil.which(target)
            if resolved and resolved.lower().endswith(".exe"):
                proc = subprocess.Popen(
                    [resolved],
                    # Aplikasi konsol (cmd, powershell) butuh jendela sendiri
                    creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
                )
                return True, f"Membuka {app_name} (PID {proc.pid})...", proc.pid

            # Tidak ada di PATH (chrome, msedge, winword: terdaftar di App Paths)
            # atau script .cmd (VS Code): ShellExecute, sama seperti perintah `start`
            os.startfile(resolved or target)
            return True, f"Membuka {app_name}...", None
        except OSError as e:
            return False, f"Gagal membuka {app_name}: {e}", None

    def list_installed_apps(self) -> List[AppEntry]:
        """Aplikasi di Start Menu, sama dengan yang dicari Start Menu sendiri."""
        try:
            entries = [AppEntry(id=app["AppID"], name=app["Name"])
                       for app in _start_apps() if app.get("AppID") and app.get("Name")]
            if entries:
                return entries
        except (OSError, subprocess.SubprocessError, ValueError) as e:
            print(f"[AppSearch] Get-StartApps gagal ({e}); memakai shortcut Start Menu")
        # Cadangan: shortcut .lnk di folder Start Menu
        return [AppEntry(id=str(lnk), name=lnk.stem, path=str(lnk))
                for root in _start_menu_dirs() if root.is_dir() for lnk in sorted(root.rglob("*.lnk"))]

    def launch_entry(self, entry: AppEntry) -> Tuple[bool, str, Optional[int]]:
        """Buka aplikasi Start Menu, seperti mengkliknya di Start Menu."""
        try:
            if entry.path:
                os.startfile(entry.path)
            else:
                # Cara Start Menu membuka aplikasi (juga aplikasi Store) dari AppID-nya
                subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{entry.id}"])
        except OSError as e:
            return False, f"Gagal membuka {entry.name}: {e}", None
        return True, f"Membuka {entry.name}...", None

    def process_names(self, app_name: str) -> Set[str]:
        """Nama aplikasi -> nama proses tanpa .exe (setelah alias)."""
        key = app_name.lower().strip()
        key = PROCESS_ALIASES.get(key, key)
        return {key[:-4] if key.endswith(".exe") else key}

    @staticmethod
    def process_key(proc_name: str) -> str:
        name = (proc_name or "").lower()
        return name[:-4] if name.endswith(".exe") else name

    # ── Jendela ──

    @property
    def can_close_windows(self) -> bool:
        try:
            import win32gui  # noqa: F401  (cek ketersediaan)
            return True
        except ImportError:
            return False

    def windows_by_pid(self, pids: set) -> Dict[int, list]:
        """Jendela top-level yang terlihat milik proses-proses tersebut: {pid: [hwnd]}."""
        try:
            import win32gui
            import win32process
        except ImportError:
            return {}

        found: Dict[int, list] = {}

        def collect(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid in pids:
                    found.setdefault(pid, []).append(hwnd)
            return True

        win32gui.EnumWindows(collect, None)
        return found

    def close_window(self, hwnd: int):
        import win32gui
        win32gui.PostMessage(hwnd, WM_CLOSE, 0, 0)

    # ── File, media, keyboard ──

    def open_path(self, target: str):
        """Buka file, folder, atau URI dengan aplikasi bawaannya."""
        os.startfile(target)

    def user_dir(self, name: str) -> Path:
        return user_dir(name)

    def has_uri_handler(self, scheme: str) -> bool:
        # ShellExecute sendiri yang melaporkan bila skema tidak terdaftar
        return True

    def media(self, action: str) -> Tuple[bool, str]:
        keys = {"play_pause": "playpause", "next": "nexttrack", "prev": "prevtrack"}
        try:
            pyautogui.press(keys[action])
            return True, ""
        except Exception as e:
            return False, f"Gagal menekan tombol media: {e}"

    def type_text(self, text: str) -> Tuple[bool, str]:
        pyautogui.typewrite(text, interval=0.02)
        return True, f"Mengetik: {text[:30]}..."

    def session_warning(self) -> Optional[str]:
        return None

    def missing_tools(self) -> List[str]:
        return []
