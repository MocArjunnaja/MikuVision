"""
Test setup: stub dependency berat (audio, GUI, Windows API) agar logika inti
bisa dites tanpa hardware dan tanpa Ollama.
"""

import http.server
import importlib
import sys
import threading
import types
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Daftarkan package `core` tanpa menjalankan core/__init__.py,
# yang meng-import seluruh modul suara/GUI.
_core_pkg = types.ModuleType("core")
_core_pkg.__path__ = [str(ROOT / "core")]
sys.modules.setdefault("core", _core_pkg)

for _name in [
    "torch",
    "ollama",
    "comtypes",
    "pycaw",
    "pycaw.pycaw",
    "pyautogui",
    "pygetwindow",
    "keyboard",
]:
    sys.modules.setdefault(_name, MagicMock())

# scipy >= 1.17 memanggil issubclass(x, torch.Tensor) bila torch ada di sys.modules;
# atribut MagicMock bukan class sehingga import librosa/MeloTTS gagal.
if isinstance(sys.modules["torch"], MagicMock):
    sys.modules["torch"].Tensor = type("Tensor", (), {})

# Paket suara/GUI/Office: dipakai bila terpasang (venv aplikasi), di-stub bila tidak (CI dengan
# paket minimal). Logika yang dites tidak bergantung pada isinya; sounddevice di Linux juga
# butuh libportaudio2 dari sistem.
for _name in [
    "sounddevice", "soundfile", "faster_whisper", "webrtcvad", "noisereduce",
    "melo", "melo.api", "customtkinter", "pygame", "docx", "pptx",
]:
    try:
        importlib.import_module(_name)
    except Exception:
        sys.modules[_name] = MagicMock()


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _no_real_desktop(monkeypatch):
    """Test tidak boleh menemukan/menutup jendela sungguhan, mengubah volume, atau membuka aplikasi.

    Backend Windows dan Linux sama-sama dites di OS mana pun, dengan jendela palsu.
    Perintah desktop Linux (wpctl, wmctrl, xdg-open, ...) gagal keras kecuali test menggantinya.
    """
    from core.desktop import linux, windows
    for backend in (linux.LinuxDesktop, windows.WindowsDesktop):
        monkeypatch.setattr(backend, "windows_by_pid", lambda self, pids: {})
        monkeypatch.setattr(backend, "close_window", lambda self, window: None)
        monkeypatch.setattr(backend, "can_close_windows", property(lambda self: True))
        # Menu aplikasi sistem kosong; test yang butuh mengisinya sendiri
        monkeypatch.setattr(backend, "list_installed_apps", lambda self: [])

    def refuse(*args, **kwargs):
        raise AssertionError(f"Test menjalankan perintah desktop sungguhan: {args}")

    for name in ("_run", "_spawn", "_start", "_copy_to_clipboard"):
        monkeypatch.setattr(linux, name, refuse)
    monkeypatch.setattr(windows, "_start_apps", refuse)


@pytest.fixture(autouse=True)
def _no_real_hotkey(monkeypatch, tmp_path):
    """Test tidak boleh memasang shortcut global sungguhan atau memakai socket --trigger milik Miku yang jalan."""
    from core import hotkey

    def refuse():
        raise AssertionError("Test membuka koneksi X11 atau memanggil RegisterHotKey sungguhan untuk shortcut")

    monkeypatch.setattr(hotkey, "_open_display", refuse)
    monkeypatch.setattr(hotkey, "_user32", refuse)
    monkeypatch.setattr(hotkey, "default_runtime_dir", lambda: tmp_path / "runtime")


@pytest.fixture(autouse=True)
def _no_real_screen(monkeypatch):
    """Test tidak boleh mengambil screenshot, membaca pohon aksesibilitas, atau memanggil model visi."""
    from core.vision import capture, model, ui_tree

    def refuse(*args, **kwargs):
        raise AssertionError("Test membaca layar atau memanggil model visi sungguhan")

    for module, name in ((capture, "_grab"), (capture, "_x11_active_window"), (capture, "_win32_active_window"),
                         (ui_tree, "_run_helper"), (model, "_client")):
        monkeypatch.setattr(module, name, refuse)


@pytest.fixture(autouse=True)
def _isolated_app_cache(monkeypatch, tmp_path):
    """Test tidak boleh membaca/menulis cache aplikasi asli di data/."""
    from core import system_control
    monkeypatch.setattr(system_control, "APP_CACHE_FILE", tmp_path / "app_cache.json")


@pytest.fixture(autouse=True)
def _isolated_long_term_memory(monkeypatch, tmp_path):
    """Test tidak boleh membaca/menulis memori jangka panjang asli di data/."""
    from core import long_term_memory
    monkeypatch.setattr(long_term_memory, "store", long_term_memory.LongTermMemory(tmp_path / "ltm.json"))


@pytest.fixture(autouse=True)
def _isolated_user_skills(monkeypatch, tmp_path):
    """Test hanya melihat contoh skill di repo, bukan skill milik user di data/skills/."""
    from core import user_skills
    monkeypatch.setattr(user_skills, "USER_SKILLS_DIR", tmp_path / "user_skills")


class _ReleaseHandler(http.server.BaseHTTPRequestHandler):
    """Aset rilis dari memori, dengan HTTP Range seperti GitHub (bisa dimatikan lewat server.ranges)."""

    def do_GET(self):
        server = self.server
        server.requests.append((self.path, self.headers.get("Range")))
        data = server.files.get(self.path.lstrip("/"))
        if data is None:
            self.send_error(404)
            return
        start = 0
        requested = self.headers.get("Range")
        if requested and server.ranges:
            start = int(requested.split("=", 1)[1].split("-", 1)[0])
            if start >= len(data):
                self.send_response(416)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}")
        else:
            self.send_response(200)
        self.send_header("Content-Length", str(len(data) - start))
        if self.path.lstrip("/") in server.types:
            self.send_header("Content-Type", server.types[self.path.lstrip("/")])
        self.end_headers()
        self.wfile.write(data[start:])

    def log_message(self, *args):
        pass


@pytest.fixture
def release_server():
    """Server HTTP lokal: .files {nama: byte}, .types {nama: Content-Type}, .ranges, .requests [(path, Range)],
    .url (berakhiran /)."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _ReleaseHandler)
    server.files, server.types, server.ranges, server.requests = {}, {}, True, []
    server.url = f"http://127.0.0.1:{server.server_port}/"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()
    server.server_close()
