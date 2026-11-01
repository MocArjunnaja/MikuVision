"""Uji "Oke Miku" (T2) dengan WakeListener, webrtcvad, dan Whisper sungguhan (tanpa mikrofon).

Dari root repo, dengan venv aplikasi:
    python experiments/wake_eval/run_eval.py <folder_set> [--beam 1] [--detect-lang id]

- Wake phrase: tiap klip ke pendengar baru; harus memicu tepat sekali, dengan perintahnya.
- Kalimat biasa: tiap klip sendiri, lalu semuanya disambung jadi satu "obrolan" panjang.
- Derau ruangan 5 menit: berapa kali Whisper jalan saat tidak ada yang bicara.
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from core.voice_input import VoiceInput  # noqa: E402
from core.wake import SpeechSegmenter, WakeListener, wake_phrase_end  # noqa: E402

SR = 16000
CHUNK = int(0.1 * SR)  # potongan seukuran callback mikrofon


def run(listener, audio):
    for i in range(0, len(audio), CHUNK):
        listener.feed(audio[i:i + CHUNK])


VAD_MODE = None


WAKE_END = None


def new_listener(transcribe, wakes, transcribe_command=None):
    segmenter = SpeechSegmenter(vad_mode=VAD_MODE) if VAD_MODE is not None else None
    return WakeListener(transcribe, wakes.append, transcribe_command=transcribe_command, wake_end=WAKE_END,
                        cooldown_sec=0, clock=lambda: 0.0, segmenter=segmenter)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("--beam", type=int, default=1)
    parser.add_argument("--no-prompt", action="store_true", help="cek wake tanpa prompt kosakata Whisper")
    parser.add_argument("--wake-prompt", default=None, help='prompt khusus untuk cek wake, misalnya "Oke Miku."')
    parser.add_argument("--cut-command", action="store_true",
                        help="perintah ditranskripsi tanpa wake phrase (dipotong lewat cap waktu kata)")
    parser.add_argument("--vad-mode", type=int, default=None, help="webrtcvad 0-3 (bawaan: dari core/wake.py)")
    parser.add_argument("--detect-lang", default=None,
                        help="bahasa tetap untuk cek wake phrase; perintah tetap dengan deteksi bahasa")
    args = parser.parse_args()
    man = json.loads((args.folder / "manifest.json").read_text(encoding="utf-8"))
    global VAD_MODE
    VAD_MODE = args.vad_mode

    vi = VoiceInput()
    assert vi.initialize(), "Whisper gagal dimuat"
    heard = []

    def transcribe(audio):
        if args.detect_lang:
            text = vi.transcribe(audio, lang=args.detect_lang, beam_size=args.beam,
                                 use_initial_prompt=not args.no_prompt, prompt=args.wake_prompt,
                                 word_timestamps=args.cut_command, verbose_logging=False)
        else:
            text = vi.transcribe(audio, languages=["ja", "id"], beam_size=args.beam, verbose_logging=False)
        heard.append(text)
        return text

    def transcribe_command(audio):
        text = vi.transcribe(audio, languages=["ja", "id"], verbose_logging=False)
        heard.append("[perintah] " + text)
        return text

    command_fn = transcribe_command if args.detect_lang else None
    global WAKE_END
    WAKE_END = (lambda: wake_phrase_end(vi.last_words)) if args.cut_command else None

    tail = np.zeros(int(1.5 * SR), dtype=np.float32)  # hening penutup + jeda tunggu lanjutan perintah
    rows, latencies = {}, []
    misses, false_wakes = [], []
    for item in man:
        audio = np.concatenate([sf.read(args.folder / "clips" / item["file"], dtype="float32")[0], tail])
        wakes = []
        heard.clear()
        lst = new_listener(transcribe, wakes, command_fn)
        started = time.perf_counter()
        run(lst, audio)
        key = (item["kind"], item["cond"])
        row = rows.setdefault(key, {"n": 0, "ok": 0, "cmd_ok": 0, "cmd_n": 0, "calls": 0})
        row["n"] += 1
        row["calls"] += lst.stats.transcriptions
        if item["kind"] == "pos":
            ok = len(wakes) == 1
            row["ok"] += ok
            latencies.append(lst.stats.transcribe_seconds)
            if item["command"]:
                row["cmd_n"] += 1
                row["cmd_ok"] += ok and item["command"].lower() in wakes[0].lower()
            if not ok or (item["command"] and item["command"].lower() not in wakes[0].lower()):
                misses.append((item["file"], wakes, list(heard)))
        else:
            row["ok"] += not wakes
            if wakes:
                false_wakes.append((item["file"], wakes, list(heard)))

    # Semua kalimat biasa disambung jadi satu obrolan, jeda acak 0,2-1,0 s
    rng = np.random.default_rng(1)
    parts = []
    for item in man:
        if item["kind"] == "neg":
            parts += [sf.read(args.folder / "clips" / item["file"], dtype="float32")[0],
                      np.zeros(int(rng.uniform(0.2, 1.0) * SR), dtype=np.float32)]
    talk = np.concatenate(parts)
    wakes = []
    heard.clear()
    lst = new_listener(transcribe, wakes, command_fn)
    started = time.perf_counter()
    run(lst, talk)
    talk_stats = {"minutes": round(len(talk) / SR / 60, 1), "false_wakes": len(wakes),
                  "transcriptions": lst.stats.transcriptions, "segments": lst.stats.segments,
                  "whisper_seconds": round(lst.stats.transcribe_seconds, 1),
                  "wall_seconds": round(time.perf_counter() - started, 1)}
    if wakes:
        false_wakes.append(("obrolan", wakes, [h for h in heard if "miku" in h.lower() or "ミク" in h]))

    room = sf.read(args.folder / "room_noise_5min.wav", dtype="float32")[0]
    wakes = []
    lst = new_listener(transcribe, wakes, command_fn)
    run(lst, room)
    room_stats = {"minutes": round(len(room) / SR / 60, 1), "segments": lst.stats.segments,
                  "transcriptions": lst.stats.transcriptions, "wakes": len(wakes)}

    print(f"\n== beam {args.beam}, cek wake: {args.detect_lang or 'deteksi bahasa'}, VAD {args.vad_mode or 'bawaan'}"
          f"{', tanpa prompt' if args.no_prompt else ''}"
          f"{f', prompt {args.wake_prompt!r}' if args.wake_prompt else ''}"
          f"{', perintah dipotong' if args.cut_command else ''}")
    for (kind, cond), r in sorted(rows.items()):
        extra = f", perintah {r['cmd_ok']}/{r['cmd_n']}" if r["cmd_n"] else ""
        label = "terpicu tepat sekali" if kind == "pos" else "tidak terpicu"
        print(f"{kind:4} {cond:7} {label} {r['ok']}/{r['n']}{extra}, panggilan Whisper {r['calls']}")
    print(f"Whisper per klip wake phrase: median {statistics.median(latencies):.2f} s")
    print("obrolan:", json.dumps(talk_stats))
    print("derau ruangan:", json.dumps(room_stats))
    for f, w, h in misses:
        print("  MISS", f, w, h)
    for f, w, h in false_wakes:
        print("  FALSE", f, w, h)


if __name__ == "__main__":
    main()
