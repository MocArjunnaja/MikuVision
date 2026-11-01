"""
Entri "Apps & features" MikuVision di HKCU, tanpa admin (docs/PLAN_INSTALLER.md bagian 6).

Entri ini juga catatan instalasi untuk Setup sendiri: folder, versi, folder model, dan komponen yang dipakai
lagi oleh Perbarui, Perbaiki, dan Hapus.

Linux tidak punya registry: catatannya ~/.local/share/mikuvision/install.json, dan pengganti "Apps & features"
adalah dua entri di menu aplikasi, "MikuVision Setup" (Perbarui, Perbaiki, Hapus) dan "Hapus MikuVision".
Fungsi write_entry, read_installed, dan delete_entry sama untuk kedua OS.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

from .procenv import child_env

APP_NAME = "MikuVision"
PUBLISHER = "MocArjunnaja"
ABOUT_URL = "https://github.com/MocArjunnaja/MikuVision"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\MikuVision"
SETUP_EXE = "MikuVisionSetup.exe" if sys.platform == "win32" else "MikuVisionSetup"
# Tempat user membuka Setup lagi; dipakai di teks halaman Hapus
ENTRY_PLACE = "\"Apps & features\"" if sys.platform == "win32" else "menu aplikasi"
# Linux: entri menu milik Setup (peluncur MikuVision sendiri, mikuvision.desktop, dibuat install.sh)
SETUP_DESKTOP = "mikuvision-setup.desktop"
UNINSTALL_DESKTOP = "mikuvision-uninstall.desktop"
# Skrip entry PyInstaller di root repo; dipakai untuk perintah hapus saat Setup jalan dari kode sumber
ENTRY_SCRIPT = Path(__file__).resolve().parents[1] / "MikuVisionSetup.py"


@dataclass
class InstalledApp:
    install_dir: Path
    version: str
    model_dir: Optional[Path] = None
    components: Set[str] = field(default_factory=lambda: {"core", "brain"})


def setup_command(install_dir: Path) -> List[str]:
    """Perintah untuk membuka Setup lagi dari "Apps & features".

    Exe disalin ke <InstallDir>\\.tools; dari kode sumber (pengembang) dipakai pythonw dengan skrip entry.
    Linux: binary MikuVisionSetup di tempat yang sama, atau python dengan skrip entry.
    """
    if getattr(sys, "frozen", False):
        return [str(Path(install_dir) / ".tools" / SETUP_EXE)]
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return [str(pythonw if pythonw.is_file() else Path(sys.executable)), str(ENTRY_SCRIPT)]


def copy_setup_exe(install_dir: Path) -> Optional[Path]:
    """Salin exe Setup yang sedang jalan ke <InstallDir>\\.tools (exe saja; dari kode sumber tidak ada salinan)."""
    if not getattr(sys, "frozen", False):
        return None
    target = Path(install_dir) / ".tools" / SETUP_EXE
    source = Path(sys.executable)
    if source.resolve() != target.resolve():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if sys.platform != "win32":
            target.chmod(0o755)
    return target


def _quote(parts: List[str]) -> str:
    return " ".join(f'"{part}"' if " " in part or not part.startswith("--") else part for part in parts)


def entry_values(app: InstalledApp, size_kb: int) -> Dict[str, object]:
    """Nilai registry untuk instalasi ini (str = REG_SZ, int = REG_DWORD)."""
    command = setup_command(app.install_dir)
    values: Dict[str, object] = {
        "DisplayName": APP_NAME,
        "DisplayVersion": app.version,
        "Publisher": PUBLISHER,
        "URLInfoAbout": ABOUT_URL,
        "InstallLocation": str(app.install_dir),
        "DisplayIcon": str(Path(app.install_dir) / ".tools" / "mikuvision.ico"),
        "UninstallString": _quote(command + ["--uninstall"]),
        "ModifyPath": _quote(command),
        "EstimatedSize": int(size_kb),
        "NoRepair": 1,  # Perbaiki ada di dalam Setup (ModifyPath)
        "MikuComponents": ",".join(sorted(app.components)),
        "MikuModelDir": str(app.model_dir) if app.model_dir else "",
    }
    return values


def _winreg():
    import winreg
    return winreg


def write_entry(app: InstalledApp, size_kb: int, key_path: str = UNINSTALL_KEY):
    if sys.platform != "win32":
        _write_record(app, size_kb)
        return
    winreg = _winreg()
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        for name, value in entry_values(app, size_kb).items():
            kind = winreg.REG_DWORD if isinstance(value, int) else winreg.REG_SZ
            winreg.SetValueEx(key, name, 0, kind, value)


def read_installed(key_path: str = UNINSTALL_KEY) -> Optional[InstalledApp]:
    """Instalasi yang tercatat, atau None (belum dipasang lewat Setup, atau foldernya sudah hilang)."""
    if sys.platform != "win32":
        return _read_record()
    winreg = _winreg()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            def value(name: str, default: str = "") -> str:
                try:
                    return str(winreg.QueryValueEx(key, name)[0])
                except OSError:
                    return default

            install_dir = Path(value("InstallLocation"))
            components = {c for c in value("MikuComponents", "core,brain").split(",") if c}
            model_dir = value("MikuModelDir")
            app = InstalledApp(install_dir, value("DisplayVersion"), Path(model_dir) if model_dir else None,
                               components)
    except OSError:
        return None
    if not str(app.install_dir).strip() or not (app.install_dir / "install.ps1").is_file():
        return None
    return app


def delete_entry(key_path: str = UNINSTALL_KEY) -> bool:
    if sys.platform != "win32":
        return _delete_record()
    winreg = _winreg()
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
        return True
    except FileNotFoundError:
        return False


# ───────────────────────── Linux ─────────────────────────

def data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def record_path() -> Path:
    """Catatan instalasi di samping folder bawaan aplikasi (~/.local/share/mikuvision/app)."""
    return data_home() / "mikuvision" / "install.json"


def applications_dir() -> Path:
    return data_home() / "applications"


def record_values(app: InstalledApp, size_kb: int) -> Dict[str, object]:
    return {
        "name": APP_NAME,
        "version": app.version,
        "install_dir": str(app.install_dir),
        "model_dir": str(app.model_dir) if app.model_dir else "",
        "components": sorted(app.components),
        "size_kb": int(size_kb),
        "setup": setup_command(app.install_dir),
    }


# Spesifikasi Desktop Entry: argumen dengan karakter ini dikutip; di dalam kutip \ " ` $ diberi backslash
_EXEC_RESERVED = re.compile(r"""[\s"'\\><~|&;$*?#()`]""")


def desktop_exec(parts: List[str]) -> str:
    """Nilai Exec untuk perintah ini. % ditulis %%, dan backslash digandakan lagi di tingkat file."""
    quoted = []
    for part in parts:
        if _EXEC_RESERVED.search(part) or not part:
            part = '"' + re.sub(r'(["`$\\])', r"\\\1", part) + '"'
        quoted.append(part.replace("%", "%%"))
    return " ".join(quoted).replace("\\", "\\\\")


def desktop_entries(app: InstalledApp) -> Dict[str, str]:
    """Nama file -> isi entri menu "MikuVision Setup" dan "Hapus MikuVision" (pengganti "Apps & features")."""
    command = setup_command(app.install_dir)
    icon = Path(app.install_dir) / ".tools" / "mikuvision.png"
    icon_value = str(icon) if icon.is_file() else "system-software-install"
    entries = {}
    for name, title, comment, extra in (
        (SETUP_DESKTOP, f"{APP_NAME} Setup", f"Perbarui, perbaiki, atau hapus {APP_NAME} {app.version}", []),
        (UNINSTALL_DESKTOP, f"Hapus {APP_NAME}", f"Hapus {APP_NAME} dari komputer ini", ["--uninstall"]),
    ):
        entries[name] = "\n".join([
            "[Desktop Entry]", "Type=Application", f"Name={title}", f"Comment={comment}",
            f"Exec={desktop_exec(command + extra)}", f"Icon={icon_value}", "Terminal=false", "Categories=Utility;",
            "",
        ])
    return entries


def _refresh_menu(apps: Path):
    command = shutil.which("update-desktop-database")
    if command:
        try:
            subprocess.run([command, str(apps)], capture_output=True, timeout=30, env=child_env())
        except (OSError, subprocess.SubprocessError):
            pass


def _write_record(app: InstalledApp, size_kb: int):
    """install.json lalu entri menu. OSError diteruskan ke register_install (jadi peringatan)."""
    path = record_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(record_values(app, size_kb), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temp, path)
    apps = applications_dir()
    apps.mkdir(parents=True, exist_ok=True)
    for name, text in desktop_entries(app).items():
        (apps / name).write_text(text, encoding="utf-8")
        (apps / name).chmod(0o755)
    _refresh_menu(apps)


def _read_record() -> Optional[InstalledApp]:
    try:
        data = json.loads(record_path().read_text(encoding="utf-8"))
        install_dir = Path(str(data["install_dir"]))
        model_dir = str(data.get("model_dir") or "")
        components = {str(c) for c in data.get("components") or ["core", "brain"] if c}
        app = InstalledApp(install_dir, str(data.get("version") or ""), Path(model_dir) if model_dir else None,
                           components)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    if not str(app.install_dir).strip() or not (app.install_dir / "install.sh").is_file():
        return None
    return app


def _delete_record() -> bool:
    existed = record_path().is_file()
    apps = applications_dir()
    for path in (record_path(), apps / SETUP_DESKTOP, apps / UNINSTALL_DESKTOP):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    _refresh_menu(apps)
    return existed
