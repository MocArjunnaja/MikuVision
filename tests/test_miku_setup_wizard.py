"""MikuVision Setup: semua halaman bisa dijalani dengan --dry-run (fase I2).

Butuh customtkinter asli dan layar; di CI customtkinter di-stub (tests/conftest.py), jadi test ini
dilewati di sana. Cek sistem dan ruang disk diganti nilai tetap, supaya tidak bergantung pada komputer.
"""

import os
import sys
import time
from unittest.mock import MagicMock

import pytest

from miku_setup.checks import FAIL, OK, CheckResult
from miku_setup.main import main

pytestmark = pytest.mark.skipif(
    isinstance(sys.modules.get("customtkinter"), MagicMock)
    or (sys.platform != "win32" and not os.environ.get("DISPLAY")),
    reason="butuh customtkinter asli dan layar")

PASSING = [lambda: [CheckResult("windows", "Windows", OK, "Windows 11 64-bit")],
           lambda: [CheckResult("gpu", "GPU NVIDIA", OK, "RTX 4050")]]


@pytest.fixture
def make_wizard(tmp_path):
    from miku_setup.components import Selection
    from miku_setup.state import SetupState
    from miku_setup.wizard import Wizard

    created = []

    def make(checks=PASSING, fail=False):
        setup = SetupState(Selection(tmp_path / "MikuVision"), tmp_path / "setup.log", dry_run=True,
                           dry_run_fail=fail)
        wizard = Wizard(setup, check_functions=checks, dry_run_delay=0)
        wizard.withdraw()
        wizard.find_ollama = lambda: "ollama.exe"
        wizard.free_bytes = lambda path: 500e9
        created.append(wizard)
        return wizard

    yield make
    for wizard in created:
        try:
            wizard.destroy()
        except Exception:
            pass


def pump(wizard, until, timeout=10.0):
    deadline = time.time() + timeout
    while not until() and time.time() < deadline:
        wizard.update()
        time.sleep(0.01)
    assert until(), "waktu habis"


def accept_license(wizard):
    wizard.go_next()
    wizard.go_next()  # Lanjut belum aktif: tetap di halaman lisensi
    assert wizard.index == 1 and wizard.next_button.cget("state") == "disabled"
    wizard.pages[1].accepted.set(True)
    wizard.pages[1]._changed()
    wizard.go_next()


def test_all_pages_with_dry_run(make_wizard):
    wizard = make_wizard()
    assert [p.title for p in wizard.pages] == ["Selamat datang", "Lisensi karakter", "Cek sistem",
                                               "Lokasi dan komponen", "Unduh dan pasang", "Selesai"]
    assert wizard.back_button.cget("state") == "disabled"
    accept_license(wizard)
    pump(wizard, lambda: wizard.pages[2].done)
    assert [r.key for r in wizard.setup.results] == ["windows", "gpu", "disk"]
    wizard.go_next()
    assert wizard.index == 3
    wizard.go_next()
    pump(wizard, lambda: wizard.index == 5)  # halaman Selesai tampil sendiri setelah instalasi
    assert wizard.setup.install_ok is True
    assert wizard.next_button.cget("text") == "Selesai" and wizard.back_button.cget("state") == "disabled"
    wizard.go_next()
    with pytest.raises(Exception):
        wizard.winfo_exists()  # jendela sudah ditutup


def test_failed_system_check_blocks_the_install(make_wizard):
    wizard = make_wizard(checks=[lambda: [CheckResult("internet", "Internet", FAIL, "Tidak terjangkau: pypi.org")]])
    accept_license(wizard)
    pump(wizard, lambda: wizard.pages[2].done)
    assert wizard.next_button.cget("state") == "disabled"
    wizard.go_next()
    assert wizard.index == 2


def test_invalid_folder_is_explained_on_the_location_page(make_wizard):
    wizard = make_wizard()
    accept_license(wizard)
    pump(wizard, lambda: wizard.pages[2].done)
    wizard.go_next()
    wizard.pages[3].install_dir.set("MikuVision")
    wizard.go_next()
    assert wizard.index == 3 and "lengkap dengan drive" in wizard.error.cget("text")


def test_failed_install_offers_retry(make_wizard):
    wizard = make_wizard(fail=True)
    accept_license(wizard)
    pump(wizard, lambda: wizard.pages[2].done)
    wizard.go_next()
    wizard.go_next()
    pump(wizard, lambda: wizard.index == 5)
    assert wizard.setup.install_ok is False and "paket Python" in wizard.setup.last_error
    assert wizard.next_button.cget("text") == "Tutup"
    wizard.retry_install()
    assert wizard.index == 4 and wizard.setup.install_ok is None
    pump(wizard, lambda: wizard.index == 5)


def test_without_dry_run_the_wizard_installs_for_real(tmp_path, monkeypatch):
    import miku_setup.main as entry
    import miku_setup.wizard as wizard_module

    opened = {}

    class FakeWizard:
        def __init__(self, setup, release_url):
            opened.update(setup=setup, release_url=release_url)

        def mainloop(self):
            pass

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(entry, "setup_logging", lambda: tmp_path / "setup.log")
    monkeypatch.setattr(wizard_module, "Wizard", FakeWizard)
    assert main(["--release-url", "http://127.0.0.1:8765/"]) == 0
    assert opened["setup"].dry_run is False and opened["release_url"] == "http://127.0.0.1:8765/"


def test_dry_run_installs_nothing_in_make_runner(make_wizard):
    from miku_setup.runner import DryRunRunner

    assert isinstance(make_wizard().make_runner(None), DryRunRunner)


@pytest.fixture
def maintain_wizard(tmp_path):
    """Setup dibuka lagi saat MikuVision 1.6.0 sudah terpasang (mode uji: tidak ada yang dihapus)."""
    from miku_setup.components import Selection
    from miku_setup.registry import InstalledApp
    from miku_setup.state import SetupState
    from miku_setup.wizard import Wizard

    created = []

    def make(latest="1.7.0"):
        app = InstalledApp(tmp_path / "MikuVision", "1.6.0")
        setup = SetupState(Selection(app.install_dir), tmp_path / "setup.log", dry_run=True, mode="maintain",
                           installed=app)
        wizard = Wizard(setup, check_functions=PASSING, dry_run_delay=0, fetch_latest=lambda: latest)
        wizard.withdraw()
        created.append(wizard)
        return wizard

    yield make
    for wizard in created:
        try:
            wizard.destroy()
        except Exception:
            pass


def test_maintenance_offers_the_newer_release_then_updates(maintain_wizard):
    wizard = maintain_wizard()
    page = wizard.pages[0]
    assert [p.title for p in wizard.pages] == ["Pilih tindakan"]
    pump(wizard, lambda: wizard.setup.latest_version == "1.7.0")
    assert page.radios["update"].cget("text") == "Perbarui ke 1.7.0" and page.choice.get() == "update"
    wizard.go_next()
    assert [p.title for p in wizard.pages] == ["Pilih tindakan", "Unduh dan pasang", "Selesai"]
    assert wizard.setup.mode == "update" and wizard.setup.desktop_shortcut is False
    pump(wizard, lambda: wizard.index == 2, timeout=30)
    assert wizard.setup.install_ok


def test_maintenance_without_a_newer_release_suggests_repair(maintain_wizard):
    wizard = maintain_wizard(latest="1.6.0")
    page = wizard.pages[0]
    pump(wizard, lambda: wizard.setup.latest_version == "1.6.0")
    assert page.radios["update"].cget("state") == "disabled" and page.choice.get() == "repair"
    wizard.go_next()
    assert wizard.setup.mode == "repair"
    pump(wizard, lambda: wizard.index == 2, timeout=30)
    assert wizard.setup.install_ok


def test_uninstall_flow_in_dry_run(maintain_wizard):
    wizard = maintain_wizard()
    wizard.pages[0].choice.set("uninstall")
    wizard.go_next()
    assert [p.title for p in wizard.pages] == ["Pilih tindakan", "Hapus", "Selesai"]
    assert wizard.next_button.cget("text") == "Hapus"
    wizard.pages[1].data.set(True)
    wizard.go_next()
    assert wizard.setup.removal.data is True and wizard.setup.removal.models is False
    pump(wizard, lambda: wizard.pages[2].done)
    assert wizard.next_button.cget("text") == "Tutup" and wizard.setup.removal_problems == []


def test_going_back_and_choosing_again_rebuilds_the_steps(maintain_wizard):
    wizard = maintain_wizard()
    wizard.pages[0].choice.set("uninstall")
    wizard.go_next()
    wizard.go_back()
    wizard.pages[0].choice.set("repair")
    wizard.go_next()
    assert [p.title for p in wizard.pages] == ["Pilih tindakan", "Unduh dan pasang", "Selesai"]
    assert len(wizard.steps) == 3


def test_dialogs_are_in_indonesian(make_wizard):
    from miku_setup.pages.base import dialog

    wizard = make_wizard()
    seen = {}

    def answer():
        window = wizard.winfo_children()[-1]
        buttons = [w for w in window.winfo_children()[-1].winfo_children()]
        seen["labels"] = {b.cget("text") for b in buttons}
        next(b for b in buttons if b.cget("text") == "Keluar").invoke()

    wizard.after(300, answer)
    assert dialog(wizard, "Keluar dari Setup?", "MikuVision belum dipasang.", ("Keluar", "Kembali")) == 0
    assert seen["labels"] == {"Keluar", "Kembali"}
