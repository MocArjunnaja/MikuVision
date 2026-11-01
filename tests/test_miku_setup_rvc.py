"""MikuVision Setup: model RVC dari link yang ditempel user (halaman 4, "Unduh dari link")."""

import hashlib
import io
import queue
import sys
import zipfile
from pathlib import Path

import pytest

from miku_setup import rvc
from miku_setup.components import Selection, install_args, space_needed, validate_selection
from miku_setup.download import DownloadError
from miku_setup.runner import InstallRunner

PTH = b"bobot" * 100
INDEX = b"index" * 100


@pytest.mark.parametrize("url, expected", [
    ("  https://huggingface.co/user/miku/blob/main/miku.pth ",
     "https://huggingface.co/user/miku/resolve/main/miku.pth"),
    ("https://huggingface.co/user/miku/resolve/main/miku.zip?download=true",
     "https://huggingface.co/user/miku/resolve/main/miku.zip?download=true"),
    ("https://example.com/blob/miku.pth", "https://example.com/blob/miku.pth"),  # hanya Hugging Face
])
def test_huggingface_page_links_become_download_links(url, expected):
    assert rvc.normalize_url(url) == expected


def test_file_name_comes_from_the_path_and_is_safe_on_windows():
    assert rvc.file_name("https://host/a/Miku%20V2.pth?token=rahasia") == "Miku V2.pth"
    assert rvc.file_name("https://host/a/mi:ku%3F.index") == "mi_ku_.index"


@pytest.mark.parametrize("model, index, problem", [
    ("https://h/m.pth", "https://h/added_m.index", None),
    ("https://h/m.zip", "", None),
    ("https://huggingface.co/u/r/blob/main/m.pth", "https://huggingface.co/u/r/blob/main/m.index", None),
    ("", "", "Tempel link model RVC"),
    ("http://h/m.pth", "https://h/m.index", "https://"),
    ("ftp://h/m.pth", "https://h/m.index", "https://"),
    ("https://h/m.ckpt", "https://h/m.index", "file .pth atau .zip"),
    ("https://huggingface.co/u/r", "", "file .pth atau .zip"),
    ("https://h/m.pth", "", "link file .index"),
    ("https://h/m.pth", "https://h/m.txt", "file .index"),
    ("https://h/m.zip", "https://h/m.index", "kosongkan link .index"),
])
def test_link_problem(model, index, problem):
    result = rvc.link_problem(model, index)
    assert result is None if problem is None else problem in result


def _zip(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def _unpacked(tmp_path, names):
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    return tmp_path


def test_zip_contents_skip_training_checkpoints_and_prefer_the_added_index(tmp_path):
    folder = _unpacked(tmp_path, ["miku/G_2333.pth", "miku/D_2333.pth", "miku/miku.pth",
                                  "miku/trained_IVF_miku.index", "miku/added_IVF_miku.index"])
    model, index = rvc.pick_model_files(folder)
    assert (model.name, index.name) == ("miku.pth", "added_IVF_miku.index")


@pytest.mark.parametrize("names, message", [
    (["a.index"], "tidak berisi file .pth"),
    (["a.pth"], "tidak berisi file .index"),
    (["a.pth", "b.pth", "a.index"], "lebih dari satu file .pth (a.pth, b.pth)"),
])
def test_unclear_zip_contents_are_explained(tmp_path, names, message):
    with pytest.raises(DownloadError, match=message.replace("(", r"\(").replace(")", r"\)")):
        rvc.pick_model_files(_unpacked(tmp_path, names))


@pytest.fixture
def links(release_server, monkeypatch):
    monkeypatch.setattr(rvc, "ALLOWED_SCHEMES", ("https", "http"))  # server uji tanpa TLS
    release_server.files.update({
        "miku.pth": PTH, "added_miku.index": INDEX,
        "miku.zip": _zip({"Miku/G_100.pth": b"latih", "Miku/miku.pth": PTH, "Miku/added_miku.index": INDEX}),
        "halaman.pth": b"<html>bukan file</html>",
    })
    release_server.types["halaman.pth"] = "text/html; charset=utf-8"
    return release_server


def test_fetch_two_links_and_reuse_them_on_retry(links, tmp_path):
    seen = []
    model, index = rvc.fetch(links.url + "miku.pth", links.url + "added_miku.index", tmp_path,
                             lambda name, done, total: seen.append(name))
    assert model.read_bytes() == PTH and index.read_bytes() == INDEX
    assert {"miku.pth", "added_miku.index"} <= set(seen)
    rvc.fetch(links.url + "miku.pth", links.url + "added_miku.index", tmp_path)
    assert len(links.requests) == 2  # Coba lagi: file yang sudah lengkap tidak diunduh ulang


def test_fetch_a_zip_with_both_files(links, tmp_path):
    model, index = rvc.fetch(links.url + "miku.zip", "", tmp_path)
    assert (model.name, model.read_bytes()) == ("miku.pth", PTH)
    assert (index.name, index.read_bytes()) == ("added_miku.index", INDEX)


def test_a_web_page_instead_of_a_file_is_refused(links, tmp_path):
    with pytest.raises(DownloadError, match="halaman web"):
        rvc.fetch(links.url + "halaman.pth", links.url + "added_miku.index", tmp_path)
    assert not list(tmp_path.rglob("halaman.pth"))


def test_files_over_the_limit_are_refused(links, tmp_path, monkeypatch):
    monkeypatch.setattr(rvc, "MAX_BYTES", len(PTH) - 1)
    with pytest.raises(DownloadError, match="lebih besar dari"):
        rvc.fetch(links.url + "miku.pth", links.url + "added_miku.index", tmp_path)
    assert not list(tmp_path.rglob("miku.pth*"))


def test_broken_zip_is_explained(links, tmp_path):
    links.files["rusak.zip"] = b"bukan zip"
    with pytest.raises(DownloadError, match="bukan zip"):
        rvc.fetch(links.url + "rusak.zip", "", tmp_path)


def test_selection_with_links_is_validated_and_counted(tmp_path):
    selection = Selection(tmp_path / "MikuVision", components={"core", "brain", "rvc"},
                          rvc_model_url="https://h/m.zip")
    assert selection.rvc_from_link
    assert validate_selection(selection, lambda folder: True) is None
    with_link = space_needed(selection, gpu=True, ollama_installed=True, environ={})
    selection.rvc_model_url = "https://h/m.pth"
    assert "link file .index" in validate_selection(selection, lambda folder: True)
    selection.rvc_model_url = ""
    assert not selection.rvc_from_link
    assert "Pilih file bobot" in validate_selection(selection, lambda folder: True)
    without = space_needed(selection, gpu=True, ollama_installed=True, environ={})
    drive = next(iter(with_link))
    assert with_link[drive] - without[drive] == pytest.approx(1e9)


@pytest.fixture
def release(release_server):
    data = _zip({"MikuVision-9.9.9/install.ps1": "# palsu"})
    release_server.files.update({
        "version.json": b'{"version": "9.9.9"}',
        "SHA256SUMS": f"{hashlib.sha256(data).hexdigest()}  MikuVision-9.9.9.zip".encode(),
        "MikuVision-9.9.9.zip": data,
    })
    return release_server


def test_runner_downloads_the_rvc_model_before_the_installer(release, links, tmp_path):
    script = tmp_path / "fake_install.py"
    script.write_text("import sys\nfrom pathlib import Path\nPath('args.txt').write_text('\\n'.join(sys.argv[1:]))\n")
    selection = Selection(tmp_path / "MikuVision", components={"core", "brain", "rvc"},
                          rvc_model_url=links.url + "miku.zip")
    run = InstallRunner(queue.Queue(), selection, tmp_path / "downloads", release_url=links.url,
                        command=lambda install_dir, args: [sys.executable, str(script), *args])
    run.start()
    run._thread.join(timeout=30)
    received = []
    while not run.events.empty():
        received.append(run.events.get())
    assert ("progress", {"event": "done", "ok": True}) in received
    assert any(k == "phase" and d["title"].startswith("Mengunduh model RVC") for k, d in received)
    args = (tmp_path / "MikuVision" / "args.txt").read_text().splitlines()
    model_flag, index_flag = ("-RvcModel", "-RvcIndex") if sys.platform == "win32" else ("--rvc-model", "--rvc-index")
    model, index = Path(args[args.index(model_flag) + 1]), Path(args[args.index(index_flag) + 1])
    assert model.read_bytes() == PTH and index.read_bytes() == INDEX
    assert tmp_path / "downloads" in model.parents
    assert install_args(selection, platform="win32")[-4:] == ["-RvcModel", str(model), "-RvcIndex", str(index)]
    assert install_args(selection, platform="linux")[-4:] == ["--rvc-model", str(model), "--rvc-index", str(index)]
