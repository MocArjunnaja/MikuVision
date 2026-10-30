"""
Aksi desktop yang berbeda per OS (volume, buka/tutup aplikasi, buka file/folder, media,
mengetik). Tool di core/system_control.py dan core/macro_tools.py memanggil backend ini,
bukan os.startfile, pycaw, atau win32 langsung.

Bukan bernama `platform` supaya tidak tertukar dengan modul standar Python.
"""

import sys

if sys.platform == "win32":
    from .windows import WindowsDesktop as Desktop, user_dir
else:
    from .linux import LinuxDesktop as Desktop, user_dir

# Backend untuk OS ini; SystemControl menerima backend lain untuk test
current = Desktop()

__all__ = ["Desktop", "current", "user_dir"]
