"""
Menjalankan instalasi dan meneruskan progresnya ke wizard lewat queue.Queue (widget Tk hanya diubah
dari main thread, seperti gui.py).

install.ps1 -Progress mencetak satu baris "##MIKU {json}" per kejadian: step {index, total, title},
warn/error {message}, done {ok}. Baris lain adalah log biasa. Fase I2 hanya punya DryRunRunner, yang
memutar ulang stdout nyata dari uji terima I1 (assets/dry_run_stdout.txt); runner install.ps1 menyusul di I3.
"""

import json
import queue
import threading
from pathlib import Path
from typing import Dict, List, Optional

PREFIX = "##MIKU "
EVENTS = {"step", "warn", "error", "done"}
SAMPLE_LOG = Path(__file__).with_name("assets") / "dry_run_stdout.txt"


def parse_progress(line: str) -> Optional[Dict]:
    """Baris "##MIKU {json}" -> dict kejadian; None untuk baris log biasa atau JSON rusak."""
    line = line.lstrip("\ufeff").strip()
    if not line.startswith(PREFIX):
        return None
    try:
        event = json.loads(line[len(PREFIX):])
    except ValueError:
        return None
    return event if isinstance(event, dict) and event.get("event") in EVENTS else None


def sample_lines(fail: bool = False) -> List[str]:
    """Log contoh untuk --dry-run. fail=True: berhenti di langkah PyTorch dengan error yang dijelaskan."""
    lines = SAMPLE_LOG.read_text(encoding="utf-8").splitlines()
    if not fail:
        return lines
    cut = next(i for i, line in enumerate(lines) if '"title":"PyTorch' in line) + 1
    message = "Instalasi paket Python gagal. Lihat detail di log."
    return lines[:cut] + [
        f"[15:33:10] [ERROR] {message}",
        PREFIX + json.dumps({"event": "error", "message": message}),
        "[15:33:10] [ERROR] Instalasi berhenti. Perbaiki masalah di atas lalu jalankan installer lagi.",
        PREFIX + json.dumps({"event": "done", "ok": False}),
    ]


class DryRunRunner:
    """Memutar ulang log contoh di thread latar: ("log", teks) dan ("progress", kejadian) ke events."""

    def __init__(self, events: "queue.Queue", lines: Optional[List[str]] = None, delay: float = 0.15):
        self.events = events
        self.lines = sample_lines() if lines is None else lines
        self.delay = delay
        self._cancel = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._cancel.clear()
        self._thread = threading.Thread(target=self._run, name="setup-dry-run", daemon=True)
        self._thread.start()

    def cancel(self):
        self._cancel.set()

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _run(self):
        for line in self.lines:
            if self._cancel.wait(self.delay):
                self.events.put(("progress", {"event": "done", "ok": False, "cancelled": True}))
                return
            event = parse_progress(line)
            self.events.put(("progress", event) if event else ("log", line))
