"""
Screenshot untuk agent visi: jendela yang sedang aktif, atau seluruh layar bila yang aktif
adalah jendela Miku sendiri (GUI) atau jendelanya tidak terbaca.

Jendela aktif dipotong, bukan seluruh layar: setelah diperkecil ke 1280 px, teks kecil di
layar 1920 px jadi sulit dibaca model. Screenshot hanya ada di memori, tidak disimpan.
"""

import io
import os
import sys
from dataclasses import dataclass
from typing import Optional, Tuple

from PIL import Image, ImageGrab


@dataclass
class Window:
    title: str
    pid: Optional[int]
    rect: Tuple[int, int, int, int]  # x, y, lebar, tinggi dalam piksel layar


@dataclass
class Capture:
    image: Image.Image
    window: Optional[Window]  # None = seluruh layar

    @property
    def label(self) -> str:
        if self.window is None:
            return "seluruh layar"
        return f"jendela '{self.window.title}'" if self.window.title else "jendela aktif"


def _x11_active_window() -> Optional[Window]:
    from Xlib import X, display

    conn = display.Display()
    try:
        root = conn.screen().root
        atom = conn.intern_atom
        active = root.get_full_property(atom("_NET_ACTIVE_WINDOW"), X.AnyPropertyType)
        if not active or not active.value or not active.value[0]:
            return None
        window = conn.create_resource_object("window", active.value[0])
        pid = window.get_full_property(atom("_NET_WM_PID"), X.AnyPropertyType)
        name = window.get_full_property(atom("_NET_WM_NAME"), atom("UTF8_STRING"))
        title = name.value if name else (window.get_wm_name() or "")
        if isinstance(title, bytes):
            title = title.decode("utf-8", "replace")
        origin = root.translate_coords(window, 0, 0)
        geometry = window.get_geometry()
        return Window(title, int(pid.value[0]) if pid and len(pid.value) else None,
                      (origin.x, origin.y, geometry.width, geometry.height))
    finally:
        conn.close()


def _win32_active_window() -> Optional[Window]:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    # Koordinat fisik seperti screenshot Pillow, hanya untuk thread ini: SetProcessDPIAware
    # akan mengubah koordinat maskot di layar dengan skala 125%
    previous = None
    try:
        previous = user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
    except Exception:
        pass
    try:
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
    finally:
        if previous:
            user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(previous))
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return Window(buffer.value, pid.value, (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top))


def active_window(platform: str = sys.platform) -> Optional[Window]:
    """Jendela yang sedang fokus, atau None bila tidak terbaca (Wayland, tanpa DISPLAY)."""
    try:
        if platform == "win32":
            return _win32_active_window()
        if os.environ.get("DISPLAY") and os.environ.get("XDG_SESSION_TYPE") != "wayland":
            return _x11_active_window()
    except Exception as e:
        print(f"[Vision] Jendela aktif tidak terbaca: {e}")
    return None


def _grab(bbox: Optional[Tuple[int, int, int, int]] = None) -> Image.Image:
    return ImageGrab.grab(bbox=bbox, all_screens=sys.platform == "win32")


def capture(own_pid: Optional[int] = None) -> Capture:
    """Screenshot jendela aktif; seluruh layar bila jendela itu milik Miku (own_pid) atau tidak terbaca."""
    own_pid = os.getpid() if own_pid is None else own_pid
    window = active_window()
    if window and window.pid != own_pid:
        x, y, width, height = window.rect
        if width >= 50 and height >= 50:
            try:
                return Capture(_grab((x, y, x + width, y + height)), window)
            except Exception as e:  # jendela sebagian di luar layar, dsb.
                print(f"[Vision] Gagal memotong jendela, pakai seluruh layar: {e}")
    return Capture(_grab(), None)


def encode_jpeg(image: Image.Image, max_side: int) -> bytes:
    """Perkecil (sisi terpanjang max_side) dan simpan sebagai JPEG untuk dikirim ke model."""
    image = image.convert("RGB")
    image.thumbnail((max_side, max_side))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()
