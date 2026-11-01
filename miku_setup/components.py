"""
Komponen yang bisa dipilih di halaman 4, ukurannya, dan argumen install.ps1 (Linux: install.sh) yang sesuai.

Ukuran diukur di laptop pengembang (31 Okt 2026, Windows 11, PyTorch CUDA 12.8); perbarui tiap rilis
bila berubah. Ukuran folder aplikasi dihitung dengan hardlink sekali saja (cache uv di-hardlink ke .venv).
"""

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

from . import checks
from .checks import WINDOWS_FILESYSTEMS, drive_of, filesystem_of, huggingface_dir, model_present, ollama_models_dir
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
# %LOCALAPPDATA%\Programs\Ollama setelah dipasang (Linux: /usr/local, installer resmi)
OLLAMA_APP_GB = 3.3
OLLAMA_APP_DIR_LINUX = Path("/usr/local")
LLM_GB = 2.5
VISION_GB = 3.3
# rvc-python + fairseq di .venv; file model RVC milik user dihitung terpisah
RVC_APP_GB = 0.8
# Model RVC dari link: ukurannya baru diketahui saat diunduh (.pth ±55 MB, index dan zip sampai ±1 GB)
RVC_LINK_GB = 1.0
# Linux: karakter yang merusak baris Exec peluncur .desktop atau file environment.d bila ada di path
LINUX_BAD_CHARS = '"\\`$%\n'


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


def default_install_dir(environ: Optional[Dict[str, str]] = None, platform: str = sys.platform) -> Path:
    """%LOCALAPPDATA%\\Programs\\MikuVision: per-user, tanpa admin (keputusan 3, bagian 11).

    Linux: ~/.local/share/mikuvision/app (di partisi Linux; venv di NTFS lambat).
    """
    environ = os.environ if environ is None else environ
    if platform != "win32":
        base = environ.get("XDG_DATA_HOME") or str(Path(environ.get("HOME") or Path.home()) / ".local" / "share")
        return Path(base) / "mikuvision" / "app"
    base = environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Programs" / "MikuVision"


def model_locations(selection: Selection, environ: Optional[Dict[str, str]] = None) -> Tuple[Path, Path]:
    """(folder model Ollama, cache Hugging Face) yang akan dipakai, sama seperti install.ps1 -ModelDir.

    Linux: Ollama yang berjalan (atau akan berjalan) sebagai layanan sistem tetap memakai foldernya sendiri;
    install.sh --model-dir hanya memindah cache Hugging Face.
    """
    hf_dir = Path(selection.model_dir) / "huggingface" if selection.model_dir else huggingface_dir(environ)
    service = checks.ollama_service_dir() if sys.platform != "win32" else None
    if service:
        return service, hf_dir
    if selection.model_dir:
        return Path(selection.model_dir) / "ollama", hf_dir
    return ollama_models_dir(environ), hf_dir


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
        add(OLLAMA_APP_DIR_LINUX if sys.platform != "win32" else Path(environ.get("LOCALAPPDATA") or Path.home()),
            OLLAMA_APP_GB)
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


def validate_selection(selection: Selection, is_writable: Callable[[Path], bool], platform: str = sys.platform,
                       filesystem: Callable[[Path], str] = filesystem_of, home: Optional[Path] = None) -> Optional[str]:
    """Pesan untuk user bila pilihan di halaman 4 belum bisa dipakai, atau None. Ruang disk dicek terpisah."""
    linux = platform != "win32"
    folders = [("Folder aplikasi", selection.install_dir)]
    if selection.model_dir:
        folders.append(("Folder model", selection.model_dir))
    for label, folder in folders:
        text = str(folder)
        if not text.strip():
            return f"{label} belum diisi"
        if '"' in text:
            return f"{label} tidak boleh berisi tanda kutip"
        if linux and any(char in text for char in LINUX_BAD_CHARS):
            return f"{label} tidak boleh berisi karakter \\ ` $ %"
        if not Path(text).is_absolute():
            if linux:
                return f"{label} harus path lengkap, misalnya {Path.home() / 'MikuVision'}"
            return f"{label} harus lengkap dengan drive, misalnya D:\\MikuVision"
        if not is_writable(Path(text)):
            if linux:
                return f"{label} tidak bisa ditulis: {text}. Pilih folder di dalam folder home Anda"
            return f"{label} tidak bisa ditulis: {text}. Pilih folder lain (bukan C:\\Program Files)"
    for label, folder in folders:
        problem = _folder_use_problem(label, Path(str(folder)), folder is selection.install_dir, home)
        if problem:
            return problem
    if linux and filesystem(Path(selection.install_dir)) in WINDOWS_FILESYSTEMS:
        return (f"Folder aplikasi ada di partisi Windows (NTFS/FAT): Python env di sana lambat dan tidak didukung. "
                f"Pilih folder di partisi Linux, misalnya {default_install_dir(platform=platform)}")
    if "rvc" in selection.components and selection.rvc_from_link:
        return link_problem(selection.rvc_model_url, selection.rvc_index_url)
    if "rvc" in selection.components:
        for path, ext, label in ((selection.rvc_model, ".pth", "bobot"), (selection.rvc_index, ".index", "index")):
            if not path:
                return f"Pilih file {label} RVC ({ext}), atau hilangkan centang Suara khas Miku"
            if Path(path).suffix.lower() != ext or not Path(path).is_file():
                return f"File {label} RVC harus file {ext} yang ada: {path}"
    return None


# Yang dibuat installer di dalam folder model (-ModelDir / --model-dir); hanya ini yang dihapus Hapus
MODEL_SUBDIRS = ("ollama", "huggingface")
# Ada di setiap instalasi MikuVision (zip rilis memuat keduanya untuk semua OS)
APP_MARKERS = ("gui.py", "miku_setup")
# Sisa di folder aplikasi sesudah Hapus yang menyimpan data user
APP_LEFTOVERS = {"data", "logs"}


def is_protected_folder(folder: Path, home: Optional[Path] = None) -> bool:
    """Akar drive/filesystem atau folder home: tidak pernah jadi folder aplikasi atau model, karena Hapus
    menghapus isinya."""
    home = Path.home() if home is None else Path(home)
    try:
        folder, home = Path(folder).resolve(), home.resolve()
    except OSError:
        folder = Path(folder)
    return folder.parent == folder or folder == home


def looks_like_app_folder(folder: Path) -> bool:
    """Folder berisi MikuVision (atau sisanya sesudah Hapus), bukan folder lain atau clone git."""
    folder = Path(folder)
    try:
        names = {entry.name for entry in folder.iterdir()}
    except OSError:
        return False
    if ".git" in names:
        return False
    return all(marker in names for marker in APP_MARKERS) or names <= APP_LEFTOVERS


def _folder_use_problem(label: str, folder: Path, app: bool, home: Optional[Path]) -> Optional[str]:
    """Folder yang sudah berisi file lain tidak boleh dipakai: Hapus nanti menghapus isinya."""
    suggestion = folder / ("MikuVision" if app else "MikuVision-models")
    if is_protected_folder(folder, home):
        return f"{label} tidak boleh langsung {folder}. Pilih folder baru di dalamnya, misalnya {suggestion}"
    if not folder.is_dir():
        return None
    try:
        names = {entry.name for entry in folder.iterdir()}
    except OSError:
        return None  # izin dicek is_writable
    if not names:
        return None
    if app and ".git" in names:
        return (f"{label} adalah clone git. Untuk clone pakai install.bat atau install.sh; "
                f"untuk Setup pilih folder baru, misalnya {suggestion}")
    if app and looks_like_app_folder(folder):
        return None
    if not app and names <= set(MODEL_SUBDIRS):
        return None
    return f"{label} sudah berisi file lain: {folder}. Pilih folder kosong, misalnya {suggestion}"


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


def install_args(selection: Selection, platform: str = sys.platform) -> List[str]:
    """Argumen install.ps1 untuk pilihan ini (dipakai runner di fase I3).

    Shortcut desktop dibuat wizard di halaman Selesai (fase I4), jadi install.ps1 hanya membuat shortcut
    Start Menu. Persetujuan untuk memasang Git/Ollama sudah diberikan di halaman 4 (-Yes).
    Linux: opsi install.sh yang setara; hak root lewat pkexec (jendela password grafis, tanpa terminal).
    """
    if platform != "win32":
        return _install_sh_args(selection)
    args = ["-Yes", "-Progress", "-StartMenu", "-SkipShortcut"]
    if selection.model_dir:
        args += ["-ModelDir", str(selection.model_dir)]
    if "vision" in selection.components:
        args.append("-WithVision")
    if "rvc" in selection.components:
        args += ["-RvcModel", selection.rvc_model, "-RvcIndex", selection.rvc_index]
    return args


def _install_sh_args(selection: Selection) -> List[str]:
    args = ["--yes", "--progress", "--menu-entry", "--skip-shortcut", "--sudo-cmd", "pkexec"]
    if selection.model_dir:
        args += ["--model-dir", str(selection.model_dir)]
    if "vision" in selection.components:
        args.append("--with-vision")
    if "rvc" in selection.components:
        args += ["--rvc-model", selection.rvc_model, "--rvc-index", selection.rvc_index]
    return args
