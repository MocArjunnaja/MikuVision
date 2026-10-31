"""
Jendela MikuVision Setup (760×520): daftar langkah di kiri, halaman di kanan, tombol di bawah.

Tanpa logika berat: cek sistem dan instalasi berjalan di thread latar dan mengirim hasil lewat
queue.Queue; widget Tk hanya diubah dari main thread (lihat crash Tk 9 di CHANGELOG v1.3.0).
"""

import logging
from tkinter import messagebox

import customtkinter as ctk

from . import checks
from .pages import PAGES
from .pages.base import ACCENT, ACCENT_HOVER, MUTED, STATUS_COLORS
from .pages.install import InstallPage
from .runner import DryRunRunner, sample_lines
from .state import SetupState

log = logging.getLogger("miku_setup")
WIDTH, HEIGHT = 760, 520


class Wizard(ctk.CTk):
    def __init__(self, setup: SetupState, check_functions=None, dry_run_delay: float = 0.15):
        ctk.set_appearance_mode("dark")
        super().__init__()
        self.setup = setup
        # Bisa diganti test supaya tidak bergantung pada komputer yang menjalankannya
        self.check_functions = checks.SYSTEM_CHECKS if check_functions is None else check_functions
        self.find_ollama = checks.find_ollama
        self.free_bytes = checks.free_bytes
        self.dry_run_delay = dry_run_delay

        self.title("MikuVision Setup" + (" (mode uji)" if setup.dry_run else ""))
        self.geometry(f"{WIDTH}x{HEIGHT}")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self._layout()

        self.pages = [page_class(self) for page_class in PAGES]
        self.built = set()
        self.index = -1
        self.show(0)

    def _layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        sidebar = ctk.CTkFrame(self, width=200, corner_radius=0)
        sidebar.grid(row=0, column=0, rowspan=2, sticky="nsew")
        sidebar.pack_propagate(False)  # lebar tetap, walau judul langkah yang tebal lebih panjang
        ctk.CTkLabel(sidebar, text="MikuVision Setup", text_color=ACCENT,
                     font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=18, pady=(22, 18))
        self.step_fonts = {"current": ctk.CTkFont(weight="bold"), "other": ctk.CTkFont()}
        self.steps = []
        for page_class in PAGES:
            label = ctk.CTkLabel(sidebar, text=page_class.title, anchor="w", text_color=MUTED)
            label.pack(fill="x", padx=18, pady=3)
            self.steps.append(label)

        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew", padx=24, pady=(22, 8))

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=1, column=1, sticky="ew", padx=24, pady=(0, 18))
        self.error = ctk.CTkLabel(bar, text="", text_color=STATUS_COLORS["fail"], anchor="w", justify="left",
                                  wraplength=300)
        self.error.pack(side="left", fill="x", expand=True)
        self.next_button = ctk.CTkButton(bar, text="Lanjut", width=100, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                                         text_color="#0B1F1E", command=self.go_next)
        self.next_button.pack(side="right")
        self.back_button = ctk.CTkButton(bar, text="Kembali", width=90, fg_color="transparent", border_width=1,
                                         border_color=MUTED, command=self.go_back)
        self.back_button.pack(side="right", padx=8)
        self.cancel_button = ctk.CTkButton(bar, text="Batal", width=80, fg_color="transparent",
                                           hover_color="#3A3A3A", command=self.cancel)
        self.cancel_button.pack(side="right")

    @property
    def page(self):
        return self.pages[self.index]

    def show(self, index: int):
        if 0 <= self.index < len(self.pages):
            self.page.frame.pack_forget()
        self.index = index
        if index not in self.built:
            self.page.build(self.content)
            self.built.add(index)
        self.page.frame.pack(fill="both", expand=True)
        self.error.configure(text="")
        log.info("Halaman %d: %s", index + 1, self.page.title)
        self.page.on_enter()
        self.refresh()

    def refresh(self):
        """Status tombol dan daftar langkah; dipanggil halaman setiap kali keadaannya berubah."""
        for i, label in enumerate(self.steps):
            if i < self.index:
                label.configure(text=f"✓  {PAGES[i].title}", text_color=MUTED, font=self.step_fonts["other"])
            elif i == self.index:
                label.configure(text=f"›  {PAGES[i].title}", text_color=ACCENT, font=self.step_fonts["current"])
            else:
                label.configure(text=f"    {PAGES[i].title}", text_color=MUTED, font=self.step_fonts["other"])
        last = self.index == len(self.pages) - 1
        self.next_button.configure(text=self.page.next_label,
                                   state="normal" if self.page.can_continue() else "disabled")
        self.back_button.configure(state="normal" if self.index > 0 and self.page.can_go_back() else "disabled")
        self.cancel_button.configure(state="disabled" if last else "normal")

    def go_next(self):
        if not self.page.can_continue():
            return
        problem = self.page.validate()
        if problem:
            self.error.configure(text=problem)
            return
        if self.index == len(self.pages) - 1:
            self.page.finish()
            self.destroy()
            return
        self.show(self.index + 1)

    def go_back(self):
        if self.index > 0 and self.page.can_go_back():
            self.show(self.index - 1)

    def retry_install(self):
        install = next(i for i, page in enumerate(self.pages) if isinstance(page, InstallPage))
        self.pages[install].reset()
        self.show(install)

    def make_runner(self, events):
        if self.setup.dry_run:
            return DryRunRunner(events, sample_lines(fail=self.setup.dry_run_fail), delay=self.dry_run_delay)
        raise NotImplementedError("Runner install.ps1 menyusul di fase I3")

    def cancel(self):
        if self.index == len(self.pages) - 1:
            self.go_next()
            return
        if self.page.busy:
            if messagebox.askyesno("Hentikan instalasi?",
                                   "Instalasi dihentikan dengan rapi. Langkah yang sudah beres tidak diulang "
                                   "saat Setup dijalankan lagi.", parent=self):
                log.info("Dibatalkan saat instalasi")
                self.page.stop()
                self.destroy()
            return
        if messagebox.askyesno("Keluar dari Setup?", "MikuVision belum dipasang.", parent=self):
            log.info("Dibatalkan di halaman %d", self.index + 1)
            self.destroy()
