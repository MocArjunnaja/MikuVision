"""
Cek sistem untuk halaman 3 dan 4 (docs/PLAN_INSTALLER.md bagian 3).

Fungsi check_*/parse_* murni: menerima keluaran perintah atau angka, supaya mudah dites.
Fungsi run_* yang memanggil sistem sengaja tipis, dan dijalankan wizard di thread latar.
Di Linux "drive" adalah titik mount ('/', '/home'), dan yang butuh hak root dipasang install.sh lewat pkexec.
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

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

# Linux: installer resmi Ollama membuat layanan systemd dengan user "ollama" ber-home di sini
OLLAMA_SERVICE_HOME = Path("/usr/share/ollama")
OLLAMA_API = "http://127.0.0.1:11434"
# Yang dipasang check_system di install.sh bila belum ada: git dan curl wajib, alat aksi desktop disarankan
REQUIRED_TOOLS = ("git", "curl")
DESKTOP_TOOLS = ("xdotool", "wmctrl", "playerctl", "xclip")
PORTAUDIO_LIB = "libportaudio.so.2"
# Filesystem Windows lewat Linux: venv di sana lambat dan tidak mendukung semua fitur POSIX (sama dengan install.sh)
WINDOWS_FILESYSTEMS = {"fuseblk", "ntfs", "ntfs3", "msdos", "vfat", "exfat"}


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


def parse_os_release(text: str) -> Dict[str, str]:
    """Isi /etc/os-release -> {'ID': 'linuxmint', 'PRETTY_NAME': 'Linux Mint 22.3', ...}."""
    values = {}
    for line in (text or "").splitlines():
        key, sep, value = line.strip().partition("=")
        if not sep or not key or key.startswith("#"):
            continue
        try:
            parts = shlex.split(value)
        except ValueError:
            parts = [value]
        values[key] = parts[0] if parts else ""
    return values


def package_manager(os_release: Dict[str, str], which: Callable[[str], Optional[str]] = shutil.which) -> str:
    """apt, dnf, pacman, zypper, atau '' (sama dengan pkg_manager di install.sh).

    ID lalu ID_LIKE: Linux Mint -> "ubuntu debian", Manjaro -> "arch".
    """
    for distro in f"{os_release.get('ID', '')} {os_release.get('ID_LIKE', '')}".split():
        if distro in ("debian", "ubuntu"):
            return "apt"
        if distro in ("fedora", "rhel", "centos"):
            return "dnf"
        if distro == "arch":
            return "pacman"
        if distro in ("suse", "sles") or distro.startswith("opensuse"):
            return "zypper"
    for command, name in (("apt-get", "apt"), ("dnf", "dnf"), ("pacman", "pacman"), ("zypper", "zypper")):
        if which(command):
            return name
    return ""


def check_linux(machine: str, os_release: Dict[str, str], manager: str) -> CheckResult:
    """machine = platform.machine() ('x86_64'); manager dari package_manager()."""
    title = "Linux"
    if machine != "x86_64":
        return CheckResult("linux", title, FAIL, f"Butuh Linux 64-bit x86_64 (komputer ini {machine or '?'})")
    name = os_release.get("PRETTY_NAME") or os_release.get("NAME") or "Linux"
    if not manager:
        return CheckResult("linux", title, WARN, f"{name}: package manager tidak dikenali (didukung apt, dnf, "
                                                 "pacman, zypper); paket sistem harus dipasang sendiri")
    return CheckResult("linux", title, OK, f"{name} 64-bit ({manager})")


def check_session(session_type: str) -> CheckResult:
    """XDG_SESSION_TYPE. Shortcut, membaca layar, dan aksi keyboard/mouse di Linux memakai X11."""
    title = "Sesi desktop"
    if session_type == "x11":
        return CheckResult("session", title, OK, "X11")
    if session_type == "wayland":
        return CheckResult("session", title, WARN, "Wayland: shortcut Ctrl+Shift+M, membaca layar, dan aksi "
                                                   "keyboard/mouse butuh X11. Pilih sesi X11 di layar login "
                                                   "untuk fitur lengkap")
    return CheckResult("session", title, WARN, f"Tidak diketahui ({session_type or 'kosong'}); fitur desktop "
                                               "butuh sesi X11")


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
    """needed/free dalam byte per drive ('C:', atau titik mount di Linux). Kebutuhan sudah termasuk cadangan
    (components.MARGIN_GB)."""
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


def check_ollama(path: Optional[str], service: bool = False) -> CheckResult:
    """service: Linux, Ollama berjalan sebagai layanan sistem (installer resmi)."""
    if path:
        where = " sebagai layanan sistem" if service else ""
        return CheckResult("ollama", "Ollama", OK, f"Sudah terpasang{where}, dipakai yang sudah ada")
    return CheckResult("ollama", "Ollama", OK, "Belum terpasang, akan dipasang")


def parse_microphones(output: str) -> List[str]:
    """Keluaran `Get-PnpDevice -Class AudioEndpoint -Status OK` (FriendlyName per baris)."""
    return [line.strip() for line in (output or "").splitlines() if _MICROPHONE.search(line)]


def parse_pactl_sources(output: str) -> List[str]:
    """Keluaran `LC_ALL=C pactl list sources`: Description tiap sumber input.

    Sumber ".monitor" merekam suara speaker, bukan mikrofon.
    """
    names, name = [], ""
    for line in (output or "").splitlines():
        line = line.strip()
        if line.startswith("Name:"):
            name = line[len("Name:"):].strip()
        elif line.startswith("Description:") and name:
            if not name.endswith(".monitor"):
                names.append(line[len("Description:"):].strip())
            name = ""
    return names


def parse_arecord(output: str) -> List[str]:
    """Keluaran `arecord -l` (cadangan tanpa PulseAudio/PipeWire): nama kartu yang bisa merekam."""
    return re.findall(r"^card \d+: \S+ \[([^\]]*)\]", output or "", re.MULTILINE)


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


def root_needs(rvc: bool, ollama_installed: bool, which: Callable[[str], Optional[str]] = shutil.which,
               has_lib: Optional[Callable[[str], bool]] = None) -> List[str]:
    """Linux: yang akan dipasang install.sh dengan hak root (check_system dan install_ollama_model).

    rvc: fairseq untuk RVC dikompilasi saat instalasi, jadi butuh g++.
    """
    has_lib = has_library if has_lib is None else has_lib
    needs = [tool for tool in REQUIRED_TOOLS if not which(tool)]
    if not has_lib(PORTAUDIO_LIB):
        needs.append("PortAudio")
    needs += [tool for tool in DESKTOP_TOOLS if not which(tool)]
    if rvc and not which("g++"):
        needs.append("g++")
    if not ollama_installed:
        needs.append("Ollama")
    return needs


def check_root(needs: List[str], pkexec: Optional[str]) -> CheckResult:
    """needs dari root_needs(); pkexec = path pkexec (jendela password grafis), atau None."""
    title = "Hak admin"
    if not needs:
        return CheckResult("root", title, OK, "Tidak perlu: paket sistem dan Ollama sudah ada")
    names = ", ".join(needs)
    if not pkexec:
        return CheckResult("root", title, FAIL, f"Perlu memasang {names}, tapi pkexec tidak ada. Pasang lewat "
                                                "terminal (sudo), lalu tekan Periksa lagi")
    return CheckResult("root", title, OK, f"Untuk memasang {names}; password diminta lewat jendela sistem")


def parse_mounts(text: str) -> List[Tuple[str, str]]:
    """Isi /proc/mounts -> [(titik mount, filesystem)]; spasi di path tertulis \\040."""
    mounts = []
    for line in (text or "").splitlines():
        fields = line.split()
        if len(fields) >= 3:
            point = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), fields[1])
            mounts.append((point, fields[2]))
    return mounts


def mount_of(path: Path, mounts: List[Tuple[str, str]]) -> Tuple[str, str]:
    """(titik mount, filesystem) terdalam yang memuat path absolut ini; mount yang ditumpuk: yang terakhir."""
    text = str(path)
    best = ("/", "")
    for point, fstype in mounts:
        if (text == point or text.startswith(point.rstrip("/") + "/")) and len(point) >= len(best[0]):
            best = (point, fstype)
    return best


def _real_path(path: Path) -> Path:
    """realpath untuk folder yang mungkin belum ada: induk terdekat yang ada di-resolve, sisanya ditempel."""
    path = Path(os.path.abspath(path))
    rest = []
    while not path.exists() and path.parent != path:
        rest.append(path.name)
        path = path.parent
    return Path(os.path.realpath(path)).joinpath(*reversed(rest))


def _mounts() -> List[Tuple[str, str]]:
    try:
        return parse_mounts(Path("/proc/mounts").read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return []


def drive_of(path: Path) -> str:
    """'C:' untuk C:\\Users\\...; di Linux titik mount yang memuatnya ('/', '/home', '/media/user/Data')."""
    if sys.platform == "win32":
        return Path(path).drive.upper() or Path(path).anchor or "/"
    return mount_of(_real_path(path), _mounts())[0]


def filesystem_of(path: Path) -> str:
    """Linux: filesystem folder ini ('ext4', 'fuseblk' untuk NTFS lewat ntfs-3g); '' bila tidak diketahui."""
    return mount_of(_real_path(path), _mounts())[1]


def drive_root(drive: str) -> Path:
    """'C:' -> C:\\ (shutil.disk_usage butuh folder, bukan 'C:'); titik mount Linux apa adanya."""
    return Path(drive + os.sep) if drive.endswith(":") else Path(drive)


def home_dir(environ: Dict[str, str]) -> Path:
    return Path(environ.get("USERPROFILE") or environ.get("HOME") or Path.home())


def model_env_file(environ: Dict[str, str]) -> Optional[Path]:
    """Linux: file environment.d yang ditulis install.sh --model-dir, atau None tanpa HOME/XDG_CONFIG_HOME."""
    if environ.get("XDG_CONFIG_HOME"):
        return Path(environ["XDG_CONFIG_HOME"]) / "environment.d" / "60-mikuvision.conf"
    if environ.get("HOME"):
        return Path(environ["HOME"]) / ".config" / "environment.d" / "60-mikuvision.conf"
    return None


def parse_env_file(text: str) -> Dict[str, str]:
    return dict(line.split("=", 1) for line in (text or "").splitlines() if "=" in line and not line.startswith("#"))


def _model_env(name: str, environ: Dict[str, str]) -> str:
    """Variabel lokasi model; di Linux juga dari file environment.d, yang baru terbaca di sesi login berikutnya."""
    if environ.get(name) or sys.platform == "win32":
        return environ.get(name, "")
    path = model_env_file(environ)
    try:
        return parse_env_file(path.read_text(encoding="utf-8")).get(name, "") if path else ""
    except OSError:
        return ""


def ollama_models_dir(environ: Optional[Dict[str, str]] = None) -> Path:
    environ = os.environ if environ is None else environ
    if _model_env("OLLAMA_MODELS", environ):
        return Path(_model_env("OLLAMA_MODELS", environ))
    return home_dir(environ) / ".ollama" / "models"


def huggingface_dir(environ: Optional[Dict[str, str]] = None) -> Path:
    environ = os.environ if environ is None else environ
    if _model_env("HF_HOME", environ):
        return Path(_model_env("HF_HOME", environ))
    return home_dir(environ) / ".cache" / "huggingface"


def parse_systemctl_show(output: str) -> Dict[str, str]:
    return dict(line.split("=", 1) for line in (output or "").splitlines() if "=" in line)


def service_models_dir(show: Dict[str, str], home_of: Callable[[str], Optional[str]]) -> Optional[Path]:
    """Folder model layanan sistem Ollama dari `systemctl show ollama`, None bila layanannya tidak ada.

    Sama dengan ollama_service_models_dir di install.sh: OLLAMA_MODELS di unit, atau ~/.ollama/models milik
    user layanannya.
    """
    if show.get("LoadState") != "loaded":
        return None
    environment = show.get("Environment", "")
    try:
        assignments = shlex.split(environment)
    except ValueError:
        assignments = environment.split()
    for assignment in assignments:
        name, _, value = assignment.partition("=")
        if name == "OLLAMA_MODELS" and value:
            return Path(value)
    user = show.get("User") or "ollama"
    return Path(home_of(user) or OLLAMA_SERVICE_HOME) / ".ollama" / "models"


def model_present(models_dir: Path, model: str) -> bool:
    """Model Ollama sudah diunduh di models_dir ('qwen3:4b-instruct' -> manifests/.../qwen3/4b-instruct).

    Folder layanan sistem Ollama di Linux tidak bisa dibaca user di luar grup "ollama"; di sana ditanyakan ke
    server Ollama yang sedang jalan.
    """
    name, _, tag = model.partition(":")
    namespace, _, name = name.rpartition("/")
    if (Path(models_dir) / "manifests" / "registry.ollama.ai" / (namespace or "library")
            / name / (tag or "latest")).is_file():
        return True
    if sys.platform == "win32" or not _denied(Path(models_dir)):
        return False
    names = ollama_api_models()
    return bool(names) and (model if ":" in model else model + ":latest") in names


def _denied(path: Path) -> bool:
    try:
        os.listdir(path)
    except PermissionError:
        return True
    except OSError:
        return False
    return False


# ───────────────────────── memanggil sistem ─────────────────────────

def _output(command: List[str], timeout: float = 15, env: Optional[Dict[str, str]] = None) -> Optional[str]:
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout, creationflags=_NO_WINDOW, env=env)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", errors="replace")


def run_windows() -> List[CheckResult]:
    import platform
    return [check_windows(platform.machine(), platform.version())]


def _os_release() -> Dict[str, str]:
    for path in ("/etc/os-release", "/usr/lib/os-release"):
        try:
            return parse_os_release(Path(path).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return {}


def run_linux() -> List[CheckResult]:
    import platform
    release = _os_release()
    return [check_linux(platform.machine(), release, package_manager(release))]


def run_session() -> List[CheckResult]:
    return [check_session(os.environ.get("XDG_SESSION_TYPE", ""))]


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


def _home_of(user: str) -> Optional[str]:
    try:
        import pwd
        return pwd.getpwnam(user).pw_dir
    except (ImportError, KeyError):
        return None


@lru_cache(maxsize=1)
def ollama_service_dir() -> Optional[Path]:
    """Linux: folder model Ollama yang berjalan sebagai layanan sistem; None bila milik user (atau di Windows).

    Bila Ollama belum terpasang di sistem dengan systemd, installer resmi akan membuat layanannya, jadi
    foldernya sudah bisa diperkirakan untuk menghitung ruang disk.
    """
    if sys.platform == "win32" or not shutil.which("systemctl"):
        return None
    output = _output(["systemctl", "show", "ollama", "--property=LoadState,Environment,User"])
    found = service_models_dir(parse_systemctl_show(output or ""), _home_of)
    if found is None and not find_ollama() and Path("/run/systemd/system").is_dir():
        return OLLAMA_SERVICE_HOME / ".ollama" / "models"
    return found


def ollama_api_models(timeout: float = 2) -> Optional[Set[str]]:
    """Nama model di server Ollama yang sedang jalan ('qwen3:4b-instruct'), atau None bila tidak terjangkau."""
    try:
        with urllib.request.urlopen(OLLAMA_API + "/api/tags", timeout=timeout) as response:
            return {m["name"] for m in json.load(response).get("models", [])}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def run_ollama() -> List[CheckResult]:
    path = find_ollama()
    return [check_ollama(path, service=bool(path) and ollama_service_dir() is not None)]


def run_microphone() -> List[CheckResult]:
    if sys.platform != "win32":
        return [check_microphone(_linux_microphones())]
    script = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
              "Get-PnpDevice -Class AudioEndpoint -Status OK | ForEach-Object { $_.FriendlyName }")
    output = _output(["powershell", "-NoProfile", "-NonInteractive", "-Command", script])
    return [check_microphone(parse_microphones(output) if output is not None else None)]


def _linux_microphones() -> Optional[List[str]]:
    """PulseAudio/PipeWire lewat pactl (label bahasa Inggris dengan LC_ALL=C), cadangannya ALSA."""
    if shutil.which("pactl"):
        output = _output(["pactl", "list", "sources"], env=dict(os.environ, LC_ALL="C"))
        if output is not None:
            return parse_pactl_sources(output)
    if shutil.which("arecord"):
        output = _output(["arecord", "-l"], env=dict(os.environ, LC_ALL="C"))
        if output is not None:
            return parse_arecord(output)
    return None


def run_user_path() -> List[CheckResult]:
    return [check_user_path(os.environ.get("LOCALAPPDATA") or str(Path.home()))]


@lru_cache(maxsize=None)
def has_library(name: str) -> bool:
    """Library sistem terdaftar di cache ldconfig (sama dengan have_lib di install.sh)."""
    ldconfig = shutil.which("ldconfig", path=os.environ.get("PATH", "") + os.pathsep + "/usr/sbin:/sbin")
    output = _output([ldconfig, "-p"]) if ldconfig else None
    return bool(output) and name in output


def run_root() -> List[CheckResult]:
    return [check_root(root_needs(rvc=False, ollama_installed=bool(find_ollama())), shutil.which("pkexec"))]


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
WINDOWS_CHECKS: List[Callable[[], List[CheckResult]]] = [
    run_windows, run_gpu, run_internet, run_ollama, run_microphone, run_user_path,
]
LINUX_CHECKS: List[Callable[[], List[CheckResult]]] = [
    run_linux, run_session, run_gpu, run_internet, run_ollama, run_microphone, run_root,
]
SYSTEM_CHECKS = WINDOWS_CHECKS if sys.platform == "win32" else LINUX_CHECKS
