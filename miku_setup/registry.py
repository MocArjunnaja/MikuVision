"""
Entri "Apps & features" MikuVision di HKCU, tanpa admin (docs/PLAN_INSTALLER.md bagian 6).

Entri ini juga catatan instalasi untuk Setup sendiri: folder, versi, folder model, dan komponen yang dipakai
lagi oleh Perbarui, Perbaiki, dan Hapus.
"""

import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

APP_NAME = "MikuVision"
PUBLISHER = "MocArjunnaja"
ABOUT_URL = "https://github.com/MocArjunnaja/MikuVision"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\MikuVision"
SETUP_EXE = "MikuVisionSetup.exe"
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
    winreg = _winreg()
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        for name, value in entry_values(app, size_kb).items():
            kind = winreg.REG_DWORD if isinstance(value, int) else winreg.REG_SZ
            winreg.SetValueEx(key, name, 0, kind, value)


def read_installed(key_path: str = UNINSTALL_KEY) -> Optional[InstalledApp]:
    """Instalasi yang tercatat, atau None (belum dipasang lewat Setup, atau foldernya sudah hilang)."""
    if sys.platform != "win32":
        return None
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
    winreg = _winreg()
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
        return True
    except FileNotFoundError:
        return False
