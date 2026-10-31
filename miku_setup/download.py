"""
Unduh kode MikuVision dari rilis GitHub, verifikasi SHA256, dan ekstrak dengan aman (docs/PLAN_INSTALLER.md
bagian 2 dan 5).

Tiap rilis melampirkan version.json, SHA256SUMS, dan MikuVision-<versi>.zip (workflow fase I5). Wizard
tidak memakai GitHub API (batas rate), hanya URL releases/latest/download/<file>. Unduhan yang terputus
dilanjutkan dari file .part lewat HTTP Range.
"""

import hashlib
import json
import shutil
import threading
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Callable, Dict, Iterable, Optional

RELEASE_URL = "https://github.com/MocArjunnaja/MikuVision/releases/latest/download/"
TIMEOUT_SEC = 30
CHUNK = 1 << 20
# Isi InstallDir yang tidak ditimpa zip rilis bila sudah ada (data user, model, env, log)
KEEP_EXISTING = ("data", "models", ".venv", ".tools", "logs")
USER_AGENT = "MikuVisionSetup"


class DownloadError(Exception):
    """Kegagalan yang pesannya bisa ditampilkan apa adanya ke user."""


class Cancelled(Exception):
    pass


def zip_name(version: str) -> str:
    return f"MikuVision-{version}.zip"


def _open(url: str, headers: Optional[Dict[str, str]] = None):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    return urllib.request.urlopen(request, timeout=TIMEOUT_SEC)


def fetch_text(url: str) -> str:
    try:
        with _open(url) as response:
            return response.read().decode("utf-8-sig")
    except (OSError, ValueError) as e:
        raise DownloadError(f"Gagal mengunduh {url.rsplit('/', 1)[-1]}: {getattr(e, 'reason', e)}") from e


def parse_version(text: str) -> str:
    """version.json: {"version": "1.6.0", ...}."""
    try:
        version = json.loads(text)["version"]
    except (ValueError, KeyError, TypeError) as e:
        raise DownloadError("version.json di rilis tidak valid") from e
    if not isinstance(version, str) or not version or "/" in version or "\\" in version:
        raise DownloadError("version.json di rilis tidak valid")
    return version


def parse_sha256sums(text: str) -> Dict[str, str]:
    """Format sha256sum: '<64 hex>  <nama file>' (atau '*<nama>' untuk mode biner)."""
    sums = {}
    for line in text.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and len(parts[0]) == 64:
            try:
                int(parts[0], 16)
            except ValueError:
                continue
            sums[parts[1].lstrip("*").strip()] = parts[0].lower()
    return sums


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def download(url: str, dest: Path, sha256: str, progress: Callable[[int, int], None] = lambda done, total: None,
             cancel: Optional[threading.Event] = None) -> Path:
    """Unduh url ke dest dan cocokkan SHA256. Dilanjutkan dari dest.part bila ada; dest yang sudah cocok dipakai."""
    dest = Path(dest)
    if dest.is_file() and sha256_of(dest) == sha256:
        progress(dest.stat().st_size, dest.stat().st_size)
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    start = part.stat().st_size if part.is_file() else 0
    try:
        response = _open(url, {"Range": f"bytes={start}-"} if start else None)
    except urllib.error.HTTPError as e:
        if e.code == 416:  # .part sudah lengkap atau rusak: mulai lagi dari nol
            part.unlink()
            return download(url, dest, sha256, progress, cancel)
        raise DownloadError(f"Gagal mengunduh {dest.name}: HTTP {e.code}") from e
    except (OSError, ValueError) as e:
        raise DownloadError(f"Gagal mengunduh {dest.name}: {getattr(e, 'reason', e)}") from e

    with response:
        resumed = bool(start) and getattr(response, "status", None) == 206
        done = start if resumed else 0
        length = int(response.headers.get("Content-Length") or 0)
        total = done + length if length else 0
        try:
            with open(part, "ab" if resumed else "wb") as out:
                while True:
                    if cancel is not None and cancel.is_set():
                        raise Cancelled()
                    block = response.read(CHUNK)
                    if not block:
                        break
                    out.write(block)
                    done += len(block)
                    progress(done, total)
        except OSError as e:
            raise DownloadError(f"Unduhan {dest.name} terputus: {e}. Coba lagi untuk melanjutkan.") from e

    if sha256_of(part) != sha256:
        part.unlink()
        raise DownloadError(f"File {dest.name} rusak (checksum tidak cocok). Coba lagi untuk mengunduh ulang.")
    part.replace(dest)
    return dest


def _common_root(names: Iterable[str]) -> str:
    """Folder puncak yang sama untuk semua entri ('MikuVision-1.6.0/'), atau '' bila tidak ada."""
    tops = {PurePosixPath(name).parts[0] for name in names if name.strip("/")}
    if len(tops) == 1:
        top = tops.pop()
        if all(name.startswith(top + "/") or name == top + "/" for name in names):
            return top + "/"
    return ""


def safe_extract(zip_path: Path, target: Path, keep: Iterable[str] = KEEP_EXISTING) -> int:
    """Ekstrak zip ke target; jumlah file yang ditulis.

    Menolak entri yang keluar dari target (path absolut, '..'; zip slip). Folder di `keep` yang sudah ada
    di target dibiarkan, supaya pembaruan tidak menimpa data, model, atau env user.
    """
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    kept = {name for name in keep if (target / name).exists()}
    written = 0
    with zipfile.ZipFile(zip_path) as archive:
        root = _common_root(archive.namelist())
        entries = []
        # Periksa semua entri dulu: zip yang tidak aman tidak menulis apa pun
        for info in archive.infolist():
            name = (info.filename[len(root):] if root else info.filename).replace("\\", "/")
            if not name.strip("/"):
                continue
            rel = PurePosixPath(name)
            if rel.is_absolute() or ".." in rel.parts or ":" in rel.parts[0]:
                raise DownloadError(f"Zip rilis tidak aman: {info.filename}")
            if rel.parts[0] not in kept:
                entries.append((info, rel))
        for info, rel in entries:
            path = target.joinpath(*rel.parts)
            if info.is_dir():
                path.mkdir(parents=True, exist_ok=True)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, open(path, "wb") as dst:
                shutil.copyfileobj(src, dst)
            written += 1
    return written
