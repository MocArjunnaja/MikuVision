"""Uji "Oke Miku" dengan suara sungguhan: skrip memberi aba-aba, user mengucapkannya.

Tidak ada aksi yang dijalankan (Notepad tidak dibuka); hanya dicatat apakah wake phrase
terdengar, perintah apa yang tertangkap, dan apa yang ditulis Whisper. Audio hanya disimpan bila
--record diberikan (satu WAV per aba-aba, untuk diputar ulang dengan replay.py).
Dari root repo, dengan venv aplikasi, di terminal (butuh Enter dari user):
    python experiments/wake_eval/live_guided.py [--out hasil.json] [--record folder]
"""
import argparse
import json
import sys
import threading
import time

import numpy as np

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from config import WAKE_CHECK_LANGUAGE, WAKE_CHECK_PROMPT  # noqa: E402
from core.voice_input import VoiceInput  # noqa: E402
from core.wake import WakeListener, wake_phrase_end  # noqa: E402

SR = 16000
# (aba-aba, wake diharapkan, kata yang harus ada di perintah)
STEPS = [
    ("Oke Miku", True, ""),
    ("Oke Miku", True, ""),
    ("Oke Miku", True, ""),
    ("Oke Miku", True, ""),
    ("Oke Miku", True, ""),
    ("Oke Miku, buka Notepad", True, "notepad"),
    ("Oke Miku, kecilkan volume ke tiga puluh", True, "volume"),
    ("Oke Miku, putar lagu di YouTube", True, "youtube"),
    ("オッケー、ミク、メモ帳を開いて", True, "メモ帳"),
    ("Oke Miku  (diam 2 detik)  buka Notepad", True, ""),
    ("Oke, nanti saja ya", False, ""),
    ("Miku lagi nyanyi lagu baru", False, ""),
    ("Hari ini aku belajar fisika dan rapat", False, ""),
    ("Aku mikir dulu deh, sebentar", False, ""),
    ("Hatsune Miku itu penyanyi virtual", False, ""),
]
WAIT_SEC = 8.0


def mic_level(seconds=3.0) -> float:
    import sounddevice as sd
    audio = sd.rec(int(seconds * SR), samplerate=SR, channels=1, dtype="float32")
    sd.wait()
    audio = audio[:, 0] - audio[:, 0].mean()
    return float(np.sqrt(np.mean(audio ** 2)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None)
    parser.add_argument("--record", default=None, help="folder untuk menyimpan audio tiap aba-aba (WAV)")
    args = parser.parse_args()

    print("\n=== Uji \"Oke Miku\" dengan suaramu ===")
    print("Memuat Whisper...", flush=True)
    vi = VoiceInput()
    assert vi.initialize(), "Whisper gagal dimuat"

    while True:
        print("\nJangan bicara 3 detik, mengukur derau ruangan...", flush=True)
        level = mic_level()
        print(f"Derau ruangan: RMS {level:.4f}", flush=True)
        if level < 0.05:
            print("Level mic wajar.")
            break
        print("Mic terlalu keras (derau ruangan seharusnya di bawah 0,05). Turunkan volume input di\n"
              "Pengaturan Suara -> Input (sekitar 20-30%), lalu tekan Enter untuk mengukur lagi,\n"
              "atau ketik 'lanjut' lalu Enter untuk tetap menguji dengan level ini.")
        if input("> ").strip().lower() == "lanjut":
            break

    heard, wakes = [], []
    event = threading.Event()

    def check(audio):
        text = vi.transcribe(audio, lang=WAKE_CHECK_LANGUAGE, beam_size=1, prompt=WAKE_CHECK_PROMPT,
                             word_timestamps=True, verbose_logging=False)
        heard.append(text)
        return text

    def command(audio):
        text = vi.transcribe(audio, languages=["ja", "id"], verbose_logging=False)
        heard.append("[perintah] " + text)
        return text

    def on_wake(cmd):
        wakes.append((time.monotonic(), cmd))
        event.set()

    lst = WakeListener(check, on_wake, transcribe_command=command,
                       wake_end=lambda: wake_phrase_end(vi.last_words))
    recorded = []
    if args.record:
        import soundfile as sf
        from pathlib import Path
        record_dir = Path(args.record)
        record_dir.mkdir(parents=True, exist_ok=True)
        listener_feed = lst.feed

        def feed(chunk):  # salin audio mikrofon yang masuk ke pendengar
            recorded.append(chunk)
            listener_feed(chunk)

        lst.feed = feed
        print(f"Audio tiap aba-aba disimpan di {record_dir}")
    error = lst.start()
    assert error is None, error

    results = []
    print(f"\nAkan ada {len(STEPS)} aba-aba. Ucapkan kalimatnya dengan suara biasa, sekali saja,")
    print(f"begitu muncul 'Bicara sekarang'. Tiap aba-aba ditunggu {WAIT_SEC:.0f} detik.")
    input("Tekan Enter untuk mulai... ")
    for i, (text, expect_wake, keyword) in enumerate(STEPS, 1):
        time.sleep(1.0)
        heard.clear()
        wakes.clear()
        event.clear()
        recorded.clear()
        print(f"\n[{i}/{len(STEPS)}] Ucapkan:  {text}", flush=True)
        time.sleep(1.5)
        print("   >> Bicara sekarang", flush=True)
        started = time.monotonic()
        event.wait(WAIT_SEC)
        if not expect_wake:
            time.sleep(max(0.0, started + WAIT_SEC - time.monotonic()))
        got = wakes[0][1] if wakes else None
        if expect_wake:
            ok = got is not None and keyword.lower() in got.lower()
        else:
            ok = not wakes
        mark = "OK  " if ok else "GAGAL"
        detail = f"perintah: {got!r}" if got is not None else "tidak terpicu"
        print(f"   {mark} {detail}")
        print(f"   Whisper mendengar: {heard}", flush=True)
        audio_file = None
        if args.record and recorded:
            time.sleep(0.5)  # sisa audio yang masih di antrean
            audio_file = f"step{i:02d}.wav"
            sf.write(record_dir / audio_file, np.concatenate(list(recorded)), SR)
        results.append({"step": i, "text": text, "expect_wake": expect_wake, "keyword": keyword,
                        "audio": audio_file,
                        "ok": ok, "command": got, "seconds_after_prompt": round(wakes[0][0] - started, 1)
                        if wakes else None, "heard": list(heard)})

    lst.stop()
    pos = [r for r in results if r["expect_wake"]]
    neg = [r for r in results if not r["expect_wake"]]
    print("\n=== Hasil ===")
    print(f"\"Oke Miku\" (dengan/tanpa perintah): {sum(r['ok'] for r in pos)}/{len(pos)}")
    print(f"Kalimat biasa tidak memicu: {sum(r['ok'] for r in neg)}/{len(neg)}")
    print(f"Derau ruangan: RMS {level:.4f}")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"room_rms": level, "results": results}, f, ensure_ascii=False, indent=1)
    print("Selesai. Terima kasih!")


if __name__ == "__main__":
    main()
