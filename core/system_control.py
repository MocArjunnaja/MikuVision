"""
System Control Module - aksi di komputer (Windows dan Linux)
Integrated with Automation Layer untuk YouTube, Spotify, Browser

Aksi yang berbeda per OS (volume, buka/tutup aplikasi, buka folder, media, mengetik)
ada di core/desktop/; modul ini memegang logika bersama: konfirmasi, pelacakan PID,
dan cara menutup aplikasi dengan sopan.
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import os
import sys
from typing import Optional, Tuple, Dict, Any, List

import psutil

# Dicek terpisah dari modul Windows: pyautogui juga jalan di Linux (X11).
# Tanpa DISPLAY, Xlib melempar KeyError, bukan ImportError.
try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except Exception:
    PYAUTOGUI_AVAILABLE = False

try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume  # noqa: F401  (cek ketersediaan)
    import pygetwindow as gw
    WINDOWS_AVAILABLE = True
except (ImportError, NotImplementedError):  # pygetwindow di Linux: NotImplementedError
    WINDOWS_AVAILABLE = False
    if sys.platform == "win32":
        print("[SystemControl] Warning: Some Windows modules not available")

from config import APP_CACHE_FILE, COMMON_WEBSITES, TURN_LOG_DIR
from . import desktop as desktop_backend
from .desktop.app_search import AppCache, AppLauncher
from .tools import registry
from .confirmation import ConfirmCallback, describe_action, requires_confirmation
from .safety import blocked_hotkey_reason, miku_process_ids, normalize_keys, terminal_focus_reason
from .turn_log import TurnLogger

# Waktu tunggu proses menutup diri sebelum dipaksa kill
CLOSE_TIMEOUT_SEC = 5

# Aksi berisiko (yang butuh konfirmasi) dan hasilnya dicatat di data/logs/actions_YYYYMMDD.jsonl
ACTION_LOG = TurnLogger(TURN_LOG_DIR, prefix="actions")

# Chrome DevTools Protocol: browser Chromium (Chrome, Edge, Brave) yang dibuka dengan
# --remote-debugging-port=9222. Hanya localhost.
CDP_URL = "http://localhost:9222"
CDP_TIMEOUT_SEC = 3
CDP_SETUP_HINT = ("Tutup SEMUA jendela browser (Chrome/Edge/Brave) lalu buka lagi dengan opsi "
                  "--remote-debugging-port=9222, misalnya di shortcut-nya: chrome.exe --remote-debugging-port=9222")

# Kata yang cocok dengan hampir semua tab; menutup "tab browser" berarti close_application
_GENERIC_TAB_WORDS = {"tab", "tabs", "browser", "chrome", "edge", "brave", "firefox", "http", "https",
                      "www", "com", "web", "website", "situs", "halaman", "page", "タブ", "ブラウザ"}

# close_window menolak bila judulnya cocok dengan lebih banyak jendela dari ini
MAX_WINDOWS_PER_CLOSE = 3


def _process_name(pid: int) -> str:
    try:
        return psutil.Process(pid).name()
    except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
        return ""


def _tab_keyword(match: str) -> str:
    """'tab YouTube' / 'YouTubeのタブ' / 'youtube.com' -> kata yang dicari di judul/alamat tab."""
    text = re.sub(r"(の)?(タブ|ブラウザ)", " ", (match or "").strip().lower())
    words = [w for w in text.split() if w not in _GENERIC_TAB_WORDS]
    return " ".join(words)

try:
    from .automation_layer import AutomationManager
    AUTOMATION_AVAILABLE = True
except ImportError:
    AUTOMATION_AVAILABLE = False
    print("[SystemControl] Automation layer not available")


class SystemControl:
    """
    Handles desktop operations and automation on Windows and Linux.
    """

    def __init__(
        self,
        spotify_client_id: str = "",
        spotify_client_secret: str = "",
        confirm_callback: Optional[ConfirmCallback] = None,
        desktop=None,
    ):
        # Tanpa callback, aksi berisiko selalu ditolak (fail closed)
        self.confirm_callback = confirm_callback
        # Backend OS ini; test memberi backend lain (misalnya WindowsDesktop di Linux)
        self.desktop = desktop or desktop_backend.current
        self.desktop.init_audio()
        warning = self.desktop.session_warning()
        if warning:
            print(f"[SystemControl] Warning: {warning}")
        missing = self.desktop.missing_tools()
        if missing:
            print(f"[SystemControl] Tool desktop belum terpasang: {', '.join(missing)}")

        # Initialize automation layer
        if AUTOMATION_AVAILABLE:
            self.automation = AutomationManager(
                spotify_client_id=spotify_client_id,
                spotify_client_secret=spotify_client_secret,
                system_control=self,
            )
        else:
            self.automation = None

        # Proses yang dibuka lewat open_application: key aplikasi -> [(pid, create_time)].
        # create_time mencegah salah kill jika PID sudah dipakai ulang proses lain.
        self._opened_apps: Dict[str, List[Tuple[int, float]]] = {}

        # Aplikasi di luar katalog config.py: dicari di menu sistem, lalu diingat (cache)
        self.apps = AppLauncher(self.desktop, AppCache(APP_CACHE_FILE, self.desktop.name))

    @registry.register("Check current system volume level (0-100). Returns integer.")
    def get_volume(self) -> int:
        """Get current system volume (0-100)"""
        return self.desktop.get_volume()

    @registry.register("Set system volume. Pass an integer between 0 and 100.")
    def set_volume(self, level: int) -> Tuple[bool, str]:
        """Set system volume"""
        # Convert to int (AI might pass string)
        try:
            level = int(level)
        except (ValueError, TypeError):
            return False, f"Invalid volume level: {level}"

        level = max(0, min(100, level))
        return self.desktop.set_volume(level)

    @registry.register("Mute or unmute system audio. True to mute, False to unmute.")
    def mute(self, mute: bool = True) -> Tuple[bool, str]:
        """Mute/unmute system audio"""
        return self.desktop.set_mute(mute)

    def is_muted(self) -> bool:
        """Check if system is muted"""
        return self.desktop.is_muted()

    @registry.register("Open any installed desktop application by its name, e.g. Notepad, Calculator, "
                       "LibreOffice, a web browser (Chrome, Brave, Firefox), VS Code, Spotify, WhatsApp. "
                       "Pass the application name the user said. "
                       "To create a Word document with content, use create_word_document instead.",
                       params={"app_name": "Application name in English or as it appears in the app menu, "
                                           "e.g. 'LibreOffice', 'Calendar', 'Notepad', even when the user "
                                           "speaks Japanese or Indonesian (カレンダー -> 'Calendar')."})
    def open_application(self, app_name: str) -> Tuple[bool, str]:
        """Katalog config.py dulu; bila tidak ada atau tidak terpasang, cache lalu menu aplikasi sistem."""
        success, message, pid = self.desktop.launch(app_name)
        if not success:
            found = self.apps.open(app_name)
            if found is not None:
                success, message, pid = found
            else:
                similar = self.apps.suggestions(app_name)
                if similar:
                    message += f". Aplikasi terpasang yang mirip: {', '.join(similar)}"
        if success and pid:
            self._track_process(app_name, pid)
        return success, message

    def _app_key(self, app_name: str) -> str:
        """Kunci pelacakan PID: nama proses utama aplikasi, sama untuk buka dan tutup."""
        return min(self.desktop.process_names(app_name))

    def _track_process(self, app_name: str, pid: int):
        try:
            created = psutil.Process(pid).create_time()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return
        self._opened_apps.setdefault(self._app_key(app_name), []).append((pid, created))

    def _tracked_processes(self, key: str) -> list:
        """Proses hasil open_application yang masih hidup dan PID-nya belum dipakai ulang."""
        procs = []
        for pid, created in self._opened_apps.pop(key, []):
            try:
                proc = psutil.Process(pid)
                if proc.create_time() == created:
                    procs.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return procs

    def _close_processes(self, procs: list) -> Tuple[int, int]:
        """
        Tutup proses dan kembalikan (jumlah tertutup, jumlah jendela masih terbuka).

        Proses berjendela dikirimi perintah tutup jendela (WM_CLOSE di Windows,
        _NET_CLOSE_WINDOW di Linux), sama seperti user menekan tombol X, sehingga
        aplikasi sempat menawarkan simpan dan tidak pernah di-kill paksa.
        Proses tanpa jendela di-terminate lalu di-kill setelah timeout, kecuali bila
        ada proses lain dari aplikasi yang sama yang berjendela: proses pembantu
        (tab browser, renderer) ikut selesai saat jendela utamanya ditutup.
        """
        windows = self.desktop.windows_by_pid({proc.pid for proc in procs})
        signaled = []
        for proc in procs:
            try:
                if proc.pid in windows:
                    for window in windows[proc.pid]:
                        self.desktop.close_window(window)
                elif windows:
                    continue
                else:
                    proc.terminate()
                signaled.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                print(f"[SystemControl] Gagal menutup PID {proc.pid}: {e}")

        gone, alive = psutil.wait_procs(signaled, timeout=CLOSE_TIMEOUT_SEC)
        # Jendelanya sudah tertutup tapi prosesnya lanjut di latar (layanan GApplication di
        # GNOME, aplikasi di system tray): dianggap tertutup dan tidak di-kill
        open_windows = self.desktop.windows_by_pid({p.pid for p in alive if p.pid in windows}) if alive else {}
        still_open = 0
        for proc in alive:
            if proc.pid in windows:
                if proc.pid in open_windows:
                    # Kemungkinan menunggu dialog "simpan perubahan?"; biarkan user memutuskan
                    still_open += 1
                else:
                    gone.append(proc)
                continue
            try:
                proc.kill()
                gone.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                print(f"[SystemControl] Gagal kill PID {proc.pid}: {e}")
        return len(gone), still_open

    @registry.register("Close (quit) a desktop application by name, with all its windows: Notepad, Calculator, "
                       "Spotify, VLC, or a whole browser. E.g. 'メモ帳を閉じて', '電卓を終了して', 'tutup notepad', "
                       "'tutup aplikasi spotify'. For a website or browser tab (YouTube, Netflix) use "
                       "close_browser_tab; for one window by its title use close_window.",
                       params={"app_name": "Application name in English, e.g. 'Notepad', 'Calculator', 'Chrome'."})
    def close_application(self, app_name: str) -> Tuple[bool, str]:
        """Close an application by exact process name (no substring match)"""
        if not app_name or not app_name.strip():
            return False, "Nama aplikasi kosong"
        # Ditambah nama proses aplikasi yang pernah dibuka lewat menu sistem (cache)
        names = self.desktop.process_names(app_name) | self.apps.process_names(app_name)
        protected = sorted(names & self.desktop.protected_processes)
        if protected:
            return False, f"Proses '{protected[0]}' dilindungi dan tidak boleh ditutup"
        # Tanpa daftar jendela, aplikasi berjendela akan dianggap proses tanpa jendela
        # lalu dimatikan; perubahan yang belum disimpan bisa hilang.
        if not self.desktop.can_close_windows:
            return False, (
                f"Menutup aplikasi belum didukung di sistem ini; tutup {app_name} "
                "lewat tombol X di jendelanya"
            )

        procs = {proc.pid: proc for proc in self._tracked_processes(self._app_key(app_name))}
        for proc in psutil.process_iter(['name']):
            if self.desktop.process_key(proc.info['name']) in names:
                procs.setdefault(proc.pid, proc)

        if not procs:
            # "YouTube閉じて" yang dikirim sebagai aplikasi: YouTube adalah tab browser
            if app_name.strip().lower() in COMMON_WEBSITES:
                return self.close_browser_tab(app_name)
            return False, f"Tidak menemukan proses {app_name}"

        # cmd, terminal, atau VS Code yang menjalankan MikuVision: menutupnya ikut mematikan Miku
        miku = miku_process_ids()
        hosting = [proc for proc in procs.values() if proc.pid in miku]
        if hosting:
            return False, (f"{app_name} sedang menjalankan MikuVision (PID {hosting[0].pid}); "
                           "menutupnya ikut mematikan Miku, jadi tidak ditutup")

        closed, still_open = self._close_processes(list(procs.values()))
        if still_open:
            return True, (
                f"Perintah tutup dikirim ke {app_name}; {still_open} proses masih terbuka "
                "(mungkin menunggu konfirmasi simpan di aplikasinya)"
            )
        if closed:
            return True, f"Menutup {app_name} ({closed} proses)"
        return False, f"Gagal menutup {app_name}"

    @registry.register("Close one window by part of its title, like pressing its X button (the app can still "
                       "ask to save): a document, a folder window, a video or media player window. E.g. "
                       "'レポートのウィンドウを閉じて', 'tutup jendela Downloads', 'tutup jendela laporan.docx'. "
                       "To quit a whole app use close_application; for a browser tab use close_browser_tab.",
                       params={"title": "Part of the window title as the user said it, e.g. 'Downloads', 'laporan'."})
    def close_window(self, title: str) -> Tuple[bool, str]:
        """Tutup jendela yang judulnya mengandung `title` (WM_CLOSE / _NET_CLOSE_WINDOW, tanpa kill)."""
        fragment = (title or "").strip().lower()
        if len(fragment) < 2:
            return False, "Sebutkan sebagian judul jendela yang mau ditutup (minimal 2 huruf)"
        if not self.desktop.can_close_windows:
            return False, f"Menutup jendela belum didukung di sistem ini; tutup '{title}' lewat tombol X-nya"

        matching = [w for w in self.desktop.list_windows() if w.title and fragment in w.title.lower()]
        if not matching:
            return False, f"Tidak ada jendela yang judulnya mengandung '{title}'"
        # Jendela Miku sendiri, terminal yang menjalankannya, desktop, dan taskbar tidak pernah ditutup
        miku = miku_process_ids()
        allowed = [w for w in matching
                   if w.pid not in miku and "mikuvision" not in w.title.lower()
                   and not self.desktop.is_shell_window(w, _process_name(w.pid))]
        if not allowed:
            return False, (f"Jendela '{matching[0].title}' milik desktop/sistem atau MikuVision sendiri, "
                           "jadi tidak ditutup")
        if len(allowed) > MAX_WINDOWS_PER_CLOSE:
            titles = "; ".join(w.title for w in allowed[:5])
            return False, (f"'{title}' cocok dengan {len(allowed)} jendela ({titles}). "
                           "Tanyakan user judul yang lebih spesifik")

        for window in allowed:
            self.desktop.close_window(window.id)
        skipped = len(matching) - len(allowed)
        note = f" ({skipped} jendela sistem/Miku dilewati)" if skipped else ""
        return True, f"Perintah tutup dikirim ke jendela: {'; '.join(w.title for w in allowed)}{note}"

    def _cdp_tabs(self) -> list:
        """Tab halaman browser lewat CDP; URLError/OSError bila browser tidak dibuka dengan port 9222."""
        with urllib.request.urlopen(f"{CDP_URL}/json", timeout=CDP_TIMEOUT_SEC) as response:
            return [t for t in json.loads(response.read().decode()) if t.get("type") == "page"]

    def _cdp_close(self, tab_id: str):
        url = f"{CDP_URL}/json/close/{urllib.parse.quote(tab_id)}"
        try:
            urllib.request.urlopen(url, timeout=CDP_TIMEOUT_SEC).close()
        except urllib.error.HTTPError as e:
            # Versi Chrome yang menolak GET untuk endpoint /json/*
            if e.code != 405:
                raise
            urllib.request.urlopen(urllib.request.Request(url, method="PUT"), timeout=CDP_TIMEOUT_SEC).close()

    @registry.register("Close browser tabs whose title or address contains `match`, without closing the "
                       "browser: a YouTube, Netflix, or any site tab. E.g. 'YouTube閉じて', 'YouTubeのタブを閉じて', "
                       "'tutup youtube', 'tutup tab youtube', 'close the Netflix tab'.",
                       params={"match": "Site name in Latin letters as in its address (ユーチューブ -> 'youtube'), "
                                        "or part of the tab title, e.g. 'youtube', 'netflix', 'github.com'. "
                                        "Never empty."})
    def close_browser_tab(self, match: str) -> Tuple[bool, str]:
        """Tutup tab yang cocok lewat CDP; tanpa CDP hanya memberi tahu jendela browser yang cocok."""
        keyword = _tab_keyword(match)
        if len(keyword) < 2:
            return False, ("Sebutkan situs atau judul tab yang mau ditutup, misalnya 'youtube'. "
                           "Untuk menutup seluruh browser pakai close_application")
        try:
            tabs = self._cdp_tabs()
        except (urllib.error.URLError, OSError, ValueError):
            windows = [w.title for w in self.desktop.list_windows() if keyword in w.title.lower()]
            hint = (f" Jendela browser yang cocok: '{windows[0]}'; close_window('{keyword}') menutup seluruh "
                    "jendela itu beserta semua tabnya.") if windows else ""
            return False, f"Tab browser tidak bisa ditutup satu per satu tanpa CDP. {CDP_SETUP_HINT}.{hint}"

        matching = [t for t in tabs
                    if keyword in t.get("title", "").lower() or keyword in t.get("url", "").lower()]
        if not matching:
            return False, f"Tidak ada tab browser yang judul/alamatnya mengandung '{match}'"
        closed = []
        for tab in matching:
            try:
                self._cdp_close(tab["id"])
                closed.append(tab.get("title") or tab.get("url", ""))
            except (urllib.error.URLError, OSError, KeyError) as e:
                print(f"[SystemControl] Gagal menutup tab {tab.get('title')!r}: {e}")
        if not closed:
            return False, f"Gagal menutup tab '{match}' lewat CDP"
        return True, f"Menutup {len(closed)} tab: {'; '.join(closed[:3])}"

    @registry.register("Open a specific local folder or directory path in the file manager. E.g. 'Desktop', 'Downloads', atau nama folder spesifik.")
    def open_folder(self, folder_name_or_path: str) -> Tuple[bool, str]:
        """Open a directory/folder in the file manager (Explorer, Nemo, ...)"""
        path = folder_name_or_path.strip()

        # Nama umum; di Linux nama foldernya bisa diterjemahkan, jadi tanya backend
        common_dirs = {name: str(self.desktop.user_dir(name))
                       for name in ("desktop", "downloads", "documents", "pictures", "music", "videos")}
        common_dirs["kuliah"] = os.path.join(common_dirs["documents"], "Kuliah")  # Fallback dummy

        try:
            if path.lower() in common_dirs:
                target = common_dirs[path.lower()]
                os.makedirs(target, exist_ok=True)
                self.desktop.open_path(target)
                return True, f"Membuka folder {path}..."

            # Jika bukan absolut path, asumsikan mencari di Desktop atau Documents
            if not os.path.isabs(path):
                for c in (os.path.join(common_dirs["desktop"], path), os.path.join(common_dirs["documents"], path)):
                    if os.path.isdir(c):
                        self.desktop.open_path(c)
                        return True, f"Membuka folder {path} di sistem..."

            if not os.path.isdir(path):
                return False, f"Folder '{path}' tidak ditemukan"

            # Path dari LLM hanya diteruskan sebagai satu argumen, tanpa shell
            self.desktop.open_path(path)
            return True, f"Membuka {path}..."
        except OSError as e:
            return False, f"Gagal membuka folder: {e}"

    def list_running_apps(self) -> list:
        """Get list of running applications"""
        apps = []
        seen = set()
        
        for proc in psutil.process_iter(['name']):
            try:
                name = proc.info['name']
                if name not in seen:
                    seen.add(name)
                    apps.append(name)
            except:
                pass
        
        return sorted(apps)
    
    @registry.register("Open a specific local web browser or predefined domain.")
    def open_website(self, url_or_name: str) -> Tuple[bool, str]:
        """Open a website in default browser"""
        url = url_or_name.strip()
        
        if url.lower() in COMMON_WEBSITES:
            url = COMMON_WEBSITES[url.lower()]

        # Nama tanpa titik ("brave") bukan alamat web: LLM kadang memakai tool ini untuk
        # membuka aplikasi, dan "https://brave" hanya membuka halaman yang tidak ada
        if not url.startswith(('http://', 'https://')) and "." not in url and url.lower() != "localhost":
            success, message = self.open_application(url)
            if success:
                return success, message
            return False, (f"'{url_or_name}' bukan alamat web dan bukan aplikasi yang dikenal; "
                           "pakai alamat lengkap (misalnya contoh.com) atau google_search")

        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        try:
            webbrowser.open(url)
            return True, f"Membuka {url}..."
        except Exception as e:
            return False, f"Gagal membuka website: {e}"
    
    @registry.register("Search something on Google in default browser.")
    def google_search(self, query: str) -> Tuple[bool, str]:
        """Search something on Google"""
        try:
            import urllib.parse
            encoded_query = urllib.parse.quote(query)
            url = f"https://www.google.com/search?q={encoded_query}"
            webbrowser.open(url)
            return True, f"Mencari '{query}' di Google..."
        except Exception as e:
            return False, f"Error: {e}"

    @registry.register("Search and play a video on YouTube.")
    def youtube_search(self, query: str) -> Tuple[bool, str]:
        """Search something on YouTube directly and play the first result"""
        try:
            import urllib.request
            import urllib.parse
            import re
            
            encoded_query = urllib.parse.quote(query)
            search_url = f"https://www.youtube.com/results?search_query={encoded_query}"
            
            # Request search results
            req = urllib.request.Request(search_url, headers={'User-Agent': 'Mozilla/5.0'})
            html = urllib.request.urlopen(req).read().decode('utf-8')
            
            # Find the first video id
            video_ids = re.findall(r'watch\?v=([a-zA-Z0-9_-]{11})', html)
            if video_ids:
                first_vid = video_ids[0]
                play_url = f"https://www.youtube.com/watch?v={first_vid}"
                webbrowser.open(play_url)
                return True, f"Memutar video '{query}' di YouTube..."
            else:
                # Fallback to just search results
                webbrowser.open(search_url)
                return True, f"Mencari '{query}' di YouTube..."
        except Exception as e:
            return False, f"Error: {e}"
            
    @registry.register("Search music or artist on Spotify Web")
    def spotify_search(self, query: str) -> Tuple[bool, str]:
        """Search something on Spotify directly (web)"""
        try:
            import urllib.parse
            encoded_query = urllib.parse.quote(query)
            url = f"https://open.spotify.com/search/{encoded_query}"
            webbrowser.open(url)
            return True, f"Mencari '{query}' di Spotify..."
        except Exception as e:
            return False, f"Error: {e}"

    @registry.register(name="browser_media_control", description="Mengontrol tab YouTube/Media spesifik di browser menggunakan Chrome DevTools Protocol (CDP) port 9222. Bisa untuk play/pause tab YouTube spesifik jika ada 2 tab menyala bersamaan. Parameter 'action' isi dengan 'play' atau 'pause'. Parameter 'target_title' isi kata kunci judul tab-nya, misal 'Podcast' atau biarkan kosong untuk semua YouTube.")
    def browser_media_control(self, action: str = "pause", target_title: str = "YouTube") -> Tuple[bool, str]:
        """Tingkat Dewa: Mengontrol media browser via CDP/WebSocket"""
        try:
            import websocket
        except ImportError:
            return False, "Modul 'websocket-client' belum terinstall."

        try:
            # Cari filter tab YouTube yang cocok
            matching_tabs = [t for t in self._cdp_tabs() if target_title.lower() in t.get('title', '').lower()]
            
            if not matching_tabs:
                return False, f"Tidak ada tab browser aktif yang judulnya mengandung '{target_title}'."
                
            success_count = 0
            for tab in matching_tabs:
                ws_url = tab.get('webSocketDebuggerUrl')
                if not ws_url:
                    continue
                    
                # Setup injeksi Javascript
                # Untuk YouTube, kita panggil tombol klik native milik video player-nya
                js_code = ""
                if action.lower() == "pause":
                    js_code = "document.querySelectorAll('video').forEach(v => v.pause());"
                elif action.lower() in ["play", "resume"]:
                    js_code = "document.querySelectorAll('video').forEach(v => v.play());"
                elif action.lower() == "next":
                    # Klik tombol next track pada player youtube
                    js_code = "document.querySelector('.ytp-next-button').click();"
                else:
                    return False, f"Aksi browser '{action}' tidak didukung."

                # Connect via Websocket & tembak script
                ws = websocket.create_connection(ws_url, timeout=3)
                cmd = json.dumps({
                    "id": 1,
                    "method": "Runtime.evaluate",
                    "params": {"expression": js_code}
                })
                ws.send(cmd)
                ws.recv() # Wait for ack
                ws.close()
                success_count += 1
            
            return True, f"Aksi '{action}' terkirim ke {success_count} tab '{target_title}' via CDP."
            
        except urllib.error.URLError:
            return False, "Koneksi CDP Gagal. Pastikan Browser (Chrome/Edge) *SEMUANYA* sudah kututup lalu dibuka kembali menggunakan shortcut --remote-debugging-port=9222."
        except Exception as e:
            return False, f"Gagal eksekusi CDP browser: {e}"

    @registry.register(name="media_control", description="Mengontrol pemutaran media pada komputer (bisa Play/Pause/Jeda musik Spotify maupun video YouTube). Isi parameter `action_type` dengan: 'play', 'pause', 'next' (berikutnya), atau 'prev' (sebelumnya).")
    def media_control(self, action_type: str) -> Tuple[bool, str]:
        """Controls system media playback (tombol media di Windows, MPRIS/playerctl di Linux)."""
        action_type = action_type.lower()
        if action_type in ["play", "pause", "play_pause", "playpause", "toggle"]:
            action, message = "play_pause", "Play/Pause status media saat ini ditekan."
        elif action_type in ["next", "berikutnya", "skip"]:
            action, message = "next", "Memutar lagu/video selanjutnya."
        elif action_type in ["prev", "previous", "sebelumnya", "back"]:
            action, message = "prev", "Kembali ke lagu/video sebelumnya."
        else:
            return False, f"Aksi '{action_type}' tidak dimengerti."
        success, error = self.desktop.media(action)
        return (True, message) if success else (False, error)

    def get_active_window(self) -> Optional[str]:
        """Get title of currently active window"""
        if not WINDOWS_AVAILABLE:
            return None
        try:
            window = gw.getActiveWindow()
            return window.title if window else None
        except:
            return None
    
    def focus_window(self, title_contains: str) -> Tuple[bool, str]:
        """Bring a window to focus"""
        if not WINDOWS_AVAILABLE:
            return False, "PyGetWindow not available"
        
        try:
            windows = gw.getWindowsWithTitle(title_contains)
            if windows:
                windows[0].activate()
                return True, f"Fokus ke window: {windows[0].title}"
            return False, "Window tidak ditemukan"
        except Exception as e:
            return False, f"Error: {e}"
    
    @registry.register("Type text using keyboard automation. Use this to search or type something.")
    def type_text(self, text: str) -> Tuple[bool, str]:
        """Type text menggunakan keyboard automation"""
        if not PYAUTOGUI_AVAILABLE:
            return False, "PyAutoGUI not available"
        blocked = terminal_focus_reason()
        if blocked:
            return False, f"Teks tidak diketik: {blocked}"
        
        try:
            # Kecepatan tetap (abaikan jeda dari LLM); di Linux teks non-ASCII lewat clipboard
            return self.desktop.type_text(text)
        except Exception as e:
            return False, f"Error: {e}"
    
    @registry.register("Press a keyboard key (like 'enter', 'tab', 'down')")
    def press_key(self, key: str) -> Tuple[bool, str]:
        """Press a keyboard key"""
        if not PYAUTOGUI_AVAILABLE:
            return False, "PyAutoGUI not available"
        blocked = terminal_focus_reason()
        if blocked:
            return False, f"Tombol {key} tidak ditekan: {blocked}"
        
        try:
            pyautogui.press(key)
            return True, f"Menekan tombol: {key}"
        except Exception as e:
            return False, f"Error: {e}"
    
    @registry.register("Press a combination of hotkeys (e.g., ['ctrl', 'c'] or ['win', 'd'])")
    def hotkey(self, keys: list) -> Tuple[bool, str]:
        """Press hotkey combination"""
        if not PYAUTOGUI_AVAILABLE:
            return False, "PyAutoGUI not available"
        
        # LLM kadang mengirim string "ctrl+c" alih-alih list; tanpa ini
        # pyautogui.hotkey(*"ctrl+c") menekan tiap karakter satu per satu.
        if isinstance(keys, str):
            keys = keys.split("+")
        keys = normalize_keys(k for k in keys if k)
        if not keys:
            return False, "Hotkey kosong"
        blocked = blocked_hotkey_reason(keys)
        if blocked:
            return False, f"Hotkey {'+'.join(keys)} tidak dijalankan: {blocked}"
        blocked = terminal_focus_reason()  # mis. ctrl+v menempel perintah dari clipboard
        if blocked:
            return False, f"Hotkey {'+'.join(keys)} tidak dijalankan: {blocked}"

        try:
            pyautogui.hotkey(*keys)
            return True, f"Hotkey: {'+'.join(keys)}"
        except Exception as e:
            return False, f"Error: {e}"
    
    @registry.register("Get basic system information, RAM, and Battery")
    def get_system_info(self) -> Dict[str, Any]:
        """Get basic system information"""
        import platform
        
        info = {
            "os": platform.system(),
            "os_version": platform.version(),
            "machine": platform.machine(),
        }
        
        try:
            mem = psutil.virtual_memory()
            info["memory_total_gb"] = round(mem.total / (1024**3), 1)
            info["memory_used_percent"] = mem.percent
        except:
            pass
        
        try:
            info["cpu_percent"] = psutil.cpu_percent()
        except:
            pass
        
        try:
            battery = psutil.sensors_battery()
            if battery:
                info["battery_percent"] = battery.percent
                info["battery_plugged"] = battery.power_plugged
        except:
            pass
        
        return info
    
    def execute_action(self, action: str, params: Dict[str, Any]) -> Tuple[bool, str]:
        """Execute an action dynamically via registry"""
        params = params or {}
        risky = requires_confirmation(action, params)
        if risky:
            summary = describe_action(action, params)
            approved = bool(self.confirm_callback and self.confirm_callback(summary))
            if not approved:
                ACTION_LOG.log({"action": action, "params": params, "approved": False})
                return False, f"Dibatalkan, user tidak mengonfirmasi: {summary}"

        result = registry.execute(action, self, params)
        if isinstance(result, tuple) and len(result) == 2:
            success, message = result
        else:
            # Macro tools mengembalikan string; pesan "Gagal..." jangan dilaporkan sebagai sukses
            message = str(result)
            success = not message.startswith("Gagal")
        if risky:
            ACTION_LOG.log({"action": action, "params": params, "approved": True,
                            "success": success, "result": message})
        return success, message
