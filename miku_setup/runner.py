"""
Menjalankan instalasi dan meneruskan progresnya ke wizard lewat queue.Queue (widget Tk hanya diubah
dari main thread, seperti gui.py).

install.ps1 -Progress mencetak satu baris "##MIKU {json}" per kejadian: step {index, total, title},
warn/error {message}, done {ok}. Baris lain adalah log biasa.

Kejadian di antrean: ("log", teks), ("progress", kejadian ##MIKU), ("phase", {title, fraction}) untuk
unduh dan ekstrak, dan ("downloaded", byte) selama install.ps1 mengunduh PyTorch dan model.
DryRunRunner memutar ulang stdout nyata dari uji terima I1 (assets/dry_run_stdout.txt).
"""

import json
import logging
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from . import rvc
from .checks import format_gb
from .components import Selection, install_args, model_locations
from .download import RELEASE_URL, Cancelled, DownloadError, download, fetch_text, parse_sha256sums, \
    parse_version, safe_extract, zip_name

log = logging.getLogger("miku_setup")

PREFIX = "##MIKU "
EVENTS = {"step", "warn", "error", "done"}
SAMPLE_LOG = Path(__file__).with_name("assets") / "dry_run_stdout.txt"
SIZE_INTERVAL_SEC = 2.0
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# Kode keluar install.ps1 (docs/PLAN_INSTALLER.md bagian 4)
EXIT_MESSAGES = {
    1: "Instalasi berhenti. Penyebabnya ada di log.",
    2: "Error tak terduga di installer. Kirim log saat melapor.",
}


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


def install_command(install_dir: Path, args: List[str]) -> List[str]:
    """PowerShell tanpa profil; -ExecutionPolicy Bypass hanya untuk proses ini, sama seperti install.bat."""
    return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            str(Path(install_dir) / "install.ps1"), *args]


def received_bytes() -> Optional[int]:
    """Byte yang diterima semua kartu jaringan sejak boot, atau None tanpa psutil.

    Mencakup unduhan aplikasi lain yang berjalan bersamaan, jadi tampil sebagai perkiraan.
    """
    try:
        import psutil
        return psutil.net_io_counters().bytes_recv
    except Exception:  # psutil tidak ada, atau kartu jaringan tidak terbaca
        return None


def folder_size(path: Path) -> int:
    total = 0
    stack = [str(path)]
    while stack:
        try:
            with os.scandir(stack.pop()) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        else:
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


class InstallRunner:
    """Unduh kode rilis → cocokkan SHA256 → ekstrak ke InstallDir → install.ps1 -Progress tanpa konsol.

    Setiap langkah aman diulang: zip yang sudah cocok tidak diunduh lagi, .part dilanjutkan, dan
    install.ps1 melewati langkah yang sudah beres. Jadi "Coba lagi" setelah batal atau gagal melanjutkan.

    fetch_code=False (Perbaiki): kode yang sudah terpasang dipakai, tanpa unduh dan ekstrak. register dipanggil
    setelah install.ps1 berhasil untuk mencatat instalasi di "Apps & features"; kegagalannya hanya peringatan.
    """

    def __init__(self, events: "queue.Queue", selection: Selection, downloads_dir: Path,
                 release_url: str = RELEASE_URL,
                 command: Callable[[Path, List[str]], List[str]] = install_command,
                 fetch_code: bool = True, version: str = "",
                 register: Optional[Callable[[Selection, str], Optional[str]]] = None):
        self.events = events
        self.selection = selection
        self.downloads_dir = Path(downloads_dir)
        self.release_url = release_url if release_url.endswith("/") else release_url + "/"
        self.command = command
        self.fetch_code = fetch_code
        self.version = version
        self.register = register
        self._cancel = threading.Event()
        self._process: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._cancel.clear()
        self._thread = threading.Thread(target=self._run, name="setup-install", daemon=True)
        self._thread.start()

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def cancel(self):
        """Hentikan dengan rapi: unduhan berhenti di blok berikutnya, install.ps1 dan anak prosesnya dimatikan."""
        self._cancel.set()
        process = self._process
        if process and process.poll() is None:
            if sys.platform == "win32":
                # Pohon proses: install.ps1 menjalankan uv, python, dan ollama pull
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True,
                               creationflags=_NO_WINDOW)
            else:
                process.kill()

    def _put(self, kind: str, data):
        self.events.put((kind, data))

    def _fail(self, message: str):
        self._put("progress", {"event": "error", "message": message})
        self._put("progress", {"event": "done", "ok": False})

    def _run(self):
        try:
            if self.fetch_code:
                self._extract(self._fetch())
            self._fetch_rvc()
            self._install()
        except Cancelled:
            self._put("progress", {"event": "done", "ok": False, "cancelled": True})
        except DownloadError as e:
            log.warning("Unduh/ekstrak gagal: %s", e)
            self._fail(str(e))
        except Exception as e:  # tetap jelaskan ke user, jangan biarkan wizard menunggu selamanya
            log.exception("Instalasi gagal tak terduga")
            self._fail(f"Error tak terduga: {e}. Kirim log saat melapor.")

    def _fetch(self) -> Path:
        self._put("phase", {"title": "Memeriksa rilis terbaru", "fraction": 0.0})
        self.version = parse_version(fetch_text(self.release_url + "version.json"))
        name = zip_name(self.version)
        sums = parse_sha256sums(fetch_text(self.release_url + "SHA256SUMS"))
        if name not in sums:
            raise DownloadError(f"SHA256SUMS di rilis {self.version} tidak memuat {name}")
        title = f"Mengunduh MikuVision {self.version}"
        last = [0.0]

        def progress(done: int, total: int):
            now = time.monotonic()
            if now - last[0] >= 0.25 or (total and done >= total):
                last[0] = now
                detail = f"{format_gb(done)}" + (f" dari {format_gb(total)}" if total else "")
                self._put("phase", {"title": f"{title} ({detail})", "fraction": done / total if total else 0.0})

        log.info("Rilis %s dari %s", self.version, self.release_url)
        return download(self.release_url + name, self.downloads_dir / name, sums[name], progress, self._cancel)

    def _extract(self, zip_path: Path):
        if self._cancel.is_set():
            raise Cancelled()
        self._put("phase", {"title": f"Menyalin MikuVision {self.version} ke {self.selection.install_dir}",
                            "fraction": 1.0})
        written = safe_extract(zip_path, self.selection.install_dir)
        self._put("log", f"[setup] {written} file diekstrak ke {self.selection.install_dir}")

    def _fetch_rvc(self):
        """Model RVC dari link user ke downloads/rvc; install.ps1 lalu menyalinnya lewat -RvcModel/-RvcIndex."""
        selection = self.selection
        if "rvc" not in selection.components or not selection.rvc_from_link:
            return
        last = [0.0]

        def progress(name: str, done: int, total: int):
            now = time.monotonic()
            if now - last[0] >= 0.25 or (total and done >= total):
                last[0] = now
                detail = f"{format_gb(done)}" + (f" dari {format_gb(total)}" if total else "")
                self._put("phase", {"title": f"Mengunduh model RVC {name} ({detail})",
                                    "fraction": done / total if total else 0.0})

        # Query link (bisa berisi token) tidak ditulis ke log
        log.info("Model RVC dari link: %s", ", ".join(
            rvc.file_name(url) for url in (selection.rvc_model_url, selection.rvc_index_url) if url))
        model, index = rvc.fetch(selection.rvc_model_url, selection.rvc_index_url, self.downloads_dir, progress,
                                 self._cancel)
        selection.rvc_model, selection.rvc_index = str(model), str(index)
        self._put("log", f"[setup] Model RVC: {model.name}, {index.name}")

    def _size_paths(self) -> List[Path]:
        """Folder yang membesar selama install.ps1 mengunduh: cache uv (PyTorch) dan blob model Ollama."""
        ollama_dir, _ = model_locations(self.selection)
        return [Path(self.selection.install_dir) / ".tools" / "uv-cache", ollama_dir / "blobs"]

    def _watch_sizes(self, stop: threading.Event):
        """Byte yang diterima jaringan sejak install.ps1 mulai.

        Ukuran cache uv tidak dipakai lagi bila psutil ada: cache ikut membesar saat wheel dibongkar dan paket
        dibangun, sehingga angkanya dua kali lipat data internet (uji terima I3).
        """
        measure = received_bytes
        if measure() is None:
            paths = self._size_paths()
            measure = lambda: sum(folder_size(p) for p in paths)  # noqa: E731
        baseline = measure()
        while not stop.wait(SIZE_INTERVAL_SEC):
            self._put("downloaded", max(measure() - baseline, 0))

    def _install(self):
        if self._cancel.is_set():
            raise Cancelled()
        install_dir = Path(self.selection.install_dir)
        command = self.command(install_dir, install_args(self.selection))
        log.info("Menjalankan: %s", " ".join(command))
        try:
            self._process = subprocess.Popen(command, cwd=install_dir, stdout=subprocess.PIPE,
                                             stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                             creationflags=_NO_WINDOW)
        except OSError as e:
            raise DownloadError(f"PowerShell tidak bisa dijalankan: {e}") from e
        stop = threading.Event()
        threading.Thread(target=self._watch_sizes, args=(stop,), name="setup-sizes", daemon=True).start()
        last_error = ""
        try:
            for raw in self._process.stdout:
                line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                event = parse_progress(line)
                if event is None:
                    self._put("log", line)
                elif event["event"] != "done":  # hasil akhir ditentukan kode keluar di bawah
                    if event["event"] == "error":
                        last_error = event.get("message", "")
                    self._put("progress", event)
            code = self._process.wait()
        finally:
            stop.set()
        log.info("install.ps1 selesai dengan kode %s", code)
        if self._cancel.is_set():
            raise Cancelled()
        if code != 0 and not last_error:
            self._put("progress", {"event": "error",
                                   "message": EXIT_MESSAGES.get(code, f"Installer berhenti dengan kode {code}.")})
        if code == 0 and self.register:
            problem = self.register(self.selection, self.version)
            if problem:
                self._put("progress", {"event": "warn", "message": problem})
        self._put("progress", {"event": "done", "ok": code == 0})
