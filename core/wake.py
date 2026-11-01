"""
Wake phrase "Oke Miku": mikrofon terus terbuka, tetapi Whisper hanya jalan saat ada ucapan.

Gerbang VAD (webrtcvad, CPU) memotong audio mikrofon menjadi segmen ucapan; saat hening
tidak ada transkripsi sama sekali. Tiap segmen ditranskripsi sekali bila pendek. Ucapan
panjang tanpa jeda dicek per jendela WAKE_CHECK_SEC, sehingga wake phrase di tengah
obrolan tetap tertangkap tanpa mentranskripsi ulang audio yang sama.

Begitu wake phrase terdengar, segmen dibiarkan selesai lalu ditranskripsi utuh, supaya
perintah yang diucapkan sekaligus ("Oke Miku, buka Notepad") tidak terpotong. on_wake
menerima sisa kalimat sesudah wake phrase ("" bila hanya "Oke Miku").

Dipakai mode suara (`miku.py`, menggantikan menyeret maskot) dan GUI (tombol Wake Phrase).
"""

import queue
import re
import threading
import time
import unicodedata
from collections import deque
from dataclasses import dataclass
from typing import Callable, List, Optional

import numpy as np

SAMPLE_RATE = 16000
FRAME_MS = 30  # webrtcvad menerima frame 10, 20, atau 30 ms

# "Oke Miku" dan variannya seperti yang ditulis Whisper (Indonesia/Jepang/Inggris):
# "Oke Miku", "OK, Miku.", "Okay Miku", "オッケー、ミク", "オーケーミク", "OKミク". Uji suara
# sintetis (experiments/wake_eval) juga menghasilkan "Oke, migu", "Oke niku", "Oke, mitu",
# "Oke, migo", dan "OK, Miuku".
_OK = r"(?:okay|okey|okei|oke|ok|oce|oche|おっけー|おーけー|オッケー|オーケー|オッケ|オケー)"
_MIKU = r"(?:[mn]iu?(?:kk|k|g|t)[uo]|meeku|ミク|みく)(?:[\s-]?(?:chan|san)|ちゃん|さん)?"
WAKE_PATTERN = re.compile(
    rf"(?<![a-z]){_OK}[\s,.、。!！~〜ー-]*{_MIKU}(?![a-z])", re.IGNORECASE
)
# Tanda baca dan kata sambung yang tersisa di depan perintah: "Oke Miku, tolong …" -> "tolong …"
_LEADING = re.compile(r"^[\s,.、。!！?？~〜ー-]+")


def _open_input_stream(sample_rate: int, callback):
    """Stream mikrofon (sounddevice), potongan 100 ms. Diganti stream palsu di test."""
    import sounddevice as sd
    stream = sd.InputStream(samplerate=sample_rate, channels=1, dtype=np.float32,
                            blocksize=int(sample_rate * 0.1), callback=callback)
    stream.start()
    return stream


def match_wake_phrase(text: str) -> Optional[str]:
    """Sisa kalimat sesudah wake phrase ("" bila hanya wake phrase), None bila tidak ada."""
    text = unicodedata.normalize("NFKC", text or "")
    match = WAKE_PATTERN.search(text)
    if not match:
        return None
    return _LEADING.sub("", text[match.end():]).strip()


class SpeechSegmenter:
    """
    Audio float32 16 kHz -> segmen ucapan, dengan webrtcvad per frame 30 ms.

    Segmen dimulai bila start_ratio dari frame dalam jendela start_window_ms terakhir berisi
    ucapan; jendela itu ikut masuk segmen, supaya awal kata ("O" di "Oke") tidak terpotong.
    Segmen selesai setelah end_silence_ms hening, atau dipotong pada max_segment_sec.

    vad_mode 3 (paling ketat): di mic laptop yang terlalu keras, mode 2 menganggap 100% derau
    ruangan sebagai ucapan, mode 3 hanya 5%; di set uji akurasinya sama (experiments/wake_eval).
    """

    def __init__(self, sample_rate: int = SAMPLE_RATE, vad_mode: int = 3, start_window_ms: int = 300,
                 start_ratio: float = 0.6, end_silence_ms: int = 600, max_segment_sec: float = 15.0,
                 vad=None):
        if vad is None:
            import webrtcvad
            vad = webrtcvad.Vad(vad_mode)
        self._vad = vad
        self.sample_rate = sample_rate
        self.frame_samples = sample_rate * FRAME_MS // 1000
        self._ring: deque = deque(maxlen=max(1, start_window_ms // FRAME_MS))
        self.start_ratio = start_ratio
        self.end_frames = max(1, end_silence_ms // FRAME_MS)
        self.max_frames = int(max_segment_sec * 1000 // FRAME_MS)
        self._pending = np.zeros(0, dtype=np.float32)
        self._frames: List[np.ndarray] = []
        self._silence = 0
        self.active = False

    def _is_speech(self, frame: np.ndarray) -> bool:
        pcm = (np.clip(frame, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
        try:
            return bool(self._vad.is_speech(pcm, self.sample_rate))
        except Exception:
            return False

    def feed(self, audio: np.ndarray) -> List[np.ndarray]:
        """Masukkan audio; kembalikan segmen yang selesai di dalamnya."""
        done = []
        self._pending = np.concatenate([self._pending, np.asarray(audio, dtype=np.float32).ravel()])
        while len(self._pending) >= self.frame_samples:
            frame = self._pending[:self.frame_samples]
            self._pending = self._pending[self.frame_samples:]
            segment = self._feed_frame(frame)
            if segment is not None:
                done.append(segment)
        return done

    def _feed_frame(self, frame: np.ndarray) -> Optional[np.ndarray]:
        speech = self._is_speech(frame)
        if not self.active:
            self._ring.append((frame, speech))
            if sum(s for _, s in self._ring) >= self.start_ratio * self._ring.maxlen:
                self.active = True
                self._frames = [f for f, _ in self._ring]
                self._ring.clear()
                self._silence = 0
            return None
        self._frames.append(frame)
        self._silence = 0 if speech else self._silence + 1
        if self._silence >= self.end_frames or len(self._frames) >= self.max_frames:
            return self._close()
        return None

    def _close(self) -> np.ndarray:
        segment = np.concatenate(self._frames)
        self._frames = []
        self._silence = 0
        self.active = False
        return segment

    @property
    def active_samples(self) -> int:
        return len(self._frames) * self.frame_samples

    def current(self) -> np.ndarray:
        """Audio segmen yang sedang berjalan."""
        return np.concatenate(self._frames) if self._frames else np.zeros(0, dtype=np.float32)

    def reset(self):
        self._pending = np.zeros(0, dtype=np.float32)
        self._frames = []
        self._ring.clear()
        self._silence = 0
        self.active = False


@dataclass
class WakeStats:
    audio_seconds: float = 0.0       # audio yang diperiksa (tidak termasuk saat sibuk)
    segments: int = 0                # segmen ucapan dari VAD
    transcriptions: int = 0          # panggilan Whisper
    transcribe_seconds: float = 0.0  # waktu Whisper
    wakes: int = 0


class WakeListener:
    """
    Pendengar "Oke Miku".

    transcribe(audio) -> teks memakai Whisper yang sudah dimuat aplikasi, untuk mengecek wake
    phrase; boleh versi murah (satu bahasa tetap, beam 1). transcribe_command (bawaan: sama)
    dipakai untuk mengambil perintah dari seluruh segmen bila ada. on_wake(perintah)
    dipanggil dari thread pendengar dan harus cepat (memasang event atau mengisi antrean).
    is_busy() benar selama Miku merekam, memproses, atau bicara: audio saat itu dibuang,
    supaya Miku tidak mendengar suaranya sendiri, dan baru didengar lagi cooldown_sec kemudian.
    """

    def __init__(self, transcribe: Callable[[np.ndarray], str], on_wake: Callable[[str], None],
                 is_busy: Callable[[], bool] = lambda: False,
                 transcribe_command: Optional[Callable[[np.ndarray], str]] = None,
                 sample_rate: int = SAMPLE_RATE,
                 check_sec: float = 2.5, overlap_sec: float = 1.0, min_check_sec: float = 0.4,
                 cooldown_sec: float = 0.5, segmenter: Optional[SpeechSegmenter] = None,
                 clock: Callable[[], float] = time.monotonic):
        self.transcribe = transcribe
        self.transcribe_command = transcribe_command
        self.on_wake = on_wake
        self.is_busy = is_busy
        self.sample_rate = sample_rate
        self.check_samples = int(check_sec * sample_rate)
        self.overlap_samples = int(overlap_sec * sample_rate)
        self.min_check_samples = int(min_check_sec * sample_rate)
        self.cooldown_sec = cooldown_sec
        self.segmenter = segmenter or SpeechSegmenter(sample_rate)
        self.clock = clock
        self.stats = WakeStats()
        self._checked = 0      # sampel segmen berjalan yang sudah ditranskripsi
        self._armed = False    # wake phrase sudah terdengar di segmen berjalan
        self._quiet_since: Optional[float] = None  # kapan terakhir tidak sibuk
        self._queue: "queue.Queue[np.ndarray]" = queue.Queue()
        self._stream = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    # ── logika (dipanggil per potongan audio; bisa dites tanpa mikrofon) ──

    def feed(self, audio: np.ndarray):
        if self._busy():
            return
        self.stats.audio_seconds += len(audio) / self.sample_rate
        for segment in self.segmenter.feed(audio):
            self.stats.segments += 1
            self._segment_ended(segment)
        if self.segmenter.active and not self._armed:
            done = self.segmenter.active_samples
            if done - self._checked >= self.check_samples:
                audio_so_far = self.segmenter.current()
                window = audio_so_far[max(0, self._checked - self.overlap_samples):done]
                self._checked = done
                if self._heard(window) is not None:
                    self._armed = True  # tunggu segmen selesai, lalu ambil perintah utuh

    def _busy(self) -> bool:
        if self.is_busy():
            self._quiet_since = None
            self.segmenter.reset()
            self._checked, self._armed = 0, False
            return True
        now = self.clock()
        if self._quiet_since is None:
            self._quiet_since = now
        return now - self._quiet_since < self.cooldown_sec

    def _segment_ended(self, segment: np.ndarray):
        armed, checked = self._armed, self._checked
        self._checked, self._armed = 0, False
        if armed:
            self._wake(self._command(segment, fallback=""))
            return
        tail = segment[max(0, checked - self.overlap_samples):] if checked else segment
        if len(tail) < self.min_check_samples:
            return
        command = self._heard(tail)
        if command is None:
            return
        if command and (self.transcribe_command or checked):
            # Perintah ikut terucap: ambil dari transkripsi seluruh segmen
            command = self._command(segment, fallback=command)
        self._wake(command)

    def _heard(self, audio: np.ndarray) -> Optional[str]:
        """Cek wake phrase (transcribe, boleh versi murah)."""
        return match_wake_phrase(self._transcribe(self.transcribe, audio))

    def _command(self, segment: np.ndarray, fallback: str) -> str:
        """Perintah sesudah wake phrase dari seluruh segmen (transcribe_command bila ada)."""
        command = match_wake_phrase(self._transcribe(self.transcribe_command or self.transcribe, segment))
        return fallback if command is None else command

    def _transcribe(self, transcribe: Callable[[np.ndarray], str], audio: np.ndarray) -> str:
        started = time.perf_counter()
        try:
            text = transcribe(audio) or ""
        except Exception as e:
            print(f"[Wake] Transkripsi gagal: {e}")
            text = ""
        self.stats.transcriptions += 1
        self.stats.transcribe_seconds += time.perf_counter() - started
        return text

    def _wake(self, command: str):
        self.stats.wakes += 1
        try:
            self.on_wake(command)
        except Exception as e:
            print(f"[Wake] Error: {e}")

    # ── mikrofon ──

    def start(self) -> Optional[str]:
        """Buka mikrofon. Kembalikan pesan error, atau None bila berhasil."""
        if self._thread:
            return None
        try:
            self._stream = _open_input_stream(
                self.sample_rate, lambda indata, frames, t, status: self._queue.put(indata[:, 0].copy()))
        except Exception as e:
            self._stream = None
            return f"mikrofon tidak bisa dibuka ({e})"
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="wake-listener", daemon=True)
        self._thread.start()
        return None

    def _run(self):
        # Whisper dijalankan di thread ini, bukan di callback audio
        while not self._stop.is_set():
            try:
                chunk = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            self.feed(chunk)

    def stop(self):
        self._stop.set()
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        self.segmenter.reset()
