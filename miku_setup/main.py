"""
Entry MikuVision Setup.

    python -m miku_setup.main            # unduh rilis terbaru dan pasang
    python -m miku_setup.main --dry-run  # jalani semua halaman tanpa mengunduh atau memasang apa pun

--update, --repair, dan --uninstall menyusul di fase I4 (docs/PLAN_INSTALLER.md).
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import List, Optional


def log_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "MikuVision-setup"


def setup_logging() -> Path:
    """Log wizard di %LOCALAPPDATA%\\MikuVision-setup\\setup-<waktu>.log; exe tidak punya konsol."""
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
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    dry_run = args.dry_run or args.dry_run_fail
    if sys.platform != "win32" and not dry_run:
        if sys.stderr:
            sys.stderr.write("MikuVision Setup hanya untuk Windows. Di Linux pakai install.sh, "
                             "atau --dry-run untuk melihat halamannya.\n")
        return 2
    log_path = setup_logging()
    logging.getLogger("miku_setup").info("MikuVision Setup dimulai%s", " (dry-run)" if dry_run else "")

    from .components import Selection, default_install_dir
    from .state import SetupState
    from .wizard import Wizard

    setup = SetupState(selection=Selection(default_install_dir()), log_path=log_path,
                       dry_run=dry_run, dry_run_fail=args.dry_run_fail)
    Wizard(setup, release_url=args.release_url).mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
