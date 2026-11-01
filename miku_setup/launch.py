"""Halaman Selesai: shortcut Desktop dan menjalankan MikuVision (GUI tanpa jendela konsol).

Linux: peluncur .desktop (salinan entri menu dari install.sh) dan run.sh, yang mencatat output ke data/logs.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from .procenv import child_env
from .registry import applications_dir

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
APP_NAME = "MikuVision"
# Linux: peluncur yang dibuat create_launcher di install.sh (--menu-entry)
MENU_ENTRY = "mikuvision.desktop"
# Tempat MikuVision bisa dibuka selain Desktop
MENU_PLACE = "Start Menu" if sys.platform == "win32" else "menu aplikasi"

# Sama dengan New-AppShortcut di install.ps1; path lewat variabel environment supaya kutip dan spasi aman
_SHORTCUT_SCRIPT = (
    "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:MIKU_LNK); "
    "$s.TargetPath = $env:MIKU_TARGET; $s.Arguments = $env:MIKU_ARGS; $s.WorkingDirectory = $env:MIKU_DIR; "
    "$s.Description = 'MikuVision - asisten desktop Hatsune Miku'; "
    "if (Test-Path $env:MIKU_ICON) { $s.IconLocation = $env:MIKU_ICON }; $s.Save()"
)


def pythonw(install_dir: Path) -> Path:
    return Path(install_dir) / ".venv" / "Scripts" / "pythonw.exe"


def desktop_dir() -> Path:
    """Folder Desktop; di Linux dari xdg-user-dir (namanya mengikuti bahasa sistem, misalnya ~/Desktop)."""
    if sys.platform == "win32":
        return Path(os.environ.get("USERPROFILE") or Path.home()) / "Desktop"
    command = shutil.which("xdg-user-dir")
    if command:
        try:
            result = subprocess.run([command, "DESKTOP"], capture_output=True, timeout=10, env=child_env())
            path = result.stdout.decode("utf-8", errors="replace").strip()
            if result.returncode == 0 and path:
                return Path(path)
        except (OSError, subprocess.SubprocessError):
            pass
    return Path.home() / "Desktop"


def menu_entry() -> Path:
    return applications_dir() / MENU_ENTRY


def _create_desktop_launcher(install_dir: Path, desktop: Path) -> Optional[str]:
    """Salin entri menu dari install.sh ke Desktop, lalu tandai tepercaya supaya Nemo/Nautilus menjalankannya."""
    entry = menu_entry()
    if not entry.is_file():
        return f"{entry} tidak ditemukan"
    if not desktop.is_dir() or desktop == Path.home():
        return f"folder Desktop tidak ada ({desktop})"
    target = desktop / f"{APP_NAME}.desktop"
    try:
        shutil.copyfile(entry, target)
        target.chmod(0o755)
    except OSError as e:
        return str(e)
    gio = shutil.which("gio")
    if gio:
        try:
            subprocess.run([gio, "set", str(target), "metadata::trusted", "true"], capture_output=True, timeout=10,
                           env=child_env())
        except (OSError, subprocess.SubprocessError):
            pass
    return None


def create_desktop_shortcut(install_dir: Path, desktop: Optional[Path] = None) -> Optional[str]:
    """None bila berhasil, selain itu alasan gagal."""
    install_dir = Path(install_dir)
    if sys.platform != "win32":
        return _create_desktop_launcher(install_dir, Path(desktop or desktop_dir()))
    lnk = Path(desktop or desktop_dir()) / f"{APP_NAME}.lnk"
    env = dict(os.environ, MIKU_LNK=str(lnk), MIKU_TARGET=str(pythonw(install_dir)),
               MIKU_ARGS=f'"{install_dir / "gui.py"}"', MIKU_DIR=str(install_dir),
               MIKU_ICON=str(install_dir / ".tools" / "mikuvision.ico"))
    try:
        result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _SHORTCUT_SCRIPT],
                                env=env, capture_output=True, timeout=30, creationflags=_NO_WINDOW)
    except (OSError, subprocess.SubprocessError) as e:
        return str(e)
    if result.returncode != 0 or not lnk.is_file():
        return result.stderr.decode("utf-8", errors="replace").strip() or "shortcut tidak terbuat"
    return None


def launch(install_dir: Path) -> Optional[str]:
    """Jalankan GUI MikuVision di prosesnya sendiri; None bila berhasil dimulai."""
    install_dir = Path(install_dir)
    if sys.platform != "win32":
        script = install_dir / "run.sh"
        if not script.is_file():
            return f"{script} tidak ditemukan"
        try:
            # Sesi sendiri: MikuVision tetap jalan setelah Setup ditutup. run.sh mencatat output ke data/logs
            subprocess.Popen(["bash", str(script)], cwd=install_dir, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
                             env=child_env())
        except OSError as e:
            return str(e)
        return None
    exe = pythonw(install_dir)
    if not exe.is_file():
        return f"{exe} tidak ditemukan"
    try:
        subprocess.Popen([str(exe), str(install_dir / "gui.py")], cwd=install_dir, close_fds=True,
                         creationflags=_NO_WINDOW)
    except OSError as e:
        return str(e)
    return None
