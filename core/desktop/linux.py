"""
Aksi desktop Linux (X11): volume lewat PipeWire/PulseAudio (wpctl, cadangan pactl),
buka aplikasi dari katalog LINUX_APPS, tutup jendela dengan sopan (wmctrl: _NET_CLOSE_WINDOW,
setara WM_CLOSE di Windows), buka file/folder (xdg-open), media (playerctl).
Semua jalan sebagai user biasa, tanpa sudo.
"""

import configparser
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from config import LINUX_APPS, LINUX_GENERIC_APPS
from .app_search import AppEntry

try:
    import pyautogui
except Exception:  # tanpa DISPLAY (SSH, CI) Xlib melempar KeyError
    pyautogui = None

# Nama proses yang tidak boleh ditutup lewat close_application
PROTECTED_PROCESSES = {
    "systemd", "init", "xorg", "x", "cinnamon", "muffin", "gnome-shell", "plasmashell",
    "kwin_x11", "xfwm4", "nemo-desktop", "pipewire", "pipewire-pulse", "wireplumber",
    "pulseaudio", "dbus-daemon", "dbus-broker", "gnome-keyring-daemon", "ollama",
    "python", "python3", "sudo", "login", "sshd",
    # Satu proses memegang semua jendela terminal, termasuk yang menjalankan MikuVision
    "gnome-terminal-server", "konsole", "xfce4-terminal", "mate-terminal",
}

# Perintah peluncur -> nama proses aplikasinya, bila berbeda
PROCESS_NAMES: Dict[str, Set[str]] = {
    "brave-browser": {"brave"},
    "brave-browser-stable": {"brave"},
    "google-chrome": {"chrome"},
    "google-chrome-stable": {"chrome"},
    "chromium-browser": {"chromium", "chrome"},
    "libreoffice": {"soffice.bin"},
    "telegram-desktop": {"telegram-desktop", "telegram"},
    "x-terminal-emulator": {"gnome-terminal-server"},
    "gnome-terminal": {"gnome-terminal-server"},
}

# Peluncur yang langsung selesai setelah membuka aplikasi; PID-nya tidak dilacak
LAUNCHERS = {"gtk-launch", "flatpak", "xdg-open"}

XDG_DIRS = {"desktop": "DESKTOP", "downloads": "DOWNLOAD", "documents": "DOCUMENTS",
            "pictures": "PICTURES", "music": "MUSIC", "videos": "VIDEOS"}
FALLBACK_DIRS = {"desktop": "Desktop", "downloads": "Downloads", "documents": "Documents",
                 "pictures": "Pictures", "music": "Music", "videos": "Videos"}

FLATPAK_APP_DIRS = (Path("/var/lib/flatpak/app"), Path.home() / ".local" / "share" / "flatpak" / "app")

WPCTL_SINK = "@DEFAULT_AUDIO_SINK@"
PACTL_SINK = "@DEFAULT_SINK@"
COMMAND_TIMEOUT_SEC = 5

MEDIA_COMMANDS = {"play_pause": "play-pause", "next": "next", "prev": "previous"}
MEDIA_KEYS = {"play_pause": "playpause", "next": "nexttrack", "prev": "prevtrack"}


def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    # LC_ALL=C: keluaran pactl tidak diterjemahkan ("Mute: yes", bukan "Bisu: ya")
    return subprocess.run(cmd, capture_output=True, text=True, timeout=COMMAND_TIMEOUT_SEC,
                          env={**os.environ, "LC_ALL": "C"})


def _spawn(argv: List[str]) -> subprocess.Popen:
    # Sesi sendiri: aplikasi tetap jalan setelah MikuVision ditutup, dan log-nya tidak ke konsol Miku
    return subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True)


def _start(argv: List[str]) -> int:
    """Jalankan peluncur yang selesai sendiri setelah membuka aplikasi (gtk-launch, gio) dan
    kembalikan exit code-nya. stdout DEVNULL: aplikasi yang dibuka mewarisi pipa yang terbuka."""
    return subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, start_new_session=True,
                          timeout=COMMAND_TIMEOUT_SEC * 2).returncode


def _copy_to_clipboard(text: str):
    # stdout harus DEVNULL: xclip tetap jalan di latar untuk melayani clipboard,
    # dan pipa yang tetap terbuka membuat subprocess.run menunggu sampai timeout
    subprocess.run(["xclip", "-selection", "clipboard"], input=text, text=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   timeout=COMMAND_TIMEOUT_SEC, check=True)


def user_dir(name: str) -> Path:
    """Folder user (desktop, downloads, ...); nama aslinya bisa diterjemahkan, jadi tanya xdg-user-dir."""
    key = XDG_DIRS.get(name)
    if key and shutil.which("xdg-user-dir"):
        try:
            path = _run(["xdg-user-dir", key]).stdout.strip()
            # Folder yang tidak dikonfigurasi dilaporkan sebagai $HOME
            if path and Path(path) != Path.home():
                return Path(path)
        except (OSError, subprocess.SubprocessError):
            pass
    return Path.home() / FALLBACK_DIRS.get(name, name)


FIELD_CODE = re.compile(r"%[a-zA-Z]")


def _application_dirs() -> List[Path]:
    """Folder menu aplikasi menurut XDG, folder user lebih dulu (menimpa yang sistem)."""
    data_home = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    data_dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    roots = [data_home] + [d for d in data_dirs.split(":") if d]
    dirs = [Path(root) / "applications" for root in roots]
    dirs += [Path("/var/lib/flatpak/exports/share/applications"),
             Path.home() / ".local" / "share" / "flatpak" / "exports" / "share" / "applications",
             Path("/var/lib/snapd/desktop/applications")]
    unique: List[Path] = []
    for path in dirs:
        if path not in unique:
            unique.append(path)
    return unique


def _read_desktop_entry(path: Path) -> Optional[Dict[str, str]]:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str  # kunci peka huruf besar: Name[id], NoDisplay
    try:
        parser.read_string(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, configparser.Error):
        return None
    return dict(parser["Desktop Entry"]) if parser.has_section("Desktop Entry") else None


def _exec_process_names(exec_line: str) -> Tuple[str, ...]:
    """Nama proses dari baris Exec ("libreoffice %U" -> soffice.bin)."""
    try:
        tokens = shlex.split(FIELD_CODE.sub("", exec_line))
    except ValueError:
        return ()
    while tokens and (tokens[0] == "env" or "=" in tokens[0]):
        tokens.pop(0)
    if not tokens:
        return ()
    command = os.path.basename(tokens[0]).lower()
    if command in ("flatpak", "snap"):
        return ()
    return tuple(sorted(PROCESS_NAMES.get(command, {command})))


def _default_browser_id() -> Optional[str]:
    """ID .desktop browser default, misalnya 'brave-browser'."""
    if not shutil.which("xdg-settings"):
        return None
    try:
        desktop_file = _run(["xdg-settings", "get", "default-web-browser"]).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return desktop_file[:-len(".desktop")] if desktop_file.endswith(".desktop") else None


class LinuxDesktop:
    name = "linux"
    protected_processes = PROTECTED_PROCESSES

    def __init__(self):
        self._audio_cmd: Optional[str] = None

    # ── Audio ──

    def init_audio(self):
        self._audio_cmd = next((cmd for cmd in ("wpctl", "pactl") if shutil.which(cmd)), None)
        if self._audio_cmd:
            print(f"[SystemControl] Audio: {self._audio_cmd}")
        else:
            print("[SystemControl] Audio: wpctl/pactl tidak ditemukan, volume tidak bisa diatur")

    def get_volume(self) -> int:
        try:
            if self._audio_cmd == "wpctl":
                match = re.search(r"Volume:\s*([\d.]+)", _run(["wpctl", "get-volume", WPCTL_SINK]).stdout)
                if match:
                    return round(float(match.group(1)) * 100)
            elif self._audio_cmd == "pactl":
                match = re.search(r"(\d+)%", _run(["pactl", "get-sink-volume", PACTL_SINK]).stdout)
                if match:
                    return int(match.group(1))
        except (OSError, subprocess.SubprocessError) as e:
            print(f"[SystemControl] Error getting volume: {e}")
        return -1

    def _audio_command(self, cmd: List[str], ok_message: str) -> Tuple[bool, str]:
        try:
            result = _run(cmd)
        except (OSError, subprocess.SubprocessError) as e:
            return False, f"Error: {e}"
        if result.returncode != 0:
            return False, f"Error: {(result.stderr or result.stdout).strip()}"
        return True, ok_message

    def set_volume(self, level: int) -> Tuple[bool, str]:
        if self._audio_cmd == "wpctl":
            # -l 1.0: tidak pernah melebihi 100%
            cmd = ["wpctl", "set-volume", "-l", "1.0", WPCTL_SINK, f"{level / 100:.2f}"]
        elif self._audio_cmd == "pactl":
            cmd = ["pactl", "set-sink-volume", PACTL_SINK, f"{level}%"]
        else:
            return False, "Audio interface not available (wpctl/pactl tidak ditemukan)"
        return self._audio_command(cmd, f"Volume diatur ke {level}%")

    def set_mute(self, mute: bool) -> Tuple[bool, str]:
        flag = "1" if mute else "0"
        if self._audio_cmd == "wpctl":
            cmd = ["wpctl", "set-mute", WPCTL_SINK, flag]
        elif self._audio_cmd == "pactl":
            cmd = ["pactl", "set-sink-mute", PACTL_SINK, flag]
        else:
            return False, "Audio interface not available (wpctl/pactl tidak ditemukan)"
        return self._audio_command(cmd, f"Audio {'dimute' if mute else 'di-unmute'}")

    def is_muted(self) -> bool:
        try:
            if self._audio_cmd == "wpctl":
                return "[MUTED]" in _run(["wpctl", "get-volume", WPCTL_SINK]).stdout
            if self._audio_cmd == "pactl":
                return "yes" in _run(["pactl", "get-sink-mute", PACTL_SINK]).stdout
        except (OSError, subprocess.SubprocessError):
            pass
        return False

    # ── Aplikasi ──

    @staticmethod
    def _lookup(app_name: str) -> Optional[str]:
        """Kunci LINUX_APPS untuk nama aplikasi; nama spesifik menang atas kata umum ("browser")."""
        name = app_name.lower().strip()
        if name in LINUX_APPS:
            return name
        contained = [key for key in LINUX_APPS if key in name]
        specific = [key for key in contained if key not in LINUX_GENERIC_APPS]
        for group in (specific, contained):
            if group:
                return max(group, key=len)
        if len(name) >= 3:
            return next((key for key in LINUX_APPS if name in key), None)
        return None

    @staticmethod
    def _resolve(candidate: str) -> Optional[List[str]]:
        """Kandidat -> argv bila terpasang, None bila tidak."""
        if candidate.startswith(("http://", "https://")):
            return ["xdg-open", candidate] if shutil.which("xdg-open") else None
        if candidate == "default-browser":
            browser = _default_browser_id()
            return ["gtk-launch", browser] if browser and shutil.which("gtk-launch") else None
        if candidate.startswith("flatpak:"):
            app_id = candidate[len("flatpak:"):]
            installed = any((root / app_id).exists() for root in FLATPAK_APP_DIRS)
            return ["flatpak", "run", app_id] if installed and shutil.which("flatpak") else None
        argv = shlex.split(candidate)
        path = shutil.which(argv[0])
        return [path] + argv[1:] if path else None

    def launch(self, app_name: str) -> Tuple[bool, str, Optional[int]]:
        """Buka aplikasi dari katalog LINUX_APPS: (sukses, pesan, PID bila bisa dilacak)."""
        key = self._lookup(app_name)
        if not key:
            return False, f"Aplikasi '{app_name}' tidak dikenali", None

        for candidate in LINUX_APPS[key]:
            argv = self._resolve(candidate)
            if not argv:
                continue
            print(f"[SystemControl] Launching: {' '.join(argv)}")
            try:
                proc = _spawn(argv)
            except OSError as e:
                return False, f"Gagal membuka {app_name}: {e}", None
            if candidate.startswith(("http://", "https://")):
                return True, f"{app_name} tidak terpasang; membuka versi web {candidate}...", None
            if os.path.basename(argv[0]) in LAUNCHERS:
                return True, f"Membuka {app_name}...", None
            return True, f"Membuka {app_name} (PID {proc.pid})...", proc.pid

        tried = ", ".join(c for c in LINUX_APPS[key] if not c.startswith(("http://", "https://")))
        return False, f"{app_name} belum terpasang (dicari: {tried})", None

    def list_installed_apps(self) -> List[AppEntry]:
        """Aplikasi di menu (file .desktop), sama dengan yang dicari menu aplikasi desktop."""
        desktops = {d.lower() for d in os.environ.get("XDG_CURRENT_DESKTOP", "").split(":") if d}
        found: Dict[str, Optional[AppEntry]] = {}
        for root in _application_dirs():
            if not root.is_dir():
                continue
            for path in sorted(root.rglob("*.desktop")):
                app_id = str(path.relative_to(root).with_suffix("")).replace(os.sep, "-")
                if app_id in found:
                    continue  # versi user (atau folder yang lebih dulu) menang, termasuk yang menyembunyikan
                entry = _read_desktop_entry(path)
                found[app_id] = None
                if not entry or entry.get("Type") != "Application" or not entry.get("Name"):
                    continue
                if "true" in (entry.get("NoDisplay", "").lower(), entry.get("Hidden", "").lower()):
                    continue
                only = {d.lower() for d in entry.get("OnlyShowIn", "").split(";") if d}
                if (only and not only & desktops) or ({d.lower() for d in entry.get("NotShowIn", "").split(";") if d} & desktops):
                    continue
                if entry.get("TryExec") and not shutil.which(entry["TryExec"]):
                    continue
                aliases = tuple(entry[k] for k in ("Name[id]", "Name[ja]", "GenericName", "GenericName[id]", "GenericName[ja]")
                                if entry.get(k))
                keywords = tuple(k for key in ("Keywords", "Keywords[id]") for k in entry.get(key, "").split(";") if k)
                found[app_id] = AppEntry(id=app_id, name=entry["Name"], aliases=aliases, keywords=keywords,
                                         process_names=_exec_process_names(entry.get("Exec", "")), path=str(path))
        return [entry for entry in found.values() if entry]

    def launch_entry(self, entry: AppEntry) -> Tuple[bool, str, Optional[int]]:
        """Buka aplikasi dari menu lewat id-nya, seperti mengkliknya di menu."""
        if shutil.which("gtk-launch"):
            argv = ["gtk-launch", entry.id]
        elif entry.path and shutil.which("gio"):
            argv = ["gio", "launch", entry.path]
        else:
            return False, "gtk-launch/gio tidak ditemukan", None
        print(f"[SystemControl] Launching: {' '.join(argv)}")
        try:
            code = _start(argv)
        except (OSError, subprocess.SubprocessError) as e:
            return False, f"Gagal membuka {entry.name}: {e}", None
        if code != 0:
            return False, f"Gagal membuka {entry.name} (exit {code})", None
        return True, f"Membuka {entry.name}...", None

    def process_names(self, app_name: str) -> Set[str]:
        """Nama-nama proses milik aplikasi ini (beda distro beda program)."""
        names = {app_name.lower().strip()}
        key = self._lookup(app_name)
        if not key:
            return names
        for candidate in LINUX_APPS[key]:
            if candidate == "default-browser":
                browser = _default_browser_id()
                command = browser or ""
            elif candidate.startswith(("http://", "https://", "flatpak:")):
                continue
            else:
                command = os.path.basename(shlex.split(candidate)[0])
            if command:
                names |= PROCESS_NAMES.get(command.lower(), {command.lower()})
        return names

    @staticmethod
    def process_key(proc_name: str) -> str:
        return (proc_name or "").lower()

    # ── Jendela ──

    @property
    def can_close_windows(self) -> bool:
        # wmctrl hanya melihat jendela X11; di Wayland jendela aplikasi tidak terdaftar
        return (bool(shutil.which("wmctrl")) and bool(os.environ.get("DISPLAY"))
                and os.environ.get("XDG_SESSION_TYPE") != "wayland")

    def windows_by_pid(self, pids: set) -> Dict[int, list]:
        """Jendela milik proses-proses tersebut: {pid: [id jendela]} dari `wmctrl -lp`."""
        try:
            output = _run(["wmctrl", "-lp"]).stdout
        except (OSError, subprocess.SubprocessError):
            return {}
        found: Dict[int, list] = {}
        for line in output.splitlines():
            parts = line.split(None, 3)
            if len(parts) < 3:
                continue
            try:
                pid = int(parts[2])
            except ValueError:
                continue
            if pid in pids:
                found.setdefault(pid, []).append(parts[0])
        return found

    def close_window(self, window_id: str):
        # Sama seperti menekan tombol X: aplikasi sempat menawarkan simpan
        _run(["wmctrl", "-ic", window_id])

    # ── File, media, keyboard ──

    def open_path(self, target: str):
        """Buka file, folder, atau URI dengan aplikasi bawaannya."""
        if not shutil.which("xdg-open"):
            raise OSError("xdg-open tidak ditemukan (paket xdg-utils)")
        _spawn(["xdg-open", target])

    def user_dir(self, name: str) -> Path:
        return user_dir(name)

    def has_uri_handler(self, scheme: str) -> bool:
        """Ada aplikasi untuk tautan scheme:// (misalnya tg:// dari Telegram Desktop)?"""
        if not shutil.which("xdg-mime"):
            return False
        try:
            return bool(_run(["xdg-mime", "query", "default", f"x-scheme-handler/{scheme}"]).stdout.strip())
        except (OSError, subprocess.SubprocessError):
            return False

    def media(self, action: str) -> Tuple[bool, str]:
        if shutil.which("playerctl"):
            try:
                if _run(["playerctl", MEDIA_COMMANDS[action]]).returncode == 0:
                    return True, ""
            except (OSError, subprocess.SubprocessError):
                pass
        # Tanpa pemutar MPRIS atau playerctl: tombol media, ditangani desktop environment
        if pyautogui is None:
            return False, "playerctl tidak ditemukan dan tombol media tidak tersedia"
        try:
            pyautogui.press(MEDIA_KEYS[action])
            return True, ""
        except Exception as e:
            return False, f"Gagal menekan tombol media: {e}"

    def type_text(self, text: str) -> Tuple[bool, str]:
        if text.isascii():
            pyautogui.typewrite(text, interval=0.02)
            return True, f"Mengetik: {text[:30]}..."
        # typewrite hanya bisa ASCII: teks Jepang atau emoji lewat clipboard lalu Ctrl+V
        if not shutil.which("xclip"):
            return False, "Teks non-ASCII butuh xclip (sudo apt install xclip)"
        try:
            _copy_to_clipboard(text)
        except (OSError, subprocess.SubprocessError) as e:
            return False, f"Gagal menyalin teks ke clipboard: {e}"
        pyautogui.hotkey("ctrl", "v")
        return True, f"Mengetik lewat clipboard: {text[:30]}..."

    def session_warning(self) -> Optional[str]:
        if os.environ.get("XDG_SESSION_TYPE") == "wayland":
            return ("Sesi Wayland: keyboard/mouse dan daftar jendela dibatasi, jadi mengetik, hotkey, "
                    "dan menutup aplikasi tidak jalan. Pilih sesi X11 di layar login untuk fitur lengkap.")
        return None

    def missing_tools(self) -> List[str]:
        wanted = ["xdg-open", "wmctrl", "playerctl", "xclip"]
        missing = [tool for tool in wanted if not shutil.which(tool)]
        if not (shutil.which("wpctl") or shutil.which("pactl")):
            missing.append("wpctl/pactl")
        return missing
