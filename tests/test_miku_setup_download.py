"""MikuVision Setup: unduh rilis (lanjut dari .part, SHA256) dan ekstrak zip dengan aman (fase I3)."""

import hashlib
import threading
import zipfile

import pytest

from miku_setup import download
from miku_setup.download import Cancelled, DownloadError, parse_sha256sums, parse_version, safe_extract

DATA = bytes(range(256)) * 40  # 10 KB
SHA = hashlib.sha256(DATA).hexdigest()


@pytest.fixture
def served(release_server):
    release_server.files["MikuVision-1.6.0.zip"] = DATA
    return release_server, release_server.url + "MikuVision-1.6.0.zip"


def test_download_checks_the_sha_and_reuses_a_verified_file(served, tmp_path):
    server, url = served
    dest = tmp_path / "MikuVision-1.6.0.zip"
    seen = []
    assert download.download(url, dest, SHA, lambda done, total: seen.append((done, total))) == dest
    assert dest.read_bytes() == DATA and not dest.with_name(dest.name + ".part").exists()
    assert seen[-1] == (len(DATA), len(DATA))
    download.download(url, dest, SHA)
    assert len(server.requests) == 1  # file yang sudah cocok tidak diunduh lagi


def test_interrupted_download_resumes_from_the_part_file(served, tmp_path):
    server, url = served
    dest = tmp_path / "MikuVision-1.6.0.zip"
    dest.with_name(dest.name + ".part").write_bytes(DATA[:4000])
    download.download(url, dest, SHA)
    assert dest.read_bytes() == DATA
    assert server.requests == [("/MikuVision-1.6.0.zip", "bytes=4000-")]


def test_server_without_range_starts_over(served, tmp_path):
    server, url = served
    server.ranges = False
    dest = tmp_path / "MikuVision-1.6.0.zip"
    dest.with_name(dest.name + ".part").write_bytes(b"x" * 4000)  # isi lama tidak boleh tersisa
    download.download(url, dest, SHA)
    assert dest.read_bytes() == DATA


def test_part_file_past_the_end_starts_over(served, tmp_path):
    server, url = served
    dest = tmp_path / "MikuVision-1.6.0.zip"
    dest.with_name(dest.name + ".part").write_bytes(DATA + b"sisa")
    download.download(url, dest, SHA)
    assert dest.read_bytes() == DATA
    assert [r for _, r in server.requests] == [f"bytes={len(DATA) + 4}-", None]  # 416, lalu dari nol


def test_checksum_mismatch_deletes_the_download(served, tmp_path):
    _, url = served
    dest = tmp_path / "MikuVision-1.6.0.zip"
    with pytest.raises(DownloadError, match="checksum"):
        download.download(url, dest, "0" * 64)
    assert not dest.exists() and not dest.with_name(dest.name + ".part").exists()


def test_cancel_keeps_the_part_file_for_the_next_try(served, tmp_path, monkeypatch):
    _, url = served
    monkeypatch.setattr(download, "CHUNK", 1000)
    dest = tmp_path / "MikuVision-1.6.0.zip"
    cancel = threading.Event()
    with pytest.raises(Cancelled):
        download.download(url, dest, SHA, lambda done, total: cancel.set(), cancel)
    part = dest.with_name(dest.name + ".part")
    assert part.stat().st_size == 1000
    download.download(url, dest, SHA)
    assert dest.read_bytes() == DATA


def test_missing_file_is_a_readable_error(release_server, tmp_path):
    with pytest.raises(DownloadError, match="HTTP 404"):
        download.download(release_server.url + "tidak-ada.zip", tmp_path / "x.zip", SHA)
    with pytest.raises(DownloadError, match="version.json"):
        download.fetch_text(release_server.url + "version.json")


def test_parse_version():
    assert parse_version('{"version": "1.6.0", "date": "2026-11-01"}') == "1.6.0"
    for text in ("bukan json", "{}", '{"version": 16}', '{"version": "../1.6.0"}', '{"version": ""}'):
        with pytest.raises(DownloadError):
            parse_version(text)


def test_parse_sha256sums():
    text = f"{SHA}  MikuVision-1.6.0.zip\n{'a' * 64} *version.json\nbaris rusak\n{'z' * 64}  x.zip\n"
    assert parse_sha256sums(text) == {"MikuVision-1.6.0.zip": SHA, "version.json": "a" * 64}


def make_zip(path, names):
    with zipfile.ZipFile(path, "w") as archive:
        for name in names:
            archive.writestr(zipfile.ZipInfo(name), b"" if name.endswith("/") else f"isi {name}".encode())
    return path


def test_extract_strips_the_release_folder_and_keeps_user_data(tmp_path):
    target = tmp_path / "MikuVision"
    (target / "data").mkdir(parents=True)
    (target / "data" / "settings.json").write_text("punya user")
    archive = make_zip(tmp_path / "r.zip", ["MikuVision-1.6.0/", "MikuVision-1.6.0/gui.py",
                                            "MikuVision-1.6.0/core/ai_brain.py",
                                            "MikuVision-1.6.0/data/settings.json",
                                            "MikuVision-1.6.0/models/README.md"])
    assert safe_extract(archive, target) == 3
    assert (target / "gui.py").read_text() == "isi MikuVision-1.6.0/gui.py"
    assert (target / "core" / "ai_brain.py").is_file() and (target / "models" / "README.md").is_file()
    assert (target / "data" / "settings.json").read_text() == "punya user"


@pytest.mark.parametrize("bad", ["../luar.txt", "/etc/luar.txt", "C:/luar.txt", "a/../../luar.txt"])
def test_extract_refuses_paths_outside_the_folder(tmp_path, bad):
    archive = make_zip(tmp_path / "r.zip", ["gui.py", bad])
    with pytest.raises(DownloadError, match="tidak aman"):
        safe_extract(archive, tmp_path / "MikuVision")
    assert not (tmp_path / "luar.txt").exists() and not (tmp_path / "MikuVision" / "gui.py").exists()
