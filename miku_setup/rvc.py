"""
Model RVC dari link yang ditempel user (halaman 4, "Unduh dari link").

Repo tidak menunjuk ke model tertentu (README, "Lisensi & kredit"): link selalu dari user. Bisa satu link
.zip berisi .pth dan .index, atau dua link terpisah. Tidak ada SHA256 dari pihak ketiga, jadi file hanya
dicek jenis dan ukurannya; peringatan bahwa .pth bisa menjalankan kode ada di halaman 4.
"""

import hashlib
import re
import threading
import zipfile
from pathlib import Path, PurePosixPath
from typing import Callable, List, Optional, Tuple
from urllib.parse import unquote, urlsplit, urlunsplit

from .download import DownloadError, download, safe_extract

# Model RVC v2 ±55 MB, index ±100–500 MB; zip berisi checkpoint latihan bisa ±1 GB
MAX_BYTES = 2 * 10**9
ALLOWED_SCHEMES = ("https",)
_UNSAFE_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# Checkpoint latihan (G_xxx.pth, D_xxx.pth) ikut di banyak zip, tapi bukan model untuk inferensi
_TRAINING_CHECKPOINT = re.compile(r"^[GD]_\d+\.pth$", re.IGNORECASE)


def normalize_url(url: str) -> str:
    """Rapikan link: spasi dibuang, link halaman Hugging Face (/blob/) diubah ke link unduhan (/resolve/)."""
    url = url.strip()
    parts = urlsplit(url)
    if parts.netloc.lower() in ("huggingface.co", "www.huggingface.co") and "/blob/" in parts.path:
        url = urlunsplit(parts._replace(path=parts.path.replace("/blob/", "/resolve/", 1)))
    return url


def file_name(url: str) -> str:
    """Nama file dari path link (tanpa query), aman untuk Windows."""
    name = PurePosixPath(unquote(urlsplit(url).path)).name
    return _UNSAFE_NAME.sub("_", name).strip(" .")


def _extension(url: str) -> str:
    return PurePosixPath(file_name(url)).suffix.lower()


def link_problem(model_url: str, index_url: str) -> Optional[str]:
    """Pesan untuk user bila link belum bisa dipakai, atau None."""
    model_url, index_url = normalize_url(model_url), normalize_url(index_url)
    if not model_url:
        return "Tempel link model RVC (.pth atau .zip), atau hilangkan centang Suara khas Miku"
    for url in filter(None, (model_url, index_url)):
        if urlsplit(url).scheme.lower() not in ALLOWED_SCHEMES or not urlsplit(url).netloc:
            return f"Link harus diawali https:// : {url}"
    model_ext = _extension(model_url)
    if model_ext not in (".pth", ".zip"):
        return f"Link model harus menunjuk ke file .pth atau .zip, bukan {file_name(model_url) or 'folder'}"
    if model_ext == ".zip":
        if index_url:
            return "Link .zip sudah berisi .index; kosongkan link .index"
        return None
    if not index_url:
        return "Tempel juga link file .index"
    if _extension(index_url) != ".index":
        return f"Link index harus menunjuk ke file .index, bukan {file_name(index_url) or 'folder'}"
    return None


def pick_model_files(folder: Path) -> Tuple[Path, Path]:
    """(.pth, .index) di folder hasil ekstrak zip. Checkpoint G_/D_ dilewati; index added_ diutamakan."""
    folder = Path(folder)
    weights = [p for p in folder.rglob("*.pth") if not _TRAINING_CHECKPOINT.match(p.name)]
    indexes = list(folder.rglob("*.index"))
    added = [p for p in indexes if p.name.lower().startswith("added_")]
    indexes = added or indexes

    def one(found: List[Path], what: str) -> Path:
        if not found:
            raise DownloadError(f"Zip tidak berisi file {what}")
        if len(found) > 1:
            names = ", ".join(sorted(p.name for p in found))
            raise DownloadError(f"Zip berisi lebih dari satu file {what} ({names}). "
                                "Ekstrak sendiri lalu pilih filenya lewat \"File di komputer\"")
        return found[0]

    return one(weights, ".pth"), one(indexes, ".index")


def fetch(model_url: str, index_url: str, downloads_dir: Path,
          progress: Callable[[str, int, int], None] = lambda name, done, total: None,
          cancel: Optional[threading.Event] = None) -> Tuple[Path, Path]:
    """Unduh model RVC dari link user; (.pth, .index) di disk.

    Folder per link (hash dari link), jadi "Coba lagi" memakai file yang sudah lengkap dan melanjutkan .part.
    """
    model_url, index_url = normalize_url(model_url), normalize_url(index_url)
    problem = link_problem(model_url, index_url)
    if problem:
        raise DownloadError(problem)
    folder = Path(downloads_dir) / "rvc" / hashlib.sha256(f"{model_url}\n{index_url}".encode()).hexdigest()[:12]

    def get(url: str) -> Path:
        name = file_name(url)
        return download(url, folder / name, None, lambda done, total: progress(name, done, total), cancel,
                        max_bytes=MAX_BYTES)

    model = get(model_url)
    if _extension(model_url) == ".zip":
        unpacked = folder / "unpacked"
        try:
            safe_extract(model, unpacked, keep=())
        except (OSError, zipfile.BadZipFile) as e:
            raise DownloadError(f"{model.name} bukan zip yang bisa dibuka: {e}") from e
        return pick_model_files(unpacked)
    return model, get(index_url)
