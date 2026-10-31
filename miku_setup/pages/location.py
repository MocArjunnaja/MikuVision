"""Halaman 4: folder aplikasi, folder model, dan komponen; total unduhan vs ruang kosong."""

import os
import shutil
import string
from pathlib import Path
from tkinter import filedialog
from typing import Dict, Optional

import customtkinter as ctk

from ..checks import FAIL, WARN, check_disk, drive_of, drive_root, huggingface_dir, ollama_models_dir
from ..components import COMPONENTS, is_writable, space_needed, validate_selection
from .base import ACCENT, ACCENT_HOVER, MUTED, STATUS_COLORS, Page, heading

APP_FOLDER_NAME = "MikuVision"


def _other_drive_with_space(needed: float, exclude: str) -> Optional[str]:
    """Drive lain yang cukup untuk semuanya, untuk saran 'coba D:\\MikuVision'."""
    for letter in string.ascii_uppercase[2:]:
        drive = f"{letter}:"
        if drive != exclude and os.path.exists(drive + os.sep):
            try:
                if shutil.disk_usage(drive + os.sep).free >= needed:
                    return drive
            except OSError:
                continue
    return None


class LocationPage(Page):
    title = "Lokasi dan komponen"

    def create(self, frame):
        heading(frame, "Lokasi dan komponen")
        selection = self.setup.selection
        grid = ctk.CTkFrame(frame, fg_color="transparent")
        grid.pack(fill="x")
        grid.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(grid, text="Folder aplikasi", anchor="w").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.install_dir = ctk.StringVar(value=str(selection.install_dir))
        ctk.CTkEntry(grid, textvariable=self.install_dir).grid(row=0, column=1, sticky="ew")
        self._browse_button(grid, lambda: self._pick_folder(self.install_dir, APP_FOLDER_NAME)).grid(
            row=0, column=2, padx=(6, 0))

        ollama_dir, hf_dir = ollama_models_dir(), huggingface_dir()
        self.model_mode = ctk.StringVar(value="custom" if selection.model_dir else "default")
        ctk.CTkLabel(grid, text="Folder model", anchor="w").grid(row=1, column=0, sticky="nw", padx=(0, 10), pady=(8, 0))
        modes = ctk.CTkFrame(grid, fg_color="transparent")
        modes.grid(row=1, column=1, columnspan=2, sticky="ew", pady=(8, 0))
        ctk.CTkRadioButton(modes, text=f"Lokasi bawaan: {ollama_dir} dan {hf_dir}", variable=self.model_mode,
                           value="default", fg_color=ACCENT, command=self._changed).pack(anchor="w")
        custom = ctk.CTkFrame(modes, fg_color="transparent")
        custom.pack(fill="x", pady=(4, 0))
        ctk.CTkRadioButton(custom, text="Folder lain:", variable=self.model_mode, value="custom",
                           fg_color=ACCENT, command=self._changed).pack(side="left")
        suggestion = selection.model_dir or Path(drive_root(drive_of(selection.install_dir))) / "MikuVision" / "models"
        self.model_dir = ctk.StringVar(value=str(suggestion))
        ctk.CTkEntry(custom, textvariable=self.model_dir).pack(side="left", fill="x", expand=True, padx=(6, 0))
        self._browse_button(custom, lambda: self._pick_folder(self.model_dir, "models")).pack(side="left", padx=(6, 0))

        self.chosen: Dict[str, ctk.BooleanVar] = {}
        box = ctk.CTkFrame(frame, corner_radius=8)
        box.pack(fill="x", pady=(12, 0))
        for component in COMPONENTS:
            line = ctk.CTkFrame(box, fg_color="transparent")
            line.pack(fill="x", padx=12, pady=3)
            var = ctk.BooleanVar(value=component.required or component.key in selection.components)
            self.chosen[component.key] = var
            check = ctk.CTkCheckBox(line, text=component.title, variable=var, width=190, fg_color=ACCENT,
                                    hover_color=ACCENT_HOVER, command=self._changed)
            check.pack(side="left")
            if component.required:
                check.configure(state="disabled")
            ctk.CTkLabel(line, text=component.size_text, text_color=MUTED, anchor="w").pack(side="left")
            if component.key == "rvc":
                self._create_rvc_row(box)

        self.space = ctk.CTkLabel(frame, text="", anchor="w", justify="left", wraplength=520)
        self.space.pack(fill="x", pady=(10, 0))
        for var in (self.install_dir, self.model_dir):
            var.trace_add("write", lambda *_: self._changed())

    def _create_rvc_row(self, box):
        """Model RVC: file di komputer, atau link unduhan milik user (repo tidak menunjuk ke model tertentu)."""
        selection = self.setup.selection
        self.rvc_row = ctk.CTkFrame(box, fg_color="transparent")
        self.rvc_source = ctk.StringVar(value="link" if selection.rvc_from_link else "file")
        sources = ctk.CTkFrame(self.rvc_row, fg_color="transparent")
        sources.pack(fill="x", padx=(28, 0))
        for value, text in (("file", "File di komputer"), ("link", "Unduh dari link")):
            ctk.CTkRadioButton(sources, text=text, variable=self.rvc_source, value=value, fg_color=ACCENT,
                               command=self._changed).pack(side="left", padx=(0, 16))

        self.rvc_file_row = ctk.CTkFrame(self.rvc_row, fg_color="transparent")
        self.rvc_model = ctk.StringVar(value=selection.rvc_model)
        self.rvc_index = ctk.StringVar(value=selection.rvc_index)
        for var, ext, label in ((self.rvc_model, ".pth", "Pilih file .pth…"),
                                (self.rvc_index, ".index", "Pilih file .index…")):
            ctk.CTkButton(self.rvc_file_row, text=label, width=140, fg_color="transparent", border_width=1,
                          border_color=ACCENT, hover_color=ACCENT_HOVER,
                          command=lambda v=var, e=ext: self._pick_file(v, e)).pack(side="left", padx=(28, 0))
        self.rvc_files = ctk.CTkLabel(self.rvc_file_row, text="", text_color=MUTED, anchor="w")
        self.rvc_files.pack(side="left", padx=8)

        # Tanpa textvariable, karena placeholder customtkinter tidak tampil bila textvariable dipakai
        self.rvc_link_row = ctk.CTkFrame(self.rvc_row, fg_color="transparent")
        self.rvc_model_url = ctk.CTkEntry(self.rvc_link_row, placeholder_text="https://… link file .pth atau .zip")
        self.rvc_index_url = ctk.CTkEntry(self.rvc_link_row,
                                          placeholder_text="https://… link file .index (kosongkan bila pakai .zip)")
        for entry, value in ((self.rvc_model_url, selection.rvc_model_url),
                             (self.rvc_index_url, selection.rvc_index_url)):
            if value:
                entry.insert(0, value)
            entry.bind("<KeyRelease>", lambda _event: self._changed())
            entry.pack(fill="x", padx=(28, 0), pady=(2, 0))
        ctk.CTkLabel(self.rvc_link_row, text="⚠ File .pth bisa menjalankan kode saat dimuat. Tempel hanya link dari "
                     "sumber yang Anda percayai, dan ikuti lisensi pembuat modelnya.", text_color=STATUS_COLORS[WARN],
                     anchor="w", justify="left", wraplength=480).pack(fill="x", padx=(28, 0), pady=(2, 0))

    def _browse_button(self, parent, command):
        return ctk.CTkButton(parent, text="Ganti…", width=70, fg_color="transparent", border_width=1,
                             border_color=ACCENT, hover_color=ACCENT_HOVER, command=command)

    def _pick_folder(self, var: ctk.StringVar, leaf: str):
        chosen = filedialog.askdirectory(parent=self.frame, initialdir=var.get())
        if chosen:
            path = Path(chosen)
            var.set(str(path if path.name.lower() == leaf.lower() else path / leaf))
            if var is self.model_dir:
                self.model_mode.set("custom")

    def _pick_file(self, var: ctk.StringVar, ext: str):
        chosen = filedialog.askopenfilename(parent=self.frame, filetypes=[(f"File {ext}", f"*{ext}")])
        if chosen:
            var.set(str(Path(chosen)))
            self._changed()

    def on_enter(self):
        self._changed()

    def _sync(self):
        """Isi widget -> self.setup.selection."""
        selection = self.setup.selection
        selection.install_dir = Path(self.install_dir.get().strip())
        selection.model_dir = Path(self.model_dir.get().strip()) if self.model_mode.get() == "custom" else None
        selection.components = {key for key, var in self.chosen.items() if var.get()}
        if self.rvc_source.get() == "link":
            selection.rvc_model, selection.rvc_index = "", ""
            selection.rvc_model_url = self.rvc_model_url.get().strip()
            selection.rvc_index_url = self.rvc_index_url.get().strip()
        else:
            selection.rvc_model, selection.rvc_index = self.rvc_model.get(), self.rvc_index.get()
            selection.rvc_model_url, selection.rvc_index_url = "", ""

    def _changed(self):
        self._sync()
        selection = self.setup.selection
        if "rvc" in selection.components:
            self.rvc_row.pack(fill="x", padx=12, pady=(0, 6))
            link = self.rvc_source.get() == "link"
            self.rvc_file_row.pack_forget()
            self.rvc_link_row.pack_forget()
            (self.rvc_link_row if link else self.rvc_file_row).pack(fill="x", pady=(4, 0))
            names = [Path(p).name for p in (selection.rvc_model, selection.rvc_index) if p]
            self.rvc_files.configure(text=", ".join(names) or "belum dipilih")
        else:
            self.rvc_row.pack_forget()
        self.disk = self._disk_check()
        text = self.disk.message
        if self.disk.status == FAIL:
            install_drive = drive_of(selection.install_dir)
            other = _other_drive_with_space(sum(self.needs.values()), install_drive)
            if other:
                text += f". Coba folder di {other}, misalnya {drive_root(other) / APP_FOLDER_NAME}"
        self.space.configure(text=("Ruang: " if self.disk.status != FAIL else "✗ ") + text,
                             text_color=STATUS_COLORS[FAIL] if self.disk.status == FAIL else MUTED)
        self.wizard.refresh()

    def _disk_check(self):
        selection = self.setup.selection
        try:
            self.needs = space_needed(selection, self.setup.gpu, self.setup.ollama_installed)
        except (OSError, ValueError):
            self.needs = {}
        free = {drive: self.wizard.free_bytes(drive_root(drive)) for drive in self.needs}
        return check_disk(self.needs, free)

    def validate(self) -> Optional[str]:
        self._sync()
        problem = validate_selection(self.setup.selection, is_writable)
        if problem:
            return problem
        if self.disk.status == FAIL:
            return f"Ruang disk kurang: {self.disk.message}"
        return None
