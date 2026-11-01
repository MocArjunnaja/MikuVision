"""
Voice Input Module - Speech Recognition menggunakan Faster-Whisper

Satu kali transkripsi per ucapan: bahasa dideteksi lebih dulu (dibatasi ke
WHISPER_LANGUAGES), lalu Whisper dijalankan dengan bahasa itu dan petunjuk kosakatanya.
"""

import numpy as np
import sounddevice as sd
import queue
import threading
import os
from typing import Iterable, List, Optional, Tuple
from faster_whisper import WhisperModel
import logging

logging.getLogger("faster_whisper").setLevel(logging.ERROR)

from config import (
    WHISPER_MODEL, WHISPER_LANGUAGE, WHISPER_LANGUAGES, WHISPER_DEVICE,
    WHISPER_INITIAL_PROMPT, WHISPER_PROMPTS, DEBUG_DUMP_AUDIO, STT_DENOISE,
)
from core.stt_text import clean_transcript, rank_languages

# Bila bahasa teratas kurang yakin dari ini, dua bahasa teratas sama-sama ditranskripsi
# dan dipilih yang log-probability-nya lebih baik
LANGUAGE_CONFIDENT = 0.8


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
        self.last_language: Optional[str] = None  # bahasa hasil transcribe() terakhir
        # (kata, mulai, selesai, peluang) dari transcribe(word_timestamps=True) terakhir; waktu dalam detik
        self.last_words: List[Tuple[str, float, float, float]] = []
        
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
    
    def _prepare_audio(self, audio: np.ndarray, verbose_logging: bool) -> Optional[np.ndarray]:
        """Tolak rekaman yang terlalu pendek/hening, lalu samakan level suaranya."""
        audio = np.asarray(audio, dtype=np.float32).flatten()
        if len(audio) < int(self.sample_rate * 0.5):
            if verbose_logging:
                print("[VoiceInput] Audio too short, skipping")
            return None

        rms = float(np.sqrt(np.mean(audio ** 2)))
        if DEBUG_DUMP_AUDIO:
            self._dump_audio(audio, "raw", rms, verbose_logging)
        if rms < 0.002:  # hampir hening / hanya derau kipas
            if verbose_logging:
                print(f"[VoiceInput] Suara diabaikan karena terlalu hening (RMS: {rms:.4f})")
            return None

        if STT_DENOISE:
            # Noise gating bisa merusak konsonan; hanya untuk mic yang sangat berisik
            import noisereduce as nr
            audio = nr.reduce_noise(y=audio, sr=self.sample_rate, prop_decrease=0.85)

        # Log-mel Whisper bergantung pada level absolut: mic laptop yang pelan dinaikkan
        # secara linear (tanpa soft-clip, yang mendistorsi harmonik)
        peak = float(np.percentile(np.abs(audio), 99.9))
        if peak > 1e-4:
            audio = np.clip(audio * min(0.5 / peak, 30.0), -1.0, 1.0)
        if DEBUG_DUMP_AUDIO:
            self._dump_audio(audio, "processed", float(np.sqrt(np.mean(audio ** 2))), verbose_logging)
        return audio

    def _dump_audio(self, audio: np.ndarray, kind: str, rms: float, verbose_logging: bool):
        import time
        from scipy.io.wavfile import write

        dump_dir = os.path.join(os.path.dirname(__file__), "..", "data", "debug_audio")
        os.makedirs(dump_dir, exist_ok=True)
        path = os.path.join(dump_dir, f"mic_dump_{int(time.time() * 1000)}_{kind}.wav")
        write(path, self.sample_rate, (np.clip(audio, -1, 1) * 32767).astype(np.int16))
        if verbose_logging:
            print(f"    [Audio Dump] {kind} -> {path} (RMS {rms:.4f})")

    def detect_language(self, audio: np.ndarray, languages: Iterable[str]) -> List[Tuple[str, float]]:
        """Peluang tiap bahasa yang diizinkan, terurut dari yang paling mungkin."""
        languages = [lang for lang in dict.fromkeys(languages) if lang]
        if len(languages) == 1:
            return [(languages[0], 1.0)]
        best, best_prob, probabilities = self.model.detect_language(audio, vad_filter=True)
        if not languages:  # tanpa batasan: pakai deteksi Whisper apa adanya
            return [(best, best_prob)]
        return rank_languages(probabilities, languages)

    def _decode(self, audio: np.ndarray, language: str, use_initial_prompt: bool, beam_size: int,
                vad_min_silence_ms: int, vad_speech_pad_ms: int, vad_threshold: float,
                prompt: Optional[str] = None, word_timestamps: bool = False,
                ) -> Tuple[str, float, List[Tuple[str, float, float, float]]]:
        """Satu kali decoding: teks bersih, rata-rata log-probability per token, dan kata + waktunya."""
        if prompt is None and use_initial_prompt:
            prompt = WHISPER_PROMPTS.get(language, WHISPER_INITIAL_PROMPT)
        segments, _ = self.model.transcribe(
            audio,
            language=language,
            initial_prompt=prompt,
            beam_size=beam_size,
            temperature=(0.0, 0.2, 0.4),  # suhu naik hanya bila hasil suhu 0 berulang/ragu
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
            word_timestamps=word_timestamps,
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=vad_min_silence_ms,
                speech_pad_ms=vad_speech_pad_ms,
                threshold=vad_threshold,
            ),
        )
        kept, words, logprob, weight = [], [], 0.0, 0.0
        for seg in segments:
            # Aturan bawaan Whisper untuk segmen tanpa ucapan, plus teks yang berulang-ulang
            if (seg.no_speech_prob > 0.6 and seg.avg_logprob < -1.0) or seg.compression_ratio > 2.4:
                continue
            kept.append(seg.text)
            words.extend((w.word, w.start, w.end, getattr(w, "probability", 1.0))
                         for w in (getattr(seg, "words", None) or []))
            duration = max(seg.end - seg.start, 0.1)
            logprob += seg.avg_logprob * duration
            weight += duration
        text = clean_transcript("".join(kept) if language == "ja" else " ".join(kept), language)
        return text, (logprob / weight if weight else -99.0), words

    def transcribe(
        self,
        audio: np.ndarray,
        lang: str = None,
        languages: Optional[Iterable[str]] = None,
        use_initial_prompt: bool = True,
        vad_min_silence_ms: int = 500,
        vad_speech_pad_ms: int = 300,
        vad_threshold: float = 0.5,
        beam_size: int = 5,
        verbose_logging: bool = True,
        prompt: Optional[str] = None,
        word_timestamps: bool = False,
    ) -> str:
        """Audio -> teks.

        ``lang`` memaksa satu bahasa. Tanpa ``lang``, bahasa dideteksi di antara ``languages``
        (bawaan WHISPER_LANGUAGES) sebelum transkripsi; bila deteksi ragu, dua bahasa teratas
        ditranskripsi dan dipilih yang lebih yakin. ``prompt`` menggantikan prompt kosakata bawaan.
        ``word_timestamps`` mengisi ``last_words`` (kata dan waktunya di audio masukan).
        """
        if self.model is None:
            raise RuntimeError("Model not initialized")
        self.last_language = None
        self.last_words = []
        if audio is None or len(audio) == 0:
            return ""

        try:
            audio = self._prepare_audio(audio, verbose_logging)
            if audio is None:
                return ""

            candidates = [lang] if lang else list(languages or WHISPER_LANGUAGES or [WHISPER_LANGUAGE])
            ranked = self.detect_language(audio, candidates)
            tries = ranked[:1] if ranked[0][1] >= LANGUAGE_CONFIDENT else ranked[:2]
            vad = dict(vad_min_silence_ms=vad_min_silence_ms, vad_speech_pad_ms=vad_speech_pad_ms,
                       vad_threshold=vad_threshold, prompt=prompt, word_timestamps=word_timestamps)
            results = [(*self._decode(audio, language, use_initial_prompt, beam_size, **vad), language)
                       for language, _ in tries]
            results = [r for r in results if r[0]]
            if not results:
                if verbose_logging:
                    print("[VoiceInput] Tidak ada ucapan yang dikenali")
                return ""
            text, logprob, words, language = max(results, key=lambda r: r[1])
            self.last_language = language
            self.last_words = words

            if verbose_logging:
                odds = ", ".join(f"{code}={p:.2f}" for code, p in ranked)
                print(f"[VoiceInput] Bahasa: {language} ({odds}), logprob {logprob:.2f}")
                print(f"[VoiceInput] Transcribed: '{text}'")
            return text

        except Exception as e:
            if verbose_logging:
                print(f"[VoiceInput] Transcription error: {e}")
            return ""

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
