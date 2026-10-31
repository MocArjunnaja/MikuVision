"""
Cek sistem untuk halaman 3 dan 4 (docs/PLAN_INSTALLER.md bagian 3).

Fungsi check_*/parse_* murni: menerima keluaran perintah atau angka, supaya mudah dites.
Fungsi run_* yang memanggil sistem sengaja tipis, dan dijalankan wizard di thread latar.
"""

import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

OK, WARN, FAIL = "ok", "warn", "fail"

# Windows 10 RTM; build 22000 ke atas = Windows 11 (platform.release() bisa tetap "10")
MIN_WINDOWS_BUILD = 10240
WINDOWS_11_BUILD = 22000
# Kartu 6 GB melaporkan sedikit di bawah 6144 MiB (RTX 4050 Laptop: 6141 MiB)
MIN_VRAM_MIB = 5800
# Situs yang dipakai install.ps1; proxy kampus sering memblokir salah satunya
SITES = {
    "pypi.org": "https://pypi.org",
    "download.pytorch.org": "https://download.pytorch.org/whl/",
    "ollama.com": "https://ollama.com",
    "huggingface.co": "https://huggingface.co",
}
SITE_TIMEOUT_SEC = 5
# Nama perangkat input yang berarti mikrofon (nama dari driver, kadang diterjemahkan Windows)
_MICROPHONE = re.compile(r"micro|mikro|マイク", re.IGNORECASE)
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass
class CheckResult:
    key: str
    title: str
    status: str   # OK, WARN, FAIL
    message: str


@dataclass
class Gpu:
    name: str
    driver: str
    vram_mib: int


def format_gb(size_bytes: float) -> str:
    """12_300_000_000 -> '12,3 GB' (koma desimal, seperti teks lain di aplikasi)."""
    return f"{size_bytes / 1e9:.1f}".replace(".", ",") + " GB"


# ───────────────────────── fungsi murni ─────────────────────────

def check_windows(machine: str, version: str) -> CheckResult:
    """machine = platform.machine() ('AMD64'), version = platform.version() ('10.0.26300')."""
    title = "Windows"
    parts = version.split(".")
    try:
        major, build = int(parts[0]), int(parts[2])
    except (IndexError, ValueError):
        return CheckResult("windows", title, WARN, f"Versi Windows tidak terbaca ({version})")
    if machine.upper() in ("X86", "I386", "I686"):
        return CheckResult("windows", title, FAIL, "Butuh Windows 64-bit; komputer ini 32-bit")
    if major < 10 or build < MIN_WINDOWS_BUILD:
        return CheckResult("windows", title, FAIL, f"Butuh Windows 10 atau 11 (komputer ini {version})")
    name = "Windows 11" if build >= WINDOWS_11_BUILD else "Windows 10"
    if machine.upper() == "ARM64":
        return CheckResult("windows", title, WARN, f"{name} ARM64: belum diuji, PyTorch berjalan lewat emulasi")
    return CheckResult("windows", title, OK, f"{name} 64-bit (build {build})")


def parse_nvidia_smi(output: str) -> List[Gpu]:
    """Keluaran `nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader`."""
    gpus = []
    for line in (output or "").splitlines():
        fields = [f.strip() for f in line.split(",")]
        if len(fields) != 3:
            continue
        match = re.match(r"(\d+)\s*MiB", fields[2])
        if fields[0] and match:
            gpus.append(Gpu(fields[0], fields[1], int(match.group(1))))
    return gpus


def check_gpu(gpus: Optional[List[Gpu]]) -> List[CheckResult]:
    """None atau kosong = tanpa GPU NVIDIA (nvidia-smi tidak ada atau gagal)."""
    if not gpus:
        return [CheckResult("gpu", "GPU NVIDIA", WARN,
                            "Tanpa GPU NVIDIA: Miku tetap jalan, tapi lambat (mode CPU)")]
    gpu = max(gpus, key=lambda g: g.vram_mib)
    results = [CheckResult("gpu", "GPU NVIDIA", OK, f"{gpu.name}, driver {gpu.driver}")]
    vram_gb = f"{gpu.vram_mib / 1024:.1f}".replace(".", ",")
    if gpu.vram_mib < MIN_VRAM_MIB:
        results.append(CheckResult("vram", "VRAM", WARN,
                                   f"{vram_gb} GB: membaca layar dan RVC mungkin tidak muat"))
    else:
        results.append(CheckResult("vram", "VRAM", OK, f"{vram_gb} GB"))
    return results


def check_disk(needed: Dict[str, float], free: Dict[str, float]) -> CheckResult:
    """needed/free dalam byte per drive ('C:'). Kebutuhan sudah termasuk cadangan (components.MARGIN_GB)."""
    short = [drive for drive in sorted(needed) if free.get(drive, 0) < needed[drive]]
    detail = ", ".join(f"{d} butuh {format_gb(needed[d])}, kosong {format_gb(free.get(d, 0))}"
                       for d in sorted(needed))
    if short:
        return CheckResult("disk", "Ruang disk", FAIL, f"Ruang kurang di {', '.join(short)} ({detail})")
    return CheckResult("disk", "Ruang disk", OK, detail)


def check_internet(errors: Dict[str, Optional[str]]) -> CheckResult:
    """errors: situs -> None bila terjangkau, atau alasan gagal."""
    blocked = [site for site, error in errors.items() if error]
    if blocked:
        return CheckResult("internet", "Internet", FAIL,
                           f"Tidak terjangkau: {', '.join(blocked)}. Cek koneksi atau proxy, lalu periksa lagi")
    return CheckResult("internet", "Internet", OK, f"{len(errors)} situs unduhan terjangkau")


def check_ollama(path: Optional[str]) -> CheckResult:
    if path:
        return CheckResult("ollama", "Ollama", OK, "Sudah terpasang, dipakai yang sudah ada")
    return CheckResult("ollama", "Ollama", OK, "Belum terpasang, akan dipasang")


def parse_microphones(output: str) -> List[str]:
    """Keluaran `Get-PnpDevice -Class AudioEndpoint -Status OK` (FriendlyName per baris)."""
    return [line.strip() for line in (output or "").splitlines() if _MICROPHONE.search(line)]


def check_microphone(names: Optional[List[str]]) -> CheckResult:
    """None = tidak bisa dicek (perintah gagal)."""
    if names is None:
        return CheckResult("mic", "Mikrofon", WARN, "Tidak bisa dicek; mode teks tetap jalan tanpa mikrofon")
    if not names:
        return CheckResult("mic", "Mikrofon", WARN, "Tidak ditemukan: mode suara butuh mikrofon, mode teks tetap jalan")
    return CheckResult("mic", "Mikrofon", OK, names[0])


def check_user_path(path: str) -> CheckResult:
    """Huruf non-ASCII di folder profil (C:\\Users\\Siti Ñ) bisa membuat sebagian paket gagal."""
    if path and not path.isascii():
        return CheckResult("path", "Folder user", WARN,
                           f"{path} berisi huruf non-ASCII; bila instalasi gagal, pilih folder seperti D:\\MikuVision")
    return CheckResult("path", "Folder user", OK, path or "-")


def drive_of(path: Path) -> str:
    """'C:' untuk C:\\Users\\..., atau anchor lain ('/' di Linux, untuk test)."""
    return Path(path).drive.upper() or Path(path).anchor or "/"


def drive_root(drive: str) -> Path:
    """'C:' -> C:\\ (shutil.disk_usage butuh folder, bukan 'C:')."""
    return Path(drive + os.sep) if drive.endswith(":") else Path(drive)


def ollama_models_dir(environ: Optional[Dict[str, str]] = None) -> Path:
    environ = os.environ if environ is None else environ
    if environ.get("OLLAMA_MODELS"):
        return Path(environ["OLLAMA_MODELS"])
    return Path(environ.get("USERPROFILE") or Path.home()) / ".ollama" / "models"


def huggingface_dir(environ: Optional[Dict[str, str]] = None) -> Path:
    environ = os.environ if environ is None else environ
    if environ.get("HF_HOME"):
        return Path(environ["HF_HOME"])
    return Path(environ.get("USERPROFILE") or Path.home()) / ".cache" / "huggingface"


def model_present(models_dir: Path, model: str) -> bool:
    """Model Ollama sudah diunduh di models_dir ('qwen3:4b-instruct' -> manifests/.../qwen3/4b-instruct)."""
    name, _, tag = model.partition(":")
    namespace, _, name = name.rpartition("/")
    return (Path(models_dir) / "manifests" / "registry.ollama.ai" / (namespace or "library")
            / name / (tag or "latest")).is_file()


# ───────────────────────── memanggil sistem ─────────────────────────

def _output(command: List[str], timeout: float = 15) -> Optional[str]:
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout, creationflags=_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", errors="replace")


def run_windows() -> List[CheckResult]:
    import platform
    return [check_windows(platform.machine(), platform.version())]


def run_gpu() -> List[CheckResult]:
    smi = shutil.which("nvidia-smi")
    output = _output([smi, "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"]) if smi else None
    return check_gpu(parse_nvidia_smi(output) if output else None)


def _site_error(url: str) -> Optional[str]:
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "MikuVisionSetup"})
    try:
        urllib.request.urlopen(request, timeout=SITE_TIMEOUT_SEC).close()
    except urllib.error.HTTPError as e:
        # Situs menjawab (misalnya 403/405 untuk HEAD): koneksinya ada
        return None if e.code < 500 else f"HTTP {e.code}"
    except (OSError, ValueError) as e:
        return str(getattr(e, "reason", e))
    return None


def run_internet() -> List[CheckResult]:
    with ThreadPoolExecutor(max_workers=len(SITES)) as pool:
        errors = dict(zip(SITES, pool.map(_site_error, SITES.values())))
    return [check_internet(errors)]


def find_ollama(environ: Optional[Dict[str, str]] = None) -> Optional[str]:
    environ = os.environ if environ is None else environ
    found = shutil.which("ollama")
    if found:
        return found
    default = Path(environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
    return str(default) if environ.get("LOCALAPPDATA") and default.is_file() else None


def run_ollama() -> List[CheckResult]:
    return [check_ollama(find_ollama())]


def run_microphone() -> List[CheckResult]:
    if sys.platform != "win32":
        return [check_microphone(None)]
    script = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
              "Get-PnpDevice -Class AudioEndpoint -Status OK | ForEach-Object { $_.FriendlyName }")
    output = _output(["powershell", "-NoProfile", "-NonInteractive", "-Command", script])
    return [check_microphone(parse_microphones(output) if output is not None else None)]


def run_user_path() -> List[CheckResult]:
    return [check_user_path(os.environ.get("LOCALAPPDATA") or str(Path.home()))]


def free_bytes(path: Path) -> float:
    """Ruang kosong di drive path; folder yang belum ada dicek lewat induk terdekat yang ada."""
    path = Path(path)
    while not path.exists() and path.parent != path:
        path = path.parent
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return 0


# Urutan tampil di halaman 3; ruang disk dihitung terpisah karena bergantung pada pilihan di halaman 4
SYSTEM_CHECKS: List[Callable[[], List[CheckResult]]] = [
    run_windows, run_gpu, run_internet, run_ollama, run_microphone, run_user_path,
]
