"""Membuka aplikasi dari menu sistem dan mengingatnya (cache)."""

import json
import subprocess
from unittest.mock import MagicMock

import pytest

from core import commands
from core import system_control as sc_module
from core.desktop import linux, windows
from core.desktop.app_search import AppCache, AppEntry, AppLauncher, find, normalize
from core.desktop.linux import LinuxDesktop
from core.desktop.windows import WindowsDesktop
from core.system_control import SystemControl

# conftest mengosongkan menu aplikasi saat test berjalan; ambil kode aslinya saat import
_LINUX_LIST = LinuxDesktop.list_installed_apps
_WINDOWS_LIST = WindowsDesktop.list_installed_apps

LIBREOFFICE = AppEntry(id="libreoffice-startcenter", name="LibreOffice", aliases=("Office",),
                       process_names=("soffice.bin",))
WRITER = AppEntry(id="libreoffice-writer", name="LibreOffice Writer", process_names=("soffice.bin",))
USB_WRITER = AppEntry(id="mintstick", name="USB Image Writer")
FILES = AppEntry(id="nemo", name="Files", aliases=("Berkas",), keywords=("folders", "explorer"))
SOFTWARE = AppEntry(id="mintinstall", name="Software Manager",
                    aliases=("Pengelola Perangkat Lunak", "ソフトウェアマネージャー"),
                    keywords=("install", "uninstall"))
UNINSTALLER = AppEntry(id="foo-uninstall", name="Uninstall Foo")
MENU = [LIBREOFFICE, WRITER, USB_WRITER, FILES, SOFTWARE, UNINSTALLER]


def _find(query, entries=MENU):
    return find(normalize(query), entries)


# ── Pencocokan nama ──

def test_normalize_keeps_japanese_and_drops_punctuation():
    assert normalize("LibreOffice!") == "libreoffice"
    assert normalize("Café  Écrire") == "cafe ecrire"
    assert normalize("ソフトウェア・マネージャー") == "ソフトウェア マネージャー"


@pytest.mark.parametrize("query, expected", [
    ("LibreOffice", LIBREOFFICE),
    ("libre office", LIBREOFFICE),                 # spasi beda
    ("librofice", LIBREOFFICE),                    # salah ketik / salah dengar
    ("office", LIBREOFFICE),                       # GenericName persis
    ("pengelola perangkat lunak", SOFTWARE),       # nama bahasa Indonesia
    ("ソフトウェアマネージャー", SOFTWARE),            # nama bahasa Jepang
    ("berkas", FILES),
    ("explorer", FILES),                           # kata kunci
])
def test_app_is_found_by_name_alias_keyword_or_typo(query, expected):
    match, candidates = _find(query)
    assert match == expected and candidates == []


def test_same_score_for_several_apps_is_ambiguous():
    match, candidates = _find("writer")

    assert match is None
    assert set(candidates) == {WRITER, USB_WRITER}


def test_unknown_app_is_not_matched():
    assert _find("zzz tidak ada") == (None, [])


def test_uninstaller_is_never_opened():
    match, candidates = _find("Uninstall Foo")
    assert match is None and UNINSTALLER not in candidates


# ── Cache ──

def test_cache_is_separate_per_os(tmp_path):
    path = tmp_path / "app_cache.json"
    AppCache(path, "linux").put("libreoffice", LIBREOFFICE)

    assert AppCache(path, "linux").get("libreoffice")["id"] == "libreoffice-startcenter"
    # Folder data/ dipakai bersama Windows saat dual-boot
    assert AppCache(path, "windows").get("libreoffice") is None


def test_cache_survives_a_broken_file(tmp_path):
    path = tmp_path / "app_cache.json"
    path.write_text("{bukan json", encoding="utf-8")
    cache = AppCache(path, "linux")

    assert cache.get("x") is None
    cache.put("libreoffice", LIBREOFFICE)
    assert cache.get("libreoffice")["name"] == "LibreOffice"


class _FakeDesktop:
    name = "linux"

    def __init__(self, entries, launch_ok=True):
        self.entries = list(entries)
        self.launch_ok = launch_ok
        self.launched = []
        self.listed = 0

    def list_installed_apps(self):
        self.listed += 1
        return self.entries

    def launch_entry(self, entry):
        self.launched.append(entry.id)
        return (True, f"Membuka {entry.name}...", None) if self.launch_ok else (False, "gagal", None)


def _launcher(tmp_path, entries=MENU, launch_ok=True):
    desktop = _FakeDesktop(entries, launch_ok)
    return AppLauncher(desktop, AppCache(tmp_path / "app_cache.json", "linux")), desktop


def test_opened_app_is_learned_and_reused(tmp_path):
    launcher, desktop = _launcher(tmp_path)

    assert launcher.open("libre office")[0]
    assert launcher.cache.get("libre office")["id"] == "libreoffice-startcenter"

    # Kedua kali dari cache: query yang sama langsung ke aplikasi yang sama
    assert launcher.open("libre office")[0]
    assert desktop.launched == ["libreoffice-startcenter", "libreoffice-startcenter"]


def test_failed_launch_is_not_learned(tmp_path):
    launcher, _ = _launcher(tmp_path, launch_ok=False)

    success, _, _ = launcher.open("LibreOffice")

    assert not success
    assert launcher.cache.get("libreoffice") is None


def test_uninstalled_app_is_forgotten_and_searched_again(tmp_path):
    launcher, desktop = _launcher(tmp_path)
    launcher.cache.put("browser kantor", AppEntry(id="sudah-dihapus", name="Lama"))

    result = launcher.open("browser kantor")

    assert result is None                     # tidak ada lagi yang cocok
    assert launcher.cache.get("browser kantor") is None
    assert desktop.launched == []


def test_ambiguous_request_launches_nothing(tmp_path):
    launcher, desktop = _launcher(tmp_path)

    success, message, _ = launcher.open("writer")

    assert not success and "LibreOffice Writer" in message and "USB Image Writer" in message
    assert desktop.launched == []


def test_suggestions_for_unknown_app(tmp_path):
    launcher, _ = _launcher(tmp_path)
    assert launcher.suggestions("libreofice writer")[0] == "LibreOffice Writer"


# ── Menu aplikasi Linux (.desktop) ──

def _desktop_file(folder, name, **fields):
    folder.mkdir(parents=True, exist_ok=True)
    body = "[Desktop Entry]\nType=Application\n" + "".join(f"{k}={v}\n" for k, v in fields.items())
    body += "\n[Desktop Action new]\nName=Bukan nama aplikasi\n"
    (folder / f"{name}.desktop").write_text(body, encoding="utf-8")


def test_linux_menu_is_read_like_the_desktop_menu(tmp_path, monkeypatch):
    user, system = tmp_path / "user", tmp_path / "system"
    _desktop_file(system, "libreoffice-writer", Name="LibreOffice Writer", **{"Name[id]": "Pengolah Kata"},
                  Keywords="Text;Word;", Exec="libreoffice --writer %U")
    _desktop_file(system, "hidden-app", Name="Tersembunyi", NoDisplay="true", Exec="x")
    _desktop_file(system, "kde-only", Name="KDE Saja", OnlyShowIn="KDE;", Exec="x")
    _desktop_file(system, "not-installed", Name="Belum Terpasang", TryExec="tidak-ada-program-ini", Exec="x")
    _desktop_file(system, "overridden", Name="Ditimpa User", Exec="x")
    _desktop_file(user, "overridden", Name="Ditimpa User", Hidden="true")
    _desktop_file(system / "kde4", "dolphin", Name="Dolphin", Exec="env QT_X=1 dolphin %u")
    monkeypatch.setattr(linux, "_application_dirs", lambda: [user, system])
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "X-Cinnamon")

    apps = {a.id: a for a in _LINUX_LIST(LinuxDesktop())}

    assert set(apps) == {"libreoffice-writer", "kde4-dolphin"}
    writer = apps["libreoffice-writer"]
    assert writer.name == "LibreOffice Writer"          # bukan nama dari [Desktop Action]
    assert "Pengolah Kata" in writer.aliases and "Word" in writer.keywords
    assert writer.process_names == ("soffice.bin",)     # libreoffice -> soffice.bin
    assert apps["kde4-dolphin"].process_names == ("dolphin",)


def test_application_dirs_follow_xdg_with_user_first(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_DATA_DIRS", "/usr/share/cinnamon:/usr/share")

    dirs = [str(d) for d in linux._application_dirs()]

    assert dirs[:3] == [str(tmp_path / "home" / "applications"),
                        "/usr/share/cinnamon/applications", "/usr/share/applications"]


def test_linux_launch_entry_uses_gtk_launch(monkeypatch):
    started = []
    monkeypatch.setattr(linux.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(linux, "_start", lambda argv: started.append(argv) or 0)

    assert LinuxDesktop().launch_entry(LIBREOFFICE) == (True, "Membuka LibreOffice...", None)
    assert started == [["gtk-launch", "libreoffice-startcenter"]]

    monkeypatch.setattr(linux, "_start", lambda argv: 4)
    assert not LinuxDesktop().launch_entry(LIBREOFFICE)[0]


# ── Lewat tool open_application / close_application ──

def _linux_control(monkeypatch, entries):
    monkeypatch.setattr(LinuxDesktop, "list_installed_apps", lambda self: entries)
    monkeypatch.setattr(linux.shutil, "which", lambda name: "/usr/bin/gtk-launch" if name == "gtk-launch" else None)
    started = []
    monkeypatch.setattr(linux, "_start", lambda argv: started.append(argv) or 0)
    return SystemControl(desktop=LinuxDesktop()), started


def test_app_outside_the_catalog_is_opened_from_the_menu(monkeypatch):
    # Kasus nyata di GUI: "libreOffice o haite kudasai" -> "Aplikasi 'LibreOffice' tidak dikenali"
    control, started = _linux_control(monkeypatch, MENU)

    success, message = control.open_application("LibreOffice")

    assert success and "LibreOffice" in message
    assert started == [["gtk-launch", "libreoffice-startcenter"]]
    assert control.apps.cache.get("libreoffice")["process_names"] == ["soffice.bin"]


def test_learned_app_can_be_closed(monkeypatch):
    control, _ = _linux_control(monkeypatch, MENU)
    control.open_application("LibreOffice")
    soffice, other = MagicMock(pid=40), MagicMock(pid=41)
    soffice.info, other.info = {"name": "soffice.bin"}, {"name": "libreoffice"}
    monkeypatch.setattr(sc_module.psutil, "process_iter", lambda attrs: [soffice, other])
    monkeypatch.setattr(sc_module.psutil, "wait_procs", lambda procs, timeout: (list(procs), []))

    success, _ = control.close_application("LibreOffice")

    assert success
    soffice.terminate.assert_called_once()


def test_unknown_app_gets_closest_names(monkeypatch):
    control, started = _linux_control(monkeypatch, MENU)

    success, message = control.open_application("libreofice writer pro max")

    assert not success and "mirip" in message and "LibreOffice Writer" in message
    assert started == []


# ── Windows (Start Menu) ──

def test_windows_reads_start_apps(monkeypatch):
    monkeypatch.setattr(windows, "_start_apps", lambda: [{"Name": "LibreOffice", "AppID": "{abc}\\soffice.exe"},
                                                         {"Name": "", "AppID": "x"}])

    apps = _WINDOWS_LIST(WindowsDesktop())

    assert apps == [AppEntry(id="{abc}\\soffice.exe", name="LibreOffice")]


def test_windows_falls_back_to_start_menu_shortcuts(monkeypatch, tmp_path):
    programs = tmp_path / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "LibreOffice"
    programs.mkdir(parents=True)
    (programs / "LibreOffice Writer.lnk").write_bytes(b"")

    def broken():
        raise subprocess.TimeoutExpired("powershell", 20)

    monkeypatch.setattr(windows, "_start_apps", broken)
    monkeypatch.setenv("ProgramData", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path / "kosong"))

    apps = _WINDOWS_LIST(WindowsDesktop())

    assert [a.name for a in apps] == ["LibreOffice Writer"]
    assert apps[0].path.endswith("LibreOffice Writer.lnk")


def test_windows_launch_entry(monkeypatch):
    popen, startfile = MagicMock(), MagicMock()
    monkeypatch.setattr(windows.subprocess, "Popen", popen)
    monkeypatch.setattr(windows.os, "startfile", startfile, raising=False)

    WindowsDesktop().launch_entry(AppEntry(id="Microsoft.WindowsCalculator_8wekyb3d8bbwe!App", name="Calculator"))
    popen.assert_called_once_with(["explorer.exe", "shell:AppsFolder\\Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"])

    WindowsDesktop().launch_entry(AppEntry(id="x", name="Writer", path=r"C:\Start Menu\Writer.lnk"))
    startfile.assert_called_once_with(r"C:\Start Menu\Writer.lnk")


# ── /apps ──

def test_apps_command_lists_and_forgets(monkeypatch):
    control, _ = _linux_control(monkeypatch, MENU)
    assert "Belum ada" in commands.handle_command("/apps", None, control)

    control.open_application("LibreOffice")
    assert "libreoffice -> LibreOffice" in commands.handle_command("/apps", None, control)

    assert "lupa" in commands.handle_command("/apps forget LibreOffice", None, control)
    assert control.apps.cache.get("libreoffice") is None
    stored = json.loads(control.apps.cache.path.read_text(encoding="utf-8"))
    assert stored == {"linux": {}}


def test_closed_window_with_background_process_counts_as_closed(monkeypatch):
    # GNOME Calendar: jendela tertutup, layanan --gapplication-service tetap jalan sebentar
    control = SystemControl(desktop=LinuxDesktop())
    calendar = MagicMock(pid=50)
    calendar.info = {"name": "gnome-calendar"}
    windows_seen = iter([{50: ["0x01"]}, {}])   # sebelum ditutup: ada jendela; sesudahnya: tidak
    monkeypatch.setattr(control.desktop, "windows_by_pid", lambda pids: next(windows_seen))
    monkeypatch.setattr(sc_module.psutil, "process_iter", lambda attrs: [calendar])
    monkeypatch.setattr(sc_module.psutil, "wait_procs", lambda procs, timeout: ([], list(procs)))

    success, message = control.close_application("gnome-calendar")

    assert success and message.startswith("Menutup")
    calendar.kill.assert_not_called()
    calendar.terminate.assert_not_called()
