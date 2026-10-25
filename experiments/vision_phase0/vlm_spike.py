"""
Fase 0 - spike pemilihan elemen (Set-of-Mark).

Model diberi tujuan + elemen bernomor dan harus menjawab nomor elemen yang benar.
Mode:
  text   - hanya daftar elemen UIA (model teks biasa, tanpa visi)
  image  - hanya gambar Set-of-Mark
  both   - gambar + daftar
Pakai: python vlm_spike.py <folder_uia_spike> <model> <mode> [runs]
"""

import base64
import io
import json
import re
import statistics
import sys
import time
from pathlib import Path

from ollama import Client
from PIL import Image

# (jendela, tujuan, nomor elemen yang dianggap benar)
GOALS = [
    ("calculator", "Tekan angka 7", {29}),
    ("calculator", "Tekan tombol tambah", {20}),
    ("calculator", "Hapus semua angka di layar (C)", {12}),
    ("calculator", "Lihat riwayat perhitungan", {34}),
    ("calculator", "Perkecil (minimize) jendela", {1}),
    ("calculator", "Hitung akar kuadrat", {16}),
    ("calculator", "電卓で8を押して", {30}),
    ("settings_bluetooth", "Buka pengaturan suara", {31, 32}),
    ("settings_bluetooth", "Tambahkan perangkat Bluetooth baru", {24}),
    ("settings_bluetooth", "Buka Windows Update", {19}),
    ("settings_bluetooth", "Kembali ke halaman sebelumnya", {6}),
    ("settings_bluetooth", "Cari sebuah pengaturan", {4, 5}),
    ("settings_bluetooth", "ディスプレイの設定を開いて", {33, 34}),
    ("settings_bluetooth", "Buka bagian privasi & keamanan", {18}),
    ("settings_bluetooth", "Tutup jendela Settings", {3}),
]

PROMPT = (
    "You control a Windows PC. Elements on screen are marked with numbers. "
    "Goal: {goal}\n{elements}"
    'Answer ONLY with JSON: {{"element": <number>}} for the element to click.'
)


def image_b64(path: Path, max_side=1024) -> str:
    img = Image.open(path)
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def main(folder: Path, model: str, mode: str, runs: int):
    client = Client(timeout=180)
    correct, latencies, rows = 0, [], []
    for window, goal, expected in GOALS:
        elements = json.loads((folder / f"{window}_elements.json").read_text(encoding="utf-8"))
        listing = ""
        if mode in ("text", "both"):
            listing = "Elements:\n" + "\n".join(f"{i}: {e['type']} '{e['name']}'" for i, e in enumerate(elements, 1)) + "\n"
        message = {"role": "user", "content": PROMPT.format(goal=goal, elements=listing)}
        if mode in ("image", "both"):
            message["images"] = [image_b64(folder / f"{window}_som.png")]
        hits = 0
        for _ in range(runs):
            t0 = time.time()
            reply = client.chat(model=model, messages=[message], options={"temperature": 0.2, "num_predict": 40, "num_ctx": 8192})
            latencies.append(time.time() - t0)
            # Model visi sering menulis angka sebagai string: {"element": "20"}
            match = re.search(r'"element"\s*:\s*"?(\d+)', reply.message.content or "")
            answer = int(match.group(1)) if match else None
            hits += answer in expected
        correct += hits
        rows.append(f"  {goal[:34]:36} {hits}/{runs}")
    total = len(GOALS) * runs
    vram = next((m["size_vram"] for m in client.ps()["models"] if m["model"] == model), 0)
    print(f"{model} [{mode}] akurasi {correct}/{total} | latensi median {statistics.median(latencies):.2f} s "
          f"| VRAM model {vram / 1e9:.1f} GB")
    print("\n".join(rows))


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 3)
