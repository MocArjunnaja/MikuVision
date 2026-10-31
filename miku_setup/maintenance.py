"""
Perbarui, Perbaiki, dan Hapus untuk instalasi yang tercatat di registry (docs/PLAN_INSTALLER.md bagian 6).

Hapus hanya menyentuh yang dibuat Setup: InstallDir, shortcut yang menunjuk ke InstallDir, entri registry,
dan ModelDir pilihan user beserta variabel OLLAMA_MODELS/HF_HOME yang menunjuk ke sana. Model di lokasi
bawaan Ollama tidak dihapus, karena bisa dipakai aplikasi lain. Ollama sendiri juga tidak dihapus.
"""

import logging
import os
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from . import registry
from .components import Selection
from .registry import APP_NAME, InstalledApp

log = logging.getLogger("miku_setup")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
MODEL_ENV_VARS = ("OLLAMA_MODELS", "HF_HOME")
# Isi InstallDir yang disimpan bila user tidak mencentang "Hapus percakapan, memori, dan skill"
USER_DATA = "data"
# Sama dengan Test-RvcModelPresent di install.ps1; folder kosongnya ikut di zip rilis (.gitkeep)
RVC_WEIGHTS = Path("models") / "miku_default_rvc" / "weights" / "miku_default_rvc.pth"


@dataclass
class RemovalPlan:
    data: bool = False      # data/: percakapan, memori, skill
    models: bool = False    # ModelDir pilihan user (hanya bila tercatat)


def selection_for(app: InstalledApp) -> Selection:
    """Pilihan untuk Perbarui/Perbaiki. File RVC sudah ada di models/, jadi -RvcModel tidak dikirim lagi."""
    return Selection(app.install_dir, model_dir=app.model_dir, components=set(app.components) - {"rvc"})


def _inside(path: Path, folder: Path) -> bool:
    try:
        return Path(path).resolve().is_relative_to(Path(folder).resolve())
    except (OSError, ValueError):
        return False


def running_processes(install_dir: Path) -> List[str]:
    """Nama proses yang berjalan dari InstallDir (MikuVision masih terbuka), kecuali Setup ini sendiri."""
    try:
        import psutil
    except ImportError:
        return []
    names = []
    for process in psutil.process_iter(["pid", "name", "exe"]):
        exe = process.info.get("exe")
        if exe and process.info["pid"] != os.getpid() and _inside(Path(exe), install_dir):
            names.append(process.info.get("name") or Path(exe).name)
    return sorted(set(names))


def folder_size(path: Path) -> int:
    """Byte di folder; file yang di-hardlink (cache uv ke .venv) dihitung sekali."""
    total = 0
    seen = set()
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                info = os.lstat(os.path.join(root, name))
            except OSError:
                continue
            if info.st_nlink > 1:
                if (info.st_dev, info.st_ino) in seen:
                    continue
                seen.add((info.st_dev, info.st_ino))
            total += info.st_size
    return total


def register_install(selection: Selection, version: str,
                     write: Callable[[InstalledApp, int], None] = registry.write_entry) -> Optional[str]:
    """Catat instalasi di "Apps & features" setelah install.ps1 berhasil; alasan bila gagal, selain itu None."""
    components = set(selection.components)
    if selection.rvc_model or (Path(selection.install_dir) / RVC_WEIGHTS).is_file():
        components.add("rvc")
    app = InstalledApp(Path(selection.install_dir), version, selection.model_dir, components)
    try:
        registry.copy_setup_exe(app.install_dir)
        write(app, folder_size(app.install_dir) // 1024)
    except OSError as e:
        log.warning("Entri Apps & features gagal ditulis: %s", e)
        return f"MikuVision tidak tercatat di \"Apps & features\": {e}"
    log.info("Tercatat di Apps & features: %s %s", APP_NAME, version)
    return None


def shortcut_target(lnk: Path) -> str:
    """Target shortcut .lnk lewat WScript.Shell; '' bila tidak terbaca."""
    script = "(New-Object -ComObject WScript.Shell).CreateShortcut($env:MIKU_LNK).TargetPath"
    try:
        result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                                env=dict(os.environ, MIKU_LNK=str(lnk)), capture_output=True, timeout=30,
                                creationflags=_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.decode("utf-8", errors="replace").strip()


def start_menu_folder() -> Path:
    return Path(os.environ.get("APPDATA") or Path.home()) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / \
        APP_NAME


def desktop_shortcut() -> Path:
    return Path(os.environ.get("USERPROFILE") or Path.home()) / "Desktop" / f"{APP_NAME}.lnk"


def app_shortcuts(install_dir: Path, target_of: Callable[[Path], str] = shortcut_target,
                  start_menu: Optional[Path] = None, desktop: Optional[Path] = None) -> List[Path]:
    """Shortcut milik instalasi ini. Shortcut Desktop bernama sama tapi menunjuk ke tempat lain dibiarkan."""
    start_menu = start_menu_folder() if start_menu is None else start_menu
    desktop = desktop_shortcut() if desktop is None else desktop
    found = sorted(start_menu.glob("*.lnk")) if start_menu.is_dir() else []
    if desktop.is_file() and _inside(Path(target_of(desktop) or "?"), install_dir):
        found.append(desktop)
    return found


def _force_remove(function, path, _exc_info):
    """rmtree: file read-only (misalnya .git objects atau wheel uv) dibuat bisa ditulis lalu dicoba lagi."""
    os.chmod(path, stat.S_IWRITE)
    function(path)


def remove_tree(path: Path) -> Optional[str]:
    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path, onerror=_force_remove)
        else:
            path.unlink()
    except OSError as e:
        return f"{path}: {e.strerror or e}"
    return None


def model_env_vars_inside(model_dir: Path, environ_user: Callable[[str], Optional[str]]) -> List[str]:
    return [name for name in MODEL_ENV_VARS if environ_user(name) and _inside(Path(environ_user(name)), model_dir)]


def _user_env(name: str) -> Optional[str]:
    if sys.platform != "win32":
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            return str(winreg.QueryValueEx(key, name)[0])
    except OSError:
        return None


def _delete_user_env(names: List[str]):
    """Hapus variabel user lalu beri tahu Windows (WM_SETTINGCHANGE), sama seperti SetEnvironmentVariable."""
    import ctypes
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as key:
        for name in names:
            try:
                winreg.DeleteValue(key, name)
            except FileNotFoundError:
                pass
    result = ctypes.c_ulong()
    ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, ctypes.byref(result))


def remove_installation(app: InstalledApp, plan: RemovalPlan, progress: Callable[[str], None] = lambda text: None,
                        shortcuts: Optional[List[Path]] = None,
                        delete_entry: Callable[[], object] = registry.delete_entry,
                        user_env: Callable[[str], Optional[str]] = _user_env,
                        delete_user_env: Callable[[List[str]], None] = _delete_user_env) -> List[str]:
    """Hapus sesuai rencana; daftar masalah (kosong = bersih).

    Entri registry hanya dihapus bila file aplikasi terhapus semua, supaya Hapus bisa diulang dari
    "Apps & features" bila ada file yang terkunci.
    """
    problems: List[str] = []
    install_dir = Path(app.install_dir)

    progress("Menghapus shortcut")
    for lnk in app_shortcuts(install_dir) if shortcuts is None else shortcuts:
        problem = remove_tree(lnk)
        problems += [problem] if problem else []
    folder = start_menu_folder()
    if shortcuts is None and folder.is_dir() and not any(folder.iterdir()):
        folder.rmdir()

    progress(f"Menghapus {install_dir}")
    app_problems = []
    if install_dir.is_dir():
        for child in sorted(install_dir.iterdir()):
            if child.name == USER_DATA and not plan.data:
                continue
            problem = remove_tree(child)
            app_problems += [problem] if problem else []
        if not any(install_dir.iterdir()):
            install_dir.rmdir()
    problems += app_problems

    if plan.models and app.model_dir:
        progress(f"Menghapus model di {app.model_dir}")
        names = model_env_vars_inside(app.model_dir, user_env)
        problem = remove_tree(Path(app.model_dir)) if Path(app.model_dir).exists() else None
        problems += [problem] if problem else []
        if names:
            delete_user_env(names)
            log.info("Variabel user dihapus: %s", ", ".join(names))

    if app_problems:
        log.warning("Entri Apps & features dibiarkan: %d file aplikasi tidak terhapus", len(app_problems))
    else:
        delete_entry()
    for problem in problems:
        log.warning("Gagal menghapus %s", problem)
    return problems
