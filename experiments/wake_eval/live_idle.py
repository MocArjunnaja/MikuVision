"""Pendengar "Oke Miku" di mikrofon sungguhan selama beberapa menit (audio tidak disimpan).

Mengukur berapa segmen ucapan dan panggilan Whisper yang terjadi di ruangan nyata, beban CPU
proses ini, dan pemakaian GPU. Setiap "Oke Miku" yang terdengar dicetak dengan jamnya.
Dari root repo, dengan venv aplikasi:
    python experiments/wake_eval/live_idle.py [--minutes 5] [--check-lang id]
"""
import argparse
import statistics
import subprocess
import sys
import time

import psutil

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from core.voice_input import VoiceInput  # noqa: E402
from core.wake import WakeListener  # noqa: E402


def gpu_utilization() -> int:
    out = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True).stdout.strip()
    return int(out.splitlines()[0]) if out else -1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=float, default=5)
    parser.add_argument("--check-lang", default="id")
    args = parser.parse_args()

    vi = VoiceInput()
    assert vi.initialize(), "Whisper gagal dimuat"
    lst = WakeListener(
        lambda audio: vi.transcribe(audio, lang=args.check_lang, beam_size=1, verbose_logging=False),
        lambda command: print(f"[{time.strftime('%H:%M:%S')}] Oke Miku! perintah: {command!r}", flush=True),
        transcribe_command=lambda audio: vi.transcribe(audio, languages=["ja", "id"], verbose_logging=False),
    )
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
    s = lst.stats
    print(f"menit {args.minutes}, segmen {s.segments}, Whisper {s.transcriptions}x ({s.transcribe_seconds:.1f} s), "
          f"wake {s.wakes}, CPU proses {cpu:.1f}% dari semua core, "
          f"GPU median {statistics.median(gpu)}% (maks {max(gpu)}%)")


if __name__ == "__main__":
    main()
