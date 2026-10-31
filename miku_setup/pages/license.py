"""Halaman 2: lisensi karakter, wajib dicentang (keputusan 2, docs/PLAN_INSTALLER.md bagian 11)."""

import webbrowser

import customtkinter as ctk

from .base import ACCENT, ACCENT_HOVER, Page, heading

README_LICENSE_URL = "https://github.com/MocArjunnaja/MikuVision#lisensi--kredit"

SUMMARY = (
    "Hatsune Miku © Crypton Future Media, INC. Karakter ini dipakai di bawah Piapro Character License "
    "(PCL).\n\n"
    "• MikuVision hanya untuk penggunaan non-komersial: tanpa tujuan bisnis dan tanpa menerima bayaran.\n"
    "• Penggunaan komersial butuh izin Crypton.\n"
    "• Jangan memakai karakter dalam konteks yang merusak nama baiknya, misalnya terlalu kasar atau seksual.\n"
    "• Model suara RVC tidak disertakan. Bila Anda memakai model sendiri, ikuti lisensi pembuatnya dan "
    "jangan mendistribusikannya; file .pth juga bisa menjalankan kode, jadi pakai hanya dari sumber "
    "yang Anda percayai.\n\n"
    "Ringkasan ini bukan nasihat hukum."
)


class LicensePage(Page):
    title = "Lisensi karakter"

    def create(self, frame):
        heading(frame, "Lisensi karakter")
        box = ctk.CTkTextbox(frame, height=230, wrap="word", font=ctk.CTkFont(size=13))
        box.insert("1.0", SUMMARY)
        box.configure(state="disabled")
        box.pack(fill="x")
        ctk.CTkButton(frame, text="Baca lengkap di README", fg_color="transparent", border_width=1,
                      border_color=ACCENT, hover_color=ACCENT_HOVER, width=200,
                      command=lambda: webbrowser.open(README_LICENSE_URL)).pack(anchor="w", pady=10)
        self.accepted = ctk.BooleanVar(value=self.setup.license_accepted)
        ctk.CTkCheckBox(frame, text="Saya mengerti dan memakai MikuVision untuk keperluan non-komersial",
                        variable=self.accepted, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                        command=self._changed).pack(anchor="w", pady=(4, 0))

    def _changed(self):
        self.setup.license_accepted = bool(self.accepted.get())
        self.wizard.refresh()

    def can_continue(self) -> bool:
        return self.setup.license_accepted
