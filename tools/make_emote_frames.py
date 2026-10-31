"""
Buat frame emosi Miku yang belum punya gambar sendiri (sad, annoyed, embarrassed,
confused, thinking) dari frame yang sudah ada di sprite sheet: ekspresi wajah diubah
beberapa piksel, lalu diberi tanda emote (air mata, 💢, ?, ..., keringat, rona pipi).

Hasilnya ditulis ke sel kosong di sheet (baris 6, indeks NEW_CELLS). Frame dasar
tidak diubah, jadi script ini aman dijalankan ulang.

    python tools/make_emote_frames.py --preview preview.png   # lihat dulu, sheet tidak diubah
    python tools/make_emote_frames.py                         # tulis ke sheet

Satuan koordinat: "piksel seni". Sheet di-upscale 3x, jadi frame 177x213 = 59x71 piksel seni.
"""

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SHEET = ROOT / "assets" / "avatar" / "miku_smart_sheet.png"
FRAME_W, FRAME_H, COLS, SCALE = 177, 213, 20, 3

# Warna dari palet sheet, ditambah biru air mata dan merah muda rona pipi
DARK = (27, 29, 34, 255)
BROWN = (91, 48, 37, 255)
RED = (204, 36, 53, 255)
WHITE = (255, 255, 255, 255)
SKIN = (253, 230, 211, 255)
TEAR = (150, 210, 255, 255)
TEAR_EDGE = (60, 130, 210, 255)
BLUSH = (244, 150, 160, 255)

# Pola piksel: huruf -> warna, "." = tidak digambar
PATTERNS = {
    "frown": ([".BBB.",
               "B...B"], {"B": BROWN}),
    "pout": ([".B.",
              "B.B"], {"B": BROWN}),
    "brow_sad_l": (["..DD",
                    "DD.."], {"D": DARK}),
    "brow_sad_r": (["DD..",
                    "..DD"], {"D": DARK}),
    "brow_angry_l": (["DD..",
                      "..DD"], {"D": DARK}),
    "brow_angry_r": (["..DD",
                      "DD.."], {"D": DARK}),
    "tear": ([".E.",
              "ELE",
              "ELE",
              ".E."], {"E": TEAR_EDGE, "L": TEAR}),
    "sweat": (["..E.",
               ".ELE",
               "ELLE",
               "ELLE",
               ".EE."], {"E": TEAR_EDGE, "L": TEAR}),
    "blush": ([".PPP.",
               "PPPPP"], {"P": BLUSH}),
    # Menutup senyum lebar frame 127 (merah di x 36-40 / 37-39) dengan warna kulit
    "smile_erase": (["SSSSS",
                     ".SSS."], {"S": SKIN}),
    "wavy_mouth": (["B.B.B",
                    ".B.B."], {"B": BROWN}),
    "anger": (["R...R",
               "RR.RR",
               ".....",
               "RR.RR",
               "R...R"], {"R": RED}),
    "question": ([".WWW.",
                  "W...W",
                  "....W",
                  "...W.",
                  "..W..",
                  ".....",
                  "..W.."], {"W": WHITE}),
    "dot": (["WW",
             "WW"], {"W": WHITE}),
}

# Tanda di luar wajah diberi garis tepi gelap supaya terbaca di latar apa pun
OUTLINED = {"question", "dot", "anger", "sweat"}

# Frame baru: (nama emosi, frame dasar, [(pola, x, y), ...])
NEW_FRAMES = [
    ("sad", 0, [("brow_sad_l", 26, 23), ("brow_sad_r", 38, 23), ("frown", 31, 34), ("tear", 26, 30)]),
    ("sad", 0, [("brow_sad_l", 26, 23), ("brow_sad_r", 38, 23), ("frown", 31, 34), ("tear", 26, 32)]),
    ("annoyed", 0, [("brow_angry_l", 26, 23), ("brow_angry_r", 38, 23), ("pout", 32, 34), ("anger", 47, 2)]),
    ("annoyed", 0, [("brow_angry_l", 26, 23), ("brow_angry_r", 38, 23), ("pout", 32, 34), ("anger", 47, 3)]),
    ("embarrassed", 127, [("smile_erase", 36, 34), ("wavy_mouth", 36, 34),
                          ("blush", 30, 30), ("blush", 41, 30), ("sweat", 46, 17)]),
    ("embarrassed", 127, [("smile_erase", 36, 34), ("wavy_mouth", 36, 34),
                          ("blush", 30, 30), ("blush", 41, 30), ("sweat", 46, 19)]),
    ("confused", 41, [("question", 46, 0)]),
    ("confused", 41, [("question", 46, 1)]),
    ("thinking", 63, [("dot", 44, 5)]),
    ("thinking", 63, [("dot", 44, 5), ("dot", 48, 5)]),
    ("thinking", 63, [("dot", 44, 5), ("dot", 48, 5), ("dot", 52, 5)]),
]
# Sel kosong di baris 6 sheet (106-119 kosong)
NEW_CELLS = list(range(106, 106 + len(NEW_FRAMES)))


def emotion_frames() -> dict:
    """Peta emosi -> indeks frame baru, untuk MIKU_EMOTION_FRAMES di config.py."""
    result: dict = {}
    for (name, _, _), cell in zip(NEW_FRAMES, NEW_CELLS):
        result.setdefault(name, []).append(cell)
    return result


def _cell_box(index: int):
    row, col = divmod(index, COLS)
    return (col * FRAME_W, row * FRAME_H, (col + 1) * FRAME_W, (row + 1) * FRAME_H)


def _stamp(art: Image.Image, name: str, x: int, y: int):
    rows, colors = PATTERNS[name]
    pixels = {(x + dx, y + dy): colors[ch]
              for dy, line in enumerate(rows) for dx, ch in enumerate(line) if ch != "."}
    px = art.load()
    if name in OUTLINED:
        for (sx, sy) in pixels:
            for nx in range(sx - 1, sx + 2):
                for ny in range(sy - 1, sy + 2):
                    if (nx, ny) not in pixels and 0 <= nx < art.width and 0 <= ny < art.height:
                        px[nx, ny] = DARK
    for (sx, sy), color in pixels.items():
        if 0 <= sx < art.width and 0 <= sy < art.height:
            px[sx, sy] = color


def build_frames(sheet: Image.Image) -> list:
    frames = []
    for _, base, stamps in NEW_FRAMES:
        art = sheet.crop(_cell_box(base)).resize((FRAME_W // SCALE, FRAME_H // SCALE), Image.NEAREST)
        for name, x, y in stamps:
            _stamp(art, name, x, y)
        frames.append(art.resize((FRAME_W, FRAME_H), Image.NEAREST))
    return frames


def write_preview(frames: list, out: Path):
    zoom = 2
    labels = [name for name, _, _ in NEW_FRAMES]
    img = Image.new("RGB", (len(frames) * FRAME_W * zoom, FRAME_H * zoom + 24), (43, 43, 43))
    draw = ImageDraw.Draw(img)
    for k, (frame, label, cell) in enumerate(zip(frames, labels, NEW_CELLS)):
        big = frame.resize((FRAME_W * zoom, FRAME_H * zoom), Image.NEAREST)
        img.paste(big, (k * FRAME_W * zoom, 24), big)
        draw.text((k * FRAME_W * zoom + 6, 6), f"{label} #{cell}", fill=(255, 255, 0))
    img.save(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--preview", type=Path, help="tulis gambar pratinjau, sheet tidak diubah")
    args = parser.parse_args()

    sheet = Image.open(SHEET).convert("RGBA")
    frames = build_frames(sheet)
    if args.preview:
        write_preview(frames, args.preview)
        print(f"Pratinjau: {args.preview}")
        return 0

    for frame, cell in zip(frames, NEW_CELLS):
        box = _cell_box(cell)
        sheet.paste(Image.new("RGBA", frame.size, (0, 0, 0, 0)), box)
        sheet.paste(frame, box)
    sheet.save(SHEET, optimize=True)
    print(f"{len(frames)} frame ditulis ke {SHEET.name}: {emotion_frames()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
