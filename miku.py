#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MikuWin v11 - CLI Mode with Sprite Avatar and Smart Automation
Push-to-talk voice chat with animated Miku sprite mascot.
Integrates YouTube, Spotify, and Browser automation for smart taskss.

Usage:
    python miku.py              # Voice mode (default, with sprite avatar & automation)
    python miku.py --text       # Text chat mode (no sprite)
    python miku.py --test       # Test initialization only
"""

import os
import warnings

# Suppress warnings BEFORE importing pygame or other noisy modules
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', category=FutureWarning)
warnings.filterwarnings('ignore', category=UserWarning)

import argparse
import sys
import time
import threading
from pathlib import Path
from typing import Optional, List, Tuple
import re
import logging
import os

# Fix UTF-8 encoding for Windows console
if sys.platform == 'win32':
    import io
    # Use line_buffering=True so that print() flushes immediately
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

# Suppress dependency warnings (fairseq, pygame, torch, etc)
logging.getLogger('fairseq').setLevel(logging.ERROR)
logging.getLogger('torch').setLevel(logging.ERROR)
logging.getLogger('pygame').setLevel(logging.ERROR)
logging.getLogger('faster_whisper').setLevel(logging.ERROR)
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from core.voice_input import VoiceInput
from core.voice_output import VoiceOutput
from core.voice_converter import VoiceConverter
from core.ai_brain import AIBrain
from core.memory import MemoryManager
from core.system_control import SystemControl
from core.macro_tools import MacroTools
from core.avatar_window import initialize_avatar_window, cleanup_avatar_window, get_avatar_window
from config import DATA_DIR, CHARACTERS, DEFAULT_CHARACTER


class MikuCLI:
    """CLI interface for MikuWin v4"""

    def __init__(self, character: str = DEFAULT_CHARACTER):
        self.character_name = character
        self.character = CHARACTERS.get(character)

        if not self.character:
            print(f"[ERROR] Character '{character}' not found")
            sys.exit(1)

        self.voice_input: Optional[VoiceInput] = None
        self.voice_output: Optional[VoiceOutput] = None
        self.voice_converter: Optional[VoiceConverter] = None
        self.ai_brain: Optional[AIBrain] = None
        self.memory_manager: Optional[MemoryManager] = None
        self.system_control: Optional[SystemControl] = None
        self.avatar_window = None  # Sprite display window (optional)

        # Hover / Drag interactive mode
        self._interaction_event = threading.Event()
        
        self.wake_trigger_language_hint = self.character.lang
        self.wake_conversation_language_hint = None
        self.wake_silence_timeout_sec = 3.0
        self.wake_max_utterance_sec = 18.0
        self.last_conversation_activity = 0.0
        self._wake_stop_event = threading.Event()
        self._wake_thread: Optional[threading.Thread] = None

        print(f"[MikuWin v11] Selected character: {self.character.display_name}")
        print(f"[MikuWin v11] Language: {self.character.lang}")

    def initialize(self) -> bool:
        """Initialize all components"""
        print("\n=== Initializing MikuWin v11 ===\n")

        # Memory
        print("[1/5] Initializing memory...")
        self.memory_manager = MemoryManager(DATA_DIR)

        # Voice Input
        print("[2/5] Loading Faster-Whisper...")
        self.voice_input = VoiceInput()
        if not self.voice_input.initialize():
            print("[ERROR] Failed to load Whisper")
            return False
        print("      ✓ Whisper loaded")

        # AI Brain
        print("[3/5] Connecting to Ollama...")
        self.ai_brain = AIBrain(self.memory_manager)
        success, msg = self.ai_brain.initialize()
        if not success:
            print(f"[ERROR] Ollama connection failed: {msg}")
            return False
        self.ai_brain.set_character(self.character_name)
        print("      ✓ Ollama connected")

        # RVC Converter
        print("[4/5] Loading RVC voice converter...")
        if self.character.rvc_config and self.character.rvc_config.enabled:
            self.voice_converter = VoiceConverter(self.character.rvc_config)
            if self.voice_converter.is_available:
                print(f"      ✓ RVC ready: {self.voice_converter.status_text}")
            else:
                print("      ⚠ RVC unavailable, using Edge-TTS only")
        else:
            print("      ⚠ RVC not used for this character")

        # Voice Output
        print("[5/5] Initializing voice output...")
        self.voice_output = VoiceOutput(
            character=self.character,
            converter=self.voice_converter if (
                self.voice_converter and self.voice_converter.is_available
            ) else None,
        )
        print("      ✓ Voice output ready")

        # System Control
        self.system_control = SystemControl()
        self.macro_tools = MacroTools()
        print("      ✓ System control ready")

        print("\n✓ All systems ready!\n")
        return True

    def chat_text_mode(self):
        """Interactive text chat mode"""
        greeting, emotion = self.ai_brain.get_greeting()
        print(f"\n{self.character.display_name} [{emotion}]: {greeting}\n")
        self.voice_output.speak(greeting, blocking=False)

        print('Type "quit" to exit\n')

        while True:
            try:
                user_input = input("You: ").strip()
            except KeyboardInterrupt:
                print("\n[Goodbye!]")
                break

            if not user_input:
                continue

            if user_input.lower() == "quit":
                print("[Goodbye!]")
                break

            # Get response
            response, function_calls, emotion = self.ai_brain.think(user_input)

            # Execute function calls (system actions)
            if function_calls and self.system_control:
                for call in function_calls:
                    action = call.get("action")
                    params = call.get("params", {})
                    success, msg = self.system_control.execute_action(action, params)
                    icon = "✅" if success else "❌"
                    print(f"[System] {icon} {msg}")

            # Clean response for display
            clean_response = re.sub(r"\{[^}]*\}", "", response)
            clean_response = re.sub(r"\[[^\]]*\]", "", clean_response)
            clean_response = clean_response.strip()

            if clean_response:
                print(f"\n{self.character.display_name} [{emotion}]: {clean_response}")
                self.voice_output.speak(clean_response, blocking=False)
                print()

            if function_calls:
                print(f"[Functions executed: {len(function_calls)}]")

    def _on_avatar_interacted(self):
        """Callback from avatar window when dragged/clicked"""
        self._interaction_event.set()

    def _on_avatar_quit(self):
        """Callback from avatar window when user right-clicks and hits Exit"""
        print("\n[Exit requested from mascot context menu]")
        self._quit_event = True
        self._interaction_event.set()  # Wake up main thread to die

    def chat_voice_mode(self):
        """Interactive drag-to-wake voice mode"""
        self._quit_event = False
        from pathlib import Path
        sprite_sheet = Path(__file__).parent / "assets" / "avatar" / "miku_smart_sheet.png"
        if sprite_sheet.exists():
            try:
                self.avatar_window = initialize_avatar_window(
                    str(sprite_sheet),
                    on_interact_callback=self._on_avatar_interacted,
                    on_quit_callback=self._on_avatar_quit
                )
                self.avatar_window.start()
                print("[avatar_window] Miku frame started in background\n")
            except Exception as e:
                print(f"[avatar_window] Warning: Could not start sprite: {e}\n")

        print("Voice mode starting... Playing greeting...")
        greeting, emotion = self.ai_brain.get_greeting()
        print(f"\n{self.character.display_name} [{emotion}]: {greeting}\n")
        if self.avatar_window:
            self.avatar_window.set_emotion(emotion)
        self.voice_output.speak(greeting, blocking=True)
        if self.avatar_window:
            self.avatar_window.set_emotion("neutral")

        print("\n" + "="*50)
        print("💡 HOW TO USE: Drag the Miku mascot on your screen to talk!")
        print("="*50 + "\n")

        import keyboard
        # Register a hotkey just in case they want a manual way to exit
        # or we just rely on Ctrl+C.
        print("Press Ctrl+C to exit.\n")

        import time
        while True:
            try:
                # Clear any lingering events before waiting to avoid accidental queueing
                self._interaction_event.clear()
                
                # Wait for user to interact with the avatar
                # We use a timeout so it can catch KeyboardInterrupt
                if not self._interaction_event.wait(1.0):
                    if getattr(self, "_quit_event", False):
                        break
                    continue
                
                # Check directly if this was an exit request rather than interaction
                if getattr(self, "_quit_event", False):
                    break
                    
                self._interaction_event.clear()
                
                # Feedback: Miku acknowledges the interaction
                print("\n[User interacted with Miku]")
                if self.avatar_window:
                    self.avatar_window.set_emotion("happy")
                
                trigger_phrase = "はい、何でしょうか？" # "Yes, what is it?"
                self.voice_output.speak(trigger_phrase, blocking=True)
                
                # Give a small pause to avoid hearing her own echo
                time.sleep(0.3)
                
                # Miku starts listening for user request
                if self.avatar_window:
                    self.avatar_window.set_emotion("listening")
                print("🎤 Listening... (speak now, waiting 3s for silence)")
                
                audio = self.voice_input.listen_until_silence(
                    max_duration=self.wake_max_utterance_sec,
                    silence_duration=2.5, # Slightly faster so you don't wait too long
                    min_duration=0.5,
                    speech_threshold=0.015, # Tingkatkan sedikit karena noise luar ramai
                    quiet=True
                )
                
                if len(audio) == 0:
                    print("... No audio captured.")
                    if self.avatar_window:
                        self.avatar_window.set_emotion("confused")
                        time.sleep(2.0)
                        self.avatar_window.set_emotion("neutral")
                    continue
                
                print("⏳ Transcribing...")
                if self.avatar_window:
                    self.avatar_window.set_emotion("thinking")
                    
                # We prioritize Japanese first, then Indonesian. 
                # Dropping 'None' and 'en' to avoid Whisper parsing Japanese as English romaji
                text = self._transcribe_best_effort(
                    audio,
                    language_order=[self.character.lang, "id"],
                    wake_mode=False,
                )
                
                if text:
                    # Filter out purely hallucinated empty tags like "[Silence]" or "ご視聴ありがとうございました"
                    hallucinations = ["ご視聴", "字幕", "silence", "terima kasih", "thank you for"]
                    is_hallucination = any(h in text.lower() for h in hallucinations) and len(text) < 30
                    
                    if is_hallucination:
                        print(f"[Ignored likely hallucination: {text}]")
                    else:
                        print(f"You: {text}\n")
                        self._process_ai_response(text)
                else:
                    print("[Pesan Anda kosong, terlalu kecil, atau gagal dikenali (Could not transcribe)]\n")
                    
                    # ADAPTIVE FEEDBACK: Karakter memberikan respons kebingungan ("apa kamu bilang?") secara otonom
                    import random
                    lang = getattr(self.character, 'lang', 'id')
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
                    if self.avatar_window:
                        self.avatar_window.set_emotion("confused")
                    
                    # Miku akan bersuara langsung dari pipeline VITS RVC (jika ada) menggunakan VoiceOutput
                    self.voice_output.speak(fallback_msg)

                if self.avatar_window:
                    self.avatar_window.set_emotion("neutral")
                    
            except KeyboardInterrupt:
                print("\n[Goodbye!]")
                break

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize text for wake phrase matching"""
        cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _score_transcript_intent(self, text: str) -> int:
        """Score transcript by command-likelihood to select best STT candidate."""
        if not text:
            return -999

        normalized = self._normalize_text(text)
        score = min(len(normalized), 80) // 8

        command_tokens = [
            "open", "buka", "play", "pause", "next", "search", "volume",
            "youtube", "spotify", "chrome", "edge", "firefox", "notepad",
            "whatsapp", "discord", "music", "app", "website", "google",
        ]
        for token in command_tokens:
            if token in normalized:
                score += 8

        japanese_tokens = ["開いて", "再生", "停止", "検索", "音量", "ミュート", "アプリ", "ブラウザ"]
        for token in japanese_tokens:
            if token in text:
                score += 8

        hallucination_phrases = ["ご視聴ありがとうございました", "はい ご覧ください", "ご覧ください"]
        for phrase in hallucination_phrases:
            if phrase in text:
                score -= 20

        return score

    def _transcribe_best_effort(
        self,
        audio,
        language_order: List[Optional[str]],
        wake_mode: bool = False,
    ) -> str:
        """Run multi-pass STT and pick the highest-scoring candidate."""
        candidates: List[Tuple[int, Optional[str], str]] = []
        seen_langs = set()
        seen_texts = set()

        for lang in language_order:
            if lang in seen_langs:
                continue
            seen_langs.add(lang)

            try:
                # Add beam_size to improve consistency, condition on previous text to avoid looping hallucination
                text = self.voice_input.transcribe(
                    audio,
                    lang=lang,
                    use_initial_prompt=False if wake_mode else (lang is not None),
                    no_speech_threshold=0.78 if wake_mode else 0.65,
                    vad_min_silence_ms=260 if wake_mode else 500,
                    vad_speech_pad_ms=160 if wake_mode else 300,
                    condition_on_previous_text=False, # Disable to prevent hallucination looping
                    beam_size=5, # Higher beam size for better accuracy
                    verbose_logging=True,
                )
            except Exception:
                text = ""

            # Filter hallucination repetition within the same output
            # "リアリカスは、食べる前に" is a common whisper Japanese hallucination on noise
            hallucinations = ["ご視聴", "字幕", "リアリカス", "食べる前に"]
            if any(h in text for h in hallucinations):
                text = ""

            # Check if we already transcribed the exact same text
            # if so, don't duplicate it.
            if not text or text.lower() in seen_texts:
                continue

            seen_texts.add(text.lower())
            
            # Boost score if the language matches our explicit hint (Japanese)
            score = self._score_transcript_intent(text)
            if lang == self.character.lang:
                score += 5
                
            candidates.append((score, lang, text))

        if not candidates:
            return ""

        best_score, best_lang, best_text = max(candidates, key=lambda x: x[0])
        debug_lang = best_lang if best_lang is not None else "auto"
        # Only log if it's not wake standby spam, or if it passed a minimum threshold
        if (not wake_mode) or (best_score >= 8 or self._is_wake_phrase(best_text)):
            print(f"[STT] Best candidate lang={debug_lang}, score={best_score}, text='{best_text}'")
            
        return best_text

    def _is_wake_phrase(self, text: str) -> bool:
        """Check if text contains wake phrase"""
        normalized = self._normalize_text(text)

        # Direct phrase matching first.
        if any(phrase in normalized for phrase in self.wake_phrase_variants):
            return True

        # Fallback: allow partial OCR/STT variations as long as "miku" + wake token exist.
        has_miku = ("miku" in normalized) or ("ミク" in text) or ("みく" in text)
        has_ok_token = (
            ("oke" in normalized)
            or ("okey" in normalized)
            or ("okay" in normalized)
            or ("ok" in normalized)
            or ("オーケ" in text)
            or ("オケ" in text)
        )
        if has_miku and has_ok_token:
            return True

        # Fallback when STT clips "miku" but command intent starts after "ok/oke".
        has_command_token = any(
            token in normalized
            for token in [
                "youtube",
                "spotify",
                "chrome",
                "edge",
                "volume",
                "buka",
                "open",
            ]
        )
        starts_with_ok = normalized.startswith(("ok ", "oke ", "okay ", "okey "))
        return starts_with_ok and has_command_token

    def _process_ai_response(self, user_text: str):
        """Process text input through AI and display response"""
        response, function_calls, emotion = self.ai_brain.think(user_text)

        # Execute function calls (system actions)
        if function_calls and self.system_control:
            all_observations = []
            
            for call in function_calls:
                action = call.get("action")
                params = call.get("params", {})
                success, msg = self.system_control.execute_action(action, params)
                icon = "✅" if success else "❌"
                print(f"[System] {icon} {msg}")
                all_observations.append(f"Action '{action}' result: {'SUKSES' if success else 'GAGAL'} - {msg}")
                
            # AGENTIC LOOP: Jika ada observasi, beri tahu AI untuk meresponnya
            if all_observations:
                print("⏳ Agent is thinking about the observation...")
                combined_obs = "\n".join(all_observations)
                response, emotion = self.ai_brain.think_observation(combined_obs)

        # Clean and display response
        clean_response = re.sub(r"\{[^}]*\}", "", response)
        clean_response = re.sub(r"\[[^\]]*\]", "", clean_response)
        clean_response = clean_response.strip()

        if clean_response:
            print(f"{self.character.display_name} [{emotion}]: {clean_response}\n")
            if self.avatar_window:
                self.avatar_window.set_emotion(emotion)
            self.voice_output.speak(clean_response, blocking=True)

    def _enter_wake_phrase_mode(self):
        """Enter 'Oke Miku' wake phrase listening mode"""
        print("\n🗣️  Wake Phrase Mode: Listening for 'Oke Miku'...")
        print("(Say wake phrase to start talking. Say 'stop wake mode' to exit.)\n")
        print(
            f"[Wake] Hybrid STT active: trigger_lang={self.wake_trigger_language_hint}, "
            "conversation_lang=auto"
        )

        self.wake_word_mode = True
        self.last_conversation_activity = time.time()

        # Announce ready
        wake_ready = "Siap dengarkan. Katakan 'Oke Miku' untuk mulai."
        print(f"{self.character.display_name}: {wake_ready}\n")
        if self.avatar_window:
            self.avatar_window.set_emotion("listening")
        # Block so wake listener does not immediately capture Miku's own voice.
        self.voice_output.speak(wake_ready, blocking=True)
        time.sleep(self.post_tts_listen_cooldown_sec)

        in_conversation = False

        try:
            while self.wake_word_mode:
                # Check timeout
                if time.time() - self.last_conversation_activity > self.conversation_timeout_sec:
                    if in_conversation:
                        print("[Wake] Idle timeout - kembali ke wake standby\n")
                        in_conversation = False
                        if self.avatar_window:
                            self.avatar_window.set_emotion("listening")
                        self.last_conversation_activity = time.time()
                        continue

                    print("[Wake] Timeout - kembali ke mode normal\n")
                    break

                if in_conversation:
                    # Keep recording while speech is present; stop only after sustained silence.
                    audio = self.voice_input.listen_until_silence(
                        max_duration=self.wake_max_utterance_sec,
                        silence_duration=self.wake_silence_timeout_sec,
                        min_duration=1.0,
                        speech_threshold=0.01,
                    )
                    if len(audio) == 0:
                        heard = ""
                    else:
                        heard = self._transcribe_best_effort(
                            audio,
                            language_order=[self.character.lang, "id", "en", None],
                            wake_mode=True,
                        )
                else:
                    audio = self.voice_input.listen_for_duration(self.wake_listen_chunk_sec)
                    if len(audio) == 0:
                        heard = ""
                    else:
                        heard = self._transcribe_best_effort(
                            audio,
                            language_order=[self.wake_trigger_language_hint, "id", "en", None],
                            wake_mode=True,
                        )
                
                if not heard:
                    continue

                normalized_heard = self._normalize_text(heard)
                if normalized_heard in {"exit", "quit", "stop wake mode", "wake off"}:
                    print(f"You: {heard}")
                    print("[Wake] Perintah keluar diterima\n")
                    break

                # In standby, ignore low-confidence garbage transcripts.
                if not in_conversation:
                    score = self._score_transcript_intent(heard)
                    if score < 12 and not self._is_wake_phrase(heard):
                        continue

                print(f"You: {heard}")

                # Standby -> conversation transition.
                if not in_conversation and self._is_wake_phrase(heard):
                    print("[Wake] Deteksi 'Oke Miku'!\n")
                    self.last_conversation_activity = time.time()
                    in_conversation = True

                    if self.avatar_window:
                        self.avatar_window.set_emotion("excited")

                    activation_reply = "Hai! Miku siap. Lanjut bicara ya."
                    print(f"{self.character.display_name}: {activation_reply}\n")
                    self.voice_output.speak(activation_reply, blocking=True)
                    time.sleep(self.post_tts_listen_cooldown_sec)
                    continue

                # While in conversation, process every utterance without manual Enter.
                if in_conversation:
                    self.last_conversation_activity = time.time()
                    if self.avatar_window:
                        self.avatar_window.set_emotion("thinking")
                    self._process_ai_response(heard)
                    if self.avatar_window:
                        self.avatar_window.set_emotion("excited")
                    time.sleep(self.post_tts_listen_cooldown_sec)

        except KeyboardInterrupt:
            print("\n[Wake mode interrupted]")
        finally:
            self.wake_word_mode = False
            print("[Wake mode exited]\n")
            if self.avatar_window:
                self.avatar_window.set_emotion("neutral")

    def cleanup(self):
        """Cleanup resources"""
        if self.avatar_window:
            cleanup_avatar_window()
        if self.voice_input:
            self.voice_input.cleanup()
        if self.voice_output:
            self.voice_output.cleanup()
        if self.ai_brain:
            self.ai_brain.cleanup()
        print("\n[Cleanup complete]")


def main():
    parser = argparse.ArgumentParser(
        description="MikuWin v4 - AI Desktop Assistant (Miku Edition)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python miku.py                # Voice mode with sprite (default)
  python miku.py --text         # Text chat mode
  python miku.py --test         # Test initialization only
        """,
    )

    parser.add_argument(
        "-c",
        "--character",
        default=DEFAULT_CHARACTER,
        help=f"Character to use (default: {DEFAULT_CHARACTER})",
        choices=list(CHARACTERS.keys()),
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--text", action="store_true", help="Text chat mode (default is voice)"
    )
    group.add_argument(
        "--test", action="store_true", help="Test initialization only"
    )

    args = parser.parse_args()

    # CLI mode - create miku instance and run
    cli = MikuCLI(character=args.character)

    # Initialize
    if not cli.initialize():
        sys.exit(1)

    try:
        # Test mode
        if args.test:
            print("[Test mode - Initialization successful!]")
            return

        # Text mode
        if args.text:
            cli.chat_text_mode()
        else:
            # Voice mode (default in CLI)
            cli.chat_voice_mode()

    except KeyboardInterrupt:
        print("\n[Interrupted]")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback

        traceback.print_exc()
    finally:
        cli.cleanup()


if __name__ == "__main__":
    main()

