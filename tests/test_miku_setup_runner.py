"""MikuVision Setup: baris ##MIKU dari install.ps1, runner --dry-run, dan InstallRunner (fase I3)."""

import hashlib
import queue
import sys
import textwrap
import time
import zipfile

import pytest

from miku_setup import runner
from miku_setup.components import Selection
from miku_setup.runner import DryRunRunner, InstallRunner, parse_progress


@pytest.mark.parametrize("line, event", [
    ('##MIKU {"event":"step","index":3,"total":13,"title":"Model RVC"}',
     {"event": "step", "index": 3, "total": 13, "title": "Model RVC"}),
    ('\ufeff##MIKU {"event":"done","ok":true}\r\n', {"event": "done", "ok": True}),
    # PowerShell 5.1 menulis <, >, & sebagai < dst.
    ('##MIKU {"event":"warn","message":"a \\u003c b"}', {"event": "warn", "message": "a < b"}),
])
def test_parse_progress(line, event):
    assert parse_progress(line) == event


@pytest.mark.parametrize("line", [
    "[15:31:01] [INFO] ==== Cek sistem ====",
    "##MIKU {rusak",
    '##MIKU {"event":"lain"}',
    "##MIKU []",
    "",
])
def test_other_lines_are_logs(line):
    assert parse_progress(line) is None


def test_sample_log_is_a_full_successful_install():
    events = [e for e in map(parse_progress, runner.sample_lines()) if e]
    steps = [e["index"] for e in events if e["event"] == "step"]
    assert steps == list(range(1, 14)) and {e["total"] for e in events if e["event"] == "step"} == {13}
    assert events[-1] == {"event": "done", "ok": True}
    text = "\n".join(runner.sample_lines())
    assert "Arjun" not in text and "02_Research" not in text  # tanpa path pribadi pengembang


def test_failing_sample_stops_with_an_error():
    events = [e for e in map(parse_progress, runner.sample_lines(fail=True)) if e]
    assert events[-2]["event"] == "error" and "paket Python" in events[-2]["message"]
    assert events[-1] == {"event": "done", "ok": False}
    assert max(e["index"] for e in events if e["event"] == "step") < 13


def _drain(events, timeout=5):
    out, deadline = [], time.time() + timeout
    while time.time() < deadline:
        try:
            out.append(events.get(timeout=0.05))
        except queue.Empty:
            if out and out[-1][0] == "progress" and out[-1][1]["event"] == "done":
                return out
    return out


def test_dry_run_runner_replays_logs_and_progress():
    events = queue.Queue()
    lines = ["[t] [INFO] satu", '##MIKU {"event":"step","index":1,"total":1,"title":"A"}',
             '##MIKU {"event":"done","ok":true}']
    DryRunRunner(events, lines, delay=0).start()
    assert _drain(events) == [("log", "[t] [INFO] satu"),
                              ("progress", {"event": "step", "index": 1, "total": 1, "title": "A"}),
                              ("progress", {"event": "done", "ok": True})]


def test_cancelled_dry_run_ends_with_a_cancelled_done():
    events = queue.Queue()
    run = DryRunRunner(events, ["[t] [INFO] x"] * 100, delay=0.05)
    run.start()
    time.sleep(0.12)
    run.cancel()
    received = _drain(events)
    assert received[-1] == ("progress", {"event": "done", "ok": False, "cancelled": True})
    assert len(received) < 100
    run._thread.join(timeout=2)
    assert not run.running


@pytest.fixture
def release(release_server, tmp_path):
    archive = tmp_path / "release.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("MikuVision-9.9.9/install.ps1", "# palsu")
        z.writestr("MikuVision-9.9.9/gui.py", "")
    data = archive.read_bytes()
    release_server.files.update({
        "version.json": b'{"version": "9.9.9"}',
        "SHA256SUMS": f"{hashlib.sha256(data).hexdigest()}  MikuVision-9.9.9.zip".encode(),
        "MikuVision-9.9.9.zip": data,
    })
    return release_server


def install_runner(release, tmp_path, body):
    """InstallRunner dengan skrip Python pengganti install.ps1; skrip mencatat argumennya di args.txt."""
    script = tmp_path / "fake_install.py"
    script.write_text("import sys, time\nfrom pathlib import Path\n"
                      "Path('args.txt').write_text(' '.join(sys.argv[1:]))\n" + textwrap.dedent(body))
    selection = Selection(tmp_path / "MikuVision", model_dir=tmp_path / "models")
    return InstallRunner(queue.Queue(), selection, tmp_path / "downloads", release_url=release.url.rstrip("/"),
                         command=lambda install_dir, args: [sys.executable, str(script), *args])


def progress(received, kind):
    return [data for k, data in received if k == "progress" and data["event"] == kind]


SUCCESS = """
    print("[t] [INFO] mulai", flush=True)
    print('##MIKU {"event":"step","index":1,"total":1,"title":"PyTorch"}', flush=True)
    print('##MIKU {"event":"done","ok":true}', flush=True)
"""


def test_install_downloads_extracts_and_runs_the_installer(release, tmp_path):
    run = install_runner(release, tmp_path, SUCCESS)
    run.start()
    received = _drain(run.events, timeout=30)
    install_dir = tmp_path / "MikuVision"
    assert (install_dir / "install.ps1").is_file() and (install_dir / "gui.py").is_file()
    args = (install_dir / "args.txt").read_text()
    assert args.startswith("-Yes -Progress") and "-ModelDir" in args
    assert any(k == "phase" and "Mengunduh MikuVision 9.9.9" in d["title"] for k, d in received)
    assert ("log", "[t] [INFO] mulai") in received
    assert progress(received, "step") == [{"event": "step", "index": 1, "total": 1, "title": "PyTorch"}]
    assert progress(received, "done") == [{"event": "done", "ok": True}]

    run.start()  # Coba lagi: zip yang sudah cocok tidak diunduh ulang
    assert progress(_drain(run.events, timeout=30), "done") == [{"event": "done", "ok": True}]
    assert [path for path, _ in release.requests].count("/MikuVision-9.9.9.zip") == 1


def test_exit_code_without_an_error_event_is_explained(release, tmp_path):
    run = install_runner(release, tmp_path, "sys.exit(2)")
    run.start()
    received = _drain(run.events, timeout=30)
    assert [e["message"] for e in progress(received, "error")] == [runner.EXIT_MESSAGES[2]]
    assert progress(received, "done") == [{"event": "done", "ok": False}]


def test_installer_error_is_passed_on_once(release, tmp_path):
    run = install_runner(release, tmp_path, """
        print('##MIKU {"event":"error","message":"Build Tools belum ada"}', flush=True)
        print('##MIKU {"event":"done","ok":false}', flush=True)
        sys.exit(1)
    """)
    run.start()
    received = _drain(run.events, timeout=30)
    assert [e["message"] for e in progress(received, "error")] == ["Build Tools belum ada"]
    assert progress(received, "done") == [{"event": "done", "ok": False}]


@pytest.mark.parametrize("sums, message", [
    ("0" * 64 + "  MikuVision-9.9.9.zip", "checksum"),
    ("0" * 64 + "  MikuVision-1.0.0.zip", "tidak memuat"),
])
def test_bad_release_stops_before_installing(release, tmp_path, sums, message):
    release.files["SHA256SUMS"] = sums.encode()
    run = install_runner(release, tmp_path, SUCCESS)
    run.start()
    received = _drain(run.events, timeout=30)
    assert message in progress(received, "error")[0]["message"]
    assert progress(received, "done") == [{"event": "done", "ok": False}]
    assert not (tmp_path / "MikuVision" / "args.txt").exists()


def test_cancel_stops_the_installer_process(release, tmp_path):
    run = install_runner(release, tmp_path, """
        print('##MIKU {"event":"step","index":1,"total":2,"title":"PyTorch"}', flush=True)
        time.sleep(60)
    """)
    run.start()
    deadline = time.time() + 30
    while not run._process or run._process.poll() is not None:
        assert time.time() < deadline, "install palsu tidak mulai"
        time.sleep(0.05)
    run.cancel()
    received = _drain(run.events, timeout=15)
    assert received[-1] == ("progress", {"event": "done", "ok": False, "cancelled": True})
    run._thread.join(timeout=5)
    assert not run.running and run._process.poll() is not None


def test_download_size_comes_from_the_network_counter(release, tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "SIZE_INTERVAL_SEC", 0.05)
    counter = iter(range(1_000_000_000, 10**12, 2_000_000))  # +2 MB per bacaan
    monkeypatch.setattr(runner, "received_bytes", lambda: next(counter))
    run = install_runner(release, tmp_path, """
        Path(".tools/uv-cache").mkdir(parents=True)
        Path(".tools/uv-cache/torch.whl").write_bytes(b"x" * 50_000_000)  # cache tidak dihitung
        time.sleep(0.5)
    """)
    run.start()
    sizes = [d for k, d in _drain(run.events, timeout=30) if k == "downloaded"]
    assert sizes and sizes == sorted(sizes) and sizes[0] == 2_000_000 and max(sizes) < 50_000_000


def test_download_size_falls_back_to_folder_sizes_without_psutil(release, tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "SIZE_INTERVAL_SEC", 0.05)
    monkeypatch.setattr(runner, "received_bytes", lambda: None)
    run = install_runner(release, tmp_path, """
        Path(".tools/uv-cache").mkdir(parents=True)
        Path(".tools/uv-cache/torch.whl").write_bytes(b"x" * 3_000_000)
        time.sleep(0.5)
    """)
    run.start()
    received = _drain(run.events, timeout=30)
    assert max(d for k, d in received if k == "downloaded") >= 3_000_000
