"""
System Control Module - Kontrol Windows OS
Integrated with Automation Layer untuk YouTube, Spotify, Browser
"""

import subprocess
import webbrowser
import os
import re
import shutil
from typing import Optional, Tuple, Dict, Any, List
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL

try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    import pyautogui
    import pygetwindow as gw
    import psutil
    WINDOWS_AVAILABLE = True
except ImportError:
    WINDOWS_AVAILABLE = False
    print("[SystemControl] Warning: Some Windows modules not available")

from config import ALLOWED_APPS, COMMON_WEBSITES
from .tools import registry
from .confirmation import ConfirmCallback, describe_action, requires_confirmation

# Nama proses (tanpa .exe) yang tidak boleh dimatikan lewat close_application
PROTECTED_PROCESSES = {
    "system", "smss", "csrss", "wininit", "winlogon", "services", "lsass",
    "svchost", "dwm", "explorer", "python", "pythonw", "ollama",
}

# Alias nama aplikasi -> nama proses (tanpa .exe)
PROCESS_ALIASES = {
    "google chrome": "chrome",
    "browser": "chrome",
    "edge": "msedge",
    "microsoft edge": "msedge",
    "word": "winword",
    "powerpoint": "powerpnt",
    "vscode": "code",
    "visual studio code": "code",
    "kalkulator": "calculatorapp",
    "calculator": "calculatorapp",
}

# Skema URI minimal 2 karakter, jadi drive letter "C:" tidak dianggap URI
URI_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]+:")

# Waktu tunggu proses menutup diri sebelum dipaksa kill
CLOSE_TIMEOUT_SEC = 5

WM_CLOSE = 0x0010


def _process_key(app_name: str) -> str:
    """Nama aplikasi -> nama proses tanpa .exe (setelah alias)."""
    key = app_name.lower().strip()
    key = PROCESS_ALIASES.get(key, key)
    return key[:-4] if key.endswith(".exe") else key


def _windows_by_pid(pids: set) -> Dict[int, list]:
    """Jendela top-level yang terlihat milik proses-proses tersebut: {pid: [hwnd]}."""
    try:
        import win32gui
        import win32process
    except ImportError:
        return {}

    found: Dict[int, list] = {}

    def collect(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid in pids:
                found.setdefault(pid, []).append(hwnd)
        return True

    win32gui.EnumWindows(collect, None)
    return found


def _post_close(hwnd: int):
    import win32gui
    win32gui.PostMessage(hwnd, WM_CLOSE, 0, 0)

try:
    from .automation_layer import AutomationManager
    AUTOMATION_AVAILABLE = True
except ImportError:
    AUTOMATION_AVAILABLE = False
    print("[SystemControl] Automation layer not available")


class SystemControl:
    """
    Handles Windows system operations and automation.
    """
    
    def __init__(
        self,
        spotify_client_id: str = "",
        spotify_client_secret: str = "",
        confirm_callback: Optional[ConfirmCallback] = None,
    ):
        # Tanpa callback, aksi berisiko selalu ditolak (fail closed)
        self.confirm_callback = confirm_callback
        self._volume_interface = None
        self._init_audio()
        
        # Initialize automation layer
        if AUTOMATION_AVAILABLE:
            self.automation = AutomationManager(
                spotify_client_id=spotify_client_id,
                spotify_client_secret=spotify_client_secret,
                system_control=self,
            )
        else:
            self.automation = None

        # Proses yang dibuka lewat open_application: key proses -> [(pid, create_time)].
        # create_time mencegah salah kill jika PID sudah dipakai ulang proses lain.
        self._opened_apps: Dict[str, List[Tuple[int, float]]] = {}
    
    def _init_audio(self):
        """Initialize audio interface"""
        if not WINDOWS_AVAILABLE:
            return
            
        try:
            import comtypes
            comtypes.CoInitialize()
        except:
            pass
            
        try:
            from pycaw.pycaw import AudioUtilities
            devices = AudioUtilities.GetSpeakers()
            self._volume_interface = devices.EndpointVolume
            print("[SystemControl] Audio initialized successfully")
        except Exception as e:
            print(f"[SystemControl] Audio init failed: {e}")
            self._volume_interface = None
    
    @registry.register("Check current system volume level (0-100). Returns integer.")
    def get_volume(self) -> int:
        """Get current system volume (0-100)"""
        if self._volume_interface:
            try:
                volume = self._volume_interface.GetMasterVolumeLevelScalar()
                return int(volume * 100)
            except Exception as e:
                print(f"[SystemControl] Error getting volume: {e}")
        return -1
    
    @registry.register("Set system volume. Pass an integer between 0 and 100.")
    def set_volume(self, level: int) -> Tuple[bool, str]:
        """Set system volume"""
        # Convert to int (AI might pass string)
        try:
            level = int(level)
        except (ValueError, TypeError):
            return False, f"Invalid volume level: {level}"
        
        level = max(0, min(100, level))
        
        if self._volume_interface:
            try:
                self._volume_interface.SetMasterVolumeLevelScalar(level / 100.0, None)
                return True, f"Volume diatur ke {level}%"
            except Exception as e:
                return False, f"Error setting volume: {e}"
        
        return False, "Audio interface not available"
    
    @registry.register("Mute or unmute system audio. True to mute, False to unmute.")
    def mute(self, mute: bool = True) -> Tuple[bool, str]:
        """Mute/unmute system audio"""
        if not self._volume_interface:
            return False, "Audio interface not available"
        
        try:
            self._volume_interface.SetMute(mute, None)
            status = "dimute" if mute else "di-unmute"
            return True, f"Audio {status}"
        except Exception as e:
            return False, f"Error: {e}"
    
    def is_muted(self) -> bool:
        """Check if system is muted"""
        if not self._volume_interface:
            return False
        try:
            return bool(self._volume_interface.GetMute())
        except:
            return False
    
    @registry.register("Open a Windows application like Notepad, Calculator, WhatsApp.")
    def open_application(self, app_name: str) -> Tuple[bool, str]:
        """Open an application by name"""
        app_lower = app_name.lower().strip()
        
        command = ALLOWED_APPS.get(app_lower)
        
        if not command:
            for key, cmd in ALLOWED_APPS.items():
                if app_lower in key or key in app_lower:
                    command = cmd
                    break
        
        if not command:
            return False, f"Aplikasi '{app_name}' tidak dikenali"
        
        target = command[len("start "):].strip() if command.startswith("start ") else command
        print(f"[SystemControl] Launching: {target}")

        # Tanpa shell=True. Command berasal dari whitelist ALLOWED_APPS.
        try:
            if URI_SCHEME.match(target):
                os.startfile(target)
                return True, f"Membuka {app_name}..."

            resolved = shutil.which(target)
            if resolved and resolved.lower().endswith(".exe"):
                proc = subprocess.Popen(
                    [resolved],
                    # Aplikasi konsol (cmd, powershell) butuh jendela sendiri
                    creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
                )
                self._track_process(app_name, proc.pid)
                return True, f"Membuka {app_name} (PID {proc.pid})..."

            # Tidak ada di PATH (chrome, msedge, winword: terdaftar di App Paths)
            # atau script .cmd (VS Code): ShellExecute, sama seperti perintah `start`
            os.startfile(resolved or target)
            return True, f"Membuka {app_name}..."
        except OSError as e:
            return False, f"Gagal membuka {app_name}: {e}"

    def _track_process(self, app_name: str, pid: int):
        try:
            created = psutil.Process(pid).create_time()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return
        self._opened_apps.setdefault(_process_key(app_name), []).append((pid, created))

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

    @staticmethod
    def _close_processes(procs: list) -> Tuple[int, int]:
        """
        Tutup proses dan kembalikan (jumlah tertutup, jumlah jendela masih terbuka).

        Proses berjendela dikirimi WM_CLOSE, sama seperti user menekan tombol X,
        sehingga aplikasi sempat menawarkan simpan dan tidak pernah di-kill paksa.
        Hanya proses tanpa jendela yang di-terminate lalu di-kill setelah timeout.
        """
        windows = _windows_by_pid({proc.pid for proc in procs})
        signaled = []
        for proc in procs:
            try:
                if proc.pid in windows:
                    for hwnd in windows[proc.pid]:
                        _post_close(hwnd)
                else:
                    proc.terminate()
                signaled.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                print(f"[SystemControl] Gagal menutup PID {proc.pid}: {e}")

        gone, alive = psutil.wait_procs(signaled, timeout=CLOSE_TIMEOUT_SEC)
        still_open = 0
        for proc in alive:
            if proc.pid in windows:
                # Kemungkinan menunggu dialog "simpan perubahan?"; biarkan user memutuskan
                still_open += 1
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
        target = _process_key(app_name)

        if not target:
            return False, "Nama aplikasi kosong"
        if target in PROTECTED_PROCESSES:
            return False, f"Proses '{target}' dilindungi dan tidak boleh ditutup"

        procs = {proc.pid: proc for proc in self._tracked_processes(target)}
        for proc in psutil.process_iter(['name']):
            proc_name = (proc.info['name'] or "").lower()
            if proc_name.endswith(".exe"):
                proc_name = proc_name[:-4]
            if proc_name == target:
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
            
    @registry.register("Open a specific local folder or directory path in Windows Explorer. E.g. 'Desktop', 'Downloads', atau nama folder spesifik.")
    def open_folder(self, folder_name_or_path: str) -> Tuple[bool, str]:
        """Open a directory/folder using Windows Explorer"""
        import os
        from pathlib import Path
        
        path = folder_name_or_path.strip()
        
        # Mapping nama umum
        common_dirs = {
            "desktop": os.path.join(os.path.expanduser("~"), "Desktop"),
            "downloads": os.path.join(os.path.expanduser("~"), "Downloads"),
            "documents": os.path.join(os.path.expanduser("~"), "Documents"),
            "pictures": os.path.join(os.path.expanduser("~"), "Pictures"),
            "music": os.path.join(os.path.expanduser("~"), "Music"),
            "videos": os.path.join(os.path.expanduser("~"), "Videos"),
            "kuliah": os.path.join(os.path.expanduser("~"), "Documents", "Kuliah") # Fallback dummy
        }
        
        if path.lower() in common_dirs:
            target = common_dirs[path.lower()]
            os.makedirs(target, exist_ok=True)
            os.startfile(target)
            return True, f"Membuka folder {path}..."
            
        # Jika bukan absolut path, asumsikan mencari di Documents atau Desktop
        if not os.path.isabs(path):
            candidates = [
                os.path.join(os.path.expanduser("~"), "Desktop", path),
                os.path.join(os.path.expanduser("~"), "Documents", path)
            ]
            for c in candidates:
                if os.path.exists(c) and os.path.isdir(c):
                    os.startfile(c)
                    return True, f"Membuka folder {path} di sistem..."
                    
        if not os.path.isdir(path):
            return False, f"Folder '{path}' tidak ditemukan"

        try:
            # Argumen list tanpa shell: path dari LLM tidak bisa menyisipkan perintah
            subprocess.Popen(["explorer", path])
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

    @registry.register(name="media_control", description="Mengontrol pemutaran media pada komputer (bisa Play/Pause/Jeda musik Spotify maupun video YouTube). Isi parameter `action_type` dengan: 'play', 'pause', 'next' (berikutnya), atau 'prev' (sebelumnya).")
    def media_control(self, action_type: str) -> Tuple[bool, str]:
        """Controls system media playback like a multimedia keyboard."""
        try:
            import pyautogui
            action_type = action_type.lower()
            if action_type in ["play", "pause", "play_pause", "playpause", "toggle"]:
                pyautogui.press("playpause")
                return True, f"Play/Pause status media saat ini ditekan."
            elif action_type in ["next", "berikutnya", "skip"]:
                pyautogui.press("nexttrack")
                return True, "Memutar lagu/video selanjutnya."
            elif action_type in ["prev", "previous", "sebelumnya", "back"]:
                pyautogui.press("prevtrack")
                return True, "Kembali ke lagu/video sebelumnya."
            else:
                return False, f"Aksi '{action_type}' tidak dimengerti."
        except Exception as e:
            return False, f"Gagal menekan tombol media: {e}"

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
            return False, f"Window tidak ditemukan"
        except Exception as e:
            return False, f"Error: {e}"
    
    @registry.register("Type text using keyboard automation. Use this to search or type something.")
    def type_text(self, text: str) -> Tuple[bool, str]:
        """Type text menggunakan keyboard automation"""
        if not WINDOWS_AVAILABLE:
            return False, "PyAutoGUI not available"
        
        try:
            # Force fast typing, ignore AI hallucinated delays
            pyautogui.typewrite(text, interval=0.02)
            return True, f"Mengetik: {text[:30]}..."
        except Exception as e:
            return False, f"Error: {e}"
    
    @registry.register("Press a keyboard key (like 'enter', 'tab', 'down')")
    def press_key(self, key: str) -> Tuple[bool, str]:
        """Press a keyboard key"""
        if not WINDOWS_AVAILABLE:
            return False, "PyAutoGUI not available"
        
        try:
            pyautogui.press(key)
            return True, f"Menekan tombol: {key}"
        except Exception as e:
            return False, f"Error: {e}"
    
    @registry.register("Press a combination of hotkeys (e.g., ['ctrl', 'c'] or ['win', 'd'])")
    def hotkey(self, keys: list) -> Tuple[bool, str]:
        """Press hotkey combination"""
        if not WINDOWS_AVAILABLE:
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
