#!/usr/bin/env python
"""
MikuWin v4 — Avatar Window (Sprite Display)
Pygame-based animated sprite mascot window, based on My_Miku_v3 concept.
Runs in background thread, safe for CLI voice mode.
"""

import pygame
import sys
import os
import time
import random
import ctypes
import threading
from ctypes import wintypes
from pathlib import Path
from typing import Optional, Dict, List

try:
    import win32api
    import win32con
    import win32gui
    WINDOWS_API_AVAILABLE = True
except ImportError:
    WINDOWS_API_AVAILABLE = False


# ══════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════
FRAME_W = 177
FRAME_H = 213
WIN_W = 220
WIN_H = 250
FPS_ANIM = 8
WALK_SPEED = 2
FUCHSIA = (255, 0, 128)
ALPHA_THR = 80

# Animation sequences (frame indices from sprite sheet)
ANIMATIONS: Dict[str, List[int]] = {
    "idle_front": [0, 1, 2, 3, 4],
    "idle_side_r": [5, 6, 7, 8],
    "idle_back": [9, 10, 11],
    "idle_side_l": [12, 13, 14],
    "idle_extra": [15, 16, 17, 18, 19],
    "walk_right": [20, 21, 22, 23, 24, 25],
    "walk_left": [26, 27, 28, 29, 30, 31],
    "run_right": [32, 33, 34, 35],
    "run_left": [36, 37, 38, 39],
    "jump_rise": [40, 41, 42],
    "jump_apex": [43, 44],
    "jump_fall": [45, 46, 47],
    "float": [48, 49, 50, 51],
    "fly": [52, 53, 54, 55],
    "attack_punch": [60, 61, 62],
    "attack_kick": [63, 64, 65],
    "attack_magic": [66, 67, 68, 69],
    "action_misc": [70, 71, 72, 73, 74],
    "hurt": [100, 101, 102],
    "knockback": [103, 104, 105],
    "ko": [106, 107],
    "crouch": [108, 109],
    "sit": [110, 111],
    "sing": [120, 121, 122, 123],
    "celebrate": [124, 125, 126, 127],
    "dance": [128, 129, 130, 131],
    "perform": [132, 133, 134, 135],
}

# State → animation mapping for emotion display
EMOTION_ANIMATIONS: Dict[str, str] = {
    "neutral": "idle_front",
    "happy": "celebrate",
    "excited": "dance",
    "thinking": "crouch",
    "confused": "sit",
    "sad": "hurt",
    "embarrassed": "idle_extra",
    "annoyed": "action_misc",
    "listening": "idle_side_r",
    "speaking": "sing",
}


# ══════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════
def setup_window(hwnd):
    """Configure window as transparent layered window (Windows only)"""
    if not WINDOWS_API_AVAILABLE:
        return

    try:
        win32gui.SetWindowLong(
            hwnd,
            win32con.GWL_EXSTYLE,
            win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            | win32con.WS_EX_LAYERED
            | win32con.WS_EX_TOPMOST
            | win32con.WS_EX_TOOLWINDOW,
        )
        win32gui.SetLayeredWindowAttributes(
            hwnd, win32api.RGB(*FUCHSIA), 0, win32con.LWA_COLORKEY
        )
    except Exception as e:
        print(f"[avatar_window] Warning: Could not setup transparent window: {e}")


def move_topmost(hwnd, x, y, w, h):
    """Position window topmost (Windows only)"""
    if not WINDOWS_API_AVAILABLE:
        return

    try:
        win32gui.SetWindowPos(
            hwnd,
            win32con.HWND_TOPMOST,
            int(x),
            int(y),
            w,
            h,
            win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW,
        )
    except Exception:
        pass


def cursor_pos():
    """Get current cursor position (Windows only)"""
    if not WINDOWS_API_AVAILABLE:
        return 0, 0

    try:
        pt = wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y
    except Exception:
        return 0, 0


# ══════════════════════════════════════
#  SPRITE LOADER
# ══════════════════════════════════════
def load_frames(path: str) -> list:
    """Load sprite frames from PNG sheet"""
    from PIL import Image

    if not os.path.exists(path):
        print(f"[avatar_window] ERROR: '{path}' not found, using placeholder")
        return []

    sheet = Image.open(path).convert("RGBA")
    sw, sh = sheet.size
    cols = sw // FRAME_W
    rows = sh // FRAME_H
    out = []

    for r in range(rows):
        for c in range(cols):
            crop = sheet.crop(
                (
                    c * FRAME_W,
                    r * FRAME_H,
                    c * FRAME_W + FRAME_W,
                    r * FRAME_H + FRAME_H,
                )
            )
            out.append(_pil_to_pygame(crop))

    print(f"[avatar_window] Loaded {len(out)} frames ({cols}×{rows})")
    return out


def _pil_to_pygame(crop) -> pygame.Surface:
    """Convert PIL Image to Pygame surface with color key"""
    rgba = crop.convert("RGBA")
    px = rgba.load()
    fw, fh = rgba.size

    # Replace transparent pixels with FUCHSIA color for colorkeying
    for y in range(fh):
        for x in range(fw):
            r, g, b, a = px[x, y]
            px[x, y] = (*FUCHSIA, 255) if a < ALPHA_THR else (r, g, b, 255)

    rgb = rgba.convert("RGB")
    surf = pygame.image.fromstring(rgb.tobytes(), (fw, fh), "RGB")
    surf.set_colorkey(FUCHSIA)
    return surf


# ══════════════════════════════════════
#  AVATAR/MASCOT
# ══════════════════════════════════════
class SpriteAvatar:
    """Animated sprite character"""

    def __init__(self, frames: list, screen_w: int, screen_h: int, hwnd=None):
        self.frames = frames
        self.frames_mirror = (
            [pygame.transform.flip(f, True, False) for f in frames]
            if frames
            else []
        )
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.hwnd = hwnd

        # Position (float for smooth movement)
        self.x = float(screen_w - WIN_W - 100) if screen_w > 0 else 0
        self.y = float(screen_h - WIN_H - 60) if screen_h > 0 else 0

        # Animation state
        self.state = "idle_front"
        self.frame_idx = 0
        self.last_frame_time = time.time()

        # Dragging
        self.dragging = False
        self.drag_sx = self.drag_sy = 0
        self.drag_ox = self.drag_oy = 0.0

        # State timer
        self.state_timer = time.time()
        self.state_wait = random.uniform(3, 6)

    def current_surface(self) -> Optional[pygame.Surface]:
        """Get current animation frame"""
        if not self.frames:
            return None

        lst = ANIMATIONS.get(self.state, ANIMATIONS["idle_front"])
        now = time.time()

        # Advance frame based on FPS
        if now - self.last_frame_time > 1.0 / FPS_ANIM:
            self.frame_idx = (self.frame_idx + 1) % len(lst)
            self.last_frame_time = now

        frame_seq_idx = lst[self.frame_idx]
        if frame_seq_idx >= len(self.frames):
            frame_seq_idx = 0

        return self.frames[frame_seq_idx]

    def update(self):
        """Update position and state"""
        if self.dragging:
            sx, sy = cursor_pos()
            self.x = self.drag_ox + (sx - self.drag_sx)
            self.y = self.drag_oy + (sy - self.drag_sy)
            if self.hwnd:
                move_topmost(self.hwnd, self.x, self.y, WIN_W, WIN_H)
            return

        # Auto-transition state periodically
        if time.time() - self.state_timer > self.state_wait:
            self._random_state()

        # Movement states
        if self.state == "walk_right":
            self.x += WALK_SPEED
            if self.x + WIN_W >= self.screen_w:
                self.x = float(self.screen_w - WIN_W) if self.screen_w > 0 else 0
                self._set("walk_left")
        elif self.state == "walk_left":
            self.x -= WALK_SPEED
            if self.x <= 0:
                self.x = 0.0
                self._set("walk_right")

        if self.hwnd:
            move_topmost(self.hwnd, self.x, self.y, WIN_W, WIN_H)

    def _random_state(self):
        """Pick random idle/animation state"""
        choices = [
            ("idle_front", 5),
            ("idle_side_r", 2),
            ("idle_side_l", 2),
            ("idle_extra", 1),
            ("sing", 2),
            ("celebrate", 1),
            ("dance", 1),
        ]
        selected = random.choices(
            [s for s, _ in choices], weights=[w for _, w in choices]
        )[0]
        self._set(selected)

    def _set(self, state: str, wait: Optional[float] = None):
        """Change animation state"""
        if state not in ANIMATIONS:
            state = "idle_front"

        self.state = state
        self.frame_idx = 0
        self.state_timer = time.time()
        self.state_wait = wait if wait else random.uniform(3, 8)

    def set_emotion(self, emotion: str):
        """Set state based on emotion name"""
        anim = EMOTION_ANIMATIONS.get(emotion, "idle_front")
        if anim == self.state:
            return  # No change
        self._set(anim, wait=2.0)  # Hold emotion for 2 seconds

    def on_drag_start(self):
        """Start dragging avatar"""
        sx, sy = cursor_pos()
        self.dragging = True
        self.drag_sx = sx
        self.drag_sy = sy
        self.drag_ox = self.x
        self.drag_oy = self.y
        self._set("idle_front", wait=999)

    def on_drag_end(self):
        """Stop dragging avatar"""
        if self.dragging:
            self.dragging = False
            self._set("idle_front", wait=2.0)

    def draw(self, screen: pygame.Surface):
        """Render frame to screen"""
        screen.fill(FUCHSIA)
        surf = self.current_surface()
        if surf:
            ox = (WIN_W - FRAME_W) // 2
            oy = (WIN_H - FRAME_H) // 2
            screen.blit(surf, (ox, oy))


# ══════════════════════════════════════
#  WINDOW MANAGER
# ══════════════════════════════════════
class AvatarWindow:
    """Pygame window running in background thread"""

    def __init__(self, sprite_sheet_path: str, on_interact_callback=None, on_quit_callback=None):
        self.sprite_sheet_path = sprite_sheet_path
        self.on_interact_callback = on_interact_callback
        self.on_quit_callback = on_quit_callback
        self.running = False
        self.thread: Optional[threading.Thread] = None

        # Shared state
        self.emotion = "neutral"
        self._emotion_lock = threading.Lock()

        # Pygame objects
        self.screen: Optional[pygame.Surface] = None
        self.avatar: Optional[SpriteAvatar] = None
        self.clock: Optional[pygame.time.Clock] = None
        self.hwnd = None

    def start(self):
        """Spawn avatar window in background thread"""
        if self.thread and self.thread.is_alive():
            print("[avatar_window] Already running")
            return

        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        print("[avatar_window] Started")

    def stop(self):
        """Stop avatar window"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        print("[avatar_window] Stopped")

    def set_emotion(self, emotion: str):
        """Update avatar emotion (thread-safe)"""
        with self._emotion_lock:
            self.emotion = emotion
        if self.avatar:
            self.avatar.set_emotion(emotion)

    def _run(self):
        """Main window loop (runs in thread)"""
        try:
            pygame.init()
            info = pygame.display.Info()
            sw, sh = info.current_w, info.current_h

            self.screen = pygame.display.set_mode((WIN_W, WIN_H), pygame.NOFRAME)
            pygame.display.set_caption("Miku Avatar")

            frames = load_frames(self.sprite_sheet_path)
            if not frames:
                print("[avatar_window] No frames loaded, falling back to placeholder")

            self.hwnd = None
            if WINDOWS_API_AVAILABLE:
                try:
                    info_dict = pygame.display.get_wm_info()
                    self.hwnd = info_dict.get("window")
                    if self.hwnd:
                        setup_window(self.hwnd)
                except Exception as e:
                    print(f"[avatar_window] Could not get hwnd: {e}")

            self.avatar = SpriteAvatar(frames, sw, sh, self.hwnd)
            if self.hwnd:
                move_topmost(
                    self.hwnd, int(self.avatar.x), int(self.avatar.y), WIN_W, WIN_H
                )

            self.clock = pygame.time.Clock()

            print("[avatar_window] Window ready")
            print("[avatar_window] Left-click = drag  |  Right-click = menu  |  ESC = exit")

            while self.running:
                # Check emotion update
                with self._emotion_lock:
                    current_emotion = self.emotion

                # Global mouse tracking for "Drag Anywhere" in bounding box
                # Because LWA_COLORKEY drops clicks on transparent pixels, this catches them
                if WINDOWS_API_AVAILABLE:
                    left_down = win32api.GetAsyncKeyState(win32con.VK_LBUTTON) < 0
                    if left_down:
                        if not self.avatar.dragging:
                            cx, cy = cursor_pos()
                            if (self.avatar.x <= cx <= self.avatar.x + WIN_W) and \
                               (self.avatar.y <= cy <= self.avatar.y + WIN_H):
                                self.avatar.on_drag_start()
                                # Prevent pygame event loop from double-firing
                    else:
                        if self.avatar.dragging:
                            self.avatar.on_drag_end()
                            if self.on_interact_callback:
                                self.on_interact_callback()

                # Process events
                for e in pygame.event.get():
                    if e.type == pygame.QUIT:
                        self.running = False
                    elif e.type == pygame.KEYDOWN:
                        if e.key == pygame.K_ESCAPE:
                            self.running = False
                    elif e.type == pygame.MOUSEBUTTONDOWN:
                        if e.button == 1 and not WINDOWS_API_AVAILABLE:  # Fallback for non-Windows
                            self.avatar.on_drag_start()
                        elif e.button == 3:  # Right click - menu (simple version)
                            if WINDOWS_API_AVAILABLE and self.hwnd:
                                menu = win32gui.CreatePopupMenu()
                                win32gui.AppendMenu(menu, win32con.MF_STRING, 1001, "Exit Miku")
                                pos = win32gui.GetCursorPos()
                                win32gui.SetForegroundWindow(self.hwnd)
                                cmd = win32gui.TrackPopupMenu(
                                    menu,
                                    win32con.TPM_LEFTALIGN | win32con.TPM_RETURNCMD | win32con.TPM_NONOTIFY,
                                    pos[0], pos[1], 0, self.hwnd, None
                                )
                                win32gui.DestroyMenu(menu)
                                if cmd == 1001:
                                    self.running = False
                                    if self.on_quit_callback:
                                        self.on_quit_callback()
                    elif e.type == pygame.MOUSEBUTTONUP:
                        if e.button == 1 and not WINDOWS_API_AVAILABLE:
                            was_dragging = self.avatar.dragging
                            self.avatar.on_drag_end()
                            # Notify interaction
                            if was_dragging and self.on_interact_callback:
                                self.on_interact_callback()

                # Update and draw
                self.avatar.update()
                self.avatar.draw(self.screen)
                pygame.display.flip()
                self.clock.tick(60)

            pygame.quit()
            print("[avatar_window] Closed")

        except Exception as e:
            print(f"[avatar_window] Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.running = False


# Singleton instance
_avatar_window: Optional[AvatarWindow] = None


def initialize_avatar_window(sprite_sheet_path: str, on_interact_callback=None, on_quit_callback=None) -> AvatarWindow:
    """Initialize global avatar window"""
    global _avatar_window
    if _avatar_window is None:
        _avatar_window = AvatarWindow(sprite_sheet_path, on_interact_callback, on_quit_callback)
    return _avatar_window


def get_avatar_window() -> Optional[AvatarWindow]:
    """Get current avatar window instance"""
    return _avatar_window


def cleanup_avatar_window():
    """Shutdown avatar window"""
    global _avatar_window
    if _avatar_window:
        _avatar_window.stop()
        _avatar_window = None


if __name__ == "__main__":
    # Test: Show avatar window
    sprite_path = Path(__file__).parent.parent / "assets" / "avatar" / "miku_smart_sheet.png"
    window = initialize_avatar_window(str(sprite_path))
    window.start()

    # Simple test loop
    emotions = ["neutral", "happy", "excited", "thinking", "sad", "singing"]
    import time
    try:
        for _ in range(30):
            for emotion in emotions:
                window.set_emotion(emotion)
                time.sleep(2)
    except KeyboardInterrupt:
        print("Interrupted")
    finally:
        cleanup_avatar_window()
