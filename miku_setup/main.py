"""
Entry MikuVision Setup.

    python -m miku_setup.main            # pasang; bila sudah terpasang: pilih Perbarui, Perbaiki, atau Hapus
    python -m miku_setup.main --dry-run  # jalani semua halaman tanpa mengunduh atau memasang apa pun
    python -m miku_setup.main --update | --repair | --uninstall

Instalasi dikenali dari entrinya di "Apps & features" (registry.py, docs/PLAN_INSTALLER.md bagian 6); di Linux
dari ~/.local/share/mikuvision/install.json.
"""

import argparse
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Optional


# OS yang didukung Setup: Windows dan Linux (macOS belum)
PLATFORMS = ("win32", "linux")


def log_dir() -> Path:
    if sys.platform != "win32":
        return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "mikuvision" / "setup"
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "MikuVision-setup"


def setup_logging() -> Path:
    """Log wizard di %LOCALAPPDATA%\\MikuVision-setup\\setup-<waktu>.log; exe tidak punya konsol.

    Linux: ~/.local/share/mikuvision/setup. Unduhan rilis disimpan di sana juga (downloads/).
    """
    path = log_dir() / f"setup-{time.strftime('%Y%m%d-%H%M%S')}.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%H:%M:%S"))
    logger = logging.getLogger("miku_setup")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    return path


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    from .download import RELEASE_URL

    parser = argparse.ArgumentParser(prog="MikuVisionSetup", description="Installer MikuVision")
    parser.add_argument("--dry-run", action="store_true",
                        help="jalani semua halaman tanpa mengunduh atau memasang apa pun")
    # Memutar ulang log yang berakhir dengan error, untuk melihat halaman gagal
    parser.add_argument("--dry-run-fail", action="store_true", help=argparse.SUPPRESS)
    # Folder rilis lain (uji terima dengan server lokal); harus berisi version.json, SHA256SUMS, dan zip
    parser.add_argument("--release-url", default=RELEASE_URL, help=argparse.SUPPRESS)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--update", action="store_true", help="perbarui instalasi yang ada ke rilis terbaru")
    modes.add_argument("--repair", action="store_true", help="jalankan ulang pemasangan dengan pilihan yang sama")
    modes.add_argument("--uninstall", action="store_true", help="hapus MikuVision (dipakai \"Apps & features\")")
    return parser.parse_args(argv)


def requested_mode(args: argparse.Namespace, installed) -> str:
    """Mode wizard: install bila belum terpasang; maintain bila Setup dibuka lagi tanpa opsi."""
    flag = next((mode for mode in ("update", "repair", "uninstall") if getattr(args, mode)), None)
    if installed is None:
        return "missing" if flag else "install"
    return flag or "maintain"


def relaunch_outside(install_dir: Path, argv: List[str]) -> bool:
    """Exe Setup di <InstallDir>\\.tools tidak bisa menghapus dirinya sendiri: salin ke Temp lalu jalankan dari sana.

    Linux: file yang sedang berjalan boleh dihapus, jadi tidak perlu.
    """
    if not getattr(sys, "frozen", False) or sys.platform != "win32":
        return False
    exe = Path(sys.executable).resolve()
    try:
        exe.relative_to(Path(install_dir).resolve())
    except ValueError:
        return False
    copy = Path(tempfile.gettempdir()) / f"MikuVisionSetup-hapus-{os.getpid()}.exe"
    shutil.copy2(exe, copy)
    subprocess.Popen([str(copy), *argv], close_fds=True)
    return True


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    dry_run = args.dry_run or args.dry_run_fail
    if sys.platform not in PLATFORMS and not dry_run:
        if sys.stderr:
            sys.stderr.write("MikuVision Setup hanya untuk Windows dan Linux; "
                             "--dry-run untuk melihat halamannya.\n")
        return 2
    log = logging.getLogger("miku_setup")
    log_path = setup_logging()
    log.info("MikuVision Setup dimulai%s", " (dry-run)" if dry_run else "")

    from .components import Selection, default_install_dir
    from .registry import read_installed
    from .state import SetupState

    installed = None if dry_run else read_installed()
    mode = requested_mode(args, installed)
    log.info("Mode: %s%s", mode, f" ({installed.version} di {installed.install_dir})" if installed else "")
    if mode == "missing":
        from tkinter import Tk, messagebox
        root = Tk()
        root.withdraw()
        messagebox.showinfo("MikuVision Setup", "MikuVision belum terpasang lewat Setup di komputer ini.",
                            parent=root)
        root.destroy()
        return 1
    if mode == "uninstall" and relaunch_outside(installed.install_dir, list(sys.argv[1:] if argv is None else argv)):
        log.info("Hapus dilanjutkan dari salinan Setup di folder Temp")
        return 0

    from .wizard import Wizard

    selection = Selection(installed.install_dir if installed else default_install_dir())
    setup = SetupState(selection=selection, log_path=log_path, dry_run=dry_run, dry_run_fail=args.dry_run_fail,
                       mode=mode, installed=installed)
    if mode in ("update", "repair"):
        from .maintenance import selection_for
        setup.selection = selection_for(installed)
        setup.desktop_shortcut = setup.launch_now = False
    Wizard(setup, release_url=args.release_url).mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
