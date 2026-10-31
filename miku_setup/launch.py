"""Halaman Selesai: shortcut Desktop dan menjalankan MikuVision (GUI tanpa jendela konsol)."""

import os
import subprocess
from pathlib import Path
from typing import Optional

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
APP_NAME = "MikuVision"

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
    return Path(os.environ.get("USERPROFILE") or Path.home()) / "Desktop"


def create_desktop_shortcut(install_dir: Path, desktop: Optional[Path] = None) -> Optional[str]:
    """None bila berhasil, selain itu alasan gagal."""
    install_dir = Path(install_dir)
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
    exe = pythonw(install_dir)
    if not exe.is_file():
        return f"{exe} tidak ditemukan"
    try:
        subprocess.Popen([str(exe), str(install_dir / "gui.py")], cwd=install_dir, close_fds=True,
                         creationflags=_NO_WINDOW)
    except OSError as e:
        return str(e)
    return None
