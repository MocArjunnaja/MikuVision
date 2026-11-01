"""Data jendela yang sama untuk backend Windows dan Linux."""

from typing import Any, NamedTuple


class WindowInfo(NamedTuple):
    id: Any       # HWND (Windows) atau id X11 "0x01e00003" (Linux)
    title: str
    pid: int
    kind: str = ""  # kelas jendela (Windows) atau nomor desktop wmctrl, "-1" = menempel di semua desktop
