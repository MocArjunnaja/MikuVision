"""
System Control Module - aksi di komputer (Windows dan Linux)
Integrated with Automation Layer untuk YouTube, Spotify, Browser

Aksi yang berbeda per OS (volume, buka/tutup aplikasi, buka folder, media, mengetik)
ada di core/desktop/; modul ini memegang logika bersama: konfirmasi, pelacakan PID,
dan cara menutup aplikasi dengan sopan.
"""

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

from config import APP_CACHE_FILE, COMMON_WEBSITES
from . import desktop as desktop_backend
from .desktop.app_search import AppCache, AppLauncher
from .tools import registry
from .confirmation import ConfirmCallback, describe_action, requires_confirmation

# Waktu tunggu proses menutup diri sebelum dipaksa kill
CLOSE_TIMEOUT_SEC = 5

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

    @registry.register("Close an application by name")
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
            return False, f"Tidak menemukan proses {app_name}"

        closed, still_open = self._close_processes(list(procs.values()))
        if still_open:
            return True, (
                f"Perintah tutup dikirim ke {app_name}; {still_open} proses masih terbuka "
                "(mungkin menunggu konfirmasi simpan di aplikasinya)"
            )
        if closed:
            return True, f"Menutup {app_name} ({closed} proses)"
        return False, f"Gagal menutup {app_name}"

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
        import json
        import urllib.request
        try:
            import websocket
        except ImportError:
            return False, "Modul 'websocket-client' belum terinstall."

        try:
            # Dapatkan list semua tab web dari Chrome CDP
            req = urllib.request.Request('http://localhost:9222/json')
            with urllib.request.urlopen(req, timeout=3) as response:
                tabs = json.loads(response.read().decode())
            
            # Cari filter tab YouTube yang cocok
            matching_tabs = [
                t for t in tabs 
                if t.get('type') == 'page' and target_title.lower() in t.get('title', '').lower()
            ]
            
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

    # Tanpa "tidak perlu judul lagu" dan frasa Jepang, qwen3:4b menjawab 次の曲にして dengan "lagu apa?"
    @registry.register(name="media_control",
                       description="Mengontrol media yang sedang diputar (Spotify, YouTube, pemutar apa pun): "
                                   "play/pause, lagu berikutnya, atau sebelumnya. Tidak perlu judul lagu. "
                                   "`action_type`: 'play', 'pause', 'next' (次の曲/スキップ/lagu berikutnya/skip), "
                                   "atau 'prev' (前の曲/lagu sebelumnya).",
                       params={"action_type": "'play', 'pause', 'next', atau 'prev'"})
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
        keys = [k.strip().lower() for k in keys if k and k.strip()]
        if not keys:
            return False, "Hotkey kosong"

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
        if requires_confirmation(action):
            summary = describe_action(action, params)
            approved = bool(self.confirm_callback and self.confirm_callback(summary))
            if not approved:
                return False, f"Dibatalkan, user tidak mengonfirmasi: {summary}"

        result = registry.execute(action, self, params)
        if isinstance(result, tuple) and len(result) == 2:
            return result
        # Macro tools mengembalikan string; pesan "Gagal..." jangan dilaporkan sebagai sukses
        text = str(result)
        return not text.startswith("Gagal"), text
