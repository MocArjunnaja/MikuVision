"""Halaman 1: apa itu MikuVision, perkiraan ukuran dan waktu."""

from pathlib import Path

import customtkinter as ctk

from .base import ACCENT, MUTED, Page, heading, paragraph

# Frame pertama sprite Miku; exe (fase I5) membawa salinannya di miku_setup/assets
SPRITE_SHEET = Path(__file__).resolve().parents[2] / "assets" / "avatar" / "miku_smart_sheet.png"
FRAME_SIZE = (177, 213)


def _logo():
    try:
        from PIL import Image
        frame = Image.open(SPRITE_SHEET).convert("RGBA").crop((0, 0, *FRAME_SIZE))
    except (OSError, ImportError):
        return None
    return ctk.CTkImage(light_image=frame, dark_image=frame, size=(118, 142))


class WelcomePage(Page):
    title = "Selamat datang"

    def create(self, frame):
        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x")
        logo = _logo()
        if logo:
            ctk.CTkLabel(row, image=logo, text="").pack(side="left", padx=(0, 18))
        text = ctk.CTkFrame(row, fg_color="transparent")
        text.pack(side="left", fill="x", expand=True)
        heading(text, "Selamat datang di MikuVision")
        paragraph(text, "Asisten desktop berwujud Hatsune Miku: mendengar suara Anda, menjalankan aksi di "
                        "komputer, lalu menjawab dengan suara Miku. Semuanya berjalan di komputer ini.", width=360)

        facts = ctk.CTkFrame(frame, corner_radius=8)
        facts.pack(fill="x", pady=(18, 0))
        for label, value in (
            ("Ruang disk", "±13–17 GB, tergantung komponen dan apakah Ollama sudah ada"),
            ("Waktu", "±20–40 menit, tergantung kecepatan internet"),
            ("Yang dipasang", "Python dan PyTorch, model suara, Ollama, dan model bahasa"),
        ):
            line = ctk.CTkFrame(facts, fg_color="transparent")
            line.pack(fill="x", padx=14, pady=4)
            ctk.CTkLabel(line, text=label, width=110, anchor="w", text_color=MUTED).pack(side="left")
            ctk.CTkLabel(line, text=value, anchor="w").pack(side="left")

        if self.setup.dry_run:
            paragraph(frame, "Mode uji: tidak ada yang diunduh atau dipasang.", color=ACCENT)
