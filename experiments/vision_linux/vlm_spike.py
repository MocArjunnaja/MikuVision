"""
Fase 0 Linux - qwen3-vl memilih elemen (Set-of-Mark) dan membaca layar.

Input: folder hasil atspi_spike.py. Model diberi tujuan + elemen bernomor dan
harus menjawab nomor elemen yang benar.
Mode:
  text   - hanya daftar elemen AT-SPI
  image  - hanya gambar Set-of-Mark
  both   - gambar + daftar
  read   - jelaskan screenshot (tanpa nomor): apakah teks penting terbaca?
Pakai (venv MikuVision): python vlm_spike.py <folder_atspi_spike> <model> <mode> [runs]
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

# Elemen yang benar: ("name", nama) atau ("nth", tipe, urutan di antara elemen TANPA nama
# bertipe itu), karena nomor elemen tanpa nama bisa bergeser antar-pengambilan
GOALS = [
    ("calculator", "Tekan angka 7", ("name", "7")),
    ("calculator", "Tekan tombol tambah", ("name", "+")),
    ("calculator", "Hitung akar kuadrat", ("name", "√")),
    ("calculator", "Batalkan langkah terakhir (undo)", ("name", "Undo")),
    ("calculator", "電卓で8を押して", ("name", "8")),
    ("text_editor", "Buka menu File", ("name", "File")),
    ("text_editor", "検索メニューを開いて", ("name", "Search")),
    ("text_editor", "Simpan dokumen lewat ikon simpan di toolbar", ("nth", "push button", 3)),
    ("text_editor", "Buat dokumen baru lewat ikon di toolbar", ("nth", "push button", 1)),
    ("text_editor", "Klik area teks untuk mulai mengetik", ("nth", "text", 1)),
    ("settings_sound", "Buka tab Input (mikrofon)", ("name", "Input")),
    ("settings_sound", "Putar suara tes", ("name", "Test sound")),
    ("settings_sound", "アプリごとの音量を見たい", ("name", "Applications")),
    ("settings_sound", "Bisukan speaker dengan tombol ikon speaker di atas slider volume", ("nth", "toggle button", 1)),
    ("settings_sound", "Geser volume output", ("nth", "slider", 1)),
    ("nemo", "Buka folder Downloads", ("name", "Downloads")),
    ("nemo", "ゴミ箱を開いて", ("name", "Trash")),
    ("nemo", "Buka menu Bookmarks", ("name", "Bookmarks")),
]

# (jendela, pertanyaan, kata yang harus muncul di jawaban)
READ = [
    ("nemo", "List the file and folder names shown in the main area of this file manager.",
     ("catatan_kuliah", "jadwal", "foto_liburan", "laporan", "tugas")),
    ("settings_sound", "What is the current output volume shown on this screen? Answer briefly.", ("50",)),
    ("calculator", "What application is this and which buttons does it have? Answer briefly.",
     ("calculator", "√", "π")),
]

PROMPT = (
    "You control a Linux desktop. Elements on screen are marked with numbers. "
    "Goal: {goal}\n{elements}"
    'Answer ONLY with JSON: {{"element": <number>}} for the element to click.'
)


def image_b64(path: Path, max_side=1280) -> str:
    img = Image.open(path)
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def expected_numbers(elements, rule):
    if rule[0] == "name":
        return {i for i, e in enumerate(elements, 1) if e["name"] == rule[1]}
    _, kind, nth = rule
    unnamed = [i for i, e in enumerate(elements, 1) if e["type"] == kind and not e["name"].strip()]
    return {unnamed[nth - 1]} if len(unnamed) >= nth else set()


def pick(client, model, folder, mode, runs):
    correct, latencies, rows = 0, [], []
    for window, goal, rule in GOALS:
        elements = json.loads((folder / f"{window}_elements.json").read_text(encoding="utf-8"))
        expected = expected_numbers(elements, rule)
        assert expected, f"{window}: {rule} tidak ada di daftar elemen"
        listing = ""
        if mode in ("text", "both"):
            listing = "Elements:\n" + "\n".join(f"{i}: {e['type']} '{e['name']}'" for i, e in enumerate(elements, 1)) + "\n"
        message = {"role": "user", "content": PROMPT.format(goal=goal, elements=listing)}
        if mode in ("image", "both"):
            message["images"] = [image_b64(folder / f"{window}_som.png")]
        hits, answers = 0, []
        for _ in range(runs):
            t0 = time.time()
            reply = client.chat(model=model, messages=[message],
                                options={"temperature": 0.2, "num_predict": 40, "num_ctx": 8192})
            latencies.append(time.time() - t0)
            match = re.search(r'"element"\s*:\s*"?(\d+)', reply.message.content or "")
            answer = int(match.group(1)) if match else None
            answers.append(answer)
            hits += answer in expected
        correct += hits
        rows.append(f"  {goal[:44]:46} {hits}/{runs}  jawab {answers} benar {sorted(expected)}")
    return correct, len(GOALS) * runs, latencies, rows


def read(client, model, folder, runs):
    correct, latencies, rows = 0, [], []
    for window, question, words in READ:
        message = {"role": "user", "content": question, "images": [image_b64(folder / f"{window}.png")]}
        found = []
        for _ in range(runs):
            t0 = time.time()
            reply = client.chat(model=model, messages=[message],
                                options={"temperature": 0.2, "num_predict": 200, "num_ctx": 8192})
            latencies.append(time.time() - t0)
            text = (reply.message.content or "").lower()
            found.append(sum(w.lower() in text for w in words))
        correct += sum(found)
        rows.append(f"  {window:16} kata ditemukan {found} dari {len(words)} | {text[:110]!r}")
    return correct, sum(len(w) for _, _, w in READ) * runs, latencies, rows


def main(folder: Path, model: str, mode: str, runs: int):
    client = Client(timeout=180)
    if mode == "read":
        correct, total, latencies, rows = read(client, model, folder, runs)
    else:
        correct, total, latencies, rows = pick(client, model, folder, mode, runs)
    vram = next((m["size_vram"] for m in client.ps()["models"] if m["model"] == model), 0)
    print(f"{model} [{mode}] akurasi {correct}/{total} | latensi median {statistics.median(latencies):.2f} s "
          f"| VRAM model {vram / 1e9:.1f} GB")
    print("\n".join(rows))


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 3)
