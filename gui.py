"""
MikuWin v4 GUI - Hatsune Miku Edition
"""

import customtkinter as ctk
from PIL import Image, ImageTk
import threading
import time
from pathlib import Path
from typing import Optional, Dict, List
import queue
import re
from tkinter import messagebox

import sys
sys.path.insert(0, str(Path(__file__).parent))

# Saat stdout bukan konsol (di-redirect, panel Run IDE, shortcut), Python memakai
# codepage ANSI dan print("初音ミク") melempar UnicodeEncodeError di thread
# inisialisasi, sehingga GUI tidak pernah siap. Paksa UTF-8.
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        if _stream is not None:
            _stream.reconfigure(encoding="utf-8", errors="replace")

# Lewat pythonw.exe (shortcut desktop) stdout/stderr bernilai None; transformers
# memanggil sys.stderr.flush saat import dan crash. Tulis ke file log sebagai gantinya.
if sys.stdout is None or sys.stderr is None:
    _log_dir = Path(__file__).parent / "data" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _gui_log = open(_log_dir / "gui.log", "a", encoding="utf-8", errors="replace", buffering=1)
    sys.stdout = sys.stdout or _gui_log
    sys.stderr = sys.stderr or _gui_log

from core.voice_input import VoiceInput
from core.voice_output import VoiceOutput
from core.voice_converter import VoiceConverter
from core.ai_brain import AIBrain
from core.system_control import SystemControl
from core.memory import MemoryManager
from core.commands import handle_command
from core.conversation import ToolResult, run_turn
from core.turn_log import TurnLogger

from config import (
    DATA_DIR,
    TURN_LOG_DIR,
    CHARACTERS,
    DEFAULT_CHARACTER,
    EMOTIONS,
    MIKU_SPRITE_SHEET,
    MIKU_FRAME_W,
    MIKU_FRAME_H,
    MIKU_SHEET_COLS,
    MIKU_EMOTION_FRAMES,
)


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class MikuSpriteAnimator:
    """Render animated Miku sprite in the GUI based on emotion state."""

    def __init__(self, widget: ctk.CTkLabel):
        self.widget = widget
        self.sheet_path = Path(MIKU_SPRITE_SHEET)
        self.frame_w = MIKU_FRAME_W
        self.frame_h = MIKU_FRAME_H
        self.cols = MIKU_SHEET_COLS

        self._sheet: Optional[Image.Image] = None
        self._cache: Dict[int, ImageTk.PhotoImage] = {}
        self._after_id: Optional[str] = None
        self._frame_idx = 0
        self._current_sequence: List[int] = [0]
        self._current_delay_ms = 120
        self._running = False
        self._direction = 1

        self.sequences: Dict[str, List[int]] = dict(MIKU_EMOTION_FRAMES)

        self.timing_ms: Dict[str, int] = {
            "neutral": 140,
            "happy": 120,
            "excited": 95,
            "thinking": 160,
            "confused": 165,
            "sad": 210,
            "embarrassed": 130,
            "annoyed": 105,
        }

        self.loop_mode: Dict[str, str] = {
            "neutral": "pingpong",
            "happy": "normal",
            "excited": "normal",
            "thinking": "pingpong",
            "confused": "pingpong",
            "sad": "pingpong",
            "embarrassed": "normal",
            "annoyed": "normal",
        }

        self._emotion = "neutral"

        self._load_sheet()

    @property
    def is_ready(self) -> bool:
        return self._sheet is not None

    def _load_sheet(self) -> None:
        if not self.sheet_path.exists():
            print(f"[GUI] Sprite sheet not found: {self.sheet_path}")
            return
        try:
            self._sheet = Image.open(self.sheet_path).convert("RGBA")
            print(f"[GUI] Sprite sheet loaded: {self.sheet_path.name}")
        except Exception as exc:
            print(f"[GUI] Failed loading sprite sheet: {exc}")
            self._sheet = None

    def _get_photo(self, frame_index: int) -> Optional[ImageTk.PhotoImage]:
        if self._sheet is None:
            return None
        if frame_index in self._cache:
            return self._cache[frame_index]

        row = frame_index // self.cols
        col = frame_index % self.cols
        x0 = col * self.frame_w
        y0 = row * self.frame_h
        x1 = x0 + self.frame_w
        y1 = y0 + self.frame_h

        crop = self._sheet.crop((x0, y0, x1, y1))
        photo = ImageTk.PhotoImage(crop)
        self._cache[frame_index] = photo
        return photo

    def set_emotion(self, emotion: str) -> None:
        self._emotion = emotion if emotion in self.sequences else "neutral"
        sequence = self.sequences.get(self._emotion, self.sequences["neutral"])
        if sequence != self._current_sequence:
            self._current_sequence = sequence
            self._frame_idx = 0
            self._direction = 1

        self._current_delay_ms = self.timing_ms.get(self._emotion, 120)

        if not self._running:
            self._running = True
            self._tick()

    def _tick(self) -> None:
        if not self._running:
            return

        frame = self._current_sequence[self._frame_idx]
        photo = self._get_photo(frame)
        if photo is not None:
            self.widget.configure(image=photo, text="")
            self.widget.image = photo

        if len(self._current_sequence) == 1:
            self._frame_idx = 0
        elif self.loop_mode.get(self._emotion, "normal") == "pingpong":
            self._frame_idx += self._direction
            if self._frame_idx >= len(self._current_sequence):
                self._frame_idx = max(0, len(self._current_sequence) - 2)
                self._direction = -1
            elif self._frame_idx < 0:
                self._frame_idx = 1
                self._direction = 1
        else:
            self._frame_idx = (self._frame_idx + 1) % len(self._current_sequence)

        self._after_id = self.widget.after(self._current_delay_ms, self._tick)

    def stop(self) -> None:
        self._running = False
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = None


class MikuGUIv4(ctk.CTk):
    """
    Main GUI Window untuk MikuWin v4 (Miku-only).
    Backend sama dengan v3, tetapi UI avatar memakai sprite Hatsune Miku.
    """

    def __init__(self):
        super().__init__()

        self.title("MikuWin v4 - Hatsune Miku")
        self.geometry("900x680")
        self.minsize(700, 520)

        # Components
        self.voice_input: Optional[VoiceInput] = None
        self.voice_output: Optional[VoiceOutput] = None
        self.voice_converter: Optional[VoiceConverter] = None
        self.ai_brain: Optional[AIBrain] = None
        self.system_control: Optional[SystemControl] = None
        self.memory_manager: Optional[MemoryManager] = None

        # Current character
        self.current_character_name = "miku"
        self.current_character = CHARACTERS[DEFAULT_CHARACTER]
        self.sprite_animator: Optional[MikuSpriteAnimator] = None

        # State
        self.is_listening = False
        self.is_processing = False
        self.message_queue = queue.Queue()

        # Wake phrase mode ("Oke Miku")
        self.wake_word_mode = False
        self.wake_phrase_variants = ["oke miku", "ok miku", "okay miku", "okey miku"]
        self.wake_listen_chunk_sec = 1.8
        self.conversation_chunk_sec = 4.0
        self.conversation_timeout_sec = 25.0
        self.last_conversation_activity = 0.0
        self._wake_stop_event = threading.Event()
        self._wake_thread: Optional[threading.Thread] = None

        self._create_widgets()
        self._apply_theme()
        self._process_messages()

        self._init_thread = threading.Thread(target=self._initialize_components)
        self._init_thread.daemon = True
        self._init_thread.start()

    # ─────────────────────── UI helpers ───────────────────────

    def _apply_theme(self):
        color = self.current_character.theme_color
        self.voice_btn.configure(fg_color=color, hover_color=self._darken_color(color))
        if hasattr(self, "wake_btn"):
            if self.wake_word_mode:
                self.wake_btn.configure(fg_color="#1E9E5A", hover_color="#197A47")
            else:
                self.wake_btn.configure(fg_color="transparent", hover_color=self._darken_color(color), border_color=color)
        self.avatar_frame.configure(border_color=color)

    def _darken_color(self, hex_color: str, factor: float = 0.8) -> str:
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        darker = tuple(int(c * factor) for c in rgb)
        return f"#{darker[0]:02x}{darker[1]:02x}{darker[2]:02x}"

    def _create_widgets(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(0, weight=1)

        # ── Left Panel ──
        self.left_panel = ctk.CTkFrame(self, corner_radius=10)
        self.left_panel.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

        self.miku_title = ctk.CTkLabel(
            self.left_panel,
            text="初音ミク • Live Avatar",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.miku_title.pack(padx=10, pady=10, fill="x")

        # Avatar frame
        self.avatar_frame = ctk.CTkFrame(
            self.left_panel,
            corner_radius=15,
            border_width=3,
            border_color=self.current_character.theme_color
        )
        self.avatar_frame.pack(padx=20, pady=10, fill="both", expand=True)

        self.avatar_label = ctk.CTkLabel(
            self.avatar_frame,
            text="Loading Miku...",
            font=ctk.CTkFont(size=20),
            text_color=(self.current_character.theme_color, self.current_character.theme_color)
        )
        self.avatar_label.pack(expand=True, fill="both", padx=20, pady=20)
        self.sprite_animator = MikuSpriteAnimator(self.avatar_label)

        self.name_label = ctk.CTkLabel(
            self.avatar_frame,
            text=self.current_character.display_name,
            font=ctk.CTkFont(size=18, weight="bold")
        )
        self.name_label.pack(pady=(0, 5))

        self.emotion_label = ctk.CTkLabel(
            self.avatar_frame,
            text="neutral",
            font=ctk.CTkFont(size=12),
            text_color=("gray60", "gray40")
        )
        self.emotion_label.pack(pady=(0, 10))

        # RVC status — NEW in v3
        self.rvc_status_label = ctk.CTkLabel(
            self.avatar_frame,
            text="🔵 RVC: initializing...",
            font=ctk.CTkFont(size=11),
            text_color=("gray50", "gray50")
        )
        self.rvc_status_label.pack(pady=(0, 10))

        # Status
        self.status_label = ctk.CTkLabel(
            self.left_panel,
            text="⚫ Initializing...",
            font=ctk.CTkFont(size=12)
        )
        self.status_label.pack(pady=5)

        # Pemakaian konteks LLM (angka asli dari Ollama)
        self.usage_label = ctk.CTkLabel(
            self.left_panel,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        )
        self.usage_label.pack(pady=(0, 5))

        # Voice button
        self.voice_btn = ctk.CTkButton(
            self.left_panel,
            text="🎤 Hold to Speak",
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=self.current_character.theme_color,
            hover_color=self._darken_color(self.current_character.theme_color),
            height=55,
            state="disabled"
        )
        self.voice_btn.pack(padx=20, pady=15, fill="x")
        self.voice_btn.bind("<ButtonPress-1>", self._on_voice_press)
        self.voice_btn.bind("<ButtonRelease-1>", self._on_voice_release)

        self.wake_btn = ctk.CTkButton(
            self.left_panel,
            text="🗣 Wake Phrase: OFF",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="transparent",
            border_width=1,
            border_color=self.current_character.theme_color,
            height=36,
            command=self._toggle_wake_word_mode,
            state="disabled"
        )
        self.wake_btn.pack(padx=20, pady=(0, 12), fill="x")

        # ── Right Panel ──
        self.right_panel = ctk.CTkFrame(self, corner_radius=10)
        self.right_panel.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        self.right_panel.grid_rowconfigure(1, weight=1)
        self.right_panel.grid_columnconfigure(0, weight=1)

        # Chat header
        self.chat_header = ctk.CTkFrame(self.right_panel, fg_color="transparent", height=40)
        self.chat_header.grid(row=0, column=0, padx=10, pady=(10, 0), sticky="ew")
        self.chat_header.grid_columnconfigure(0, weight=1)

        header_title = ctk.CTkLabel(
            self.chat_header,
            text="💬 Chat",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        header_title.grid(row=0, column=0, sticky="w")

        clear_btn = ctk.CTkButton(
            self.chat_header,
            text="🗑️ Clear",
            width=70,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color="transparent",
            border_width=1,
            command=self._clear_chat
        )
        clear_btn.grid(row=0, column=1, padx=5)

        resume_btn = ctk.CTkButton(
            self.chat_header,
            text="↺ Sesi lalu",
            width=90,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color="transparent",
            border_width=1,
            command=self._resume_last_session
        )
        resume_btn.grid(row=0, column=2, padx=5)

        # Chat display
        self.chat_display = ctk.CTkTextbox(
            self.right_panel,
            font=ctk.CTkFont(size=13),
            state="disabled",
            wrap="word"
        )
        self.chat_display.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")

        # Input frame
        self.input_frame = ctk.CTkFrame(self.right_panel, fg_color="transparent")
        self.input_frame.grid(row=2, column=0, padx=10, pady=10, sticky="ew")
        self.input_frame.grid_columnconfigure(0, weight=1)

        self.text_input = ctk.CTkEntry(
            self.input_frame,
            placeholder_text="Ketik pesan atau tekan tombol suara...",
            font=ctk.CTkFont(size=13),
            height=45
        )
        self.text_input.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        self.text_input.bind("<Return>", self._on_send)

        self.send_btn = ctk.CTkButton(
            self.input_frame,
            text="Send",
            width=80,
            height=45,
            command=self._on_send,
            state="disabled"
        )
        self.send_btn.grid(row=0, column=1)

        # Initial placeholder message
        char = self.current_character
        self._add_chat_message(
            char.display_name,
            "Tunggu sebentar, sedang mempersiapkan diri...",
            char.expressions.get("thinking", "🤔")
        )

        self.system_control = SystemControl(confirm_callback=self._confirm_action)
        self.turn_logger = TurnLogger(TURN_LOG_DIR)

    def _confirm_action(self, summary: str) -> bool:
        """
        Dipanggil dari worker thread. Dialog Tk harus dibuat di main thread,
        jadi permintaan dikirim lewat message_queue lalu ditunggu jawabannya.
        """
        done = threading.Event()
        result = {"approved": False}
        self.message_queue.put(("confirm", (summary, done, result)))
        # Tidak dijawab dalam 60 detik = batal
        done.wait(timeout=60)
        return result["approved"]

    # ─────────────────────── Character mode ───────────────────────
    # v4 intentionally keeps a single character: Hatsune Miku.

    # ─────────────────────── Initialization ───────────────────────

    def _initialize_components(self):
        """Initialize all AI components in background thread"""

        self.memory_manager = MemoryManager(DATA_DIR)

        # 1. Whisper
        self._update_status("🟡 Loading Whisper...")
        self.voice_input = VoiceInput()
        if not self.voice_input.initialize():
            self._update_status("🔴 Whisper failed!")
            self._add_chat_message("System", "❌ Gagal load speech recognition.", "❌")
            return

        # 2. Ollama / AI Brain
        self._update_status("🟡 Connecting to AI...")
        self.ai_brain = AIBrain(self.memory_manager)
        success, msg = self.ai_brain.initialize()
        if not success:
            self._update_status("🔴 AI failed!")
            self._add_chat_message("System", f"❌ Gagal connect ke Ollama: {msg}", "❌")
            return

        self.ai_brain.set_character(self.current_character_name)

        # 3. RVC Voice Converter (load once for Miku)
        self._update_status("🟡 Loading RVC model...")
        self._update_rvc_status("🟡 RVC: loading...")

        char_rvc = self.current_character.rvc_config
        if char_rvc and char_rvc.enabled:
            self.voice_converter = VoiceConverter(char_rvc)
            if self.voice_converter.is_available:
                self._update_rvc_status(f"🟢 {self.voice_converter.status_text}")
            else:
                self._update_rvc_status("🔴 RVC: unavailable (MeloTTS only)")
        else:
            self.voice_converter = None
            self._update_rvc_status("⚫ RVC: not used")

        # 4. Voice Output (with converter if available)
        self.voice_output = VoiceOutput(
            character=self.current_character,
            converter=self.voice_converter if (self.voice_converter and self.voice_converter.is_available) else None
        )

        # All ready
        self._update_status("🟢 Ready")
        self._enable_controls()

        greeting, emotion = self.ai_brain.get_greeting()
        self._add_chat_message(
            self.current_character.display_name,
            greeting,
            self.current_character.expressions.get(emotion, "😊")
        )
        self._update_avatar(emotion)

        if self.voice_output:
            self.voice_output.speak(greeting, blocking=False)

    # ─────────────────────── Message queue (thread-safe UI) ───────────────────────

    def _update_status(self, text: str):
        self.message_queue.put(("status", text))

    def _update_rvc_status(self, text: str):
        self.message_queue.put(("rvc_status", text))

    def _add_chat_message(self, sender: str, message: str, emoji: str = ""):
        self.message_queue.put(("chat", (sender, message, emoji)))

    def _enable_controls(self):
        self.message_queue.put(("enable", None))

    @staticmethod
    def _normalize_text(text: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _is_wake_phrase(self, text: str) -> bool:
        normalized = self._normalize_text(text)
        return any(phrase in normalized for phrase in self.wake_phrase_variants)

    def _toggle_wake_word_mode(self):
        if not self.voice_input:
            self._add_chat_message("System", "⚠ Voice input belum siap.", "⚠")
            return

        self.wake_word_mode = not self.wake_word_mode
        if self.wake_word_mode:
            self.wake_btn.configure(text="🗣 Wake Phrase: ON")
            self._update_status("🟢 Wake mode aktif (ucap: Oke Miku)")
            self._wake_stop_event.clear()
            self._wake_thread = threading.Thread(target=self._wake_word_worker, daemon=True)
            self._wake_thread.start()
        else:
            self.wake_btn.configure(text="🗣 Wake Phrase: OFF")
            self._wake_stop_event.set()
            self._update_status("🟢 Ready")

        self._apply_theme()

    def _wake_word_worker(self):
        while self.wake_word_mode and not self._wake_stop_event.is_set():
            if self.is_processing or self.is_listening:
                time.sleep(0.2)
                continue

            heard = self.voice_input.listen_and_transcribe(duration=self.wake_listen_chunk_sec)
            if not heard:
                continue

            if self._is_wake_phrase(heard):
                self._add_chat_message("You", f"🎤 {heard}", "")
                self._start_wake_conversation()

        self.last_conversation_activity = 0.0

    def _start_wake_conversation(self):
        self.last_conversation_activity = time.time()
        self.message_queue.put(("avatar", "excited"))
        self._add_chat_message(
            self.current_character.display_name,
            "[Wake] Hai! Miku siap. Silakan lanjut bicara ya.",
            self.current_character.expressions.get("excited", "🎉")
        )
        if self.voice_output:
            self.voice_output.speak("Hai, Miku siap. Silakan lanjut bicara.", blocking=False)

        while self.wake_word_mode and not self._wake_stop_event.is_set():
            if time.time() - self.last_conversation_activity > self.conversation_timeout_sec:
                self._add_chat_message(
                    self.current_character.display_name,
                    "[Wake] Oke, Miku standby lagi. Ucapkan Oke Miku kalau mau lanjut.",
                    self.current_character.expressions.get("neutral", "😊")
                )
                self.message_queue.put(("avatar", "neutral"))
                break

            if self.is_processing:
                time.sleep(0.2)
                continue

            self._update_status("🎤 Wake mode: listening...")
            heard = self.voice_input.listen_and_transcribe(duration=self.conversation_chunk_sec)
            if not heard:
                continue

            if self._is_wake_phrase(heard):
                self.last_conversation_activity = time.time()
                continue

            self.last_conversation_activity = time.time()
            self._add_chat_message("You", f"🎤 {heard}", "")
            self._process_input(heard)

        if self.wake_word_mode:
            self._update_status("🟢 Wake mode aktif (ucap: Oke Miku)")

    def _process_messages(self):
        try:
            while True:
                msg_type, data = self.message_queue.get_nowait()

                if msg_type == "status":
                    self.status_label.configure(text=data)

                elif msg_type == "usage":
                    self.usage_label.configure(text=data)

                elif msg_type == "rvc_status":
                    self.rvc_status_label.configure(text=data)

                elif msg_type == "chat":
                    sender, message, emoji = data
                    self.chat_display.configure(state="normal")

                    if sender == "You":
                        prefix = "👤 You: "
                    elif sender == "System":
                        prefix = "ℹ️ System: "
                    else:
                        prefix = f"{emoji} {sender}: " if emoji else f"{sender}: "

                    self.chat_display.insert("end", f"\n{prefix}{message}\n")
                    self.chat_display.configure(state="disabled")
                    self.chat_display.see("end")

                elif msg_type == "enable":
                    self.send_btn.configure(state="normal")
                    self.voice_btn.configure(state="normal")
                    self.wake_btn.configure(state="normal")

                elif msg_type == "avatar":
                    self._update_avatar(data)

                elif msg_type == "confirm":
                    summary, done, result = data
                    result["approved"] = messagebox.askyesno(
                        "Konfirmasi Aksi", f"{summary}\n\nLanjutkan?", parent=self
                    )
                    done.set()

        except queue.Empty:
            pass

        self.after(50, self._process_messages)

    # ─────────────────────── Avatar ───────────────────────

    def _update_avatar(self, emotion: str):
        color = EMOTIONS.get(emotion, EMOTIONS["neutral"]).color
        self.avatar_label.configure(text_color=(color, color))
        if self.sprite_animator and self.sprite_animator.is_ready:
            self.sprite_animator.set_emotion(emotion)
        else:
            fallback = self.current_character.expressions.get(
                emotion, self.current_character.expressions.get("neutral", "😊")
            )
            self.avatar_label.configure(text=fallback)
        self.emotion_label.configure(text=emotion)

    # ─────────────────────── Chat ───────────────────────

    def _resume_last_session(self):
        """Muat sesi terakhir ke memori AI dan tampilkan isinya di chat."""
        if not self.ai_brain or self.is_processing:
            return
        ok, msg = self.ai_brain.resume_session()
        if not ok:
            self._add_chat_message("System", f"⚠ {msg}", "⚠")
            return

        self.chat_display.configure(state="normal")
        self.chat_display.delete("1.0", "end")
        self.chat_display.configure(state="disabled")
        self._add_chat_message("System", f"↺ {msg}", "↺")
        char = self.current_character
        for message in self.ai_brain.memory.current_context.messages:
            text = re.sub(r"\[EMOTION:[^\]]*\]", "", message.content).strip()
            if message.role == "user" and text:
                self._add_chat_message("You", text, "")
            elif message.role == "assistant" and text:
                self._add_chat_message(char.display_name, text, char.expressions.get(message.emotion or "neutral", "😊"))

    def _clear_chat(self):
        self.chat_display.configure(state="normal")
        self.chat_display.delete("1.0", "end")
        self.chat_display.configure(state="disabled")
        if self.ai_brain:
            self.ai_brain.clear_history()

    def _on_send(self, event=None):
        text = self.text_input.get().strip()
        if not text or self.is_processing:
            return

        self.text_input.delete(0, "end")
        self._add_chat_message("You", text, "")

        if text.lower().split(" ")[0] == "/resume":
            self._resume_last_session()
            return

        # Slash command di worker thread: /routine bisa membuka dialog konfirmasi
        target = self._process_command if text.startswith("/") else self._process_input
        thread = threading.Thread(target=target, args=(text,))
        thread.daemon = True
        thread.start()

    # ─────────────────────── Voice ───────────────────────

    def _on_voice_press(self, event):
        if self.wake_word_mode:
            self._add_chat_message("System", "ℹ Wake mode aktif. Ucapkan: Oke Miku", "ℹ")
            return

        if not self.voice_input or self.is_listening or self.is_processing:
            return

        self.is_listening = True
        self.voice_btn.configure(text="🔴 Listening...", fg_color="#FF4444")
        self._update_status("🎤 Listening...")
        self._update_avatar("thinking")
        self.voice_input.start_listening()

    def _on_voice_release(self, event):
        if not self.is_listening:
            return

        color = self.current_character.theme_color
        self.voice_btn.configure(text="🎤 Hold to Speak", fg_color=color)

        thread = threading.Thread(target=self._process_voice)
        thread.daemon = True
        thread.start()

    def _process_voice(self):
        self.is_listening = False
        self._update_status("🟡 Processing voice...")

        audio = self.voice_input.stop_listening()

        if len(audio) == 0:
            self._update_status("🟢 Ready")
            self.message_queue.put(("avatar", "neutral"))
            return

        lang = getattr(self.current_character, 'lang', None)
        # Frasa halusinasi Whisper ("ご視聴ありがとうございました" dll.) sudah dibuang di VoiceInput
        text = self.voice_input.transcribe(audio, languages=[lang, "id"])

        if text:
            self._add_chat_message("You", f"🎤 {text}", "")
            self._process_input(text)
        else:
            self._update_status("🟢 Ready")
            char = self.current_character
            
            import random
            if lang == "ja":
                feedbacks = [
                    "ん？もう一回言ってくれる？",
                    "ええっと、よく聞こえなかったみたい。もう一回お願い！",
                    "ごめんなさい、ちょっと聞き取れなかったの。"
                ]
            else:
                feedbacks = [
                    "Maaf, suaranya kurang jelas. Bisa diulangi?",
                    "Eh, ngomong apa barusan? Tolong diulangi ya.",
                    "Hmm? Aku kurang dengar nih, ulangi sekali lagi dong!"
                ]
            fallback_msg = random.choice(feedbacks)
            
            self._add_chat_message(
                char.display_name,
                fallback_msg,
                char.expressions.get("confused", "😕")
            )
            self.message_queue.put(("avatar", "confused"))
            if self.voice_output:
                self.voice_output.speak(fallback_msg, blocking=False)

    # ─────────────────────── AI Processing ───────────────────────

    def _process_command(self, text: str):
        self.is_processing = True
        try:
            output = handle_command(text, self.ai_brain, self.system_control)
            self._add_chat_message("System", output or "", "⌘")
        except Exception as e:
            self._add_chat_message("System", f"❌ Error: {e}", "❌")
        finally:
            self.is_processing = False
            self._update_status("🟢 Ready")

    def _show_tool_result(self, result: ToolResult):
        icon = "✅" if result.success else "❌"
        self._add_chat_message("System", f"{icon} {result.message}", icon)
        self._update_status("⏳ Checking observation...")

    def _process_input(self, text: str):
        if not self.ai_brain:
            return

        self.is_processing = True
        self._update_status("🟡 Thinking...")
        self.message_queue.put(("avatar", "thinking"))

        try:
            turn = run_turn(
                self.ai_brain, self.system_control, text,
                source="gui", report_results=True,
                on_tool_result=self._show_tool_result, logger=self.turn_logger,
            )
            response, emotion = turn.reply, turn.emotion
            self.message_queue.put(("avatar", emotion))
            usage = self.ai_brain.turn_usage
            self.message_queue.put((
                "usage",
                f"🧠 {usage.context_text()} · {turn.latency_seconds:.1f} s",
            ))

            if response:
                char = self.current_character
                char = self.current_character
                self._add_chat_message(
                    char.display_name,
                    response,
                    char.expressions.get(emotion, "😊")
                )

                if self.voice_output:
                    speak_text = re.sub(r'\{[^}]*\}', '', response)
                    speak_text = re.sub(r'\[[^\]]*\]', '', speak_text)
                    speak_text = re.sub(r'[\n\r]+', ' ', speak_text).strip()

                    if speak_text and len(speak_text) > 2:
                        self._update_status("🟡 Speaking...")
                        self.voice_output.speak(speak_text, blocking=False)

        except Exception as e:
            self._add_chat_message("System", f"❌ Error: {e}", "❌")
            self.message_queue.put(("avatar", "confused"))

        finally:
            self.is_processing = False
            self._update_status("🟢 Ready")

    # ─────────────────────── Cleanup ───────────────────────

    def on_closing(self):
        self.wake_word_mode = False
        self._wake_stop_event.set()
        if self.sprite_animator:
            self.sprite_animator.stop()
        if self.voice_input:
            self.voice_input.cleanup()
        if self.voice_output:
            self.voice_output.cleanup()
        if self.ai_brain:
            self.ai_brain.cleanup()
        self.destroy()


def main():
    app = MikuGUIv4()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()


if __name__ == "__main__":
    main()
