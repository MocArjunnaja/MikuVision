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


def dialog(parent, title: str, message: str, buttons=("OK",), default: int = 0) -> Optional[int]:
    """Dialog modal berbahasa Indonesia; indeks tombol yang ditekan, None bila ditutup.

    messagebox Tk memakai bahasa Windows untuk tombolnya ("Yes"/"No"), jadi dialog dibuat sendiri.
    Tombol pertama berwarna aksen.
    """
    window = ctk.CTkToplevel(parent)
    window.title(title)
    window.resizable(False, False)
    window.transient(parent)
    choice = {"index": None}

    def close(index: Optional[int]):
        choice["index"] = index
        window.grab_release()
        window.destroy()

    ctk.CTkLabel(window, text=message, anchor="w", justify="left", wraplength=360).pack(
        fill="x", padx=20, pady=(18, 14))
    row = ctk.CTkFrame(window, fg_color="transparent")
    row.pack(fill="x", padx=20, pady=(0, 16))
    for index, text in reversed(list(enumerate(buttons))):
        style = dict(fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="#0B1F1E") if index == 0 else \
            dict(fg_color="transparent", border_width=1, border_color=MUTED)
        ctk.CTkButton(row, text=text, width=90, command=lambda i=index: close(i), **style).pack(side="right", padx=(8, 0))
    window.protocol("WM_DELETE_WINDOW", lambda: close(None))
    window.bind("<Return>", lambda _event: close(default))
    window.bind("<Escape>", lambda _event: close(None))
    window.update_idletasks()
    x = parent.winfo_rootx() + (parent.winfo_width() - window.winfo_reqwidth()) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - window.winfo_reqheight()) // 3
    window.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    window.after(50, window.grab_set)  # CTkToplevel baru bisa di-grab setelah tampil
    window.focus_force()
    parent.wait_window(window)
    return choice["index"]


def ask_yes_no(parent, title: str, message: str, yes: str = "Ya", no: str = "Tidak") -> bool:
    return dialog(parent, title, message, (yes, no)) == 0


def paragraph(parent, text: str, color: Optional[str] = None, size: int = 13, width: int = 500) -> ctk.CTkLabel:
    label = ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=size), anchor="w", justify="left",
                         wraplength=width, text_color=color)
    label.pack(fill="x", pady=(0, 6))
    return label


class Page:
    """Satu halaman: dibuat sekali, lalu dimunculkan lagi saat user kembali ke sini."""

    title = ""              # nama di daftar langkah
    next_label = "Lanjut"
    cancellable = True      # False: Batal diabaikan selama busy (misalnya saat menghapus file)

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

    def finish(self):
        """Tombol halaman terakhir (Selesai, Tutup) ditekan; jendela ditutup sesudahnya."""

    @property
    def busy(self) -> bool:
        """Sedang mengerjakan sesuatu yang perlu dihentikan dengan rapi bila user membatalkan."""
        return False

    def stop(self):
        """Hentikan pekerjaan latar (Batal)."""
