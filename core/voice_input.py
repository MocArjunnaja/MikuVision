"""
Voice Input Module - Speech Recognition menggunakan Faster-Whisper
Enhanced dengan initial_prompt dan better VAD, multi-language support
"""

import numpy as np
import sounddevice as sd
import queue
import threading
import os
from typing import Optional
from faster_whisper import WhisperModel
import logging

logging.getLogger("faster_whisper").setLevel(logging.ERROR)

from config import (
    WHISPER_MODEL, WHISPER_LANGUAGE, WHISPER_DEVICE,
    WHISPER_INITIAL_PROMPT, WHISPER_PROMPTS
)


class VoiceInput:
    """
    Handles microphone input dan speech-to-text conversion.
    """
    
    def __init__(self):
        self.model: Optional[WhisperModel] = None
        self.audio_queue = queue.Queue()
        self.is_listening = False
        self.sample_rate = 16000
        self._stream = None
        self._lock = threading.Lock()
        
    def initialize(self) -> bool:
        """Load Whisper model"""
        try:
            print(f"[VoiceInput] Loading Whisper model '{WHISPER_MODEL}'...")
            
            # Gunakan int8 di CUDA untuk menghemat ±50% VRAM (large-v3 dari 3GB jadi cuma 1.5GB)
            compute_type = "int8_float16" if WHISPER_DEVICE == "cuda" else "int8"
            
            self.model = WhisperModel(
                WHISPER_MODEL,
                device=WHISPER_DEVICE,
                compute_type=compute_type
            )
            
            print(f"[VoiceInput] Model loaded successfully on {WHISPER_DEVICE}")
            return True
            
        except Exception as e:
            print(f"[VoiceInput] Error loading model: {e}")
            return False
    
    def _audio_callback(self, indata, frames, time_info, status):
        """Callback untuk sounddevice stream"""
        if status:
            print(f"[VoiceInput] Audio status: {status}")
        self.audio_queue.put(indata.copy())
    
    def start_listening(self, quiet: bool = False):
        """Mulai mendengarkan dari microphone"""
        with self._lock:
            if self.is_listening:
                return
            self.is_listening = True
        
        self.audio_queue = queue.Queue()
        
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype=np.float32,
            callback=self._audio_callback,
            blocksize=int(self.sample_rate * 0.1)
        )
        self._stream.start()
        if not quiet:
            print("[VoiceInput] Started listening...")
    
    def stop_listening(self, quiet: bool = False) -> np.ndarray:
        """Stop listening dan return accumulated audio"""
        if not self.is_listening:
            return np.array([])
            
        self.is_listening = False
        
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        
        audio_chunks = []
        while not self.audio_queue.empty():
            try:
                audio_chunks.append(self.audio_queue.get_nowait())
            except queue.Empty:
                break
        
        if not audio_chunks:
            return np.array([])
            
        audio = np.concatenate(audio_chunks, axis=0).flatten()
        if not quiet:
            print(f"[VoiceInput] Captured {len(audio)/self.sample_rate:.1f}s of audio")
        return audio
    
    def transcribe(
        self,
        audio: np.ndarray,
        lang: str = None,
        use_initial_prompt: Optional[bool] = None,
        no_speech_threshold: float = 0.6,
        vad_min_silence_ms: int = 500,
        vad_speech_pad_ms: int = 300,
        vad_threshold: float = 0.5,
        condition_on_previous_text: bool = True,
        beam_size: int = 5,
        verbose_logging: bool = True,
    ) -> str:
        """Convert audio numpy array ke text dengan opsi decoding yang bisa dituning."""
        if self.model is None:
            raise RuntimeError("Model not initialized")
        
        if len(audio) == 0:
            return ""
        
        # Minimum audio length check (at least 0.5 seconds)
        min_samples = int(self.sample_rate * 0.5)
        if len(audio) < min_samples:
            if verbose_logging:
                print("[VoiceInput] Audio too short, skipping")
            return ""
        
        try:
            audio = audio.astype(np.float32)
            
            # 1. Cek Root Mean Square (Kekuatan sinyal asli sebelum diapa-apakan)
            original_rms = np.sqrt(np.mean(audio**2))
            
            # DEBUG: Ekspor audio Murni sebelum ada pengecekan RMS agar tahu kenapa ditolak
            import time
            from scipy.io.wavfile import write
            DEBUG_DUMP_AUDIO = True
            if DEBUG_DUMP_AUDIO:
                dump_dir = os.path.join(os.path.dirname(__file__), "..", "data", "debug_audio")
                os.makedirs(dump_dir, exist_ok=True)
                timestamp = int(time.time() * 1000)
                wav_path_raw = os.path.join(dump_dir, f"mic_dump_{timestamp}_raw.wav")
                audio_int16 = (audio * 32767).astype(np.int16)
                write(wav_path_raw, self.sample_rate, audio_int16)
                if verbose_logging:
                    print(f"    [Audio Dump] RAW Tersimpan ke: {wav_path_raw} (RMS Original: {original_rms:.4f})")

            # 1.5. Spectral Noise Gating (Menyapu bersih noise lingkungan & dengung kipas sebelum dianalisa)
            import noisereduce as nr
            # prop_decrease=0.85 artinya membuang 85% noise, disisakan sedikit agar suara tidak terlalu kering/kaku.
            audio = nr.reduce_noise(y=audio, sr=self.sample_rate, prop_decrease=0.85)
            
            if original_rms < 0.002:  # Benar-benar hampir hening / hanya static noise kipas
                if verbose_logging:
                    print(f"[VoiceInput] Suara diabaikan karena terlalu hening (RMS Asli: {original_rms:.4f})")   
                return ""

            # 2. Safe Auto-Gain (Mencegah amplifikasi white-noise & mic statis)
            # Kita ambil percentile ke-99.5 agar peak abnormal (seperti suara ketukan meja) diabaikan 
            peak = np.percentile(np.abs(audio), 99.5)
            
            # HANYA lakukan penguatan gain JIKA terdapat tanda-tanda suara (peak antara 0.02 - 0.70).
            # - < 0.02: White-noise/kipas laptop -> JANGAN dinaikkan, nanti hancur
            # - > 0.70: Sudah cukup keras -> JANGAN dinaikkan, nanti distorsi/clipping kasar
            if 0.02 < peak < 0.70:
                # Gunakan Batas Maskimal Gain (Multiplier max 8x) agar distorsi tidak berlebihan
                target_peak = 0.80
                multiplier = min((target_peak / peak), 8.0)
                
                # Soft-clip manual (mencegah flat top yg bisa merusak harmonik Whisper)
                audio_amplified = audio * multiplier
                # Gunakan fungsi tanh untuk meratakan ujung gelombang lebih halus dibanding np.clip()
                audio = np.tanh(audio_amplified)
                
            # 3. Cek kembali RMS Pasca-Gain (Filter akhir) 
            post_rms = np.sqrt(np.mean(audio**2))
            
            if DEBUG_DUMP_AUDIO:
                wav_path_processed = os.path.join(dump_dir, f"mic_dump_{timestamp}_processed.wav")
                audio_processed_int16 = (audio * 32767).astype(np.int16)
                write(wav_path_processed, self.sample_rate, audio_processed_int16)
                if verbose_logging:
                    print(f"    [Audio Dump] PROCESSED Tersimpan ke: {wav_path_processed} (RMS Processed: {post_rms:.4f})")

            if post_rms < 0.01:
                if verbose_logging:
                    print("[VoiceInput] Setelah dinaikkan volumenya, tetap tidak terdeteksi vokal.")
                return ""

            language = lang if lang else WHISPER_LANGUAGE
            
            # For auto-detect language, default to no initial prompt to avoid command hallucination.
            if use_initial_prompt is None:
                use_initial_prompt = language is not None

            initial_prompt = None
            if use_initial_prompt:
                initial_prompt = WHISPER_PROMPTS.get(language, WHISPER_INITIAL_PROMPT)

            segments, info = self.model.transcribe(
                audio,
                language=language,
                initial_prompt=initial_prompt,  # Language-specific vocabulary hint
                beam_size=beam_size,
                best_of=5,
                temperature=0.0,
                condition_on_previous_text=condition_on_previous_text,  # Don't hallucinate from context
                no_speech_threshold=no_speech_threshold,
                vad_filter=True,
                vad_parameters=dict(
                    min_silence_duration_ms=vad_min_silence_ms,
                    speech_pad_ms=vad_speech_pad_ms,
                    threshold=vad_threshold,
                )
            )
            
            segments_list = list(segments)
            text = " ".join([segment.text for segment in segments_list])
            text = text.strip()
            
            # Post-processing: common corrections
            text = self._post_process(text)
            
            if verbose_logging:
                if info and hasattr(info, 'language'):
                    print(f"[VoiceInput] Detected language: {info.language}")
                print(f"[VoiceInput] Transcribed: '{text}'")
            return text
            
        except Exception as e:
            if verbose_logging:
                print(f"[VoiceInput] Transcription error: {e}")
            return ""
    
    def _post_process(self, text: str) -> str:
        """Post-process transcription untuk common corrections"""
        if not text:
            return text
        
        # Common misrecognitions -> corrections
        corrections = {
            # Chrome variations
            "krom": "Chrome",
            "crom": "Chrome",
            "chrome": "Chrome",
            "google krom": "Google Chrome",
            "google crom": "Google Chrome",
            
            # Edge variations
            "ej": "Edge",
            "edj": "Edge",
            
            # Buka variations
            "bukal": "buka",
            "bukak": "buka",
            "bukain": "buka",
            
            # Volume variations  
            "bolum": "volume",
            "folum": "volume",
            "volum": "volume",
            
            # Screenshot
            "skrinshot": "screenshot",
            "screen shot": "screenshot",
            
            # Common commands
            "tolong buka": "buka",
            "coba buka": "buka",
            "tak tokel": "buka",  # Common misrecognition
        }
        
        text_lower = text.lower()
        for wrong, correct in corrections.items():
            if wrong in text_lower:
                # Case-insensitive replace
                import re
                text = re.sub(re.escape(wrong), correct, text, flags=re.IGNORECASE)
        
        return text.strip()
    
    def listen_and_transcribe(self, duration: float = 5.0, lang: str = None, **transcribe_kwargs) -> str:
        """Listen untuk durasi tertentu, lalu transcribe."""
        audio = self.listen_for_duration(duration)
        
        if len(audio) == 0:
            return ""
            
        return self.transcribe(audio, lang=lang, **transcribe_kwargs)

    def listen_for_duration(self, duration: float = 5.0) -> np.ndarray:
        """Record audio for a fixed duration and return raw waveform."""
        import time

        self.start_listening(quiet=True)
        time.sleep(duration)
        audio = self.stop_listening(quiet=True)
        
        # Don't print the "Captured X.X s of audio" spam in fixed-duration loop
        return audio

    def listen_until_silence(
        self,
        max_duration: float = 18.0,
        silence_duration: float = 1.5, # Diturunkan dari 3.0 jadi 1.5 detik (karena WebRTC sangat instan presisi)
        min_duration: float = 1.0,
        speech_threshold: float = 0.005,
        quiet: bool = False,
    ) -> np.ndarray:
        """Listen until speech ends and silence is sustained for a while (Using WebRTC VAD)."""
        import time
        import webrtcvad

        self.start_listening(quiet=quiet)

        start_time = time.time()
        last_voice_time = start_time
        had_voice = False
        chunks = []
        
        # Inisialisasi Google WebRTC VAD
        # Mode 3: Mode paling ketat/agresif dalam menyaring noise lingkungan
        vad = webrtcvad.Vad(3)

        # 30 ms frame = 480 samples @ 16000Hz = 960 bytes (2 bytes per sampel int16)
        frame_duration_ms = 30
        frame_samples = int(self.sample_rate * frame_duration_ms / 1000)
        frame_bytes = frame_samples * 2

        try:
            while True:
                now = time.time()
                elapsed = now - start_time

                if elapsed >= max_duration:
                    break

                try:
                    chunk = self.audio_queue.get(timeout=0.1)
                except queue.Empty:
                    if had_voice and elapsed >= min_duration and (now - last_voice_time) >= silence_duration:
                        break
                    continue

                chunks.append(chunk)

                # Convert audio float32 (sounddevice) array ke RAW int16 bytes untuk webrtcvad
                chunk_flat = chunk.flatten()
                chunk_int16_bytes = (chunk_flat * 32767).astype(np.int16).tobytes()

                is_speech = False
                # Pecah 1 chunk sounddevice (biasanya 100ms) menjadi kepingan 30ms secara presisi
                for i in range(0, len(chunk_int16_bytes), frame_bytes):
                    frame = chunk_int16_bytes[i:i + frame_bytes]
                    if len(frame) == frame_bytes:
                        try:
                            if vad.is_speech(frame, self.sample_rate):
                                is_speech = True
                                break
                        except Exception:
                            pass
                
                if is_speech:
                    if not had_voice and not quiet:
                        pass # first time voice detected
                    elif not had_voice and quiet:
                        # Give a visual cue in console even if quiet
                        import sys
                        sys.stdout.write("\r[Voice Detected] Listening... ")
                        sys.stdout.flush()
                        
                    had_voice = True
                    last_voice_time = now

                if had_voice and elapsed >= min_duration and (now - last_voice_time) >= silence_duration:
                    if quiet:
                        import sys
                        sys.stdout.write("\r[Silence Detected] Processing... \n")
                        sys.stdout.flush()
                    break
        finally:
            self.is_listening = False
            if self._stream:
                self._stream.stop()
                self._stream.close()
                self._stream = None

        if not chunks:
            return np.array([])

        audio = np.concatenate(chunks, axis=0).flatten()
        if not quiet:
            print(f"[VoiceInput] Captured {len(audio)/self.sample_rate:.1f}s of audio (silence-stop)")
        return audio

    def listen_until_silence_and_transcribe(
        self,
        max_duration: float = 18.0,
        silence_duration: float = 3.0,
        min_duration: float = 1.0,
        speech_threshold: float = 0.01,
        lang: str = None,
        **transcribe_kwargs,
    ) -> str:
        """Listen with silence-stop strategy and return transcription."""
        audio = self.listen_until_silence(
            max_duration=max_duration,
            silence_duration=silence_duration,
            min_duration=min_duration,
            speech_threshold=speech_threshold,
        )

        if len(audio) == 0:
            return ""

        return self.transcribe(audio, lang=lang, **transcribe_kwargs)
    
    def cleanup(self):
        """Release resources"""
        if self._stream:
            self._stream.stop()
            self._stream.close()
        self.model = None
        print("[VoiceInput] Cleaned up")
