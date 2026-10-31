"""Maskot Linux (X11): bentuk jendela dari piksel sprite, dan menu klik kanan."""

import sys
from unittest.mock import MagicMock

import pytest

from core import avatar_window
from core.avatar_x11 import pixel_rectangles


def _grid(rows):
    return lambda x, y: rows[y][x] == "#"


def _as_tuples(rects):
    return sorted((r["x"], r["y"], r["width"], r["height"]) for r in rects)


def test_rows_with_the_same_run_merge_into_one_rectangle():
    # Sprite di-upscale 3x: blok piksel identik di beberapa baris = satu persegi
    rows = ["......",
            ".###..",
            ".###..",
            ".###..",
            "......"]

    assert _as_tuples(pixel_rectangles(6, 5, _grid(rows))) == [(1, 1, 3, 3)]


def test_separate_runs_and_offset():
    rows = ["##..##",
            "##..##",
            "..##.."]

    rects = pixel_rectangles(6, 3, _grid(rows), offset=(10, 20))

    assert _as_tuples(rects) == [(10, 20, 2, 2), (12, 22, 2, 1), (14, 20, 2, 2)]


def test_rectangles_cover_exactly_the_filled_pixels():
    rows = ["..##....#",
            ".####..##",
            ".####..##",
            "..##.....",
            "#.......#"]
    filled = {(x, y) for y, row in enumerate(rows) for x, ch in enumerate(row) if ch == "#"}

    covered = set()
    for r in pixel_rectangles(9, 5, _grid(rows)):
        for x in range(r["x"], r["x"] + r["width"]):
            for y in range(r["y"], r["y"] + r["height"]):
                assert (x, y) not in covered, "persegi tumpang tindih"
                covered.add((x, y))

    assert covered == filled


def test_empty_mask_has_no_rectangles():
    assert pixel_rectangles(4, 4, lambda x, y: False) == []


# Bagian berikut butuh pygame.Rect asli (di CI pygame di-stub)
real_pygame = pytest.mark.skipif(isinstance(sys.modules.get("pygame"), MagicMock), reason="butuh pygame asli")


def _window(monkeypatch):
    win = avatar_window.AvatarWindow("tidak-dipakai.png")
    win.x11 = MagicMock()
    win.avatar = MagicMock(last_surface=object())
    monkeypatch.setattr(avatar_window, "mask_rectangles",
                        lambda surf, offset: [{"x": 1, "y": 2, "width": 3, "height": 4}])
    return win


@real_pygame
def test_shape_is_sent_only_when_frame_or_menu_changes(monkeypatch):
    win = _window(monkeypatch)

    win._update_shape()
    win._update_shape()   # frame sama, menu sama: tidak dikirim lagi
    assert win.x11.set_shape.call_count == 1

    win._open_menu((110, 120))
    win._update_shape()
    rects = win.x11.set_shape.call_args.args[0]
    menu = win.menu_rect
    # Menu ikut bentuk jendela, kalau tidak klik pada menu jatuh ke jendela di bawahnya
    assert {"x": menu.x, "y": menu.y, "width": menu.width, "height": menu.height} in rects


@real_pygame
@pytest.mark.parametrize("click", [(0, 0), (219, 249), (110, 10), (5, 200)])
def test_menu_stays_inside_the_window(click):
    win = avatar_window.AvatarWindow("tidak-dipakai.png")

    win._open_menu(click)

    r = win.menu_rect
    assert 0 <= r.left and r.right <= avatar_window.WIN_W
    assert 0 <= r.top and r.bottom <= avatar_window.WIN_H


def test_menu_exit_calls_quit_callback():
    quit_cb = MagicMock()
    win = avatar_window.AvatarWindow("tidak-dipakai.png", on_quit_callback=quit_cb)
    win.running = True

    win._quit_from_menu()

    assert not win.running
    quit_cb.assert_called_once()
