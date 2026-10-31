"""Hapus MikuVision: pilih apa yang disimpan, lalu hapus di thread latar (bagian 6)."""

import logging
import queue
import threading
from typing import Optional

import customtkinter as ctk

from ..components import LLM_MODEL
from ..maintenance import RemovalPlan, remove_installation, running_processes
from .base import ACCENT, ACCENT_HOVER, MUTED, STATUS_COLORS, Page, heading, paragraph
from .install import open_folder
from .maintenance import still_running_message

log = logging.getLogger("miku_setup")


class UninstallPage(Page):
    title = "Hapus"
    next_label = "Hapus"

    def create(self, frame):
        app = self.setup.installed
        heading(frame, "Hapus MikuVision")
        paragraph(frame, f"Aplikasi di {app.install_dir}, shortcut-nya, dan entrinya di \"Apps & features\" "
                         "akan dihapus.")
        self.data = ctk.BooleanVar(value=False)
        self.models = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(frame, text="Hapus juga percakapan, memori, dan skill (folder data)", variable=self.data,
                        fg_color=ACCENT, hover_color=ACCENT_HOVER).pack(anchor="w", pady=(8, 2))
        paragraph(frame, "Bila tidak dicentang, folder data disimpan dan dipakai lagi saat MikuVision dipasang "
                         "di folder yang sama.", color=MUTED).pack_configure(padx=(28, 0))
        if app.model_dir:
            ctk.CTkCheckBox(frame, text=f"Hapus juga model di {app.model_dir}", variable=self.models,
                            fg_color=ACCENT, hover_color=ACCENT_HOVER).pack(anchor="w", pady=(8, 2))
        else:
            paragraph(frame, "Model Ollama dan Whisper di lokasi bawaan tidak dihapus, karena bisa dipakai "
                             f"aplikasi lain. Bila tidak dipakai lagi: ollama rm {LLM_MODEL}.", color=MUTED)
        paragraph(frame, "Ollama tetap terpasang. Hapus lewat \"Apps & features\" bila tidak dipakai lagi.",
                  color=MUTED)

    def validate(self) -> Optional[str]:
        if not self.setup.dry_run:
            running = running_processes(self.setup.installed.install_dir)
            if running:
                return still_running_message(running)
        self.setup.removal = RemovalPlan(data=bool(self.data.get()), models=bool(self.models.get()))
        log.info("Hapus: data=%s, model=%s", self.setup.removal.data, self.setup.removal.models)
        return None


class RemovePage(Page):
    title = "Selesai"
    next_label = "Tutup"
    cancellable = False  # file yang setengah terhapus lebih buruk daripada menunggu beberapa detik

    def __init__(self, wizard):
        super().__init__(wizard)
        self.thread: Optional[threading.Thread] = None
        self.done = False
        self.events: "queue.Queue" = queue.Queue()

    def create(self, frame):
        self.head = heading(frame, "Menghapus MikuVision…")
        self.status = paragraph(frame, "", color=MUTED)
        self.details = paragraph(frame, "")

    def on_enter(self):
        if self.thread is None:
            self.thread = threading.Thread(target=self._remove, name="setup-remove", daemon=True)
            self.thread.start()
            self.frame.after(100, self._poll)

    def _remove(self):
        if self.setup.dry_run:
            self.events.put(("done", []))
            return
        try:
            problems = remove_installation(self.setup.installed, self.setup.removal,
                                           lambda text: self.events.put(("status", text)))
        except Exception as e:  # tetap jelaskan, jangan biarkan halaman menunggu selamanya
            log.exception("Hapus gagal tak terduga")
            problems = [f"Error tak terduga: {e}"]
        self.events.put(("done", problems))

    def _poll(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "status":
                    self.status.configure(text=data + "…")
                else:
                    self._finished(data)
                    return
        except queue.Empty:
            pass
        self.frame.after(100, self._poll)

    def _finished(self, problems):
        self.done = True
        self.setup.removal_problems = problems
        if problems:
            self.head.configure(text="Sebagian tidak terhapus")
            self.status.configure(text="File berikut sedang dipakai atau dikunci. Tutup aplikasi yang memakainya, "
                                       "lalu jalankan Hapus lagi dari \"Apps & features\".",
                                  text_color=STATUS_COLORS["warn"])
            self.details.configure(text="\n".join(problems[:6]) + ("\n…" if len(problems) > 6 else ""))
            ctk.CTkButton(self.frame, text="Buka log", width=120, fg_color="transparent", border_width=1,
                          border_color=ACCENT, hover_color=ACCENT_HOVER,
                          command=lambda: open_folder(self.setup.log_path.parent)).pack(anchor="w", pady=6)
        else:
            self.head.configure(text="MikuVision sudah dihapus")
            data = self.setup.installed.install_dir / "data"
            kept = f" Percakapan, memori, dan skill disimpan di {data}." if data.is_dir() else ""
            self.status.configure(text=f"Terima kasih sudah memakai MikuVision.{kept}", text_color=MUTED)
        log.info("Hapus selesai: %d masalah", len(problems))
        self.wizard.refresh()

    @property
    def busy(self) -> bool:
        return bool(self.thread and self.thread.is_alive())

    def can_continue(self) -> bool:
        return self.done

    def can_go_back(self) -> bool:
        return False
