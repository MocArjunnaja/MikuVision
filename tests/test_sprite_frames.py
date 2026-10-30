"""Setiap frame animasi harus menunjuk ke sel sprite sheet yang berisi gambar."""

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Import modul tanpa dependency berat (torch di config, pygame di avatar_window,
# serta core/__init__.py yang memuat modul suara)
_core_pkg = types.ModuleType("core")
_core_pkg.__path__ = [str(ROOT / "core")]
sys.modules.setdefault("core", _core_pkg)
for _name in ["torch", "pygame"]:
    sys.modules.setdefault(_name, MagicMock())

import config  # noqa: E402
from core.avatar_window import ANIMATIONS, EMOTION_ANIMATIONS  # noqa: E402


@pytest.fixture(scope="module")
def sheet() -> Image.Image:
    return Image.open(config.MIKU_SPRITE_SHEET).convert("RGBA")


def _is_empty(sheet: Image.Image, index: int) -> bool:
    w, h, cols = config.MIKU_FRAME_W, config.MIKU_FRAME_H, config.MIKU_SHEET_COLS
    row, col = divmod(index, cols)
    cell = sheet.crop((col * w, row * h, (col + 1) * w, (row + 1) * h))
    return cell.getchannel("A").getbbox() is None


def test_frame_grid_matches_sheet_size(sheet):
    width, height = sheet.size
    assert width == config.MIKU_FRAME_W * config.MIKU_SHEET_COLS
    assert height % config.MIKU_FRAME_H == 0


def test_emotion_frames_are_not_empty(sheet):
    empty = {
        name: [i for i in frames if _is_empty(sheet, i)]
        for name, frames in config.MIKU_EMOTION_FRAMES.items()
    }
    assert not {k: v for k, v in empty.items() if v}


def test_avatar_animations_are_not_empty(sheet):
    empty = {
        name: [i for i in frames if _is_empty(sheet, i)]
        for name, frames in ANIMATIONS.items()
    }
    assert not {k: v for k, v in empty.items() if v}


def test_every_emotion_maps_to_existing_animation():
    for emotion, animation in EMOTION_ANIMATIONS.items():
        assert animation in ANIMATIONS, f"{emotion} -> {animation}"
    assert set(config.MIKU_EMOTION_FRAMES) <= set(EMOTION_ANIMATIONS)


# ── Frame emosi buatan tools/make_emote_frames.py ──

sys.path.insert(0, str(ROOT / "tools"))
import make_emote_frames  # noqa: E402


def test_generated_emotions_are_used_by_config():
    for emotion, frames in make_emote_frames.emotion_frames().items():
        assert config.MIKU_EMOTION_FRAMES[emotion] == frames


def test_sheet_matches_generator(sheet):
    # Sheet dan script harus sejalan: ubah polanya di script, lalu jalankan ulang script
    for frame, cell in zip(make_emote_frames.build_frames(sheet), make_emote_frames.NEW_CELLS):
        row, col = divmod(cell, config.MIKU_SHEET_COLS)
        box = (col * config.MIKU_FRAME_W, row * config.MIKU_FRAME_H,
               (col + 1) * config.MIKU_FRAME_W, (row + 1) * config.MIKU_FRAME_H)
        assert sheet.crop(box).tobytes() == frame.convert("RGBA").tobytes(), f"frame {cell}"


def test_generator_only_uses_empty_cells_and_real_base_frames():
    original_frames = {base for _, base, _ in make_emote_frames.NEW_FRAMES}
    assert not original_frames & set(make_emote_frames.NEW_CELLS)
    assert len(set(make_emote_frames.NEW_CELLS)) == len(make_emote_frames.NEW_FRAMES)
