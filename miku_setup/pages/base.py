"""Dasar halaman wizard dan gaya bersama."""

from typing import Optional

import customtkinter as ctk

ACCENT = "#39C5BB"          # theme_color Miku di config.py, sama dengan GUI MikuVision
ACCENT_HOVER = "#2E9E96"
MUTED = "#9AA5A4"
STATUS_COLORS = {"ok": "#4CC38A", "warn": "#E5B454", "fail": "#F26B6B", "pending": MUTED}
STATUS_ICONS = {"ok": "✓", "warn": "⚠", "fail": "✗", "pending": "…"}


def heading(parent, text: str) -> ctk.CTkLabel:
    label = ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=20, weight="bold"), anchor="w")
    label.pack(fill="x", pady=(0, 8))
    return label


def paragraph(parent, text: str, color: Optional[str] = None, size: int = 13, width: int = 500) -> ctk.CTkLabel:
    label = ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=size), anchor="w", justify="left",
                         wraplength=width, text_color=color)
    label.pack(fill="x", pady=(0, 6))
    return label


class Page:
    """Satu halaman: dibuat sekali, lalu dimunculkan lagi saat user kembali ke sini."""

    title = ""              # nama di daftar langkah
    next_label = "Lanjut"

    def __init__(self, wizard):
        self.wizard = wizard
        self.setup = wizard.setup
        self.frame: Optional[ctk.CTkFrame] = None

    def build(self, parent) -> ctk.CTkFrame:
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.create(self.frame)
        return self.frame

    def create(self, frame: ctk.CTkFrame):
        """Isi halaman; dipanggil sekali."""

    def on_enter(self):
        """Setiap kali halaman ini tampil."""

    def can_continue(self) -> bool:
        return True

    def can_go_back(self) -> bool:
        return True

    def validate(self) -> Optional[str]:
        """Pesan bila belum boleh lanjut; dipanggil saat tombol Lanjut ditekan."""
        return None

    @property
    def busy(self) -> bool:
        """Sedang mengerjakan sesuatu yang perlu dihentikan dengan rapi bila user membatalkan."""
        return False

    def stop(self):
        """Hentikan pekerjaan latar (Batal)."""
