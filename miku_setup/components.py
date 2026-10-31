"""
Komponen yang bisa dipilih di halaman 4, ukurannya, dan argumen install.ps1 yang sesuai.

Ukuran diukur di laptop pengembang (31 Okt 2026, Windows 11, PyTorch CUDA 12.8); perbarui tiap rilis
bila berubah. Ukuran folder aplikasi dihitung dengan hardlink sekali saja (cache uv di-hardlink ke .venv).
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

from .checks import drive_of, huggingface_dir, model_present, ollama_models_dir
from .rvc import link_problem

GB = 1e9
# Sama dengan OLLAMA_MODEL dan VISION_MODEL di config.py (dicek test). Exe setup tidak membawa config.py
LLM_MODEL = "qwen3:4b-instruct"
VISION_MODEL = "qwen3-vl:4b-instruct"
# Cadangan ruang di tiap drive di atas total unduhan (docs/PLAN_INSTALLER.md bagian 3, halaman 4)
MARGIN_GB = 2.0
# .venv + .tools dengan PyTorch CUDA (8,8 GB, tanpa dependency RVC); PyTorch CPU ±3,8 GB lebih kecil (perkiraan)
CORE_APP_GB = 8.8
CORE_APP_GB_CPU = 5.0
# Whisper large-v3-turbo + MeloTTS dan BERT-nya di cache Hugging Face
SPEECH_MODELS_GB = 1.9
# %LOCALAPPDATA%\Programs\Ollama setelah dipasang
OLLAMA_APP_GB = 3.3
LLM_GB = 2.5
VISION_GB = 3.3
# rvc-python + fairseq di .venv; file model RVC milik user dihitung terpisah
RVC_APP_GB = 0.8
# Model RVC dari link: ukurannya baru diketahui saat diunduh (.pth ±55 MB, index dan zip sampai ±1 GB)
RVC_LINK_GB = 1.0


@dataclass(frozen=True)
class Component:
    key: str
    title: str
    description: str
    size_text: str
    required: bool = False


COMPONENTS: List[Component] = [
    Component("core", "Inti", "Suara, GUI, dan aksi desktop: Python, PyTorch, Whisper, MeloTTS",
              "±10,7 GB (±6,9 GB tanpa GPU NVIDIA)", required=True),
    Component("brain", "Otak Miku", f"Ollama dan model {LLM_MODEL}", "±2,5 GB (+3,3 GB bila Ollama belum ada)",
              required=True),
    Component("vision", "Membaca layar", f"Model {VISION_MODEL}: \"error apa ini?\", \"bacakan tulisan di layar\"",
              "±3,3 GB"),
    Component("rvc", "Suara khas Miku (RVC)", "Model RVC pilihan Anda: file .pth dan .index, atau link unduhannya",
              "±0,8 GB + file model"),
]


@dataclass
class Selection:
    """Pilihan di halaman 4."""
    install_dir: Path
    model_dir: Optional[Path] = None      # None = lokasi bawaan Ollama dan Hugging Face (atau OLLAMA_MODELS/HF_HOME)
    components: Set[str] = field(default_factory=lambda: {"core", "brain"})
    rvc_model: str = ""
    rvc_index: str = ""
    # Diisi bila model RVC diunduh dari link; rvc_model/rvc_index diisi runner setelah diunduh
    rvc_model_url: str = ""
    rvc_index_url: str = ""

    @property
    def rvc_from_link(self) -> bool:
        return bool(self.rvc_model_url or self.rvc_index_url)


def default_install_dir(environ: Optional[Dict[str, str]] = None) -> Path:
    """%LOCALAPPDATA%\\Programs\\MikuVision: per-user, tanpa admin (keputusan 3, bagian 11)."""
    environ = os.environ if environ is None else environ
    base = environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Programs" / "MikuVision"


def model_locations(selection: Selection, environ: Optional[Dict[str, str]] = None) -> Tuple[Path, Path]:
    """(folder model Ollama, cache Hugging Face) yang akan dipakai, sama seperti install.ps1 -ModelDir."""
    if selection.model_dir:
        return Path(selection.model_dir) / "ollama", Path(selection.model_dir) / "huggingface"
    return ollama_models_dir(environ), huggingface_dir(environ)


def space_needed(selection: Selection, gpu: bool, ollama_installed: bool,
                 environ: Optional[Dict[str, str]] = None,
                 rvc_file_size: Callable[[str], int] = lambda path: os.path.getsize(path) if path else 0,
                 ) -> Dict[str, float]:
    """Byte yang dibutuhkan per drive, sudah termasuk MARGIN_GB di tiap drive yang dipakai.

    Model Ollama yang sudah diunduh tidak dihitung lagi.
    """
    environ = os.environ if environ is None else environ
    ollama_dir, hf_dir = model_locations(selection, environ)
    needs: Dict[str, float] = {}

    def add(path: Path, size_gb: float):
        needs[drive_of(path)] = needs.get(drive_of(path), 0) + size_gb * GB

    add(selection.install_dir, CORE_APP_GB if gpu else CORE_APP_GB_CPU)
    add(hf_dir, SPEECH_MODELS_GB)
    if not ollama_installed:
        add(Path(environ.get("LOCALAPPDATA") or Path.home()), OLLAMA_APP_GB)
    if not model_present(ollama_dir, LLM_MODEL):
        add(ollama_dir, LLM_GB)
    if "vision" in selection.components and not model_present(ollama_dir, VISION_MODEL):
        add(ollama_dir, VISION_GB)
    if "rvc" in selection.components:
        add(selection.install_dir, RVC_APP_GB)
        if selection.rvc_from_link:
            add(selection.install_dir, RVC_LINK_GB)
        for path in ([] if selection.rvc_from_link else (selection.rvc_model, selection.rvc_index)):
            try:
                needs[drive_of(selection.install_dir)] += rvc_file_size(path)
            except OSError:
                pass
    return {drive: size + MARGIN_GB * GB for drive, size in needs.items()}


def validate_selection(selection: Selection, is_writable: Callable[[Path], bool]) -> Optional[str]:
    """Pesan untuk user bila pilihan di halaman 4 belum bisa dipakai, atau None. Ruang disk dicek terpisah."""
    folders = [("Folder aplikasi", selection.install_dir)]
    if selection.model_dir:
        folders.append(("Folder model", selection.model_dir))
    for label, folder in folders:
        text = str(folder)
        if not text.strip():
            return f"{label} belum diisi"
        if '"' in text:
            return f"{label} tidak boleh berisi tanda kutip"
        if not Path(text).is_absolute():
            return f"{label} harus lengkap dengan drive, misalnya D:\\MikuVision"
        if not is_writable(Path(text)):
            return f"{label} tidak bisa ditulis: {text}. Pilih folder lain (bukan C:\\Program Files)"
    if "rvc" in selection.components and selection.rvc_from_link:
        return link_problem(selection.rvc_model_url, selection.rvc_index_url)
    if "rvc" in selection.components:
        for path, ext, label in ((selection.rvc_model, ".pth", "bobot"), (selection.rvc_index, ".index", "index")):
            if not path:
                return f"Pilih file {label} RVC ({ext}), atau hilangkan centang Suara khas Miku"
            if Path(path).suffix.lower() != ext or not Path(path).is_file():
                return f"File {label} RVC harus file {ext} yang ada: {path}"
    return None


def is_writable(folder: Path) -> bool:
    """Bisa membuat folder (atau induk terdekatnya) dan menulis file sementara di dalamnya."""
    probe = Path(folder)
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    test_file = probe / ".mikuvision-setup-test"
    try:
        test_file.write_bytes(b"")
        test_file.unlink()
        return True
    except OSError:
        return False


def install_args(selection: Selection) -> List[str]:
    """Argumen install.ps1 untuk pilihan ini (dipakai runner di fase I3).

    Shortcut desktop dibuat wizard di halaman Selesai (fase I4), jadi install.ps1 hanya membuat shortcut
    Start Menu. Persetujuan untuk memasang Git/Ollama sudah diberikan di halaman 4 (-Yes).
    """
    args = ["-Yes", "-Progress", "-StartMenu", "-SkipShortcut"]
    if selection.model_dir:
        args += ["-ModelDir", str(selection.model_dir)]
    if "vision" in selection.components:
        args.append("-WithVision")
    if "rvc" in selection.components:
        args += ["-RvcModel", selection.rvc_model, "-RvcIndex", selection.rvc_index]
    return args
