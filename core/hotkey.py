"""
Pemicu "mulai bicara" dari aplikasi mana pun (T1 di docs/PLAN_VISION_AGENT.md):

- Shortcut keyboard global (default Ctrl+Shift+M, `WAKE_HOTKEY` di config.py).
  - Linux X11: XGrabKey pada root window lewat python-xlib (tanpa root; library yang sama dengan maskot).
  - Windows: library `keyboard`.
  - Wayland: belum didukung, Miku memberi tahu dan jalan tanpa shortcut.
- `python miku.py --trigger`: mengirim "dengar" ke Miku yang sedang jalan lewat
  multiprocessing.connection (Unix socket di Linux, named pipe di Windows) dengan authkey acak.
  User memasangnya sebagai shortcut di pengaturan keyboard desktop; jalan juga di Wayland.

Modul ini sengaja hanya memakai library standar (python-xlib dan `keyboard` di-import saat dipakai):
`miku.py --trigger` memuatnya langsung dari file tanpa config.py dan package core, yang memuat
torch dan Whisper (±20 s).
"""

import hashlib
import os
import socket
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, FrozenSet, List, Optional, Tuple

# Urutan tampilan, dan nama modifier yang diterima di WAKE_HOTKEY
MODIFIER_ORDER = ("ctrl", "alt", "shift", "super")
_MODIFIER_ALIASES = {
    "ctrl": "ctrl", "control": "ctrl",
    "alt": "alt",
    "shift": "shift",
    "super": "super", "win": "super", "windows": "super", "meta": "super",
}

# Nilai protokol X11 (X.h), supaya modul ini bisa dites tanpa python-xlib
_X_MASKS = {"shift": 1 << 0, "ctrl": 1 << 2, "alt": 1 << 3, "super": 1 << 6}
_X_LOCK_MASK = 1 << 1   # CapsLock
_X_MOD2_MASK = 1 << 4   # NumLock
# CapsLock/NumLock ikut di state event: grab semua kombinasinya
_X_IGNORED_MASKS = (0, _X_LOCK_MASK, _X_MOD2_MASK, _X_LOCK_MASK | _X_MOD2_MASK)
_X_KEY_PRESS = 2
_X_GRAB_MODE_ASYNC = 1

_WINDOWS_NAMES = {"ctrl": "ctrl", "alt": "alt", "shift": "shift", "super": "windows"}

_LISTEN = b"listen"
_OK = b"ok"


@dataclass(frozen=True)
class Combo:
    modifiers: FrozenSet[str]
    key: str  # "m", "7", "f9"

    def __str__(self) -> str:
        parts = [m.capitalize() for m in MODIFIER_ORDER if m in self.modifiers]
        return "+".join(parts + [self.key.upper()])


def parse_combo(text: str) -> Combo:
    """"ctrl+shift+m" → Combo. ValueError bila tidak valid.

    Kombinasi tanpa Ctrl, Alt, atau Super ditolak (kecuali tombol F): grab global pada huruf
    biasa atau Shift+huruf akan menelan ketikan user di semua aplikasi.
    """
    parts = [p.strip().lower() for p in text.split("+")]
    if not text.strip() or any(not p for p in parts):
        raise ValueError(f"shortcut '{text}' tidak lengkap")

    *mods, key = parts
    modifiers = set()
    for mod in mods:
        if mod not in _MODIFIER_ALIASES:
            raise ValueError(f"modifier '{mod}' tidak dikenal (pakai ctrl, alt, shift, super)")
        modifiers.add(_MODIFIER_ALIASES[mod])

    is_function_key = key[0] == "f" and key[1:].isdigit() and 1 <= int(key[1:]) <= 24
    if not (is_function_key or (len(key) == 1 and key.isascii() and key.isalnum())):
        raise ValueError(f"tombol '{key}' tidak didukung (pakai huruf, angka, atau F1-F24)")
    if not is_function_key and not modifiers & {"ctrl", "alt", "super"}:
        raise ValueError(f"shortcut '{text}' butuh Ctrl, Alt, atau Super")
    return Combo(frozenset(modifiers), key)


# ───────────────────────── Shortcut global ─────────────────────────

def _open_display():
    from Xlib import display
    return display.Display()


def _keysym(key: str) -> int:
    from Xlib import XK
    return XK.string_to_keysym(key.upper() if len(key) > 1 else key)


class _GrabErrors:
    """Penangan error request python-xlib: mencatat error (BadAccess bila kombinasi sudah dipakai)."""

    def __init__(self):
        self.errors = []

    def __call__(self, error, request):
        self.errors.append(error)
        return 1


class X11Hotkey:
    """XGrabKey pada root window, dengan koneksi Display sendiri yang dibaca di thread terpisah."""

    POLL_SEC = 0.02

    def __init__(self, combo: Combo, on_press: Callable[[], None]):
        self.combo = combo
        self.on_press = on_press
        self._display = None
        self._keycode = 0
        self._mask = 0
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> Optional[str]:
        """Pasang grab. None bila berhasil, selain itu alasan gagal."""
        if os.environ.get("XDG_SESSION_TYPE") == "wayland":
            return "Wayland belum didukung"
        if not os.environ.get("DISPLAY"):
            return "tidak ada DISPLAY X11"
        try:
            self._display = _open_display()
            self._keycode = self._display.keysym_to_keycode(_keysym(self.combo.key))
        except Exception as e:
            self._close()
            return f"X11 tidak tersedia ({e})"
        if not self._keycode:
            self._close()
            return f"tombol {self.combo.key.upper()} tidak ada di keyboard ini"

        self._mask = 0
        for mod in self.combo.modifiers:
            self._mask |= _X_MASKS[mod]
        root = self._display.screen().root
        errors = _GrabErrors()
        for extra in _X_IGNORED_MASKS:
            root.grab_key(self._keycode, self._mask | extra, True,
                          _X_GRAB_MODE_ASYNC, _X_GRAB_MODE_ASYNC, onerror=errors)
        self._display.sync()
        if errors.errors:
            self._release()
            return "sudah dipakai aplikasi lain"

        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="hotkey-x11", daemon=True)
        self._thread.start()
        return None

    def _loop(self):
        while not self._stop.is_set():
            try:
                while self._display.pending_events():
                    event = self._display.next_event()
                    if event.type == _X_KEY_PRESS and event.detail == self._keycode:
                        self.on_press()
            except Exception as e:
                print(f"[Hotkey] Error: {e}")
            self._stop.wait(self.POLL_SEC)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        self._release()

    def _release(self):
        if self._display is None:
            return
        try:
            root = self._display.screen().root
            for extra in _X_IGNORED_MASKS:
                root.ungrab_key(self._keycode, self._mask | extra)
            self._display.sync()
        except Exception:
            pass
        self._close()

    def _close(self):
        if self._display is not None:
            try:
                self._display.close()
            except Exception:
                pass
            self._display = None


class KeyboardHotkey:
    """Windows: library `keyboard` (hook keyboard global tanpa hak admin)."""

    def __init__(self, combo: Combo, on_press: Callable[[], None]):
        self.combo = combo
        self.on_press = on_press
        self._handle = None

    def start(self) -> Optional[str]:
        try:
            import keyboard
        except Exception as e:
            return f"library keyboard tidak tersedia ({e})"
        names = [_WINDOWS_NAMES[m] for m in MODIFIER_ORDER if m in self.combo.modifiers]
        try:
            self._handle = keyboard.add_hotkey("+".join(names + [self.combo.key]), self.on_press)
        except Exception as e:
            return f"gagal dipasang ({e})"
        return None

    def stop(self):
        if self._handle is None:
            return
        try:
            import keyboard
            keyboard.remove_hotkey(self._handle)
        except Exception:
            pass
        self._handle = None


def make_hotkey(combo: Combo, on_press: Callable[[], None], platform: str = sys.platform):
    if platform == "win32":
        return KeyboardHotkey(combo, on_press)
    if platform.startswith("linux"):
        return X11Hotkey(combo, on_press)
    return None


# ───────────────────────── miku.py --trigger ─────────────────────────

def default_runtime_dir() -> Path:
    """Folder pribadi user untuk socket dan kunci: bukan folder repo, yang di partisi NTFS bisa dibaca siapa pun."""
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "MikuVision"
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    return Path(runtime) / "mikuvision" if runtime else Path.home() / ".cache" / "mikuvision"


def trigger_paths(runtime_dir: Path) -> Tuple[str, Path]:
    """Alamat listener dan file kunci di runtime_dir."""
    if sys.platform == "win32":
        digest = hashlib.sha1(str(runtime_dir).encode("utf-8")).hexdigest()[:12]
        address = rf"\\.\pipe\mikuvision-trigger-{digest}"
    else:
        address = str(runtime_dir / "trigger.sock")
    return address, runtime_dir / "trigger.key"


def _socket_is_stale(path: str) -> bool:
    """Socket ditinggal Miku yang crash: file ada tapi tidak ada yang mendengarkan."""
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        probe.connect(path)
        return False
    except ConnectionRefusedError:
        return True
    except OSError:
        return False
    finally:
        probe.close()


def _write_key(path: Path, key: bytes):
    # O_BINARY: tanpa itu Windows mengubah byte \n di kunci acak menjadi \r\n
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(key)
    if sys.platform != "win32":
        os.chmod(path, 0o600)


class TriggerListener:
    """Menerima `miku.py --trigger` dari proses lain milik user yang sama."""

    def __init__(self, on_trigger: Callable[[], None], runtime_dir: Optional[Path] = None):
        self.on_trigger = on_trigger
        self.runtime_dir = runtime_dir or default_runtime_dir()
        self._address, self._key_path = trigger_paths(self.runtime_dir)
        self._key = b""
        self._listener = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> Optional[str]:
        """None bila siap, selain itu alasan gagal."""
        from multiprocessing.connection import Listener

        self.runtime_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        key = os.urandom(32)
        try:
            self._listener = Listener(self._address, authkey=key)
        except OSError:
            if sys.platform == "win32" or not _socket_is_stale(self._address):
                return "Miku lain sudah jalan"
            os.unlink(self._address)
            try:
                self._listener = Listener(self._address, authkey=key)
            except OSError as e:
                return f"socket gagal dibuat ({e})"
        # Kunci ditulis setelah listener jadi, supaya Miku kedua tidak menimpa kunci Miku pertama
        self._key = key
        _write_key(self._key_path, key)

        self._stop.clear()
        self._thread = threading.Thread(target=self._serve, name="miku-trigger", daemon=True)
        self._thread.start()
        return None

    def _serve(self):
        while not self._stop.is_set():
            try:
                conn = self._listener.accept()
            except Exception:  # kunci salah, koneksi putus di tengah autentikasi
                if self._stop.is_set():
                    break
                time.sleep(0.05)
                continue
            with conn:
                if self._stop.is_set():
                    break
                try:
                    # recv_bytes, bukan recv: tanpa pickle, jadi isi pesan tidak pernah dieksekusi
                    if conn.poll(1.0) and conn.recv_bytes(64) == _LISTEN:
                        self.on_trigger()
                        conn.send_bytes(_OK)
                except (EOFError, OSError):
                    pass
                except Exception as e:
                    print(f"[Trigger] Error: {e}")

    def _wake(self):
        from multiprocessing.connection import Client

        try:
            Client(self._address, authkey=self._key).close()
        except Exception:
            pass

    def stop(self):
        if self._listener is None:
            return
        self._stop.set()
        # accept() tidak bisa diinterupsi dari thread lain: bangunkan dengan satu koneksi, di thread
        # sendiri. Bila thread layanan sudah keluar (stop() tepat setelah satu pemicu), koneksi itu
        # menunggu jawaban autentikasi sampai listener ditutup di bawah, bukan menahan stop()
        threading.Thread(target=self._wake, name="miku-trigger-wake", daemon=True).start()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        try:
            self._listener.close()
        except Exception:
            pass
        self._listener = None
        try:
            if self._key_path.read_bytes() == self._key:
                self._key_path.unlink()
        except OSError:
            pass


def send_trigger(runtime_dir: Optional[Path] = None) -> Tuple[bool, str]:
    """Minta Miku yang sedang jalan mendengarkan. Dipanggil oleh `python miku.py --trigger`."""
    from multiprocessing import AuthenticationError
    from multiprocessing.connection import Client

    address, key_path = trigger_paths(runtime_dir or default_runtime_dir())
    not_running = (False, "Miku tidak sedang jalan. Jalankan dulu python miku.py atau run.sh.")
    try:
        key = key_path.read_bytes()
    except OSError:
        return not_running
    try:
        with Client(address, authkey=key) as conn:
            conn.send_bytes(_LISTEN)
            if conn.poll(3.0) and conn.recv_bytes(16) == _OK:
                return True, "Miku mendengarkan."
    except (AuthenticationError, EOFError, OSError):
        return not_running
    return False, "Miku tidak menjawab."


# ───────────────────────── Gabungan untuk miku.py dan gui.py ─────────────────────────

class ListenTriggers:
    """Shortcut global + `miku.py --trigger`; keduanya memanggil on_trigger.

    on_trigger dipanggil dari thread lain dan harus cepat (memasang event atau mengisi antrean).
    Tekan beruntun dalam debounce_sec (termasuk auto-repeat saat tombol ditahan) diabaikan.
    """

    def __init__(self, on_trigger: Callable[[], None], combo: str, hotkey_enabled: bool = True,
                 runtime_dir: Optional[Path] = None, debounce_sec: float = 0.5,
                 platform: str = sys.platform):
        self.on_trigger = on_trigger
        self.combo_text = combo
        self.hotkey_enabled = hotkey_enabled
        self.debounce_sec = debounce_sec
        self.platform = platform
        self.hotkey = None
        self.listener = TriggerListener(self._fire, runtime_dir)
        self.hotkey_active = False
        self._last_fire = float("-inf")
        self._lock = threading.Lock()

    def _fire(self):
        with self._lock:
            now = time.monotonic()
            if now - self._last_fire < self.debounce_sec:
                return
            self._last_fire = now
        try:
            self.on_trigger()
        except Exception as e:
            print(f"[Hotkey] Error: {e}")

    def start(self) -> List[str]:
        """Pasang shortcut dan listener. Kembalikan pesan untuk user."""
        messages = []
        fallback = "pasang `python miku.py --trigger` sebagai shortcut di pengaturan keyboard desktop"
        if self.hotkey_enabled:
            try:
                combo = parse_combo(self.combo_text)
            except ValueError as e:
                combo = None
                messages.append(f"Shortcut tidak dipasang: {e}. Perbaiki WAKE_HOTKEY di config.py.")
            if combo:
                self.hotkey = make_hotkey(combo, self._fire, self.platform)
                error = self.hotkey.start() if self.hotkey else "OS ini belum didukung"
                if error:
                    self.hotkey = None
                    messages.append(f"Shortcut {combo} tidak dipasang: {error}. "
                                    f"Ganti WAKE_HOTKEY di config.py, atau {fallback}.")
                else:
                    self.hotkey_active = True
                    messages.append(f"Shortcut {combo}: mulai bicara dari aplikasi mana pun.")

        error = self.listener.start()
        if error:
            messages.append(f"`--trigger` tidak aktif: {error}.")
        return messages

    def stop(self):
        if self.hotkey:
            self.hotkey.stop()
            self.hotkey = None
        self.hotkey_active = False
        self.listener.stop()
