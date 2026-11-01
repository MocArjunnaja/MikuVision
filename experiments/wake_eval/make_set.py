"""Set uji "Oke Miku" (T2): wake phrase dan kalimat biasa via edge-tts, versi bersih dan mic laptop.

Butuh edge-tts >= 7.3.1 (tidak ada di venv aplikasi), misalnya:
    uv run --no-project --with "edge-tts>=7.3.1" --with soundfile --with scipy \
        python experiments/wake_eval/make_set.py <folder_keluaran>
"""
import asyncio, io, json, sys
from pathlib import Path
import edge_tts, numpy as np, soundfile as sf
from scipy.signal import resample_poly, lfilter

OUT = Path(sys.argv[1])
SR = 16000
# (bahasa, ucapan, kata yang harus ada di perintah sesudah wake phrase; "" = hanya wake phrase)
POSITIVE = [
    ("id", "Oke Miku.", ""),
    ("id", "Oke Miku, buka Notepad.", "notepad"),
    ("id", "Oke Miku, kecilkan volume ke tiga puluh.", "volume"),
    ("id", "Ok Miku.", ""),
    ("id", "Okay Miku, putar lagu di YouTube.", "youtube"),
    ("ja", "オッケー、ミク。", ""),
    ("ja", "オッケー、ミク、メモ帳を開いて。", "メモ帳"),
    ("ja", "オーケー、ミク。", ""),
    ("en", "OK Miku.", ""),
    ("en", "Okay Miku, open YouTube.", "youtube"),
]
# Kalimat biasa, termasuk yang mirip: "oke …", "… Miku …", perintah tanpa wake phrase
NEGATIVE = [
    ("id", "Oke, nanti saja ya."),
    ("id", "Miku lagi nyanyi lagu baru."),
    ("id", "Aku mikir dulu deh, sebentar."),
    ("id", "Oke makasih banyak ya."),
    ("id", "Hatsune Miku itu penyanyi virtual dari Jepang."),
    ("id", "Ok, kita mulai rapatnya sekarang."),
    ("id", "Jangan lupa beli susu nanti sore."),
    ("id", "Buka Notepad."),
    ("id", "Tolong kecilkan volumenya sedikit."),
    ("id", "Hari ini aku belajar fisika dan rapat organisasi."),
    ("id", "Kemarin aku nonton konser Miku di televisi."),
    ("id", "Oke, minggu depan kita ketemu di kampus."),
    ("id", "Tugas basis data dikumpulkan hari Jumat."),
    ("id", "Nanti malam hujan, bawa payung ya."),
    ("ja", "オッケー、わかった。"),
    ("ja", "ミクの新しい曲を聞いた？"),
    ("ja", "初音ミクが大好きです。"),
    ("ja", "メモ帳を開いて。"),
    ("ja", "今日はいい天気ですね。"),
    ("ja", "ちょっと待ってね、今行くから。"),
    ("ja", "オーケー、じゃあまた明日。"),
    ("ja", "明日の会議は十時からです。"),
    ("en", "OK, see you tomorrow."),
    ("en", "Okay, let me check the schedule."),
    ("en", "I like Hatsune Miku songs."),
    ("en", "Can you send me the file later?"),
]
VOICES = {"id": ["id-ID-GadisNeural", "id-ID-ArdiNeural"], "ja": ["ja-JP-NanamiNeural", "ja-JP-KeitaNeural"],
          "en": ["en-US-JennyNeural", "en-US-GuyNeural"]}
rng = np.random.default_rng(0)


def pink(n):
    b = [0.049922035, -0.095993537, 0.050612699, -0.004408786]
    a = [1, -2.494956002, 2.017265875, -0.522189400]
    x = lfilter(b, a, rng.standard_normal(n))
    return (x / np.max(np.abs(x))).astype(np.float32)


def laptop_mic(y, snr_db=12, gain=0.08):
    """Derau pink (kipas/ruangan) + dengung 120 Hz, volume kecil seperti mic laptop."""
    n = pink(len(y)) + 0.002 * np.sin(2 * np.pi * 120 * np.arange(len(y)) / SR)
    p_s = np.mean(y ** 2) or 1e-9
    n *= np.sqrt(p_s / (np.mean(n ** 2) * 10 ** (snr_db / 10)))
    z = (y + n) * gain / max(np.max(np.abs(y + n)), 1e-6)
    return z.astype(np.float32)


async def tts(text, voice):
    buf = b""
    async for c in edge_tts.Communicate(text, voice).stream():
        if c["type"] == "audio":
            buf += c["data"]
    y, sr = sf.read(io.BytesIO(buf), dtype="float32")
    y = y.mean(axis=1) if y.ndim > 1 else y
    return resample_poly(y, SR, sr).astype(np.float32)


async def main():
    (OUT / "clips").mkdir(parents=True, exist_ok=True)
    man = []
    jobs = [("pos", i, lang, text, cmd) for i, (lang, text, cmd) in enumerate(POSITIVE)]
    jobs += [("neg", i, lang, text, None) for i, (lang, text) in enumerate(NEGATIVE)]
    for kind, i, lang, text, cmd in jobs:
        for v, voice in enumerate(VOICES[lang]):
            y = await tts(text, voice)
            pad = lambda s: np.concatenate([np.zeros(int(0.4 * SR)), s, np.zeros(int(0.4 * SR))]).astype(np.float32)
            conds = {"clean": pad(y * 0.5), "laptop": laptop_mic(pad(y))}
            if kind == "pos":
                conds["noisy"] = laptop_mic(pad(y), snr_db=5)
            for cond, sig in conds.items():
                f = f"{kind}_{lang}_{i:02d}_v{v}_{cond}.wav"
                sf.write(OUT / "clips" / f, sig, SR)
                man.append({"file": f, "kind": kind, "lang": lang, "text": text, "command": cmd, "cond": cond})
    # 5 menit derau ruangan tanpa ucapan: Whisper seharusnya tidak pernah jalan
    room = laptop_mic(1e-3 * rng.standard_normal(5 * 60 * SR).astype(np.float32), snr_db=-30, gain=0.01)
    sf.write(OUT / "room_noise_5min.wav", room, SR)
    (OUT / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    print(len(man), "klip")

asyncio.run(main())
