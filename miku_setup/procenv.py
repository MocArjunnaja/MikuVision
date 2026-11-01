"""
Environment untuk program yang dijalankan Setup (install.sh, MikuVision, nvidia-smi, gio, ...).

Binary satu file PyInstaller di Linux mengarahkan LD_LIBRARY_PATH ke library bawaannya di /tmp/_MEI…, yang
dibangun di Ubuntu 22.04 dan dihapus saat Setup ditutup. Program sistem harus memakai library distronya
sendiri: curl dan git di distro yang lebih baru bisa butuh OpenSSL yang lebih baru, dan MikuVision tetap
berjalan setelah Setup ditutup. Variabel _PYI_* juga dibuang, supaya program PyInstaller lain tidak mengira
dirinya anak proses Setup.
"""

import os
import sys
from typing import Dict, Mapping, Optional


def clean_env(environ: Mapping[str, str]) -> Dict[str, str]:
    """environ tanpa jejak bootloader PyInstaller; LD_LIBRARY_PATH asli (LD_LIBRARY_PATH_ORIG) dikembalikan."""
    env = {name: value for name, value in environ.items() if not name.startswith("_PYI_") and name != "_MEIPASS2"}
    original = env.pop("LD_LIBRARY_PATH_ORIG", None)
    if original is not None:
        env["LD_LIBRARY_PATH"] = original
    else:
        env.pop("LD_LIBRARY_PATH", None)
    return env


def child_env(extra: Optional[Mapping[str, str]] = None) -> Optional[Dict[str, str]]:
    """Untuk subprocess(env=...). None (warisi apa adanya) bila Setup tidak berjalan sebagai binary Linux
    dan tidak ada variabel tambahan, jadi perilaku di Windows dan dari kode sumber tidak berubah."""
    frozen_linux = getattr(sys, "frozen", False) and sys.platform != "win32"
    if not frozen_linux and not extra:
        return None
    env = clean_env(os.environ) if frozen_linux else dict(os.environ)
    env.update(extra or {})
    return env
