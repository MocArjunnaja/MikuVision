"""Keyakinan Whisper pada wake phrase: rekaman "Oke Miku" sungguhan vs audio yang tidak boleh memicu.

Memutar ulang rekaman ke WakeListener dengan pengaturan aplikasi, lalu untuk setiap cek yang
cocok dengan pola wake phrase mencatat peluang terendah Whisper di kata-kata wake phrase
(wake_phrase_confidence). Dipakai untuk memilih WAKE_MIN_CONFIDENCE.
Dari root repo, dengan venv aplikasi:
    python experiments/wake_eval/confidence_scan.py --voice hasil.json folder_rekaman --noise musik.wav [--runs 2]
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from config import WAKE_CHECK_LANGUAGE, WAKE_CHECK_PROMPT  # noqa: E402
from core.voice_input import VoiceInput  # noqa: E402
from core.wake import WakeListener, match_wake_phrase, wake_phrase_confidence, wake_phrase_end  # noqa: E402

SR = 16000


def scan(vi, audio):
    """Semua cek yang cocok dengan pola: [(teks, keyakinan)]; plus jumlah cek."""
    matches, checks = [], [0]

    def check(chunk):
        text = vi.transcribe(chunk, lang=WAKE_CHECK_LANGUAGE, beam_size=1, prompt=WAKE_CHECK_PROMPT,
                             word_timestamps=True, verbose_logging=False)
        checks[0] += 1
        if match_wake_phrase(text) is not None:
            matches.append((text, wake_phrase_confidence(vi.last_words)))
        return text

    lst = WakeListener(check, lambda command: None, cooldown_sec=0, clock=lambda: 0.0,
                       transcribe_command=lambda a: vi.transcribe(a, languages=["ja", "id"], verbose_logging=False),
                       wake_end=lambda: wake_phrase_end(vi.last_words), on_warning=lambda m: None)
    audio = np.concatenate([audio, np.zeros(int(1.5 * SR), dtype=np.float32)])
    for i in range(0, len(audio), 1600):
        lst.feed(audio[i:i + 1600])
    return matches, checks[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--voice", nargs=2, metavar=("HASIL_JSON", "FOLDER"), action="append", default=[])
    parser.add_argument("--noise", action="append", default=[], help="WAV yang tidak boleh memicu (musik, video)")
    parser.add_argument("--runs", type=int, default=1)
    args = parser.parse_args()

    vi = VoiceInput()
    assert vi.initialize(), "Whisper gagal dimuat"
    positives, negatives = [], []
    for results, folder in args.voice:
        for step in json.loads(Path(results).read_text(encoding="utf-8"))["results"]:
            if not step.get("audio"):
                continue
            audio = sf.read(Path(folder) / step["audio"], dtype="float32")[0]
            for _ in range(args.runs):
                matches, _ = scan(vi, audio)
                bucket = positives if step["expect_wake"] else negatives
                bucket += [(f"{Path(folder).name}/{step['audio']}", t, c) for t, c in matches]
                if step["expect_wake"] and not matches:
                    print(f"  (tidak cocok) {step['audio']} {step['text']}")
    for path in args.noise:
        audio = sf.read(path, dtype="float32")[0]
        for _ in range(args.runs):
            matches, checks = scan(vi, audio)
            negatives += [(Path(path).name, t, c) for t, c in matches]
            print(f"{Path(path).name}: {len(audio) / SR / 60:.1f} menit, {checks} cek, {len(matches)} cocok pola")

    print("\nCocok pola pada \"Oke Miku\" sungguhan:")
    for name, text, conf in sorted(positives, key=lambda r: r[2] if r[2] is not None else -1):
        print(f"  {conf if conf is None else round(conf, 3)!s:6}  {name}  {text!r}")
    print("\nCocok pola pada audio yang tidak boleh memicu:")
    for name, text, conf in sorted(negatives, key=lambda r: r[2] if r[2] is not None else -1):
        print(f"  {conf if conf is None else round(conf, 3)!s:6}  {name}  {text!r}")
    pos = [c for _, _, c in positives if c is not None]
    neg = [c for _, _, c in negatives if c is not None]
    if pos:
        print(f"\nPositif: min {min(pos):.3f}, median {float(np.median(pos)):.3f}; "
              f"negatif: {'maks %.3f' % max(neg) if neg else 'tidak ada'}")


if __name__ == "__main__":
    main()
