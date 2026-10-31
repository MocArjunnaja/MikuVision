"""Halaman 5: unduh dan pasang. Progres dari baris ##MIKU install.ps1 (lihat runner.py)."""

import logging
import os
import queue
import sys
import time
import webbrowser

import customtkinter as ctk

from ..checks import format_gb
from .base import ACCENT, ACCENT_HOVER, MUTED, STATUS_COLORS, Page, heading, paragraph

log = logging.getLogger("miku_setup")
LOG_LINES = 400


def open_folder(path):
    if sys.platform == "win32":
        os.startfile(path)
    else:
        webbrowser.open(path.as_uri())


class InstallPage(Page):
    title = "Unduh dan pasang"

    def __init__(self, wizard):
        super().__init__(wizard)
        self.events: "queue.Queue" = queue.Queue()
        self.runner = None
        self.started_at = 0.0
        self.downloaded = 0

    def create(self, frame):
        heading(frame, "Memasang MikuVision")
        self.step = paragraph(frame, "Menyiapkan…", size=14)
        self.step_color = self.step.cget("text_color")
        self.bar = ctk.CTkProgressBar(frame, progress_color=ACCENT)
        self.bar.set(0)
        self.bar.pack(fill="x", pady=(4, 6))
        self.info = paragraph(frame, "", color=MUTED)
        buttons = ctk.CTkFrame(frame, fg_color="transparent")
        buttons.pack(fill="x", pady=(4, 6))
        self.toggle = ctk.CTkButton(buttons, text="Tampilkan log", width=130, fg_color="transparent", border_width=1,
                                    border_color=ACCENT, hover_color=ACCENT_HOVER, command=self._toggle_log)
        self.toggle.pack(side="left")
        ctk.CTkButton(buttons, text="Buka folder log", width=130, fg_color="transparent", border_width=1,
                      border_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=lambda: open_folder(self.setup.log_path.parent)).pack(side="left", padx=8)
        self.log_box = ctk.CTkTextbox(frame, height=190, font=ctk.CTkFont(family="Consolas", size=11), wrap="none")

    def _toggle_log(self):
        if self.log_box.winfo_ismapped():
            self.log_box.pack_forget()
            self.toggle.configure(text="Tampilkan log")
        else:
            self.log_box.pack(fill="both", expand=True)
            self.toggle.configure(text="Sembunyikan log")

    def on_enter(self):
        if self.runner is None:
            self.start()

    def start(self):
        self.setup.install_ok, self.setup.last_error, self.setup.warnings = None, "", []
        self.downloaded = 0
        self.bar.set(0)
        self.step.configure(text="Menyiapkan…", text_color=self.step_color)
        self.log_box.delete("1.0", "end")
        self.events = queue.Queue()
        self.runner = self.wizard.make_runner(self.events)
        self.runner.start()
        self.started_at = time.monotonic()
        log.info("Instalasi dimulai (dry-run=%s)", self.setup.dry_run)
        self.wizard.refresh()
        self.frame.after(100, self._poll)

    def _poll(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "log":
                    self._log(data)
                elif kind == "phase":
                    # Unduh dan ekstrak kode, sebelum langkah install.ps1
                    self.step.configure(text=data["title"])
                    self.bar.set(0.05 * data.get("fraction", 0))
                elif kind == "downloaded":
                    self.downloaded = data
                elif self._progress(data):
                    return
        except queue.Empty:
            pass
        self._show_info()
        self.frame.after(100, self._poll)

    def _log(self, line: str):
        log.info("install: %s", line)
        self.log_box.insert("end", line + "\n")
        if int(self.log_box.index("end-1c").split(".")[0]) > LOG_LINES:
            self.log_box.delete("1.0", "2.0")
        self.log_box.see("end")

    def _progress(self, event) -> bool:
        """True bila instalasi selesai (berhasil, gagal, atau dibatalkan)."""
        kind = event["event"]
        if kind == "step":
            self.step.configure(text=f"Langkah {event['index']} dari {event['total']}: {event['title']}")
            self.bar.set(0.05 + 0.95 * (event["index"] - 1) / max(event["total"], 1))
        elif kind == "warn":
            self.setup.warnings.append(event.get("message", ""))
        elif kind == "error":
            self.setup.last_error = event.get("message", "")
        elif kind == "done":
            self.setup.install_ok = bool(event.get("ok"))
            if event.get("cancelled"):
                self.setup.last_error = "Instalasi dibatalkan."
            self._finished()
            return True
        return False

    def _show_info(self):
        minutes, seconds = divmod(int(time.monotonic() - self.started_at), 60)
        parts = [f"Berjalan {minutes:02d}:{seconds:02d}"]
        if self.downloaded >= 10e6:
            parts.append(f"{format_gb(self.downloaded)} terunduh")
        if self.setup.warnings:
            parts.append(f"{len(self.setup.warnings)} peringatan")
        self.info.configure(text=" · ".join(parts))

    def _finished(self):
        self._show_info()
        ok = self.setup.install_ok
        log.info("Instalasi selesai: ok=%s, error=%s", ok, self.setup.last_error)
        if ok:
            self.bar.set(1)
            self.step.configure(text="Selesai.")
        else:
            self.step.configure(text=self.setup.last_error or "Instalasi gagal.", text_color=STATUS_COLORS["fail"])
        self.wizard.refresh()
        self.frame.after(800, self.wizard.go_next)

    def reset(self):
        """Untuk Coba lagi: instalasi dijalankan ulang saat halaman ini tampil lagi."""
        self.runner = None

    @property
    def busy(self) -> bool:
        return bool(self.runner and self.runner.running)

    def stop(self):
        if self.runner:
            self.runner.cancel()

    def can_continue(self) -> bool:
        return self.setup.install_ok is not None

    def can_go_back(self) -> bool:
        return False
