"""Backend desktop Linux: perintah yang dijalankan diperiksa, tidak ada yang benar-benar dijalankan."""

import re
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core import macro_tools
from core import system_control as sc_module
from core.desktop import linux
from core.desktop.linux import LinuxDesktop
from core.desktop.windowing import WindowInfo
from core.desktop.windows import WindowsDesktop
from core.system_control import SystemControl
from core.tools import registry


def _done(stdout="", returncode=0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


@pytest.fixture
def run(monkeypatch):
    """Ganti _run: catat perintah, balas dengan keluaran yang diatur per program."""
    calls = []
    replies = {}

    def fake_run(cmd):
        calls.append(cmd)
        return replies.get(cmd[0], _done())

    monkeypatch.setattr(linux, "_run", fake_run)
    fake_run.calls, fake_run.replies = calls, replies
    return fake_run


@pytest.fixture
def spawned(monkeypatch):
    calls = []
    monkeypatch.setattr(linux, "_spawn", lambda argv: calls.append(argv) or MagicMock(pid=777))
    return calls


@pytest.fixture
def installed(monkeypatch):
    """Program yang 'terpasang' untuk shutil.which di modul linux."""
    programs = set()
    monkeypatch.setattr(linux.shutil, "which", lambda name: f"/usr/bin/{name}" if name in programs else None)
    return programs


# ── Volume ──

def _audio(installed, run, tool="wpctl"):
    installed.add(tool)
    desktop = LinuxDesktop()
    desktop.init_audio()
    return desktop


def test_wpctl_volume_is_read_and_set(installed, run):
    desktop = _audio(installed, run)
    run.replies["wpctl"] = _done("Volume: 0.55\n")

    assert desktop.get_volume() == 55
    assert desktop.set_volume(30) == (True, "Volume diatur ke 30%")
    # -l 1.0: volume tidak pernah di atas 100%
    assert run.calls[-1] == ["wpctl", "set-volume", "-l", "1.0", "@DEFAULT_AUDIO_SINK@", "0.30"]


def test_wpctl_mute(installed, run):
    desktop = _audio(installed, run)

    assert desktop.set_mute(True) == (True, "Audio dimute")
    assert run.calls[-1] == ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "1"]
    run.replies["wpctl"] = _done("Volume: 0.30 [MUTED]\n")
    assert desktop.is_muted()


def test_pactl_is_the_fallback(installed, run):
    desktop = _audio(installed, run, tool="pactl")
    run.replies["pactl"] = _done("Volume: front-left: 36036 /  55% / -15.58 dB,   front-right: 36036 /  55%\n")

    assert desktop.get_volume() == 55
    desktop.set_volume(30)
    assert run.calls[-1] == ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "30%"]


def test_volume_without_audio_tools_is_reported(installed, run):
    desktop = _audio(installed, run, tool="nothing")

    success, msg = desktop.set_volume(30)

    assert not success and "wpctl/pactl" in msg
    assert run.calls == []


def test_failed_volume_command_is_reported(installed, run):
    desktop = _audio(installed, run)
    run.replies["wpctl"] = _done(returncode=1)

    assert not desktop.set_volume(30)[0]


def test_set_volume_tool_clamps_and_uses_backend(installed, run):
    control = SystemControl(desktop=_audio(installed, run))

    assert control.set_volume("150") == (True, "Volume diatur ke 100%")
    assert run.calls[-1][-1] == "1.00"


# ── Membuka aplikasi ──

def test_first_installed_candidate_is_launched(installed, spawned):
    installed.update({"xed"})   # Mint: tidak ada gnome-text-editor

    success, msg, pid = LinuxDesktop().launch("notepad")

    assert success and pid == 777 and "PID 777" in msg
    assert spawned == [["/usr/bin/xed"]]


def test_specific_app_beats_generic_word(installed, spawned):
    # "Brave web browser" memuat kata umum "browser"; yang dibuka harus Brave
    installed.update({"brave-browser", "firefox"})

    LinuxDesktop().launch("Brave web browser")

    assert spawned == [["/usr/bin/brave-browser"]]


def test_command_arguments_are_kept(installed, spawned):
    installed.add("libreoffice")

    LinuxDesktop().launch("word")

    assert spawned == [["/usr/bin/libreoffice", "--writer"]]


def test_web_fallback_when_app_is_not_installed(installed, spawned):
    installed.add("xdg-open")

    success, msg, pid = LinuxDesktop().launch("whatsapp")

    assert success and pid is None
    assert spawned == [["xdg-open", "https://web.whatsapp.com"]]
    assert "versi web" in msg


def test_missing_app_lists_what_was_tried(installed, spawned):
    success, msg, _ = LinuxDesktop().launch("calculator")

    assert not success
    assert "gnome-calculator" in msg
    assert spawned == []


def test_unknown_app_is_rejected(installed, spawned):
    success, _, _ = LinuxDesktop().launch("zzz-tidak-ada")

    assert not success and spawned == []


def test_default_browser_comes_from_xdg_settings(installed, spawned, run):
    installed.update({"xdg-settings", "gtk-launch"})
    run.replies["xdg-settings"] = _done("brave-browser.desktop\n")

    success, _, pid = LinuxDesktop().launch("browser")

    assert success and pid is None   # gtk-launch hanya peluncur
    assert spawned == [["gtk-launch", "brave-browser"]]


def test_open_website_with_app_name_opens_the_app(installed, spawned, monkeypatch):
    # Kasus nyata: "buka Brave web browser" -> open_website("brave") membuka https://brave
    installed.add("brave-browser")
    browser = MagicMock()
    monkeypatch.setattr(sc_module.webbrowser, "open", browser)

    success, _ = SystemControl(desktop=LinuxDesktop()).open_website("brave")

    assert success
    assert spawned == [["/usr/bin/brave-browser"]]
    browser.assert_not_called()


def test_open_website_unknown_dotless_name_is_not_opened(installed, spawned, monkeypatch):
    browser = MagicMock()
    monkeypatch.setattr(sc_module.webbrowser, "open", browser)

    success, _ = SystemControl(desktop=LinuxDesktop()).open_website("zzz-tidak-ada")

    assert not success
    browser.assert_not_called()


# ── Menutup aplikasi ──

# conftest mengganti keduanya saat test berjalan; ambil kode aslinya saat modul di-import
_ORIGINAL = {"windows_by_pid": LinuxDesktop.windows_by_pid, "close_window": LinuxDesktop.close_window,
             "list_windows": LinuxDesktop.list_windows}


def test_wmctrl_window_list_is_parsed(run, monkeypatch):
    monkeypatch.setattr(LinuxDesktop, "list_windows", _ORIGINAL["list_windows"])
    run.replies["wmctrl"] = _done(
        "0x05400003  0 4321   laptop MikuVision - Hatsune Miku\n"
        "0x04a00007  0 999    laptop Untitled - xed\n"
        "0x04a0000b -1 999    laptop sticky window\n"
        "0x03c00001  0 0      laptop no pid\n"
    )

    found = _ORIGINAL["windows_by_pid"](LinuxDesktop(), {999, 0})

    assert found == {999: ["0x04a00007", "0x04a0000b"], 0: ["0x03c00001"]}
    assert run.calls == [["wmctrl", "-lp"]]


def test_wmctrl_window_titles_and_desktops_are_parsed(run):
    run.replies["wmctrl"] = _done(
        "0x04a00007  0 999    laptop Untitled - xed\n"
        "0x0480000b -1 1200   laptop Desktop\n"
        "0x03c00001  0 0      laptop\n"
    )

    windows = _ORIGINAL["list_windows"](LinuxDesktop())

    assert windows == [WindowInfo("0x04a00007", "Untitled - xed", 999, "0"),
                       WindowInfo("0x0480000b", "Desktop", 1200, "-1"),
                       WindowInfo("0x03c00001", "", 0, "0")]


def test_close_window_is_polite(run):
    _ORIGINAL["close_window"](LinuxDesktop(), "0x04a00007")

    assert run.calls == [["wmctrl", "-ic", "0x04a00007"]]


def _proc(pid, name):
    proc = MagicMock(pid=pid)
    proc.info = {"name": name}
    proc.create_time.return_value = 100.0
    return proc


def test_helper_processes_of_a_windowed_app_are_not_terminated(monkeypatch, installed):
    # Brave: proses utama punya jendela, proses renderer tidak
    installed.add("brave-browser")
    main, renderer = _proc(10, "brave"), _proc(11, "brave")
    control = SystemControl(desktop=LinuxDesktop())
    closed = []
    monkeypatch.setattr(control.desktop, "windows_by_pid", lambda pids: {10: ["0x01"]})
    monkeypatch.setattr(control.desktop, "close_window", closed.append)
    monkeypatch.setattr(sc_module.psutil, "process_iter", lambda attrs: [main, renderer])
    monkeypatch.setattr(sc_module.psutil, "wait_procs", lambda procs, timeout: (list(procs), []))

    success, _ = control.close_application("brave")

    assert success and closed == ["0x01"]
    renderer.terminate.assert_not_called()
    main.terminate.assert_not_called()


def test_close_matches_the_installed_program_name(monkeypatch):
    # "kalkulator" -> gnome-calculator; nama lain tidak tersentuh
    calc, other = _proc(20, "gnome-calculator"), _proc(21, "gnome-calendar")
    control = SystemControl(desktop=LinuxDesktop())
    monkeypatch.setattr(sc_module.psutil, "process_iter", lambda attrs: [calc, other])
    monkeypatch.setattr(sc_module.psutil, "wait_procs", lambda procs, timeout: (list(procs), []))

    success, _ = control.close_application("kalkulator")

    assert success
    calc.terminate.assert_called_once()
    other.terminate.assert_not_called()


def test_terminal_is_protected(monkeypatch):
    # Satu gnome-terminal-server memegang semua terminal, termasuk yang menjalankan Miku
    proc = _proc(30, "gnome-terminal-server")
    monkeypatch.setattr(sc_module.psutil, "process_iter", lambda attrs: [proc])

    success, msg = SystemControl(desktop=LinuxDesktop()).close_application("terminal")

    assert not success and "dilindungi" in msg
    proc.terminate.assert_not_called()


# ── File, folder, media, keyboard ──

def test_open_path_uses_xdg_open(installed, spawned):
    installed.add("xdg-open")

    LinuxDesktop().open_path("/home/miku/Desktop/Miku_Documents/catatan.docx")

    assert spawned == [["xdg-open", "/home/miku/Desktop/Miku_Documents/catatan.docx"]]


def test_open_path_without_xdg_open_raises(installed, spawned):
    with pytest.raises(OSError):
        LinuxDesktop().open_path("/tmp/x")


def test_user_dir_follows_xdg(installed, run):
    installed.add("xdg-user-dir")
    run.replies["xdg-user-dir"] = _done("/home/miku/Unduhan\n")

    assert linux.user_dir("downloads") == Path("/home/miku/Unduhan")
    assert run.calls == [["xdg-user-dir", "DOWNLOAD"]]


def test_user_dir_falls_back_when_not_configured(installed, run):
    installed.add("xdg-user-dir")
    run.replies["xdg-user-dir"] = _done(str(Path.home()) + "\n")   # tidak dikonfigurasi

    assert linux.user_dir("music") == Path.home() / "Music"


def test_media_uses_playerctl(installed, run):
    installed.add("playerctl")

    assert LinuxDesktop().media("next") == (True, "")
    assert run.calls == [["playerctl", "next"]]


def test_media_falls_back_to_media_keys(installed, run, monkeypatch):
    installed.add("playerctl")
    run.replies["playerctl"] = _done(returncode=1)   # "No players found"
    keys = MagicMock()
    monkeypatch.setattr(linux, "pyautogui", keys)

    assert LinuxDesktop().media("play_pause") == (True, "")
    keys.press.assert_called_once_with("playpause")


def test_media_control_tool_messages(installed, run):
    installed.add("playerctl")

    success, msg = SystemControl(desktop=LinuxDesktop()).media_control("pause")

    assert success and "Play/Pause" in msg
    assert run.calls == [["playerctl", "play-pause"]]


def test_media_control_accepts_every_action_its_schema_names(installed, run):
    """Nilai action_type yang disebut skema untuk LLM semuanya dikenali fungsinya."""
    installed.add("playerctl")
    schema = registry.get_tool("media_control").to_openai_schema()["function"]
    named = re.findall(r"'(\w+)'", schema["parameters"]["properties"]["action_type"]["description"])

    assert named == ["play", "pause", "next", "prev"]
    control = SystemControl(desktop=LinuxDesktop())
    assert all(control.media_control(action)[0] for action in named)
    assert run.calls == [["playerctl", "play-pause"]] * 2 + [["playerctl", "next"], ["playerctl", "previous"]]
    # Tanpa frasa ini qwen3:4b-instruct bertanya "lagu apa?" (bench_skills.py regression)
    assert "次の曲" in schema["description"]


def test_japanese_text_is_pasted_from_clipboard(installed, monkeypatch):
    installed.add("xclip")
    copied, keys = [], MagicMock()
    monkeypatch.setattr(linux, "_copy_to_clipboard", copied.append)
    monkeypatch.setattr(linux, "pyautogui", keys)

    success, _ = LinuxDesktop().type_text("こんにちは")

    assert success and copied == ["こんにちは"]
    keys.hotkey.assert_called_once_with("ctrl", "v")
    keys.typewrite.assert_not_called()


def test_japanese_text_without_xclip_is_reported(installed):
    success, msg = LinuxDesktop().type_text("こんにちは")

    assert not success and "xclip" in msg


def test_uri_handler_check(installed, run):
    installed.add("xdg-mime")
    run.replies["xdg-mime"] = _done("\n")
    assert not LinuxDesktop().has_uri_handler("tg")

    run.replies["xdg-mime"] = _done("org.telegram.desktop.desktop\n")
    assert LinuxDesktop().has_uri_handler("tg")


def test_wayland_is_warned(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert "X11" in LinuxDesktop().session_warning()
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    assert LinuxDesktop().session_warning() is None


# ── Dokumen & pesan ──

def test_saved_document_is_not_a_failure_when_it_cannot_be_opened(monkeypatch, tmp_path):
    # Sebelumnya os.startfile tidak ada di Linux, dokumen tersimpan tapi dilaporkan "Gagal..."
    monkeypatch.setattr(macro_tools, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(macro_tools.desktop.current, "open_path",
                        MagicMock(side_effect=OSError("xdg-open tidak ditemukan")))
    document = MagicMock()
    monkeypatch.setattr(macro_tools, "Document", lambda *a: document, raising=False)

    result = macro_tools.MacroTools().create_word_document("Catatan", "Judul\nIsi")

    assert not result.startswith("Gagal")
    assert "tidak bisa dibuka otomatis" in result
    document.save.assert_called_once()


def test_linux_whatsapp_opens_web_draft_without_pressing_enter(monkeypatch, tmp_path):
    contacts = tmp_path / "contacts_db.json"
    contacts.write_text('{"Budi Santoso": "628123"}', encoding="utf-8")
    monkeypatch.setattr(macro_tools, "CONTACTS_DB_PATH", contacts)
    monkeypatch.setattr(macro_tools.desktop, "current", LinuxDesktop())
    opened, keys = MagicMock(), MagicMock()
    monkeypatch.setattr(macro_tools.webbrowser, "open", opened)
    monkeypatch.setattr(macro_tools, "pyautogui", keys)

    result = macro_tools.MacroTools().send_whatsapp_message("budi", "Halo")

    opened.assert_called_once_with("https://web.whatsapp.com/send?phone=628123&text=Halo")
    keys.press.assert_not_called()
    assert "belum terkirim" in result


def test_telegram_without_desktop_app_is_reported(monkeypatch, installed, run):
    installed.add("xdg-mime")
    monkeypatch.setattr(macro_tools.desktop, "current", LinuxDesktop())

    result = macro_tools.MacroTools().send_telegram_message("@miku", "Halo")

    assert result.startswith("Gagal") and "Telegram Desktop" in result


# ── Windows: urutan whitelist ──

def test_windows_brave_is_not_matched_as_generic_browser(monkeypatch):
    launched = []
    monkeypatch.setattr("core.desktop.windows.os.startfile", launched.append, raising=False)
    monkeypatch.setattr("core.desktop.windows.shutil.which", lambda name: None)

    WindowsDesktop().launch("Brave web browser")

    assert launched == ["brave"]
