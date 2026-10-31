"""Halaman 6: selesai, atau penjelasan gagal dengan Coba lagi dan Buka log."""

import logging

import customtkinter as ctk

from .base import ACCENT, ACCENT_HOVER, MUTED, STATUS_COLORS, Page, heading, paragraph
from .install import open_folder

log = logging.getLogger("miku_setup")


class FinishPage(Page):
    title = "Selesai"

    @property
    def next_label(self) -> str:
        return "Selesai" if self.setup.install_ok else "Tutup"

    def create(self, frame):
        self.body = None

    def on_enter(self):
        if self.body is not None:
            self.body.destroy()
        self.body = ctk.CTkFrame(self.frame, fg_color="transparent")
        self.body.pack(fill="both", expand=True)
        (self._success if self.setup.install_ok else self._failure)(self.body)

    def _success(self, body):
        heading(body, "MikuVision siap")
        paragraph(body, "Tekan Ctrl+Shift+M untuk mulai bicara dari aplikasi mana pun, atau seret maskot Miku.")
        if self.setup.warnings:
            paragraph(body, f"{len(self.setup.warnings)} peringatan selama instalasi, misalnya: "
                            f"{self.setup.warnings[0]}", color=STATUS_COLORS["warn"])
        self.desktop = ctk.BooleanVar(value=self.setup.desktop_shortcut)
        self.launch = ctk.BooleanVar(value=self.setup.launch_now)
        for text, var in (("Buat shortcut di Desktop", self.desktop), ("Jalankan MikuVision sekarang", self.launch)):
            ctk.CTkCheckBox(body, text=text, variable=var, fg_color=ACCENT,
                            hover_color=ACCENT_HOVER).pack(anchor="w", pady=4)

    def _failure(self, body):
        heading(body, "Instalasi belum selesai")
        paragraph(body, self.setup.last_error or "Instalasi berhenti sebelum selesai.", color=STATUS_COLORS["fail"])
        paragraph(body, "Langkah yang sudah beres tidak diulang saat dicoba lagi. Bila masalahnya tetap sama, "
                        "kirimkan log saat melapor.", color=MUTED)
        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.pack(anchor="w", pady=8)
        ctk.CTkButton(buttons, text="Coba lagi", width=120, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=self.wizard.retry_install).pack(side="left")
        ctk.CTkButton(buttons, text="Buka log", width=120, fg_color="transparent", border_width=1,
                      border_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=lambda: open_folder(self.setup.log_path.parent)).pack(side="left", padx=8)

    def can_go_back(self) -> bool:
        return False

    def finish(self):
        """Tombol Selesai. Shortcut desktop dan menjalankan MikuVision menyusul di fase I4."""
        if self.setup.install_ok:
            self.setup.desktop_shortcut = bool(self.desktop.get())
            self.setup.launch_now = bool(self.launch.get())
        log.info("Selesai: ok=%s, shortcut desktop=%s, jalankan=%s%s", self.setup.install_ok,
                 self.setup.desktop_shortcut, self.setup.launch_now,
                 " (dry-run: tidak dijalankan)" if self.setup.dry_run else "")
