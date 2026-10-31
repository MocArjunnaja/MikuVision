"""Shortcut "mulai bicara" (T1): parse_combo, backend X11/Windows, `miku.py --trigger`, dan penyambungannya."""

import queue
import socket
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from core import hotkey
from core.hotkey import Combo, ListenTriggers, TriggerListener, parse_combo, send_trigger, trigger_paths

KEYCODE_M = 58
CTRL_SHIFT = 4 | 1
# Ctrl+Shift, + CapsLock, + NumLock, + keduanya
CTRL_SHIFT_VARIANTS = {CTRL_SHIFT, CTRL_SHIFT | 2, CTRL_SHIFT | 16, CTRL_SHIFT | 2 | 16}


# ───────────────────────── parse_combo ─────────────────────────

def test_parse_combo():
    combo = parse_combo("ctrl+shift+m")

    assert combo == Combo(frozenset({"ctrl", "shift"}), "m")
    assert str(combo) == "Ctrl+Shift+M"


def test_parse_combo_ignores_case_spaces_and_order_and_accepts_aliases():
    assert parse_combo(" Shift + CONTROL + M ") == parse_combo("ctrl+shift+m")
    assert str(parse_combo("win+alt+f9")) == "Alt+Super+F9"
    assert parse_combo("f9") == Combo(frozenset(), "f9")


@pytest.mark.parametrize("text", [
    "", "ctrl+", "ctrl++m", "ctrl+shift",  # tidak lengkap / tanpa tombol
    "hyper+m",                             # modifier tidak dikenal
    "ctrl+mm", "ctrl+f25", "ctrl+é",       # tombol tidak didukung
    "m", "shift+m",                        # akan menelan ketikan biasa
])
def test_parse_combo_rejects(text):
    with pytest.raises(ValueError):
        parse_combo(text)


# ───────────────────────── Backend X11 ─────────────────────────

class FakeRoot:
    def __init__(self, display):
        self.display = display

    def grab_key(self, keycode, modifiers, owner_events, pointer_mode, keyboard_mode, onerror=None):
        if modifiers in self.display.taken:
            onerror(SimpleNamespace(name="BadAccess"), None)
        else:
            self.display.grabs.add((keycode, modifiers))

    def ungrab_key(self, keycode, modifiers):
        self.display.grabs.discard((keycode, modifiers))


class FakeDisplay:
    def __init__(self, taken=()):
        self.grabs = set()
        self.taken = set(taken)
        self.events = queue.Queue()
        self.closed = False
        self.root = FakeRoot(self)

    def screen(self):
        return SimpleNamespace(root=self.root)

    def keysym_to_keycode(self, keysym):
        return KEYCODE_M if keysym == ord("m") else 0

    def sync(self):
        pass

    def pending_events(self):
        return self.events.qsize()

    def next_event(self):
        return self.events.get_nowait()

    def close(self):
        self.closed = True


@pytest.fixture
def x11(monkeypatch):
    display = FakeDisplay()
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.setattr(hotkey, "_open_display", lambda: display)
    monkeypatch.setattr(hotkey, "_keysym", lambda key: ord(key) if len(key) == 1 else 0)
    return display


def test_x11_grabs_all_lock_variants_and_fires_on_key_press(x11):
    pressed = threading.Event()
    key = hotkey.X11Hotkey(parse_combo("ctrl+shift+m"), pressed.set)

    assert key.start() is None
    assert x11.grabs == {(KEYCODE_M, mask) for mask in CTRL_SHIFT_VARIANTS}

    x11.events.put(SimpleNamespace(type=3, detail=KEYCODE_M))  # KeyRelease: diabaikan
    x11.events.put(SimpleNamespace(type=2, detail=KEYCODE_M))  # KeyPress
    assert pressed.wait(1.0)

    key.stop()
    assert x11.grabs == set()
    assert x11.closed


def test_x11_combo_taken_by_other_app_releases_everything(x11):
    x11.taken = {CTRL_SHIFT | 16}  # aplikasi lain memegang Ctrl+Shift+M dengan NumLock
    key = hotkey.X11Hotkey(parse_combo("ctrl+shift+m"), lambda: None)

    assert key.start() == "sudah dipakai aplikasi lain"
    assert x11.grabs == set()
    assert x11.closed
    assert key._thread is None


def test_x11_key_missing_from_keyboard(x11):
    key = hotkey.X11Hotkey(parse_combo("ctrl+f9"), lambda: None)

    assert "tidak ada di keyboard" in key.start()
    assert x11.closed


def test_x11_not_attempted_on_wayland_or_without_display(monkeypatch):
    # conftest membuat _open_display gagal keras: kedua kasus tidak boleh menyentuhnya
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert "Wayland" in hotkey.X11Hotkey(parse_combo("ctrl+shift+m"), lambda: None).start()

    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.delenv("DISPLAY")
    assert "DISPLAY" in hotkey.X11Hotkey(parse_combo("ctrl+shift+m"), lambda: None).start()


# ───────────────────────── Backend Windows ─────────────────────────

def test_windows_backend_uses_keyboard_library(monkeypatch):
    fake = MagicMock()
    fake.add_hotkey.return_value = "handle"
    monkeypatch.setitem(sys.modules, "keyboard", fake)
    callback = lambda: None  # noqa: E731
    key = hotkey.make_hotkey(parse_combo("super+shift+m"), callback, platform="win32")

    assert key.start() is None
    fake.add_hotkey.assert_called_once_with("shift+windows+m", callback)

    key.stop()
    fake.remove_hotkey.assert_called_once_with("handle")


def test_windows_backend_reports_failure(monkeypatch):
    fake = MagicMock()
    fake.add_hotkey.side_effect = ValueError("bad")
    monkeypatch.setitem(sys.modules, "keyboard", fake)

    error = hotkey.make_hotkey(parse_combo("ctrl+shift+m"), lambda: None, platform="win32").start()

    assert "gagal dipasang" in error


# ───────────────────────── miku.py --trigger ─────────────────────────

@pytest.fixture
def listener(tmp_path):
    calls = []
    started = []

    def start(on_trigger=lambda: calls.append(1)):
        item = TriggerListener(on_trigger, tmp_path)
        assert item.start() is None
        started.append(item)
        return item

    yield SimpleNamespace(start=start, calls=calls, dir=tmp_path)
    for item in started:
        item.stop()


def test_trigger_round_trip(listener):
    item = listener.start()

    assert send_trigger(listener.dir) == (True, "Miku mendengarkan.")
    assert listener.calls == [1]

    item.stop()
    address, key_path = trigger_paths(listener.dir)
    assert not key_path.exists()
    if sys.platform != "win32":
        assert not (listener.dir / "trigger.sock").exists()
    ok, message = send_trigger(listener.dir)
    assert not ok and "tidak sedang jalan" in message


def test_trigger_without_running_miku(tmp_path):
    ok, message = send_trigger(tmp_path)

    assert not ok and "tidak sedang jalan" in message


def test_trigger_with_wrong_key_is_rejected_and_listener_keeps_serving(listener):
    listener.start()
    _, key_path = trigger_paths(listener.dir)
    real_key = key_path.read_bytes()

    key_path.write_bytes(b"x" * 32)
    assert send_trigger(listener.dir)[0] is False
    assert listener.calls == []

    key_path.write_bytes(real_key)
    assert send_trigger(listener.dir)[0] is True
    assert listener.calls == [1]


def test_trigger_callback_error_does_not_kill_the_listener(listener):
    def broken():
        listener.calls.append(1)
        raise RuntimeError("rusak")

    item = listener.start(broken)

    assert send_trigger(listener.dir)[0] is False
    assert send_trigger(listener.dir)[0] is False
    assert listener.calls == [1, 1]

    started = time.monotonic()
    item.stop()  # tidak menggantung menunggu thread yang sudah mati
    assert time.monotonic() - started < 2


def test_stop_right_after_a_trigger_does_not_hang(listener):
    """stop() tepat setelah satu pemicu: thread layanan sudah keluar sebelum accept() berikutnya."""
    from multiprocessing.connection import Client

    item = listener.start()
    item._stop.set()
    address, key_path = trigger_paths(listener.dir)
    Client(address, authkey=key_path.read_bytes()).close()  # thread melihat _stop lalu keluar
    item._thread.join(2.0)
    assert not item._thread.is_alive()

    started = time.monotonic()
    item.stop()
    assert time.monotonic() - started < 3


def test_trigger_ignores_other_messages(listener):
    from multiprocessing.connection import Client

    listener.start()
    address, key_path = trigger_paths(listener.dir)
    with Client(address, authkey=key_path.read_bytes()) as conn:
        conn.send_bytes(b"rm -rf ~")
        with pytest.raises(EOFError):  # ditutup tanpa jawaban "ok"
            conn.recv_bytes()

    assert listener.calls == []


def test_second_miku_does_not_steal_the_trigger(listener):
    listener.start()
    second_calls = []

    second = TriggerListener(lambda: second_calls.append(1), listener.dir)
    assert second.start() == "Miku lain sudah jalan"
    second.stop()

    assert send_trigger(listener.dir)[0] is True
    assert listener.calls == [1] and second_calls == []


@pytest.mark.skipif(sys.platform == "win32", reason="named pipe hilang bersama prosesnya")
def test_stale_socket_from_crashed_miku_is_replaced(listener):
    path = str(listener.dir / "trigger.sock")
    stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stale.bind(path)
    stale.close()  # file socket tertinggal tanpa pendengar

    listener.start()

    assert send_trigger(listener.dir)[0] is True


def test_trigger_key_is_written_byte_for_byte(tmp_path):
    # Byte \n dan \r di kunci acak tidak boleh diterjemahkan (mode teks di Windows)
    path = tmp_path / "trigger.key"
    path.write_bytes(b"lama, lebih panjang dari kunci baru" * 2)

    hotkey._write_key(path, b"\n\r\x00" * 8)

    assert path.read_bytes() == b"\n\r\x00" * 8


@pytest.mark.skipif(sys.platform == "win32", reason="izin file POSIX")
def test_trigger_key_is_private(listener):
    listener.start()
    _, key_path = trigger_paths(listener.dir)

    assert key_path.stat().st_mode & 0o777 == 0o600


# ───────────────────────── ListenTriggers ─────────────────────────

def test_listen_triggers_debounce(monkeypatch, tmp_path):
    now = [100.0]
    monkeypatch.setattr(hotkey.time, "monotonic", lambda: now[0])
    calls = []
    triggers = ListenTriggers(lambda: calls.append(now[0]), "ctrl+shift+m", runtime_dir=tmp_path)

    triggers._fire()
    now[0] += 0.25  # auto-repeat / tekan dobel
    triggers._fire()
    now[0] += 0.5
    triggers._fire()

    assert calls == [100.0, 100.75]


def test_listen_triggers_start_and_stop(x11, tmp_path):
    pressed = threading.Event()
    triggers = ListenTriggers(pressed.set, "ctrl+shift+m", runtime_dir=tmp_path, platform="linux")

    assert triggers.start() == ["Shortcut Ctrl+Shift+M: mulai bicara dari aplikasi mana pun."]
    assert triggers.hotkey_active
    assert send_trigger(tmp_path)[0] is True
    assert pressed.is_set()

    triggers.stop()
    assert x11.grabs == set()
    assert send_trigger(tmp_path)[0] is False


def test_listen_triggers_explain_failures(x11, tmp_path):
    x11.taken = {CTRL_SHIFT}
    messages = ListenTriggers(lambda: None, "ctrl+shift+m", runtime_dir=tmp_path, platform="linux").start()
    assert "sudah dipakai aplikasi lain" in messages[0] and "--trigger" in messages[0]

    messages = ListenTriggers(lambda: None, "shift+m", runtime_dir=tmp_path / "b", platform="linux").start()
    assert "WAKE_HOTKEY" in messages[0]

    triggers = ListenTriggers(lambda: None, "ctrl+shift+m", hotkey_enabled=False, runtime_dir=tmp_path / "c")
    assert triggers.start() == []
    assert not triggers.hotkey_active
    triggers.stop()


# ───────────────────────── Penyambungan ─────────────────────────

class FakeTriggers:
    """Pengganti ListenTriggers di miku.py: memicu satu interaksi sesudah loop mulai menunggu."""

    fire = None

    def __init__(self, on_trigger, combo, hotkey_enabled=True):
        self.on_trigger = on_trigger
        self.hotkey_active = False
        self.stopped = False

    def start(self):
        threading.Timer(0.2, FakeTriggers.fire or self.on_trigger).start()
        return []

    def stop(self):
        self.stopped = True


def _import_miku(monkeypatch, tmp_path):
    # Import pertama core.macro_tools mencari folder Desktop lewat xdg-user-dir
    from core import desktop
    monkeypatch.setattr(desktop, "user_dir", lambda key: tmp_path)
    import miku
    return miku


# Import miku.py membungkus ulang stdout/stdin untuk konsol Windows, yang bentrok dengan capture pytest
voice_mode = pytest.mark.skipif(sys.platform == "win32", reason="miku.py membungkus stdout di Windows")


def _run_voice_mode(monkeypatch, tmp_path, fire=None):
    miku = _import_miku(monkeypatch, tmp_path)

    monkeypatch.setattr(miku, "ListenTriggers", FakeTriggers)
    monkeypatch.setattr(FakeTriggers, "fire", fire)
    avatar = MagicMock()
    monkeypatch.setattr(miku, "initialize_avatar_window", lambda *a, **k: avatar)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)

    cli = miku.MikuCLI()
    cli.ai_brain = MagicMock()
    cli.ai_brain.get_greeting.return_value = ("Halo", "happy")
    cli.voice_output = MagicMock()
    cli.voice_input = MagicMock()
    cli.system_control = MagicMock()

    def listen(**kwargs):
        cli._quit_event = True
        return np.array([])

    cli.voice_input.listen_until_silence.side_effect = listen
    if fire is not None:
        FakeTriggers.fire = lambda: fire(cli)
    cli.chat_voice_mode()
    return cli, avatar


@voice_mode
def test_voice_mode_shortcut_listens_without_spoken_greeting(monkeypatch, tmp_path):
    cli, avatar = _run_voice_mode(monkeypatch, tmp_path)

    cli.voice_input.listen_until_silence.assert_called_once()
    spoken = [c.args[0] for c in cli.voice_output.speak.call_args_list]
    assert spoken == ["Halo"]  # hanya sapaan awal, tanpa 「はい、何でしょうか？」
    avatar.set_emotion.assert_any_call("listening")


@voice_mode
def test_voice_mode_mascot_drag_still_answers_first(monkeypatch, tmp_path):
    cli, _ = _run_voice_mode(monkeypatch, tmp_path, fire=lambda cli: cli._on_avatar_interacted())

    cli.voice_input.listen_until_silence.assert_called_once()
    spoken = [c.args[0] for c in cli.voice_output.speak.call_args_list]
    assert spoken == ["Halo", "はい、何でしょうか？"]


@voice_mode
def test_voice_mode_cleanup_releases_the_shortcut(monkeypatch, tmp_path):
    cli = _import_miku(monkeypatch, tmp_path).MikuCLI()
    cli.triggers = FakeTriggers(lambda: None, "ctrl+shift+m")
    cli.cleanup()

    assert cli.triggers.stopped


real_customtkinter = pytest.mark.skipif(
    isinstance(sys.modules.get("customtkinter"), MagicMock), reason="butuh customtkinter asli")


@real_customtkinter
def test_gui_shortcut_only_queues_then_toggles_recording():
    import gui

    app = SimpleNamespace(message_queue=queue.Queue(), is_listening=False,
                          voice_output=SimpleNamespace(is_speaking=False),
                          _on_voice_press=MagicMock(), _on_voice_release=MagicMock())

    # Dari thread shortcut: hanya mengisi antrean (Tk tidak disentuh)
    gui.MikuGUIv4._on_listen_trigger(app)
    assert app.message_queue.get_nowait() == ("shortcut", None)
    app._on_voice_press.assert_not_called()

    # Di main thread: tekan pertama mulai merekam, tekan kedua selesai
    gui.MikuGUIv4._on_shortcut(app)
    app._on_voice_press.assert_called_once()
    app.is_listening = True
    gui.MikuGUIv4._on_shortcut(app)
    app._on_voice_release.assert_called_once()

    # Saat Miku sedang bicara, shortcut tidak mulai merekam
    app.is_listening = False
    app.voice_output.is_speaking = True
    gui.MikuGUIv4._on_shortcut(app)
    app._on_voice_press.assert_called_once()
