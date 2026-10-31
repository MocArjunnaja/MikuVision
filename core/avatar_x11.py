"""
Maskot desktop di Linux (X11): jendela pygame dibentuk persis seperti sprite
(ekstensi SHAPE), selalu di atas, tidak muncul di taskbar, dan bisa dipindah.
Setara layered window + WM_CLOSE di core/avatar_window.py untuk Windows.

Memakai python-xlib, yang sudah terpasang sebagai dependency pyautogui.
"""

from typing import Dict, List, Optional, Tuple

try:
    from Xlib import X, Xutil, display as xdisplay
    from Xlib.ext import shape
    from Xlib.protocol import event
    XLIB_AVAILABLE = True
except Exception:  # python-xlib tidak terpasang (Windows)
    XLIB_AVAILABLE = False

# _NET_WM_STATE: 1 = tambahkan
_NET_WM_STATE_ADD = 1


def mask_rectangles(surface, offset: Tuple[int, int] = (0, 0)) -> List[Dict[str, int]]:
    """Piksel tidak transparan sebuah surface pygame (colorkey/alpha) sebagai daftar persegi."""
    import pygame

    mask = pygame.mask.from_surface(surface)
    width, height = mask.get_size()
    return pixel_rectangles(width, height, lambda x, y: mask.get_at((x, y)), offset)


def pixel_rectangles(width: int, height: int, is_set, offset: Tuple[int, int] = (0, 0)) -> List[Dict[str, int]]:
    """Piksel yang terisi (is_set(x, y)) sebagai persegi untuk bentuk jendela X11.

    Tiap baris dipecah menjadi deretan piksel yang terisi; deretan yang sama di baris
    berikutnya digabung ke atas, jadi sprite yang di-upscale 3x butuh ±1/3 jumlah persegi.
    """
    ox, oy = offset
    done: List[Dict[str, int]] = []
    open_rects: Dict[Tuple[int, int], Dict[str, int]] = {}
    for y in range(height):
        runs = []
        x = 0
        while x < width:
            if is_set(x, y):
                start = x
                while x < width and is_set(x, y):
                    x += 1
                runs.append((start, x))
            else:
                x += 1
        still_open = {}
        for run in runs:
            rect = open_rects.pop(run, None)
            if rect is None:
                rect = {"x": ox + run[0], "y": oy + y, "width": run[1] - run[0], "height": 0}
            rect["height"] += 1
            still_open[run] = rect
        done.extend(open_rects.values())
        open_rects = still_open
    done.extend(open_rects.values())
    return done


def active_window_id() -> Optional[int]:
    """Jendela yang sedang fokus (_NET_ACTIVE_WINDOW), untuk dikembalikan setelah maskot muncul."""
    if not XLIB_AVAILABLE:
        return None
    try:
        conn = xdisplay.Display()
        try:
            root = conn.screen().root
            prop = root.get_full_property(conn.intern_atom("_NET_ACTIVE_WINDOW"), X.AnyPropertyType)
            return int(prop.value[0]) if prop and prop.value[0] else None
        finally:
            conn.close()
    except Exception:
        return None


class X11Window:
    """Atur jendela pygame lewat koneksi X11 sendiri (dipakai dari thread maskot saja)."""

    def __init__(self, window_id: int):
        self.display = xdisplay.Display()
        self.window = self.display.create_resource_object("window", window_id)
        self.root = self.display.screen().root
        self.can_shape = bool(self.display.has_extension("SHAPE"))

    def _add_state(self, first: str, second: Optional[str] = None):
        atom = self.display.intern_atom
        data = [_NET_WM_STATE_ADD, atom(first), atom(second) if second else 0, 1, 0]
        message = event.ClientMessage(window=self.window, client_type=atom("_NET_WM_STATE"),
                                      data=(32, data))
        self.root.send_event(message, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)

    def setup(self):
        """Selalu di atas, di semua workspace, tidak di taskbar, dan tidak mengambil fokus keyboard."""
        self._add_state("_NET_WM_STATE_ABOVE", "_NET_WM_STATE_STICKY")
        self._add_state("_NET_WM_STATE_SKIP_TASKBAR", "_NET_WM_STATE_SKIP_PAGER")
        self.window.set_wm_hints(flags=Xutil.InputHint, input=0)
        self.display.flush()

    def set_shape(self, rectangles: List[Dict[str, int]]):
        """Bentuk jendela = persegi-persegi ini; klik di luarnya jatuh ke jendela di bawahnya."""
        if not self.can_shape:
            return
        self.window.shape_rectangles(shape.ShapeBounding, shape.ShapeSet, X.Unsorted, 0, 0, rectangles)
        self.display.flush()

    def activate(self, window_id: int):
        """Kembalikan fokus ke jendela lain (window manager memberi fokus ke jendela baru)."""
        atom = self.display.intern_atom
        target = self.display.create_resource_object("window", window_id)
        # Sumber 2 = permintaan dari alat bantu pengguna, bukan aplikasi yang minta perhatian
        message = event.ClientMessage(window=target, client_type=atom("_NET_ACTIVE_WINDOW"),
                                      data=(32, [2, X.CurrentTime, 0, 0, 0]))
        self.root.send_event(message, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
        self.display.flush()

    def move(self, x: float, y: float):
        self.window.configure(x=int(x), y=int(y))
        self.display.flush()

    def pointer(self) -> Tuple[int, int]:
        """Posisi kursor di layar (bukan relatif ke jendela)."""
        reply = self.root.query_pointer()
        return reply.root_x, reply.root_y

    def close(self):
        try:
            self.display.close()
        except Exception:
            pass
