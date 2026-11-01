"""Halaman 3: cek sistem. ✗ menghentikan instalasi, ⚠ boleh lanjut (docs/PLAN_INSTALLER.md bagian 3)."""

import logging
import queue
import sys
import threading

import customtkinter as ctk

from ..checks import FAIL, OK, CheckResult, check_disk, drive_root
from ..components import space_needed
from .base import ACCENT, ACCENT_HOVER, MUTED, STATUS_COLORS, STATUS_ICONS, Page, heading, paragraph

log = logging.getLogger("miku_setup")
CHECKING = "Windows, GPU, internet, Ollama, mikrofon…" if sys.platform == "win32" else \
    "Distro, sesi desktop, GPU, internet, Ollama, mikrofon…"


class SystemCheckPage(Page):
    title = "Cek sistem"

    def __init__(self, wizard):
        super().__init__(wizard)
        self.events: "queue.Queue" = queue.Queue()
        self.running = False
        self.done = False

    def create(self, frame):
        heading(frame, "Cek sistem")
        self.rows = ctk.CTkScrollableFrame(frame, height=270, fg_color="transparent")
        self.rows.pack(fill="both", expand=True)
        self.summary = paragraph(frame, "")
        self.again = ctk.CTkButton(frame, text="Periksa lagi", width=130, fg_color="transparent", border_width=1,
                                   border_color=ACCENT, hover_color=ACCENT_HOVER, command=self.start)
        self.again.pack(anchor="w")

    def on_enter(self):
        if not self.done and not self.running:
            self.start()

    def start(self):
        for child in self.rows.winfo_children():
            child.destroy()
        self.setup.results = []
        self.done, self.running = False, True
        self.pending = self._row(CheckResult("", "Memeriksa", "pending", CHECKING))
        self.summary.configure(text="")
        self.again.configure(state="disabled")
        self.wizard.refresh()
        threading.Thread(target=self._work, name="setup-checks", daemon=True).start()
        self.frame.after(100, self._poll)

    def _work(self):
        """Thread latar: hanya mengisi antrean, tidak menyentuh widget."""
        results = []
        for check in self.wizard.check_functions:
            try:
                batch = check()
            except Exception as e:  # cek yang rusak tidak boleh menghentikan wizard
                log.exception("Cek %s gagal", getattr(check, "__name__", check))
                batch = [CheckResult(getattr(check, "__name__", "cek"), "Cek", "warn", f"Tidak bisa dicek: {e}")]
            results += batch
            self.events.put(("results", batch))
        gpu = any(r.key == "gpu" and r.status == OK for r in results)
        ollama_installed = bool(self.wizard.find_ollama())
        needs = space_needed(self.setup.selection, gpu, ollama_installed)
        free = {drive: self.wizard.free_bytes(drive_root(drive)) for drive in needs}
        disk = check_disk(needs, free)
        self.events.put(("results", [disk]))
        self.events.put(("done", (gpu, ollama_installed)))

    def _poll(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "results":
                    self.setup.results += data
                    for result in data:
                        self._row(result)
                        log.info("Cek %s: %s - %s", result.key, result.status, result.message)
                elif kind == "done":
                    self.setup.gpu, self.setup.ollama_installed = data
                    self._finish()
                    return
        except queue.Empty:
            pass
        self.frame.after(100, self._poll)

    def _row(self, result: CheckResult) -> ctk.CTkFrame:
        row = ctk.CTkFrame(self.rows, fg_color="transparent")
        row.pack(fill="x", pady=3)
        ctk.CTkLabel(row, text=STATUS_ICONS[result.status], width=22, text_color=STATUS_COLORS[result.status],
                     font=ctk.CTkFont(size=15, weight="bold")).pack(side="left", anchor="n")
        ctk.CTkLabel(row, text=result.title, width=110, anchor="w").pack(side="left", anchor="n")
        ctk.CTkLabel(row, text=result.message, anchor="w", justify="left", wraplength=360,
                     text_color=MUTED if result.status == OK else STATUS_COLORS[result.status]).pack(
            side="left", anchor="n", fill="x", expand=True)
        return row

    def _finish(self):
        self.pending.destroy()
        self.running, self.done = False, True
        failed = {r.key for r in self.setup.results if r.status == FAIL}
        if failed - {"disk"}:
            self.summary.configure(text="Instalasi belum bisa dilanjutkan. Perbaiki yang bertanda ✗, lalu "
                                        "tekan Periksa lagi.", text_color=STATUS_COLORS[FAIL])
        elif failed:
            self.summary.configure(text="Ruang di lokasi bawaan kurang. Di langkah berikutnya, pilih folder "
                                        "di drive lain.", text_color=STATUS_COLORS["warn"])
        else:
            self.summary.configure(text="Siap dipasang. Ruang disk dihitung ulang setelah Anda memilih "
                                        "folder dan komponen.", text_color=MUTED)
        self.again.configure(state="normal")
        self.wizard.refresh()

    def can_continue(self) -> bool:
        return self.done and not any(r.status == FAIL and r.key != "disk" for r in self.setup.results)
