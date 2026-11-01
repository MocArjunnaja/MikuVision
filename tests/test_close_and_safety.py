"""Menutup tab/jendela dan batas aman tool: tidak ada jendela, tab, atau file sungguhan yang disentuh."""

import json
import sys
import types
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import config
from core import macro_tools, safety
from core import system_control as sc_module
from core.confirmation import requires_confirmation
from core.desktop.linux import LinuxDesktop
from core.desktop.windowing import WindowInfo
from core.desktop.windows import WindowsDesktop
from core.skills import select_skills, tool_names
from core.system_control import SystemControl
from core.tools import registry

# conftest mengganti fungsi-fungsi ini saat test berjalan; ambil kode aslinya saat modul di-import
_ORIGINAL = {"windows_list": WindowsDesktop.list_windows, "cdp_tabs": SystemControl._cdp_tabs,
             "cdp_close": SystemControl._cdp_close}

WINDOWS = sys.platform == "win32"


# ── Path yang dilindungi ──

def _protected_paths(home: Path):
    if WINDOWS:
        return [Path("C:/"), Path("C:/Windows/System32/drivers/etc/hosts"), Path("C:/Program Files/App/app.exe"),
                Path("C:/ProgramData/x.txt"), home, home.parent,
                home / "AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup/evil.bat",
                home / ".ssh/id_rsa", config.BASE_DIR / "config.py", config.BASE_DIR]
    return [Path("/"), Path("/usr/bin/python3"), Path("/etc/passwd"), Path("/boot/vmlinuz"), home, home.parent,
            home / ".bashrc", home / ".config/autostart/evil.desktop", config.BASE_DIR / "config.py"]


def test_system_and_app_locations_are_protected():
    home = Path.home()
    for path in _protected_paths(home):
        assert safety.protected_path_reason(path) is not None, path


def test_user_folders_and_temp_are_not_protected(tmp_path):
    home = Path.home()
    for path in (home / "Desktop" / "Miku_Documents" / "laporan.docx", home / "Documents" / "a.txt",
                 tmp_path / "a.docx"):
        assert safety.protected_path_reason(path) is None, path


@pytest.mark.parametrize("name, expected", [
    ("Hukum_Newton", "Hukum_Newton.docx"),
    ("laporan.docx", "laporan.docx"),
    ("C:\\Windows\\win.ini", "win.ini.docx"),
    ("../../.bashrc", "bashrc.docx"),
    ("/etc/passwd", "passwd.docx"),
    ("C:laporan", "C_laporan.docx"),
    ("CON", "Miku_Dokumen.docx"),
    ("", "Miku_Dokumen.docx"),
    ("...", "Miku_Dokumen.docx"),
])
def test_safe_filename_never_has_folders(name, expected):
    assert safety.safe_filename(name, ".docx") == expected


def test_path_in_folder_stays_in_folder(tmp_path):
    for name in ("../../evil", "C:\\Windows\\System32\\evil", "/etc/evil", "sub/../../evil"):
        path = safety.path_in_folder(tmp_path, name, ".docx")
        assert path.parent == tmp_path


def test_path_in_folder_refuses_protected_folder():
    with pytest.raises(ValueError):
        safety.path_in_folder(config.BASE_DIR, "config", ".py")


def test_unused_path_never_returns_existing_file(tmp_path):
    first = tmp_path / "a.docx"
    first.write_bytes(b"lama")
    (tmp_path / "a (2).docx").write_bytes(b"lama")

    assert safety.unused_path(first) == tmp_path / "a (3).docx"
    assert safety.unused_path(tmp_path / "b.docx") == tmp_path / "b.docx"


# ── Dokumen Office ──

@pytest.fixture
def documents(monkeypatch, tmp_path):
    """OUTPUT_DIR sementara, dokumen palsu yang ditulis ke disk, dan tidak ada yang dibuka."""
    class FakeDocument:
        def __init__(self, path=None):
            self.paragraphs = []

        def add_paragraph(self, text=""):
            self.paragraphs.append(text)

        def save(self, path):
            Path(path).write_text("\n".join(self.paragraphs), encoding="utf-8")

    monkeypatch.setattr(macro_tools, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(macro_tools, "Document", FakeDocument, raising=False)
    monkeypatch.setattr(macro_tools, "_open_saved", lambda path: "")
    return tmp_path


def test_word_document_with_folder_name_stays_in_output_dir(documents):
    message = macro_tools.MacroTools().create_word_document("..\\..\\Windows\\win", "isi")

    assert (documents / "win.docx").read_text(encoding="utf-8") == "isi"
    assert str(documents / "win.docx") in message
    assert [p.name for p in documents.iterdir()] == ["win.docx"]


def test_word_document_never_overwrites_existing_file(documents):
    (documents / "laporan.docx").write_text("punya user", encoding="utf-8")

    message = macro_tools.MacroTools().create_word_document("laporan", "baru")

    assert (documents / "laporan.docx").read_text(encoding="utf-8") == "punya user"
    assert (documents / "laporan (2).docx").read_text(encoding="utf-8") == "baru"
    assert "laporan (2).docx" in message


def test_edit_word_document_cannot_reach_outside_output_dir(documents, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "rahasia.docx"
    outside.write_text("jangan diubah", encoding="utf-8")

    message = macro_tools.MacroTools().edit_word_document(str(outside), "delete", target_text="jangan")

    assert "tidak ditemukan" in message
    assert outside.read_text(encoding="utf-8") == "jangan diubah"


# ── Konfirmasi dan log aksi ──

@pytest.mark.parametrize("action, params", [
    ("close_application", {"app_name": "notepad"}),
    ("close_window", {"title": "laporan"}),
    ("close_browser_tab", {"match": "youtube"}),
    ("edit_word_document", {"filename": "a", "action": "delete", "target_text": "x"}),
])
def test_destructive_actions_need_confirmation(action, params):
    assert requires_confirmation(action, params)


def test_appending_to_document_needs_no_confirmation():
    assert not requires_confirmation("edit_word_document", {"filename": "a", "action": "append", "new_text": "x"})


def _read_action_log():
    files = list(sc_module.ACTION_LOG.log_dir.glob("actions_*.jsonl"))
    if not files:
        return []
    return [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]


def test_denied_close_is_not_run_and_is_logged(monkeypatch):
    control = SystemControl(desktop=WindowsDesktop())
    executed = MagicMock()
    monkeypatch.setattr(sc_module.registry, "execute", executed)
    control.confirm_callback = lambda summary: False

    success, _ = control.execute_action("close_browser_tab", {"match": "youtube"})

    assert not success
    executed.assert_not_called()
    assert _read_action_log() == [{"ts": _read_action_log()[0]["ts"], "action": "close_browser_tab",
                                   "params": {"match": "youtube"}, "approved": False}]


def test_approved_close_is_logged_with_result(monkeypatch):
    control = SystemControl(desktop=WindowsDesktop())
    monkeypatch.setattr(sc_module.registry, "execute", MagicMock(return_value=(True, "Menutup 1 tab")))
    asked = []
    control.confirm_callback = lambda summary: asked.append(summary) or True

    assert control.execute_action("close_window", {"title": "laporan"}) == (True, "Menutup 1 tab")
    assert "laporan" in asked[0]
    entry = _read_action_log()[0]
    assert (entry["action"], entry["approved"], entry["success"], entry["result"]) == (
        "close_window", True, True, "Menutup 1 tab")


def test_safe_actions_are_not_logged(monkeypatch):
    control = SystemControl(desktop=WindowsDesktop())
    monkeypatch.setattr(sc_module.registry, "execute", MagicMock(return_value=(True, "ok")))
    control.execute_action("set_volume", {"level": 30})
    assert _read_action_log() == []


# ── Proses penting ──

def _proc(pid, name):
    proc = MagicMock(pid=pid)
    proc.info = {"name": name}
    proc.create_time.return_value = 100.0
    return proc


@pytest.fixture(autouse=True)
def _no_real_wait(monkeypatch):
    monkeypatch.setattr(sc_module.psutil, "wait_procs", lambda procs, timeout: (procs, []))


def test_closing_the_terminal_running_miku_is_refused(monkeypatch):
    # cmd.exe yang menjalankan run.bat adalah induk proses Miku
    monkeypatch.setattr(sc_module, "miku_process_ids", lambda: frozenset({4242}))
    host, other = _proc(4242, "cmd.exe"), _proc(77, "cmd.exe")
    monkeypatch.setattr(sc_module.psutil, "process_iter", lambda attrs: [host, other])

    success, message = SystemControl(desktop=WindowsDesktop()).close_application("cmd")

    assert not success and "MikuVision" in message
    host.terminate.assert_not_called()
    other.terminate.assert_not_called()


def test_miku_own_process_tree_is_known():
    import os
    assert os.getpid() in safety.miku_process_ids()
    assert os.getppid() in safety.process_ancestry(os.getpid())


@pytest.mark.parametrize("backend, name", [
    (WindowsDesktop, "explorer"), (WindowsDesktop, "csrss"), (WindowsDesktop, "conhost"),
    (WindowsDesktop, "sihost"), (WindowsDesktop, "python"), (WindowsDesktop, "ollama"),
    (LinuxDesktop, "gnome-shell"), (LinuxDesktop, "xfdesktop"), (LinuxDesktop, "systemd"),
    (LinuxDesktop, "gnome-terminal-server"), (LinuxDesktop, "python3"),
])
def test_critical_processes_are_never_closed(monkeypatch, backend, name):
    proc = _proc(55, name + (".exe" if backend is WindowsDesktop else ""))
    monkeypatch.setattr(sc_module.psutil, "process_iter", lambda attrs: [proc])

    success, message = SystemControl(desktop=backend()).close_application(name)

    assert not success and "dilindungi" in message
    proc.terminate.assert_not_called()
    proc.kill.assert_not_called()


# ── close_window ──

@pytest.fixture
def windows_on_screen(monkeypatch):
    """Jendela palsu; yang ditutup dicatat, bukan dikirimi WM_CLOSE."""
    closed = []

    def install(backend, windows, names=None):
        monkeypatch.setattr(backend, "list_windows", lambda self: windows)
        monkeypatch.setattr(backend, "close_window", lambda self, window_id: closed.append(window_id))
        monkeypatch.setattr(sc_module, "_process_name", lambda pid: (names or {}).get(pid, "app"))
        monkeypatch.setattr(sc_module, "miku_process_ids", lambda: frozenset({4242}))
        return SystemControl(desktop=backend())

    install.closed = closed
    return install


def test_close_window_closes_only_the_matching_window(windows_on_screen):
    control = windows_on_screen(WindowsDesktop, [
        WindowInfo(1, "laporan.docx - Word", 10, "OpusApp"),
        WindowInfo(2, "Downloads", 11, "CabinetWClass"),
    ], {10: "WINWORD.EXE", 11: "explorer.exe"})

    success, message = control.close_window("Downloads")

    assert success and "Downloads" in message
    assert windows_on_screen.closed == [2]


@pytest.mark.parametrize("window, names", [
    (WindowInfo(1, "MikuVision", 4242, "TkTopLevel"), {}),                      # Miku sendiri
    (WindowInfo(2, "C:\\Windows\\system32\\cmd.exe - run.bat", 4242, "ConsoleWindowClass"), {}),
    (WindowInfo(3, "MikuVision - Hatsune Miku", 50, "TkTopLevel"), {}),
    (WindowInfo(4, "Program Manager", 60, "Progman"), {60: "explorer.exe"}),     # desktop: dialog shutdown
    (WindowInfo(5, "Windows Security", 70, "Dialog"), {70: "lsass.exe"}),
])
def test_close_window_refuses_miku_and_shell_windows(windows_on_screen, window, names):
    control = windows_on_screen(WindowsDesktop, [window], names)

    success, _ = control.close_window(window.title)

    assert not success
    assert windows_on_screen.closed == []


def test_close_window_skips_linux_desktop_and_panels(windows_on_screen):
    control = windows_on_screen(LinuxDesktop, [
        WindowInfo("0x1", "Desktop", 20, "-1"),
        WindowInfo("0x2", "Desktop - Nemo", 21, "0"),
        WindowInfo("0x3", "Terminal", 22, "0"),
    ], {20: "nemo-desktop", 21: "nemo", 22: "gnome-terminal-server"})

    success, message = control.close_window("desktop")

    assert success and "dilewati" in message
    assert windows_on_screen.closed == ["0x2"]
    assert not control.close_window("terminal")[0]


def test_close_window_refuses_vague_titles(windows_on_screen):
    control = windows_on_screen(WindowsDesktop, [WindowInfo(i, f"Dokumen {i}", 10 + i, "X") for i in range(5)])

    assert not control.close_window("d")[0]
    success, message = control.close_window("dokumen")

    assert not success and "5 jendela" in message
    assert windows_on_screen.closed == []


def test_close_window_needs_window_support(windows_on_screen, monkeypatch):
    control = windows_on_screen(LinuxDesktop, [WindowInfo("0x2", "laporan", 21, "0")])
    monkeypatch.setattr(LinuxDesktop, "can_close_windows", property(lambda self: False))

    success, message = control.close_window("laporan")

    assert not success and "tombol X" in message
    assert windows_on_screen.closed == []


def test_windows_list_skips_hidden_and_untitled_windows(monkeypatch):
    windows = {1: (True, "laporan - Word", 10, "OpusApp"), 2: (False, "hidden", 11, "X"),
               3: (True, "", 12, "Shell_TrayWnd")}
    fake_gui = types.SimpleNamespace(
        EnumWindows=lambda callback, extra: [callback(hwnd, extra) for hwnd in windows],
        IsWindowVisible=lambda hwnd: windows[hwnd][0],
        GetWindowText=lambda hwnd: windows[hwnd][1],
        GetClassName=lambda hwnd: windows[hwnd][3],
    )
    fake_process = types.SimpleNamespace(GetWindowThreadProcessId=lambda hwnd: (0, windows[hwnd][2]))
    monkeypatch.setitem(sys.modules, "win32gui", fake_gui)
    monkeypatch.setitem(sys.modules, "win32process", fake_process)

    assert _ORIGINAL["windows_list"](WindowsDesktop()) == [WindowInfo(1, "laporan - Word", 10, "OpusApp")]


# ── close_browser_tab ──

TABS = [
    {"id": "A", "type": "page", "title": "Lagu santai - YouTube", "url": "https://www.youtube.com/watch?v=1"},
    {"id": "B", "type": "page", "title": "Tugas kalkulus", "url": "https://docs.google.com/document/d/1"},
    {"id": "C", "type": "page", "title": "Shorts", "url": "https://m.youtube.com/shorts/2"},
]


@pytest.fixture
def browser(monkeypatch):
    closed = []
    monkeypatch.setattr(SystemControl, "_cdp_tabs", lambda self: list(TABS))
    monkeypatch.setattr(SystemControl, "_cdp_close", lambda self, tab_id: closed.append(tab_id))
    browser.closed = closed
    return browser


@pytest.mark.parametrize("match", ["youtube", "YouTube", "tab youtube", "YouTubeのタブ", "youtube.com"])
def test_close_browser_tab_closes_matching_tabs_by_title_or_url(browser, match):
    success, message = SystemControl(desktop=WindowsDesktop()).close_browser_tab(match)

    assert success and "2 tab" in message
    assert browser.closed == ["A", "C"]


@pytest.mark.parametrize("match", ["", "tab", "browser", "タブ", "chrome tab", "a"])
def test_close_browser_tab_refuses_matches_for_every_tab(browser, match):
    success, _ = SystemControl(desktop=WindowsDesktop()).close_browser_tab(match)

    assert not success
    assert browser.closed == []


def test_close_browser_tab_without_cdp_explains_and_closes_nothing(monkeypatch):
    def no_cdp(self):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(SystemControl, "_cdp_tabs", no_cdp)
    monkeypatch.setattr(WindowsDesktop, "list_windows",
                        lambda self: [WindowInfo(1, "Lagu santai - YouTube - Google Chrome", 10, "Chrome_WidgetWin_1")])
    closed = []
    monkeypatch.setattr(WindowsDesktop, "close_window", lambda self, window: closed.append(window))

    success, message = SystemControl(desktop=WindowsDesktop()).close_browser_tab("youtube")

    assert not success
    assert "9222" in message and "Lagu santai - YouTube" in message
    assert closed == []


def test_close_application_youtube_falls_back_to_the_tab(browser, monkeypatch):
    monkeypatch.setattr(sc_module.psutil, "process_iter", lambda attrs: [])

    success, _ = SystemControl(desktop=WindowsDesktop()).close_application("YouTube")

    assert success
    assert browser.closed == ["A", "C"]


def test_cdp_tabs_lists_only_pages(release_server, monkeypatch):
    release_server.files["json"] = json.dumps(TABS + [
        {"id": "W", "type": "service_worker", "title": "YouTube worker", "url": "https://www.youtube.com/sw.js"},
    ]).encode()
    monkeypatch.setattr(sc_module, "CDP_URL", release_server.url.rstrip("/"))

    tabs = _ORIGINAL["cdp_tabs"](SystemControl(desktop=WindowsDesktop()))

    assert [t["id"] for t in tabs] == ["A", "B", "C"]


def test_cdp_close_retries_with_put(monkeypatch):
    calls = []

    class Response:
        def close(self):
            pass

    def fake_urlopen(request, timeout):
        if isinstance(request, str):
            calls.append(("GET", request))
            raise urllib.error.HTTPError(request, 405, "Method Not Allowed", {}, None)
        calls.append((request.get_method(), request.full_url))
        return Response()

    monkeypatch.setattr(sc_module.urllib.request, "urlopen", fake_urlopen)

    _ORIGINAL["cdp_close"](SystemControl(desktop=WindowsDesktop()), "A B")

    assert calls == [("GET", f"{sc_module.CDP_URL}/json/close/A%20B"),
                     ("PUT", f"{sc_module.CDP_URL}/json/close/A%20B")]


# ── Keyboard ──

@pytest.mark.parametrize("keys", [["alt", "f4"], "alt+F4", ["windows", "r"], ["win", "x"], ["shift", "del"],
                                  ["ctrl", "alt", "delete"], ["alt", "f2"]])
def test_dangerous_hotkeys_are_refused(monkeypatch, keys):
    fake = MagicMock()
    monkeypatch.setattr(sc_module, "pyautogui", fake)

    success, message = SystemControl(desktop=WindowsDesktop()).hotkey(keys)

    assert not success and "tidak dijalankan" in message
    fake.hotkey.assert_not_called()


def test_normal_hotkeys_still_work(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(sc_module, "pyautogui", fake)

    assert SystemControl(desktop=WindowsDesktop()).hotkey("Ctrl+C")[0]
    fake.hotkey.assert_called_once_with("ctrl", "c")


# ── Untuk LLM ──

@pytest.mark.parametrize("text, tool", [
    ("YouTube閉じて", "close_browser_tab"),
    ("tutup tab youtube", "close_browser_tab"),
    ("tutup youtube", "close_browser_tab"),
    ("YouTubeのタブを閉じて", "close_browser_tab"),
    ("tutup jendela Downloads", "close_window"),
    ("レポートのウィンドウを閉じて", "close_window"),
])
def test_close_tools_are_sent_for_close_phrases(text, tool):
    assert tool in tool_names(select_skills(text, fallback_all=False))


def test_close_tool_descriptions_name_japanese_and_indonesian_phrases():
    # qwen3:4b-instruct melewatkan perintah yang frasanya tidak ada di deskripsi tool
    tab = registry.get_tool("close_browser_tab").description
    window = registry.get_tool("close_window").description
    assert "YouTube閉じて" in tab and "tutup tab youtube" in tab
    assert "閉じて" in window and "tutup jendela" in window
    assert "close_browser_tab" in registry.get_tool("close_application").description


# ── Routine dan skill tidak bisa melewati gerbang konfirmasi ──

def test_routine_step_that_closes_still_asks(monkeypatch):
    from core import routines
    routine = routines.Routine("tutup semua", steps=[{"action": "close_browser_tab", "params": {"match": "youtube"}}])
    monkeypatch.setattr(routines, "find_routine", lambda name: routine)
    executed = MagicMock(return_value=(True, "ok"))
    control = SystemControl(desktop=WindowsDesktop())
    original = sc_module.registry.execute
    monkeypatch.setattr(sc_module.registry, "execute",
                        lambda action, instance, params: original(action, instance, params)
                        if action == "run_routine" else executed(action, params))

    success, message = control.execute_action("run_routine", {"name": "tutup semua"})

    assert not success and "Dibatalkan" in message
    executed.assert_not_called()
