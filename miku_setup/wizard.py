"""
Jendela MikuVision Setup (760×520): daftar langkah di kiri, halaman di kanan, tombol di bawah.

Tanpa logika berat: cek sistem dan instalasi berjalan di thread latar dan mengirim hasil lewat
queue.Queue; widget Tk hanya diubah dari main thread (lihat crash Tk 9 di CHANGELOG v1.3.0).
"""

import logging
import sys

import customtkinter as ctk

from . import checks
from .download import RELEASE_URL, fetch_text, parse_version
from .maintenance import register_install, selection_for
from .pages import FLOWS
from .pages.base import ACCENT, ACCENT_HOVER, MUTED, STATUS_COLORS, ask_yes_no
from .pages.install import InstallPage
from .runner import DryRunRunner, InstallRunner, sample_lines
from .state import SetupState

log = logging.getLogger("miku_setup")
# Linux: baris teks Tk (Xft) lebih tinggi, dan halaman 4 bisa memuat izin hak admin
WIDTH, HEIGHT = 760, 520 if sys.platform == "win32" else 580


class Wizard(ctk.CTk):
    def __init__(self, setup: SetupState, check_functions=None, dry_run_delay: float = 0.15,
                 release_url: str = RELEASE_URL, fetch_latest=None):
        ctk.set_appearance_mode("dark")
        super().__init__()
        self.setup = setup
        self.release_url = release_url
        # Bisa diganti test supaya tidak bergantung pada komputer yang menjalankannya
        self.check_functions = checks.SYSTEM_CHECKS if check_functions is None else check_functions
        self.find_ollama = checks.find_ollama
        self.free_bytes = checks.free_bytes
        # Linux: yang dipasang install.sh dengan hak root (halaman 4 meminta izin dulu); Windows: tidak ada
        self.root_needs = checks.root_needs if sys.platform != "win32" else lambda rvc, ollama_installed: []
        # Versi rilis terbaru untuk halaman Pilih tindakan; bisa diganti test supaya tidak ke internet
        self.fetch_latest = fetch_latest or (lambda: parse_version(fetch_text(self.release_url + "version.json")))
        self.dry_run_delay = dry_run_delay

        self.title("MikuVision Setup" + (" (mode uji)" if setup.dry_run else ""))
        self.geometry(f"{WIDTH}x{HEIGHT}")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.page_classes = list(FLOWS[setup.mode])
        self._layout()

        self.pages = [page_class(self) for page_class in self.page_classes]
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
        self.sidebar = sidebar
        self.steps = []
        self._build_steps()

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

    def _build_steps(self):
        for label in self.steps:
            label.destroy()
        self.steps = []
        for page_class in self.page_classes:
            label = ctk.CTkLabel(self.sidebar, text=page_class.title, anchor="w", text_color=MUTED)
            label.pack(fill="x", padx=18, pady=3)
            self.steps.append(label)

    def switch_flow(self, mode: str):
        """Dari halaman Pilih tindakan: sambungkan halaman Perbarui, Perbaiki, atau Hapus setelah halaman ini."""
        self.setup.mode = mode
        if mode in ("update", "repair"):
            self.setup.selection = selection_for(self.setup.installed)
            self.setup.desktop_shortcut = False  # shortcut sudah ada sejak instalasi pertama
            self.setup.launch_now = False
        for index in sorted(i for i in self.built if i > self.index):
            self.pages[index].frame.destroy()
            self.built.discard(index)
        self.page_classes = self.page_classes[:self.index + 1] + list(FLOWS[mode])
        self.pages = self.pages[:self.index + 1] + [page_class(self) for page_class in FLOWS[mode]]
        self._build_steps()

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
            title = self.page_classes[i].title
            if i < self.index:
                label.configure(text=f"✓  {title}", text_color=MUTED, font=self.step_fonts["other"])
            elif i == self.index:
                label.configure(text=f"›  {title}", text_color=ACCENT, font=self.step_fonts["current"])
            else:
                label.configure(text=f"    {title}", text_color=MUTED, font=self.step_fonts["other"])
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
        repair = self.setup.mode == "repair"
        return InstallRunner(events, self.setup.selection, self.setup.log_path.parent / "downloads",
                             release_url=self.release_url, fetch_code=not repair,
                             version=self.setup.installed.version if repair else "", register=register_install)

    def cancel(self):
        if self.index == len(self.pages) - 1:
            self.go_next()
            return
        if self.page.busy and not self.page.cancellable:
            return
        if self.page.busy:
            if ask_yes_no(self, "Hentikan instalasi?",
                          "Instalasi dihentikan dengan rapi. Langkah yang sudah beres tidak diulang "
                          "saat Setup dijalankan lagi.", yes="Hentikan", no="Lanjutkan"):
                log.info("Dibatalkan saat instalasi")
                self.page.stop()
                self.destroy()
            return
        message = "MikuVision belum dipasang." if self.setup.mode == "install" else "Belum ada yang diubah."
        if ask_yes_no(self, "Keluar dari Setup?", message, yes="Keluar", no="Kembali"):
            log.info("Dibatalkan di halaman %d", self.index + 1)
            self.destroy()
