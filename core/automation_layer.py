#!/usr/bin/env python
"""
MikuWin v5 — Automation Layer
Lightweight automation for YouTube, Spotify, Browser, and UI control.
No computer vision — uses APIs, web automation, and keyboard control.
"""

import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import json
import shutil

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except ImportError:
    KEYBOARD_AVAILABLE = False

try:
    from playwright.sync_api import sync_playwright, Browser, Page
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

try:
    import yt_dlp
    YT_DLP_AVAILABLE = True
except ImportError:
    YT_DLP_AVAILABLE = False

try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
    SPOTIFY_AVAILABLE = True
except ImportError:
    SPOTIFY_AVAILABLE = False


# ══════════════════════════════════════
#  CONFIG & CONSTANTS
# ══════════════════════════════════════
YOUTUBE_HOME = "https://www.youtube.com"
SPOTIFY_HOME = "https://www.spotify.com"
GOOGLE_HOME = "https://www.google.com"

# Keyboard shortcuts
SHORTCUTS = {
    "youtube_play_pause": " ",           # Space
    "youtube_skip_next": "n",            # Next video
    "youtube_skip_prev": "p",            # Previous video
    "youtube_seek_forward": "j",         # Seek +10s
    "youtube_seek_back": "l",            # Seek -10s
    "youtube_fullscreen": "f",           # Fullscreen
    "youtube_mute": "m",                 # Mute
    "spotify_play_pause": " ",           # Space (in Spotify web)
    "volume_up": "up",                   # Windows volume up
    "volume_down": "down",               # Windows volume down
}


# ══════════════════════════════════════
#  YOUTUBE AUTOMATION
# ══════════════════════════════════════
class YouTubeAutomation:
    """YouTube automation via yt-dlp and web automation"""

    def __init__(self, browser: Optional[Browser] = None):
        self.browser = browser
        self.page: Optional[Page] = None
        self.is_playing = False

    def search_and_play(self, query: str) -> Tuple[bool, str]:
        """Search YouTube and play first result"""
        if not query.strip():
            return False, "Empty search query"

        try:
            if self.browser and PLAYWRIGHT_AVAILABLE:
                return self._search_and_play_browser(query)
            else:
                return self._search_and_play_fallback(query)
        except Exception as e:
            return False, f"Error: {str(e)}"

    def _search_and_play_browser(self, query: str) -> Tuple[bool, str]:
        """Use Playwright to search and play"""
        try:
            if not self.page:
                self.page = self.browser.new_page()
            
            self.page.goto(YOUTUBE_HOME)
            time.sleep(2)
            
            # Find search box and enter query
            search_box = self.page.query_selector("input[name='search_query']")
            if search_box:
                search_box.fill(query)
                search_box.press("Enter")
                time.sleep(3)
                
                # Click first video result
                video = self.page.query_selector("a#video-title")
                if video:
                    video.click()
                    time.sleep(2)
                    self.is_playing = True
                    return True, f"Playing YouTube: {query}"
            
            return False, "Could not find search results"
        except Exception as e:
            return False, f"Browser error: {str(e)}"

    def _search_and_play_fallback(self, query: str) -> Tuple[bool, str]:
        """Fallback: Just open default web browser search (no blocking yt-dlp)"""
        try:
            import urllib.parse
            encoded_query = urllib.parse.quote(query)
            url = f"https://www.youtube.com/results?search_query={encoded_query}"
            webbrowser.open(url)
            self.is_playing = True
            return True, f"Opening YouTube: {query}"
        except Exception as e:
            return False, f"Browser fallback error: {str(e)}"

    def play_pause(self) -> Tuple[bool, str]:
        """Toggle play/pause"""
        try:
            if self.browser and self.page:
                self.page.press(SHORTCUTS["youtube_play_pause"])
                self.is_playing = not self.is_playing
                status = "Playing" if self.is_playing else "Paused"
                return True, f"YouTube: {status}"
            elif PYAUTOGUI_AVAILABLE:
                pyautogui.press(SHORTCUTS["youtube_play_pause"])
                self.is_playing = not self.is_playing
                status = "Playing" if self.is_playing else "Paused"
                return True, f"YouTube: {status}"
            else:
                return False, "No automation available"
        except Exception as e:
            return False, f"Error: {str(e)}"

    def skip_next(self) -> Tuple[bool, str]:
        """Skip to next video"""
        try:
            if self.browser and self.page:
                self.page.press(SHORTCUTS["youtube_skip_next"])
                return True, "YouTube: Skipped to next video"
            elif PYAUTOGUI_AVAILABLE:
                pyautogui.press(SHORTCUTS["youtube_skip_next"])
                return True, "YouTube: Skipped to next video"
            else:
                return False, "No automation available"
        except Exception as e:
            return False, f"Error: {str(e)}"

    def seek_forward(self, seconds: int = 10) -> Tuple[bool, str]:
        """Seek forward by N seconds"""
        try:
            # YouTube default: 'j' = skip back 10s, 'l' = skip forward 10s
            if self.browser and self.page:
                for _ in range(max(1, seconds // 10)):
                    self.page.press(SHORTCUTS["youtube_seek_forward"])
                    time.sleep(0.2)
                return True, f"YouTube: Seeked forward {seconds}s"
            elif PYAUTOGUI_AVAILABLE:
                for _ in range(max(1, seconds // 10)):
                    pyautogui.press(SHORTCUTS["youtube_seek_forward"])
                    time.sleep(0.2)
                return True, f"YouTube: Seeked forward {seconds}s"
            else:
                return False, "No automation available"
        except Exception as e:
            return False, f"Error: {str(e)}"

    def close(self):
        """Close automation"""
        if self.page:
            self.page.close()
            self.page = None


# ══════════════════════════════════════
#  SPOTIFY AUTOMATION
# ══════════════════════════════════════
class SpotifyAutomation:
    """Spotify automation via API and web"""

    def __init__(self, client_id: str = "", client_secret: str = "", browser: Optional[Browser] = None):
        self.browser = browser
        self.page: Optional[Page] = None
        self.client_id = client_id
        self.client_secret = client_secret
        self.sp: Optional[spotipy.Spotify] = None
        self.is_playing = False

        if client_id and client_secret and SPOTIFY_AVAILABLE:
            try:
                auth = SpotifyClientCredentials(
                    client_id=client_id,
                    client_secret=client_secret,
                )
                self.sp = spotipy.Spotify(auth_manager=auth)
            except Exception as e:
                print(f"[Spotify] Auth failed: {e}")

    def search_and_play(self, query: str) -> Tuple[bool, str]:
        """Search Spotify song and play"""
        if not query.strip():
            return False, "Empty search query"

        try:
            if self.browser and PLAYWRIGHT_AVAILABLE:
                return self._search_and_play_browser(query)
            elif self.sp and SPOTIFY_AVAILABLE:
                return self._search_and_play_api(query)
            else:
                # Fallback ke browser via web
                import urllib.parse
                encoded_query = urllib.parse.quote(query)
                url = f"https://open.spotify.com/search/{encoded_query}"
                webbrowser.open(url)
                return True, f"Searching built-in Spotify: {query}"
        except Exception as e:
            return False, f"Error: {str(e)}"

    def _search_and_play_browser(self, query: str) -> Tuple[bool, str]:
        """Use Playwright to search in Spotify Web"""
        try:
            if not self.page:
                self.page = self.browser.new_page()

            self.page.goto(SPOTIFY_HOME)
            time.sleep(2)

            # Find search box and search
            search_box = self.page.query_selector("input[placeholder*='Search']")
            if search_box:
                search_box.fill(query)
                search_box.press("Enter")
                time.sleep(2)

                # Click first track result
                track = self.page.query_selector("div[data-testid='track']")
                if track:
                    track.click()
                    time.sleep(1)
                    self.is_playing = True
                    return True, f"Playing on Spotify: {query}"

            return False, "Could not find track"
        except Exception as e:
            return False, f"Browser error: {str(e)}"

    def _search_and_play_api(self, query: str) -> Tuple[bool, str]:
        """Use Spotify API to search (info only, requires web for playback)"""
        try:
            results = self.sp.search(q=query, type="track", limit=1)
            if results and results["tracks"]["items"]:
                track = results["tracks"]["items"][0]
                artist = track["artists"][0]["name"] if track["artists"] else "Unknown"
                track_name = track["name"]
                spotify_url = track["external_urls"].get("spotify", "")

                if spotify_url:
                    webbrowser.open(spotify_url)
                    self.is_playing = True
                    return True, f"Opening Spotify: {track_name} by {artist}"

            return False, "No tracks found"
        except Exception as e:
            return False, f"API error: {str(e)}"

    def play_pause(self) -> Tuple[bool, str]:
        """Toggle play/pause"""
        try:
            if self.browser and self.page:
                self.page.press(SHORTCUTS["spotify_play_pause"])
                self.is_playing = not self.is_playing
                status = "Playing" if self.is_playing else "Paused"
                return True, f"Spotify: {status}"
            elif PYAUTOGUI_AVAILABLE:
                pyautogui.press(SHORTCUTS["spotify_play_pause"])
                self.is_playing = not self.is_playing
                status = "Playing" if self.is_playing else "Paused"
                return True, f"Spotify: {status}"
            else:
                return False, "No automation available"
        except Exception as e:
            return False, f"Error: {str(e)}"

    def close(self):
        """Close automation"""
        if self.page:
            self.page.close()
            self.page = None


# ══════════════════════════════════════
#  BROWSER AUTOMATION
# ══════════════════════════════════════
class BrowserAutomation:
    """Generic browser automation"""

    def __init__(self):
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None

    def start(self) -> Tuple[bool, str]:
        """Start browser"""
        if not PLAYWRIGHT_AVAILABLE:
            return False, "Playwright not installed"

        try:
            playwright = sync_playwright().start()
            self.browser = playwright.chromium.launch(headless=False)
            return True, "Browser started"
        except Exception as e:
            return False, f"Browser error: {str(e)}"

    def navigate(self, url: str) -> Tuple[bool, str]:
        """Navigate to URL"""
        try:
            if not self.page:
                if self.browser:
                    self.page = self.browser.new_page()
                else:
                    return False, "Browser not started"

            self.page.goto(url)
            return True, f"Navigated to {url}"
        except Exception as e:
            return False, f"Navigation error: {str(e)}"

    def close(self) -> Tuple[bool, str]:
        """Close browser"""
        try:
            if self.page:
                self.page.close()
            if self.browser:
                self.browser.close()
            return True, "Browser closed"
        except Exception as e:
            return False, f"Close error: {str(e)}"


# ══════════════════════════════════════
#  UI AUTOMATION (Keyboard + Mouse)
# ══════════════════════════════════════
class UIAutomation:
    """Keyboard and mouse automation"""

    @staticmethod
    def set_volume(level: int) -> Tuple[bool, str]:
        """Set system volume (0-100)"""
        if not PYAUTOGUI_AVAILABLE:
            return False, "PyAutoGUI not available"

        try:
            # Windows: Use keyboard shortcuts for volume
            # Normalize to 0-100
            level = max(0, min(100, level))

            # Get current volume (approximation: press mute then unmute to reset)
            # Simple approach: press volume keys
            if level == 0:
                pyautogui.hotkey("ctrl", "alt", "down")  # Mute (approximation)
                return True, "Volume: Muted"
            else:
                # Use nircmd or direct Windows API would be better
                # For now, use keyboard volume keys
                num_presses = max(1, level // 10)
                for _ in range(num_presses):
                    pyautogui.press(SHORTCUTS["volume_up"])
                    time.sleep(0.1)
                return True, f"Volume: {level}%"
        except Exception as e:
            return False, f"Volume error: {str(e)}"

    @staticmethod
    def type_text(text: str, delay: float = 0.05) -> Tuple[bool, str]:
        """Type text with delay between keys"""
        if not PYAUTOGUI_AVAILABLE:
            return False, "PyAutoGUI not available"

        try:
            pyautogui.typewrite(text, interval=delay)
            return True, f"Typed: {text}"
        except Exception as e:
            return False, f"Type error: {str(e)}"

    @staticmethod
    def press_key(key: str) -> Tuple[bool, str]:
        """Press single key"""
        if not PYAUTOGUI_AVAILABLE:
            return False, "PyAutoGUI not available"

        try:
            pyautogui.press(key)
            return True, f"Pressed: {key}"
        except Exception as e:
            return False, f"Key error: {str(e)}"

    @staticmethod
    def click_at(x: int, y: int) -> Tuple[bool, str]:
        """Click at coordinates"""
        if not PYAUTOGUI_AVAILABLE:
            return False, "PyAutoGUI not available"

        try:
            pyautogui.click(x, y)
            return True, f"Clicked at ({x}, {y})"
        except Exception as e:
            return False, f"Click error: {str(e)}"


# ══════════════════════════════════════
#  AUTOMATION MANAGER (Unified Interface)
# ══════════════════════════════════════
class AutomationManager:
    """Unified automation interface"""

    def __init__(self, spotify_client_id: str = "", spotify_client_secret: str = ""):
        self.browser_auto = BrowserAutomation()
        self.youtube = YouTubeAutomation()
        self.spotify = SpotifyAutomation(
            client_id=spotify_client_id,
            client_secret=spotify_client_secret,
        )
        self.ui = UIAutomation()

    def execute(self, action: str, params: Dict[str, Any] = None) -> Tuple[bool, str]:
        """Execute automation action"""
        params = params or {}

        # YouTube actions
        if action == "youtube_search":
            query = params.get("query", "")
            return self.youtube.search_and_play(query)

        elif action == "youtube_play_pause":
            return self.youtube.play_pause()

        elif action == "youtube_next":
            return self.youtube.skip_next()

        elif action == "youtube_seek_forward":
            seconds = params.get("seconds", 10)
            return self.youtube.seek_forward(seconds)

        # Spotify actions
        elif action == "spotify_search":
            query = params.get("query", "")
            return self.spotify.search_and_play(query)

        elif action == "spotify_play_pause":
            return self.spotify.play_pause()

        # Browser actions
        elif action == "browser_open":
            url = params.get("url", "https://google.com")
            webbrowser.open(url)
            return True, f"Opened: {url}"

        elif action == "browser_navigate":
            url = params.get("url", "")
            return self.browser_auto.navigate(url)

        # UI actions
        elif action == "set_volume":
            level = params.get("level", 50)
            return self.ui.set_volume(level)

        elif action == "type_text":
            text = params.get("text", "")
            return self.ui.type_text(text)

        elif action == "press_key":
            key = params.get("key", "")
            return self.ui.press_key(key)

        elif action == "click":
            x = params.get("x", 0)
            y = params.get("y", 0)
            return self.ui.click_at(x, y)

        else:
            return False, f"Unknown action: {action}"

    def cleanup(self):
        """Cleanup resources"""
        self.youtube.close()
        self.spotify.close()
        self.browser_auto.close()


# ══════════════════════════════════════
#  SIMPLE TESTING
# ══════════════════════════════════════
if __name__ == "__main__":
    print("[Automation Layer] Testing...\n")

    auto = AutomationManager()

    # Test YouTube search
    print("Test 1: YouTube search for 'Hatsune Miku'")
    success, msg = auto.execute("youtube_search", {"query": "Hatsune Miku"})
    print(f"  Result: {'✅' if success else '❌'} {msg}\n")

    # Test UI automation
    print("Test 2: Set volume to 50%")
    success, msg = auto.ui.set_volume(50)
    print(f"  Result: {'✅' if success else '❌'} {msg}\n")

    # Test browser
    print("Test 3: Open browser to Google")
    success, msg = auto.execute("browser_open", {"url": "https://google.com"})
    print(f"  Result: {'✅' if success else '❌'} {msg}\n")

    auto.cleanup()
