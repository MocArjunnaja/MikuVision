"""MikuVision Setup: baris ##MIKU dari install.ps1 dan runner --dry-run."""

import queue
import time

import pytest

from miku_setup import runner
from miku_setup.runner import DryRunRunner, parse_progress


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
