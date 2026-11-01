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
from typing import Callable, List, Optional, Tuple

import numpy as np

SAMPLE_RATE = 16000
FRAME_MS = 30  # webrtcvad menerima frame 10, 20, atau 30 ms

# "Oke Miku" dan variannya seperti yang ditulis Whisper (Indonesia/Jepang/Inggris):
# "Oke Miku", "OK, Miku.", "Okay Miku", "オッケー、ミク", "オーケーミク", "OKミク". Uji suara
# sintetis (experiments/wake_eval) juga menghasilkan "Oke, migu", "Oke niku", "Oke, mitu",
# "Oke, migo", dan "OK, Miuku"; suara sungguhan juga "Oke emigu" dan "Oke, amiku".
_OK = r"(?:okay|okey|okei|oke|ok|oce|oche|おっけー|おーけー|オッケー|オーケー|オッケ|オケー)"
_MIKU = r"(?:[ae]?[mn]iu?(?:kk|k|g|t)[uo]|meeku|ミク|みく)(?:[\s-]?(?:chan|san)|ちゃん|さん)?"
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
    rest = _LEADING.sub("", text[match.end():])
    # Whisper kadang menulis wake phrase dua kali: 「OK、ミク、OK、ミク」
    while (again := WAKE_PATTERN.match(rest)):
        rest = _LEADING.sub("", rest[again.end():])
    return rest.strip()


def _wake_words(words) -> Optional[List[tuple]]:
    """Kata-kata (dari VoiceInput.last_words) yang membentuk wake phrase pertama, None bila tidak ada."""
    text, spans = "", []
    for item in words:
        word = unicodedata.normalize("NFKC", item[0])
        spans.append((len(text), len(text) + len(word), item))
        text += word
    match = WAKE_PATTERN.search(text)
    if not match:
        return None
    return [item for start, stop, item in spans if start < match.end() and stop > match.start()]


def wake_phrase_end(words) -> Optional[float]:
    """Detik akhir wake phrase dari kata + waktunya (VoiceInput.last_words), None bila tidak ada."""
    found = _wake_words(words)
    return found[-1][2] if found else None


def wake_phrase_confidence(words) -> Optional[float]:
    """Peluang terendah Whisper di antara kata-kata wake phrase, None bila tidak ada atau tanpa peluang."""
    found = _wake_words(words)
    if not found or any(len(item) < 4 for item in found):
        return None
    return min(item[3] for item in found)


class SpeechSegmenter:
    """
    Audio float32 16 kHz -> segmen ucapan, dengan webrtcvad per frame 30 ms.

    Segmen dimulai bila start_ratio dari frame dalam jendela start_window_ms terakhir berisi
    ucapan. pre_roll_ms audio sebelumnya ikut masuk segmen: VAD mode 3 baru yakin setelah suku
    kata pertama, dan tanpa ini "Oke Miku" terbaca "Gimicu" dan "Miku lagi nyanyi" terbaca
    "Lagi nyanyi" (uji suara sungguhan). Segmen selesai setelah end_silence_ms hening, atau
    dipotong pada max_segment_sec.

    vad_mode 3 (paling ketat): di mic laptop yang terlalu keras, mode 2 menganggap 100% derau
    ruangan sebagai ucapan, mode 3 hanya 5%; di set uji akurasinya sama (experiments/wake_eval).
    """

    def __init__(self, sample_rate: int = SAMPLE_RATE, vad_mode: int = 3, start_window_ms: int = 300,
                 start_ratio: float = 0.6, end_silence_ms: int = 600, max_segment_sec: float = 15.0,
                 pre_roll_ms: int = 800, vad=None):
        if vad is None:
            import webrtcvad
            vad = webrtcvad.Vad(vad_mode)
        self._vad = vad
        self.sample_rate = sample_rate
        self.frame_samples = sample_rate * FRAME_MS // 1000
        self._recent: deque = deque(maxlen=max(1, start_window_ms // FRAME_MS))  # ucapan? per frame
        self._history: deque = deque(maxlen=max(self._recent.maxlen, pre_roll_ms // FRAME_MS))
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
            self._history.append(frame)
            self._recent.append(speech)
            if sum(self._recent) >= self.start_ratio * self._recent.maxlen:
                self.active = True
                self._frames = list(self._history)
                self._history.clear()
                self._recent.clear()
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
        self._history.clear()
        self._recent.clear()
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

    Perintah yang ikut terucap ditahan continue_sec: bila user melanjutkan sesudah jeda
    singkat ("kecilkan volume … ke tiga puluh"), kedua bagian digabung dan ditranskripsi ulang.

    wake_end() (opsional) memberi detik akhir wake phrase di audio yang baru dicek, dari cap
    waktu kata Whisper. Perintah lalu ditranskripsi tanpa wake phrase di depannya: "Oke Miku"
    berbunyi seperti bahasa Jepang, sehingga "Oke Miku, buka Notepad" utuh tertulis 「ブカ、Notepad」.
    on_warning(pesan) dipanggil sekali bila derau mikrofon di awal terlalu tinggi.
    on_heard(teks) (opsional) menerima setiap hasil cek yang tidak kosong, supaya user bisa
    melihat apa yang terdengar ketika "Oke Miku" tidak dikenali.
    """

    def __init__(self, transcribe: Callable[[np.ndarray], str], on_wake: Callable[[str], None],
                 is_busy: Callable[[], bool] = lambda: False,
                 transcribe_command: Optional[Callable[[np.ndarray], str]] = None,
                 wake_end: Optional[Callable[[], Optional[float]]] = None,
                 on_warning: Callable[[str], None] = print,
                 on_heard: Optional[Callable[[str], None]] = None,
                 sample_rate: int = SAMPLE_RATE,
                 check_sec: float = 2.5, overlap_sec: float = 1.0, min_check_sec: float = 0.4,
                 cooldown_sec: float = 0.5, continue_sec: float = 0.6,
                 segmenter: Optional[SpeechSegmenter] = None, clock: Callable[[], float] = time.monotonic):
        self.transcribe = transcribe
        self.transcribe_command = transcribe_command
        self.wake_end = wake_end
        self.on_warning = on_warning
        self.on_heard = on_heard
        self.on_wake = on_wake
        self.is_busy = is_busy
        self.sample_rate = sample_rate
        self.check_samples = int(check_sec * sample_rate)
        self.overlap_samples = int(overlap_sec * sample_rate)
        self.min_check_samples = int(min_check_sec * sample_rate)
        self.cooldown_sec = cooldown_sec
        self.continue_samples = int(continue_sec * sample_rate)
        self.segmenter = segmenter or SpeechSegmenter(sample_rate)
        self.clock = clock
        self.stats = WakeStats()
        self._checked = 0      # sampel segmen berjalan yang sudah ditranskripsi
        self._armed = False    # wake phrase sudah terdengar di segmen berjalan
        self._armed_command = ""  # perintah menurut cek jendela itu (cadangan)
        self._held: Optional[Tuple[np.ndarray, str, Optional[int]]] = None  # (audio, perintah, potong)
        self._held_left = 0    # sampel hening yang masih ditunggu sebelum perintah dilepas
        self._cut: Optional[int] = None  # sampel akhir wake phrase di segmen berjalan
        self._levels: Optional[List[float]] = []  # RMS potongan awal, untuk peringatan mic terlalu keras
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
        self._check_level(audio)
        was_held = self._held is not None
        for segment in self.segmenter.feed(audio):
            self.stats.segments += 1
            self._segment_ended(segment)
        if was_held and self._held is not None and not self.segmenter.active:
            self._held_left -= len(audio)
            if self._held_left <= 0:
                self._release()
        if self.segmenter.active and not self._armed and self._held is None:
            done = self.segmenter.active_samples
            if done - self._checked >= self.check_samples:
                audio_so_far = self.segmenter.current()
                start = max(0, self._checked - self.overlap_samples)
                window = audio_so_far[start:done]
                self._checked = done
                heard = self._heard(window, offset=start)
                if heard is not None:
                    # Tunggu segmen selesai, lalu ambil perintah utuh
                    self._armed, self._armed_command = True, heard

    def _busy(self) -> bool:
        if self.is_busy():
            self._quiet_since = None
            self.segmenter.reset()
            self._checked, self._armed, self._armed_command, self._held, self._cut = 0, False, "", None, None
            return True
        now = self.clock()
        if self._quiet_since is None:
            self._quiet_since = now
        return now - self._quiet_since < self.cooldown_sec

    def _segment_ended(self, segment: np.ndarray):
        armed, armed_command, checked = self._armed, self._armed_command, self._checked
        self._checked, self._armed, self._armed_command = 0, False, ""
        if self._held is not None:
            # Lanjutan perintah sesudah jeda singkat: transkripsi ulang gabungannya
            audio, command, self._cut = self._held
            self._held = None
            self._wake(self._command(np.concatenate([audio, segment]), fallback=command))
            self._cut = None
            return
        if armed:
            command = self._command(segment, fallback=armed_command)
        else:
            self._cut = None
            start = max(0, checked - self.overlap_samples) if checked else 0
            tail = segment[start:]
            if len(tail) < self.min_check_samples:
                return
            command = self._heard(tail, offset=start)
            if command is None:
                return
            if command and (self.transcribe_command or checked or self._cut is not None):
                # Perintah ikut terucap: ambil dari transkripsi seluruh segmen
                command = self._command(segment, fallback=command)
        cut, self._cut = self._cut, None
        if command and self.continue_samples:
            self._held, self._held_left = (segment, command, cut), self.continue_samples
            return
        self._wake(command)

    def _release(self):
        _, command, _ = self._held
        self._held = None
        self._wake(command)

    def _check_level(self, audio: np.ndarray):
        """Sekali, sesudah ±3 s pertama: peringatkan bila derau mikrofon terlalu tinggi."""
        if self._levels is None or not len(audio):
            return
        centered = audio - audio.mean()
        self._levels.append(float(np.sqrt(np.mean(centered ** 2))))
        if len(self._levels) * len(audio) >= 3 * self.sample_rate:
            level, self._levels = float(np.median(self._levels)), None
            if level > 0.05:
                self.on_warning(
                    f"Volume mikrofon terlalu tinggi (derau ruangan RMS {level:.2f}), jadi \"Oke Miku\" "
                    "sulit dikenali. Turunkan volume input di pengaturan Suara ke sekitar 20-30%.")

    def _heard(self, audio: np.ndarray, offset: int = 0) -> Optional[str]:
        """Cek wake phrase (transcribe, boleh versi murah). offset: posisi audio ini di segmen."""
        text = self._transcribe(self.transcribe, audio)
        if text.strip() and self.on_heard is not None:
            try:
                self.on_heard(text)
            except Exception as e:
                print(f"[Wake] Error: {e}")
        command = match_wake_phrase(text)
        if command is not None and self.wake_end is not None:
            end = self.wake_end()
            self._cut = offset + int(end * self.sample_rate) if end is not None else None
        return command

    def _command(self, segment: np.ndarray, fallback: str) -> str:
        """Perintah sesudah wake phrase dari seluruh segmen (transcribe_command bila ada)."""
        if self._cut is not None and len(segment) - self._cut >= self.min_check_samples:
            # Hanya audio sesudah wake phrase, supaya bahasanya dideteksi dari perintah saja
            text = self._transcribe(self.transcribe_command or self.transcribe, segment[self._cut:])
            command = match_wake_phrase(text)
            return (text.strip() if command is None else command) or fallback
        text = self._transcribe(self.transcribe_command or self.transcribe, segment)
        command = match_wake_phrase(text)
        if command is not None:
            return command
        # Transkripsi lengkap kadang salah menulis wake phrase ("Gameku, putar lagu di Youtube"):
        # ambil mulai dari kata pertama perintah hasil cek
        words = fallback.split()
        start = text.lower().find(words[0].lower()) if words else -1
        return text[start:].strip() if start >= 0 else fallback

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
