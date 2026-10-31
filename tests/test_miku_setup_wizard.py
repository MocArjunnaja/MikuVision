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


def test_without_dry_run_the_real_install_is_not_there_yet():
    assert main([]) == 2
