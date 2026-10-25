"""Set uji STT: frasa perintah MikuVision via edge-tts, versi bersih dan versi mic laptop (derau + volume kecil)."""
import asyncio, io, json, sys
from pathlib import Path
import edge_tts, numpy as np, soundfile as sf
from scipy.signal import resample_poly, lfilter

OUT = Path(sys.argv[1])
SR = 16000
PHRASES = [
    ("id", "Buka Notepad"),
    ("id", "Tolong buka YouTube dan cari lagu Hatsune Miku"),
    ("id", "Atur volume ke tiga puluh persen"),
    ("id", "Kecilkan volumenya sedikit"),
    ("id", "Tutup Google Chrome"),
    ("id", "Ingat bahwa ulang tahunku tanggal dua belas Mei"),
    ("id", "Buka folder Download"),
    ("id", "Putar lagu di Spotify"),
    ("id", "Kirim pesan WhatsApp ke Budi"),
    ("id", "Buat dokumen Word baru"),
    ("id", "Sekarang jam berapa"),
    ("id", "Matikan suaranya"),
    ("id", "Ya, lanjutkan"),
    ("id", "Jangan, batalkan"),
    ("ja", "メモ帳を開いて"),
    ("ja", "ユーチューブで初音ミクの歌を検索して"),
    ("ja", "ダウンロードフォルダを開いて"),
    ("ja", "今の音量はいくつ"),
    ("ja", "グーグルクロームを閉じて"),
    ("ja", "明日の天気を教えて"),
    ("ja", "ワードで新しい文書を作って"),
    ("ja", "ミュートにして"),
    ("ja", "はい、お願い"),
    ("ja", "いいえ、やめて"),
]
VOICES = {"id": ["id-ID-GadisNeural", "id-ID-ArdiNeural"], "ja": ["ja-JP-NanamiNeural", "ja-JP-KeitaNeural"]}
rng = np.random.default_rng(0)

def pink(n):
    # derau pink (kipas/ruangan) lewat filter Voss sederhana
    b = [0.049922035, -0.095993537, 0.050612699, -0.004408786]
    a = [1, -2.494956002, 2.017265875, -0.522189400]
    x = lfilter(b, a, rng.standard_normal(n))
    return (x / np.max(np.abs(x))).astype(np.float32)

def laptop_mic(y, snr_db=12, gain=0.08):
    y = np.concatenate([np.zeros(int(0.4 * SR)), y, np.zeros(int(0.6 * SR))]).astype(np.float32)
    n = pink(len(y)) + 0.002 * np.sin(2 * np.pi * 120 * np.arange(len(y)) / SR)  # dengung 120 Hz
    p_s = np.mean(y ** 2); p_n = np.mean(n ** 2)
    n *= np.sqrt(p_s / (p_n * 10 ** (snr_db / 10)))
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
    for i, (lang, text) in enumerate(PHRASES):
        voice = VOICES[lang][i % 2]
        y = await tts(text, voice)
        clean = np.concatenate([np.zeros(int(0.3 * SR)), y * 0.5, np.zeros(int(0.5 * SR))]).astype(np.float32)
        for cond, sig in (("clean", clean), ("noisy", laptop_mic(y))):
            f = f"{lang}_{i:02d}_{cond}.wav"
            sf.write(OUT / "clips" / f, sig, SR)
            man.append({"file": f, "lang": lang, "ref": text, "cond": cond})
    for k in range(6):  # tanpa ucapan: harus menghasilkan teks kosong
        sig = laptop_mic(np.zeros(int(2.5 * SR)) + 1e-4 * rng.standard_normal(int(2.5 * SR)), snr_db=-20, gain=0.03 * (k + 1))
        f = f"noise_{k}.wav"
        sf.write(OUT / "clips" / f, sig, SR)
        man.append({"file": f, "lang": None, "ref": "", "cond": "noise"})
    (OUT / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    print(len(man), "clips")

asyncio.run(main())
