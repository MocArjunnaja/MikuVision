"""
Fase 0 - spike UI Automation.

Membuka jendela uji, mengambil elemen yang bisa diinteraksi (nama, jenis, kotak),
lalu menggambar Set-of-Mark (kotak bernomor) di screenshot jendela itu.
Hanya jendela uji yang ditangkap, bukan seluruh layar.

Pakai: python uia_spike.py <folder_output>
"""

import ctypes
import json
import subprocess
import sys
import time
from pathlib import Path

import uiautomation as auto
import win32gui
import win32ui
from PIL import Image, ImageDraw

ctypes.windll.user32.SetProcessDPIAware()

INTERACTIVE = {
    "ButtonControl", "MenuItemControl", "ListItemControl", "HyperlinkControl", "EditControl",
    "CheckBoxControl", "RadioButtonControl", "TabItemControl", "ComboBoxControl",
    "TreeItemControl", "SplitButtonControl", "SliderControl", "DataItemControl",
}

TEST_WINDOWS = [
    # (label, perintah pembuka, ClassName jendela top-level)
    ("calculator", ["calc.exe"], "ApplicationFrameWindow"),
    ("settings_bluetooth", ["explorer.exe", "ms-settings:bluetooth"], "ApplicationFrameWindow"),
    ("explorer_documents", ["explorer.exe", str(Path.home() / "Documents")], "CabinetWClass"),
]


def top_level_handles(class_name):
    return {w.NativeWindowHandle for w in auto.GetRootControl().GetChildren() if w.ClassName == class_name}


def new_window(class_name, before, timeout=10.0):
    """Jendela yang BARU muncul setelah perintah dijalankan; jendela milik user tidak disentuh."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for w in auto.GetRootControl().GetChildren():
            if w.ClassName == class_name and w.NativeWindowHandle not in before and w.Name:
                return w
        time.sleep(0.3)
    return None


def interactive_elements(window, max_depth=25):
    elements = []
    win_rect = window.BoundingRectangle
    for control, depth in auto.WalkControl(window, maxDepth=max_depth):
        if control.ControlTypeName not in INTERACTIVE:
            continue
        rect = control.BoundingRectangle
        if rect.width() <= 2 or rect.height() <= 2 or control.IsOffscreen:
            continue
        # Hanya elemen yang tampak di dalam jendela
        if rect.right < win_rect.left or rect.left > win_rect.right or rect.bottom < win_rect.top or rect.top > win_rect.bottom:
            continue
        elements.append({
            "type": control.ControlTypeName.replace("Control", ""),
            "name": (control.Name or "").strip()[:60],
            "rect": [rect.left, rect.top, rect.right, rect.bottom],
            "enabled": bool(control.IsEnabled),
        })
    return elements


def capture(hwnd, path):
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    w, h = right - left, bottom - top
    hdc = win32gui.GetWindowDC(hwnd)
    src = win32ui.CreateDCFromHandle(hdc)
    mem = src.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(src, w, h)
    mem.SelectObject(bmp)
    ctypes.windll.user32.PrintWindow(hwnd, mem.GetSafeHdc(), 2)
    info = bmp.GetInfo()
    img = Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]), bmp.GetBitmapBits(True), "raw", "BGRX", 0, 1)
    win32gui.DeleteObject(bmp.GetHandle()); mem.DeleteDC(); src.DeleteDC(); win32gui.ReleaseDC(hwnd, hdc)
    img.save(path)
    return img, (left, top)


def draw_som(img, origin, elements, path):
    """Set-of-Mark: kotak + nomor untuk setiap elemen bernama."""
    som = img.copy()
    draw = ImageDraw.Draw(som)
    for i, el in enumerate(elements, 1):
        l, t, r, b = el["rect"]
        box = [l - origin[0], t - origin[1], r - origin[0], b - origin[1]]
        draw.rectangle(box, outline=(255, 0, 80), width=2)
        draw.rectangle([box[0], box[1], box[0] + 22, box[1] + 14], fill=(255, 0, 80))
        draw.text((box[0] + 2, box[1]), str(i), fill=(255, 255, 255))
    som.save(path)


def main(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    report = []
    for label, command, class_name in TEST_WINDOWS:
        before = top_level_handles(class_name)
        subprocess.Popen(command)
        window = new_window(class_name, before)
        if window is None:
            report.append({"window": label, "error": "jendela tidak ditemukan"})
            continue
        time.sleep(2.5)  # tunggu render selesai
        t0 = time.time()
        elements = interactive_elements(window)
        walk_s = round(time.time() - t0, 2)
        named = [e for e in elements if e["name"]]
        img, origin = capture(window.NativeWindowHandle, out_dir / f"{label}.png")
        draw_som(img, origin, named, out_dir / f"{label}_som.png")
        (out_dir / f"{label}_elements.json").write_text(json.dumps(named, ensure_ascii=False, indent=1), encoding="utf-8")
        report.append({"window": label, "title": window.Name, "interactive": len(elements),
                       "named": len(named), "walk_seconds": walk_s})
        # Tutup HANYA jendela uji ini (seperti tombol X), bukan seluruh proses
        try:
            window.GetWindowPattern().Close()
        except Exception as e:  # pola Window tidak selalu tersedia
            report[-1]["close_error"] = str(e)
        time.sleep(1)
    (out_dir / "uia_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    for row in report:
        print(row)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
