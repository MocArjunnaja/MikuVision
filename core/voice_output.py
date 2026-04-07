"""
Voice Output Module v4 - Text-to-Speech Lokal (MeloTTS) dengan RVC Voice Conversion
Pipeline: Text -> MeloTTS (100% Offline) -> [RVC Conversion] -> Playback
"""

import os
import uuid
import threading
from pathlib import Path
from typing import Optional, Dict

try:
    from melo.api import TTS
except ImportError:
    print("[VoiceOutput] Warning: MeloTTS module not found. Did you install it?")
    TTS = None

from config import TTS_VOICE, TTS_RATE, TTS_PITCH, AUDIO_DIR, Character
from core.voice_converter import VoiceConverter


class VoiceOutput:
    """
    Text-to-Speech with optional RVC voice conversion.

    v4 pipeline (Offline Lokal):
    1. MeloTTS generates base audio (WAV) via CPU
    2. If RVC converter is available, convert to character voice (WAV)
    3. Play the result
    """

    def __init__(self, character: Optional[Character] = None, converter: Optional[VoiceConverter] = None):
        # Default TTS config
        self.voice = "JP"  # MeloTTS menggunakan language ID 'JP', 'EN', dll.
        self.rate = 1.0    # Speed multiplier di MeloTTS

        # Prepare MeloTTS Engine (CPU-based lokal)
        self.model_tts = None
        self.speaker_id = 0
        if TTS is not None:
            print("[VoiceOutput] Loading MeloTTS engine (100% Offline CPU)...")
            try:
                self.model_tts = TTS(language='JP', device='cpu')
                self.speaker_id = self.model_tts.hps.data.spk2id['JP']
            except Exception as e:
                print(f"[VoiceOutput] Error loading MeloTTS: {e}")

        # Apply character config if provided
        if character and character.voice_config:
            self.apply_character_voice(character)

        # RVC voice converter (optional)
        self.converter = converter
        self.current_process = None
        self._is_speaking = False

    def set_converter(self, converter: Optional[VoiceConverter]):
        """Set or replace the voice converter"""
        self.converter = converter

    def apply_character_voice(self, character: Character):
        """Apply voice configuration dari character"""
        config = character.voice_config
        # Untuk MeloTTS kita tidak perlu set config yang rumit-rumit
        self.rate = config.get("rate_multiplier", 1.0)
        print(f"[VoiceOutput] Applied MeloTTS voice config for {character.display_name}")

    def _generate_audio(self, text: str, output_path: str) -> bool:
        """Generate audio file dari text via MeloTTS Lokal (Sync)"""
        if not self.model_tts:
            print("[VoiceOutput] Cannot generate audio: MeloTTS model not loaded")
            return False

        try:
            # 🔨 FASE 1: "The Iron Voice" Sanitizer
            # Filter ketat: Hanya izinkan Alfabet, Angka, Kana, Kanji, spasi, dan sedikit punctuation.
            import re
            cleaned_text = re.sub(
                r'[^\w\s\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\.,!?\'"()]+', 
                '', 
                text
            )
            # Buang simbol-simbol nakal halusinasi LLM kecil (misal: ™, }, dll)
            cleaned_text = re.sub(r'[™®©\[\]{}<>\-_~@#$%^&*+=|\\/]', '', cleaned_text)

            if not cleaned_text.strip():
                print(f"[VoiceOutput] Text kosong setelah distrip karakter asing. Skip TTS.")
                return False

            print(f"[VoiceOutput] Safe Text: {cleaned_text[:50]}...")
            
            try:
                # Generate offline audio directly to wav
                self.model_tts.tts_to_file(cleaned_text, self.speaker_id, output_path, speed=self.rate)
                return True
            except Exception as tts_err:
                print(f"[VoiceOutput] Internal MeloTTS error pada teks: '{cleaned_text[:50]}...' -> {tts_err}")
                # Fallback: Buang semua Kanji dan Hanzi, hanya Hiragana Katakana Romaji
                fallback_text = re.sub(r'[\u4E00-\u9FFF]+', '', cleaned_text)
                if fallback_text.strip():
                    print(f"[VoiceOutput] RETRY TTS dengan membuang Kanji: {fallback_text[:50]}...")
                    self.model_tts.tts_to_file(fallback_text, self.speaker_id, output_path, speed=self.rate)
                    return True
                return False
                
        except Exception as e:
            print(f"[VoiceOutput] Error fatal generating MeloTTS audio: {e}")
            return False

    def _play_audio_sync(self, audio_path: str):
        """Play audio file using sounddevice"""
        try:
            import soundfile as sf
            import sounddevice as sd

            data, samplerate = sf.read(audio_path)
            sd.play(data, samplerate)
            sd.wait()

        except Exception as e:
            print(f"[VoiceOutput] Error playing audio: {e}")
        finally:
            try:
                if os.path.exists(audio_path):
                    os.remove(audio_path)
            except:
                pass

    def speak(self, text: str, blocking: bool = True) -> bool:
        """
        Convert text to speech locally with optional RVC conversion.

        Pipeline Offline:
        1. MeloTTS -> WAV (Base)
        2. RVC conversion -> WAV (Hatsune Miku)
        3. Play audio
        """
        if not text.strip():
            return False

        print(f"[VoiceOutput] Speaking (Offline): '{text[:50]}...'")
        self._is_speaking = True

        uid = uuid.uuid4().hex[:8]
        # MeloTTS output berupa WAV bukan MP3 seperti edge-tts
        tts_path = str(AUDIO_DIR / f"tts_{uid}.wav")

        # Step 1: Generate TTS audio (Sekarang fully synchronous, sangat cepat!)
        success = self._generate_audio(text, tts_path)

        if not success:
            self._is_speaking = False
            return False

        # Step 2: RVC conversion (if available)
        play_path = tts_path
        rvc_path = str(AUDIO_DIR / f"rvc_{uid}.wav")

        if self.converter and self.converter.is_available:
            if self.converter.convert(tts_path, rvc_path):
                play_path = rvc_path
                # Clean up original melo TTS file (base voice)
                try:
                    if os.path.exists(tts_path):
                        os.remove(tts_path)
                except:
                    pass

        # Step 3: Play audio
        if blocking:
            self._play_audio_sync(play_path)
            self._is_speaking = False
        else:
            thread = threading.Thread(
                target=self._play_audio_and_cleanup,
                args=(play_path,)
            )
            thread.daemon = True
            thread.start()

        return True

    def _play_audio_and_cleanup(self, audio_path: str):
        """Background playback with cleanup"""
        self._play_audio_sync(audio_path)
        self._is_speaking = False

    def stop(self):
        """Stop current playback"""
        try:
            import sounddevice as sd
            sd.stop()
            self._is_speaking = False
        except:
            pass

    @property
    def is_speaking(self) -> bool:
        return self._is_speaking

    def set_voice(self, voice: str):
        self.voice = voice

    def set_rate(self, rate: float):
        self.rate = rate

    @staticmethod
    async def list_voices() -> list:
        # MeloTTS statis, kita kembalikan daftar palsu karena API ini sebelumnya dipakai edge-tts
        return [{"Name": "JP", "Gender": "Female", "Locale": "ja-JP"}]

    def cleanup(self):
        """Cleanup temp files and resources"""
        self.stop()
        if self.converter:
            self.converter.cleanup()
        for f in AUDIO_DIR.glob("tts_*.wav"):
            try:
                f.unlink()
            except:
                pass
        for f in AUDIO_DIR.glob("rvc_*.wav"):
            try:
                f.unlink()
            except:
                pass

        print("[VoiceOutput] Cleaned up")
