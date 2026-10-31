"""Setup dibuka lagi saat MikuVision sudah terpasang: Perbarui, Perbaiki, atau Hapus (bagian 6)."""

import logging
import queue
import threading
from typing import Optional

import customtkinter as ctk

from ..maintenance import running_processes
from .base import ACCENT, MUTED, STATUS_COLORS, Page, heading, paragraph

log = logging.getLogger("miku_setup")

CHOICES = (
    ("update", "Perbarui", "Unduh rilis terbaru. Percakapan, memori, skill, dan model tetap ada."),
    ("repair", "Perbaiki", "Jalankan ulang pemasangan dengan pilihan yang sama, tanpa mengunduh kode lagi."),
    ("uninstall", "Hapus", "Hapus MikuVision dari komputer ini. Anda memilih apa yang disimpan."),
)


def still_running_message(names) -> str:
    return f"Tutup MikuVision dulu ({', '.join(names)} masih berjalan), lalu tekan Lanjut lagi"


class MaintenancePage(Page):
    title = "Pilih tindakan"

    def create(self, frame):
        app = self.setup.installed
        heading(frame, "MikuVision sudah terpasang")
        paragraph(frame, f"Versi {app.version or 'tidak diketahui'} di {app.install_dir}", color=MUTED)
        self.latest = paragraph(frame, "Memeriksa versi terbaru…", color=MUTED)
        self.choice = ctk.StringVar(value=self.setup.mode if self.setup.mode in ("repair", "uninstall") else "update")
        self.radios = {}
        for key, title, description in CHOICES:
            radio = ctk.CTkRadioButton(frame, text=title, variable=self.choice, value=key, fg_color=ACCENT,
                                       font=ctk.CTkFont(weight="bold"))
            radio.pack(anchor="w", pady=(10, 0))
            self.radios[key] = radio
            paragraph(frame, description, color=MUTED).pack_configure(padx=(28, 0))
        self.events: "queue.Queue" = queue.Queue()
        threading.Thread(target=self._check_latest, name="setup-latest", daemon=True).start()
        self.frame.after(100, self._poll)

    def _check_latest(self):
        try:
            self.events.put(("latest", self.wizard.fetch_latest()))
        except Exception as e:  # offline, rilis tanpa version.json: Perbarui tetap bisa dicoba
            log.warning("Versi terbaru tidak terbaca: %s", e)
            self.events.put(("latest", None))

    def _poll(self):
        try:
            _, latest = self.events.get_nowait()
        except queue.Empty:
            self.frame.after(100, self._poll)
            return
        installed = self.setup.installed.version
        self.setup.latest_version = latest or ""
        if latest is None:
            self.latest.configure(text="Versi terbaru tidak bisa diperiksa (offline?). Perbarui tetap bisa dicoba.",
                                  text_color=STATUS_COLORS["warn"])
        elif latest == installed:
            self.latest.configure(text=f"Sudah versi terbaru ({latest}).")
            self.radios["update"].configure(state="disabled")
            if self.choice.get() == "update":
                self.choice.set("repair")
        else:
            self.latest.configure(text=f"Versi terbaru: {latest}", text_color=STATUS_COLORS["ok"])
            self.radios["update"].configure(text=f"Perbarui ke {latest}")

    def validate(self) -> Optional[str]:
        choice = self.choice.get()
        if not self.setup.dry_run:
            running = running_processes(self.setup.installed.install_dir)
            if running:
                return still_running_message(running)
        log.info("Tindakan dipilih: %s", choice)
        self.wizard.switch_flow(choice)
        return None
