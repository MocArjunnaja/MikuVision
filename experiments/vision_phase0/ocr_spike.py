"""
Fase 0 - spike OCR Windows (winrt) pada screenshot jendela uji.

Mengukur latensi dan seberapa banyak nama elemen UIA yang juga terbaca OCR
(OCR berguna untuk teks yang tidak ada di pohon UIA: game, gambar, canvas).

Pakai: python ocr_spike.py <folder_output_uia_spike> calculator settings_bluetooth
"""

import asyncio
import json
import sys
import time
from pathlib import Path

from winrt.windows.graphics.imaging import BitmapDecoder
from winrt.windows.media.ocr import OcrEngine
from winrt.windows.storage import FileAccessMode, StorageFile


async def ocr_file(engine, path: Path):
    file = await StorageFile.get_file_from_path_async(str(path.resolve()))
    stream = await file.open_async(FileAccessMode.READ)
    bitmap = await (await BitmapDecoder.create_async(stream)).get_software_bitmap_async()
    t0 = time.time()
    result = await engine.recognize_async(bitmap)
    words = [w.text for line in result.lines for w in line.words]
    return words, time.time() - t0


async def main(folder: Path, labels):
    engine = OcrEngine.try_create_from_user_profile_languages()
    print("OCR language:", engine.recognizer_language.language_tag)
    for label in labels:
        words, seconds = await ocr_file(engine, folder / f"{label}.png")
        names = json.loads((folder / f"{label}_elements.json").read_text(encoding="utf-8"))
        text = " ".join(words).lower()
        visible = [e["name"] for e in names if e["name"] and len(e["name"]) <= 20]
        found = [n for n in visible if n.lower() in text]
        print(f"{label}: {len(words)} kata OCR, {seconds:.2f} s | nama UIA pendek yang juga terbaca OCR: "
              f"{len(found)}/{len(visible)} | contoh OCR: {' '.join(words[:25])}")


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1]), sys.argv[2:]))
