"""Putar ulang rekaman uji suara (live_guided.py --record) ke WakeListener dengan pengaturan lain.

Dari root repo, dengan venv aplikasi:
    python experiments/wake_eval/replay.py <hasil.json> <folder_rekaman> [--prompt "Oke Miku."]
        [--no-cut] [--check-lang id]
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from core.voice_input import VoiceInput  # noqa: E402
from core.wake import WakeListener, wake_phrase_end  # noqa: E402

SR = 16000


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("results", type=Path)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--prompt", default="Oke Miku.", help='prompt cek wake; "" = tanpa prompt')
    parser.add_argument("--no-cut", action="store_true", help="perintah dari seluruh segmen, tanpa dipotong")
    parser.add_argument("--check-lang", default="id")
    args = parser.parse_args()
    steps = json.loads(args.results.read_text(encoding="utf-8"))["results"]

    vi = VoiceInput()
    assert vi.initialize(), "Whisper gagal dimuat"
    heard = []

    def check(audio):
        text = vi.transcribe(audio, lang=args.check_lang, beam_size=1, prompt=args.prompt or None,
                             use_initial_prompt=False, word_timestamps=not args.no_cut, verbose_logging=False)
        heard.append(text)
        return text

    def command(audio):
        text = vi.transcribe(audio, languages=["ja", "id"], verbose_logging=False)
        heard.append("[perintah] " + text)
        return text

    ok_pos = ok_neg = n_pos = n_neg = 0
    for step in steps:
        if not step.get("audio"):
            continue
        audio = sf.read(args.folder / step["audio"], dtype="float32")[0]
        audio = np.concatenate([audio, np.zeros(int(1.5 * SR), dtype=np.float32)])
        wakes, heard[:] = [], []
        lst = WakeListener(check, wakes.append, transcribe_command=command, cooldown_sec=0, clock=lambda: 0.0,
                           wake_end=None if args.no_cut else (lambda: wake_phrase_end(vi.last_words)))
        for i in range(0, len(audio), 1600):
            lst.feed(audio[i:i + 1600])
        got = wakes[0] if wakes else None
        if step["expect_wake"]:
            n_pos += 1
            ok = got is not None and step["keyword"].lower() in got.lower()
            ok_pos += ok
        else:
            n_neg += 1
            ok = not wakes
            ok_neg += ok
        print(f"{step['step']:2} {'OK  ' if ok else 'GAGAL'} {step['text'][:36]:36} -> {got!r}  {heard}")
    print(f"\n\"Oke Miku\" {ok_pos}/{n_pos}, kalimat biasa tidak memicu {ok_neg}/{n_neg} "
          f"(prompt {args.prompt!r}, potong perintah: {not args.no_cut})")


if __name__ == "__main__":
    main()
