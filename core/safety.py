"""
Batas aman tool Miku: folder dan proses yang tidak boleh disentuh, apa pun kata LLM.

LLM bisa salah dengar (STT) atau salah tafsir, dan skill/routine bisa ditulis siapa saja,
jadi aturan di sini dicek di dalam tool, bukan hanya di prompt. Gerbang konfirmasi
(core/confirmation.py) menanyakan user; modul ini menolak tanpa bertanya.

Mirip is_protected_folder di miku_setup/components.py (akar drive dan folder home),
ditambah folder sistem, folder program, folder konfigurasi di home, dan folder aplikasi ini.
"""

import os
import re
import sys
import tempfile
from pathlib import Path
from typing import FrozenSet, Iterable, List, Optional, Set

import psutil

from config import BASE_DIR

# Folder di dalam home yang menyimpan konfigurasi/autostart: menulis ke sana bisa merusak
# sistem atau menjalankan program saat login (Startup, ~/.config/autostart, ~/.bashrc)
_WINDOWS_HOME_PROTECTED = ("AppData",)


def _windows_system_trees() -> List[Path]:
    env = os.environ
    names = ("SystemRoot", "windir", "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "ProgramData")
    defaults = (r"C:\Windows", r"C:\Program Files", r"C:\Program Files (x86)", r"C:\ProgramData")
    return [Path(p) for p in {*(env.get(n) for n in names), *defaults} if p]


_LINUX_SYSTEM_TREES = ("/usr", "/etc", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/boot", "/var",
                       "/opt", "/proc", "/sys", "/dev", "/root", "/snap", "/srv", "/run")


def _resolve(path) -> Path:
    try:
        return Path(path).expanduser().resolve()
    except (OSError, RuntimeError):
        return Path(os.path.abspath(Path(path).expanduser()))


def _comparable(path: Path) -> Path:
    # Path Windows tidak peka huruf besar/kecil
    return Path(str(path).lower()) if sys.platform == "win32" else path


def _inside(path: Path, tree: Path) -> bool:
    path, tree = _comparable(path), _comparable(tree)
    return path == tree or tree in path.parents


def protected_path_reason(path, home: Optional[Path] = None, app_dir: Path = BASE_DIR) -> Optional[str]:
    """Alasan path tidak boleh ditulis/dihapus/dipindah oleh tool, atau None bila boleh.

    Ditolak: akar drive/filesystem, folder home itu sendiri, folder sistem dan program beserta
    isinya, folder konfigurasi tersembunyi di home (.ssh, .config, AppData), dan folder MikuVision.
    """
    target = _resolve(path)
    home = _resolve(Path.home() if home is None else home)
    if target.parent == target:
        return f"{target} adalah akar drive/filesystem"
    # Folder sementara memang untuk file buangan (di Windows letaknya di dalam AppData)
    if _inside(target, _resolve(tempfile.gettempdir())) and target != _resolve(tempfile.gettempdir()):
        return None
    if _inside(target, _resolve(app_dir)):
        return f"{target} ada di folder aplikasi MikuVision"
    trees = _windows_system_trees() if sys.platform == "win32" else [Path(p) for p in _LINUX_SYSTEM_TREES]
    for tree in trees:
        resolved_tree = _resolve(tree)
        # Home bisa berada di dalam folder sistem (mis. /var/home di Fedora Silverblue)
        if _inside(target, resolved_tree) and not _inside(target, home):
            return f"{target} ada di folder sistem {resolved_tree}"
    if _comparable(target) == _comparable(home.parent):
        return f"{target} berisi folder home semua user"
    if _inside(target, home):
        if _comparable(target) == _comparable(home):
            return f"{target} adalah folder home"
        first = _comparable(target).relative_to(_comparable(home)).parts[0]
        if first.startswith(".") or first.lower() in (p.lower() for p in _WINDOWS_HOME_PROTECTED):
            return f"{target} ada di folder konfigurasi {home / first}"
    return None


# Karakter yang tidak boleh ada di nama file Windows (juga dipakai di Linux supaya sama)
_BAD_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_WINDOWS_NAMES = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
                           *(f"lpt{i}" for i in range(1, 10))}


def safe_filename(filename: str, suffix: str, default: str = "Miku_Dokumen") -> str:
    """Nama file dari LLM -> nama file saja (tanpa folder), dengan akhiran suffix.

    "C:\\Windows\\win.ini", "../../.bashrc", atau "/etc/passwd" menjadi "win.ini.docx",
    ".bashrc.docx" -> "bashrc.docx", "passwd.docx": file selalu jatuh di folder yang dipilih pemanggil.
    """
    name = re.split(r"[\\/]", (filename or "").strip())[-1]
    if name.lower().endswith(suffix.lower()):
        name = name[:-len(suffix)]
    name = _BAD_FILENAME_CHARS.sub("_", name).strip(" .")
    if not name or name.lower() in _RESERVED_WINDOWS_NAMES:
        name = default
    return name[:100] + suffix


def path_in_folder(folder: Path, filename: str, suffix: str) -> Path:
    """Path file di folder; ValueError bila tetap keluar dari folder (symlink) atau dilindungi."""
    path = Path(folder) / safe_filename(filename, suffix)
    resolved_folder = _resolve(folder)
    if _resolve(path).parent != resolved_folder:
        raise ValueError(f"'{filename}' keluar dari folder {folder}")
    reason = protected_path_reason(path)
    if reason:
        raise ValueError(reason)
    return path


def unused_path(path: Path) -> Path:
    """path, atau "nama (2).ext", "nama (3).ext", ... bila sudah ada: file lama tidak ditimpa."""
    if not path.exists():
        return path
    for i in range(2, 1000):
        candidate = path.with_name(f"{path.stem} ({i}){path.suffix}")
        if not candidate.exists():
            return candidate
    raise ValueError(f"Terlalu banyak file bernama {path.stem} di {path.parent}")


# ── Proses ──

def process_ancestry(pid: int) -> Set[int]:
    """PID proses ini dan semua induknya."""
    try:
        proc = psutil.Process(pid)
        return {proc.pid, *(parent.pid for parent in proc.parents())}
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return {pid}


# Dihitung sekali: induk MikuVision tidak berganti selama berjalan
MIKU_PROCESS_IDS: FrozenSet[int] = frozenset(process_ancestry(os.getpid()))


def miku_process_ids() -> FrozenSet[int]:
    """PID MikuVision dan semua induknya (terminal, cmd, VS Code yang menjalankannya).

    Menutup salah satunya ikut mematikan Miku. Anak proses tidak termasuk: aplikasi yang
    dibuka Miku (Notepad dari open_application) harus tetap bisa ditutup.
    """
    return MIKU_PROCESS_IDS


# ── Keyboard ──

_KEY_ALIASES = {
    "windows": "win", "winleft": "win", "winright": "win", "super": "win", "meta": "win",
    "command": "win", "cmd": "win", "control": "ctrl", "ctrlleft": "ctrl", "ctrlright": "ctrl",
    "altleft": "alt", "altright": "alt", "shiftleft": "shift", "shiftright": "shift", "del": "delete",
}

# Kombinasi yang membuka jalan ke perintah sistem atau menghapus/menutup tanpa sasaran jelas
BLOCKED_HOTKEYS = {
    frozenset({"win", "r"}): "membuka dialog Run (bisa menjalankan perintah apa pun)",
    frozenset({"alt", "f2"}): "membuka dialog Run Command di desktop Linux (bisa menjalankan perintah apa pun)",
    frozenset({"win", "x"}): "membuka menu Power User (shutdown, terminal admin)",
    frozenset({"ctrl", "alt", "delete"}): "membuka layar keamanan Windows",
    frozenset({"shift", "delete"}): "menghapus file permanen tanpa Recycle Bin",
    frozenset({"alt", "f4"}): ("menutup jendela yang sedang aktif, yang bisa jadi Miku sendiri atau desktop "
                               "(dialog shutdown); pakai close_window atau close_application"),
}


def normalize_keys(keys: Iterable[str]) -> List[str]:
    return [_KEY_ALIASES.get(k, k) for k in (str(k).strip().lower() for k in keys) if k]


def blocked_hotkey_reason(keys: Iterable[str]) -> Optional[str]:
    combo: FrozenSet[str] = frozenset(normalize_keys(keys))
    return BLOCKED_HOTKEYS.get(combo)
