"""Pendengar "Oke Miku" di mikrofon sungguhan selama beberapa menit (audio tidak disimpan kecuali --record).

Mengukur berapa segmen ucapan dan panggilan Whisper yang terjadi di ruangan nyata, beban CPU
proses ini, dan pemakaian GPU. Pengaturannya sama dengan mode suara (bahasa, prompt, dan
pemotongan perintah dari config.py). Setiap "Oke Miku" dan setiap ucapan lain yang terdengar
dicetak dengan jamnya; dengan musik atau video diputar, setiap "Oke Miku" berarti pemicu palsu.
--record menyimpan seluruh audio mikrofon ke satu WAV (16 kHz), untuk diputar ulang offline.
Dari root repo, dengan venv aplikasi:
    python experiments/wake_eval/live_idle.py [--minutes 5] [--out hasil.json] [--record audio.wav]
"""
import argparse
import json
import statistics
import subprocess
import sys
import time

import psutil

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from config import WAKE_CHECK_LANGUAGE, WAKE_CHECK_PROMPT  # noqa: E402
from core.voice_input import VoiceInput  # noqa: E402
from core.wake import WakeListener, wake_phrase_end  # noqa: E402


def gpu_utilization() -> int:
    out = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True).stdout.strip()
    return int(out.splitlines()[0]) if out else -1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=float, default=5)
    parser.add_argument("--out", default=None, help="simpan yang terdengar dan pemicunya ke JSON")
    parser.add_argument("--record", default=None, help="simpan seluruh audio mikrofon ke WAV ini")
    args = parser.parse_args()

    vi = VoiceInput()
    assert vi.initialize(), "Whisper gagal dimuat"
    started = time.time()
    heard, wakes = [], []

    def stamp() -> str:
        return f"{(time.time() - started) / 60:5.1f} mnt"

    def on_heard(text):
        heard.append({"minute": round((time.time() - started) / 60, 2), "text": text})
        print(f"[{stamp()}] terdengar: {text!r}", flush=True)

    def on_wake(command):
        wakes.append({"minute": round((time.time() - started) / 60, 2), "command": command,
                      "heard": heard[-1]["text"] if heard else ""})
        print(f"[{stamp()}] >>> OKE MIKU terpicu, perintah: {command!r}", flush=True)

    lst = WakeListener(
        lambda audio: vi.transcribe(audio, lang=WAKE_CHECK_LANGUAGE, beam_size=1, prompt=WAKE_CHECK_PROMPT,
                                    word_timestamps=True, verbose_logging=False),
        on_wake,
        transcribe_command=lambda audio: vi.transcribe(audio, languages=["ja", "id"], verbose_logging=False),
        wake_end=lambda: wake_phrase_end(vi.last_words),
        on_heard=on_heard,
    )
    recorded = []
    if args.record:
        listener_feed = lst.feed

        def feed(chunk):  # salin audio mikrofon yang masuk ke pendengar
            recorded.append(chunk)
            listener_feed(chunk)

        lst.feed = feed
    process = psutil.Process()
    error = lst.start()
    assert error is None, error
    process.cpu_percent()
    gpu, end = [], time.time() + args.minutes * 60
    print(f"Mendengarkan {args.minutes} menit...", flush=True)
    while time.time() < end:
        time.sleep(5)
        gpu.append(gpu_utilization())
    cpu = process.cpu_percent() / psutil.cpu_count()
    lst.stop()
    if args.record and recorded:
        import numpy as np
        import soundfile as sf
        sf.write(args.record, np.concatenate(recorded), 16000, subtype="PCM_16")
        print(f"Audio disimpan: {args.record}")
    s = lst.stats
    summary = {"minutes": args.minutes, "segments": s.segments, "transcriptions": s.transcriptions,
               "whisper_seconds": round(s.transcribe_seconds, 1), "wakes": s.wakes,
               "cpu_percent": round(cpu, 1), "gpu_median": statistics.median(gpu), "gpu_max": max(gpu)}
    print(f"menit {args.minutes}, segmen {s.segments}, Whisper {s.transcriptions}x ({s.transcribe_seconds:.1f} s), "
          f"wake {s.wakes}, CPU proses {cpu:.1f}% dari semua core, "
          f"GPU median {statistics.median(gpu)}% (maks {max(gpu)}%)")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"summary": summary, "wakes": wakes, "heard": heard}, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
