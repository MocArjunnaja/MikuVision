"""
Fase 0 Linux - cakupan AT-SPI2 (pengganti UI Automation Windows).

Membuka jendela uji, membaca elemen interaktif dari pohon aksesibilitas, lalu
menyimpan daftar elemen + screenshot + gambar Set-of-Mark ke <out>. Hanya
jendela yang BARU muncul setelah perintah dijalankan yang dibaca dan ditutup.

Jalankan dengan Python sistem (pyatspi adalah paket sistem, tidak ada di venv):
    /usr/bin/python3 experiments/vision_linux/atspi_spike.py <out>
"""

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pyatspi
from PIL import Image, ImageDraw, ImageFont, ImageGrab

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
INTERACTIVE_ROLES = {
    pyatspi.ROLE_PUSH_BUTTON, pyatspi.ROLE_TOGGLE_BUTTON, pyatspi.ROLE_CHECK_BOX, pyatspi.ROLE_RADIO_BUTTON,
    pyatspi.ROLE_MENU_ITEM, pyatspi.ROLE_MENU, pyatspi.ROLE_COMBO_BOX, pyatspi.ROLE_ENTRY, pyatspi.ROLE_TEXT,
    pyatspi.ROLE_PASSWORD_TEXT, pyatspi.ROLE_LIST_ITEM, pyatspi.ROLE_PAGE_TAB, pyatspi.ROLE_LINK,
    pyatspi.ROLE_SLIDER, pyatspi.ROLE_SPIN_BUTTON, pyatspi.ROLE_TABLE_CELL, pyatspi.ROLE_ICON,
    pyatspi.ROLE_TOGGLE_BUTTON, pyatspi.ROLE_SPLIT_PANE,
}
MAX_NODES = 3000


def windows():
    out = subprocess.run(["wmctrl", "-lp"], capture_output=True, text=True).stdout
    rows = {}
    for line in out.splitlines():
        parts = line.split(None, 4)
        if len(parts) >= 4:
            rows[parts[0]] = (int(parts[2]), parts[4] if len(parts) > 4 else "")
    return rows


def wait_new_window(before, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        new = {w: v for w, v in windows().items() if w not in before}
        if new:
            time.sleep(1.5)  # biarkan isi jendela selesai digambar
            wid = next(iter(new))
            return wid, windows().get(wid, new[wid])
        time.sleep(0.2)
    return None, None


def window_geometry(wid):
    out = subprocess.run(["xwininfo", "-id", wid], capture_output=True, text=True).stdout
    get = lambda key: int(next(l.split(":")[1] for l in out.splitlines() if key in l))
    return get("Absolute upper-left X"), get("Absolute upper-left Y"), get("Width"), get("Height")


def find_frame(pid, title):
    """Frame AT-SPI milik pid (atau aplikasi single-instance) dengan judul jendela baru."""
    desktop = pyatspi.Registry.getDesktop(0)
    candidates = []
    for app in desktop:
        if app is None:
            continue
        for frame in app:
            if frame is None:
                continue
            candidates.append((app, frame))
    exact = [f for a, f in candidates if f.name == title]
    if exact:
        return exact[0]
    by_pid = [f for a, f in candidates if a.get_process_id() == pid]
    return by_pid[0] if by_pid else None


def collect(frame, bounds, keep_accessible=False):
    wx, wy, ww, wh = bounds
    elements, stack, visited = [], [frame], 0
    while stack and visited < MAX_NODES:
        acc = stack.pop()
        visited += 1
        try:
            state = acc.getState()
            if not state.contains(pyatspi.STATE_SHOWING):
                continue
            role = acc.getRole()
            try:
                actions = acc.queryAction()
                action_names = [actions.getName(i) for i in range(actions.nActions)]
            except NotImplementedError:
                action_names = []
            if role in INTERACTIVE_ROLES or action_names:
                box = acc.queryComponent().getExtents(pyatspi.DESKTOP_COORDS)
                inside = box.width > 0 and box.height > 0 and wx <= box.x + box.width / 2 <= wx + ww \
                    and wy <= box.y + box.height / 2 <= wy + wh
                if inside:
                    elements.append({
                        "type": acc.getRoleName(), "name": acc.name or "", "description": acc.description or "",
                        "rect": [box.x, box.y, box.width, box.height], "actions": action_names,
                        "enabled": state.contains(pyatspi.STATE_SENSITIVE),
                        "password": role == pyatspi.ROLE_PASSWORD_TEXT,
                        **({"accessible": acc} if keep_accessible else {}),
                    })
            stack.extend(acc[i] for i in reversed(range(acc.childCount)))
        except Exception:  # elemen bisa hilang saat dibaca
            continue
    return elements, visited


def draw_som(shot, elements, origin, path):
    """Kotak + nomor besar. Nomor diletakkan di luar kotak (kiri atas) supaya teks tombol tetap terbaca."""
    img = shot.convert("RGB")
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, 16)
    ox, oy = origin
    for i, e in enumerate(elements, 1):
        x, y, w, h = e["rect"]
        x, y = x - ox, y - oy
        draw.rectangle([x, y, x + w, y + h], outline=(255, 0, 80), width=2)
        label = str(i)
        tw, th = draw.textbbox((0, 0), label, font=font)[2:]
        lx = max(0, x - tw - 6) if x - tw - 6 >= 0 else x
        ly = y if lx < x else max(0, y - th - 4)
        draw.rectangle([lx, ly, lx + tw + 6, ly + th + 4], fill=(255, 0, 80))
        draw.text((lx + 3, ly + 1), label, fill="white", font=font)
    img.save(path)


def run_case(name, argv, out: Path):
    before = windows()
    proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    wid, (pid, title) = wait_new_window(before)
    if wid is None:
        print(f"{name}: jendela baru tidak muncul")
        return None
    try:
        bounds = window_geometry(wid)
        t0 = time.time()
        frame = find_frame(pid, title)
        if frame is None:
            print(f"{name}: frame AT-SPI tidak ditemukan (pid {pid}, '{title}')")
            return {"window": name, "elements": 0, "named": 0, "seconds": 0, "note": "tidak ada di AT-SPI"}
        elements, visited = collect(frame, bounds)
        seconds = time.time() - t0
        x, y, w, h = bounds
        shot = ImageGrab.grab(bbox=(x, y, x + w, y + h))
        shot.save(out / f"{name}.png")
        draw_som(shot, elements, (x, y), out / f"{name}_som.png")
        (out / f"{name}_elements.json").write_text(json.dumps(elements, ensure_ascii=False, indent=1), encoding="utf-8")
        named = sum(bool(e["name"].strip()) for e in elements)
        row = {"window": name, "elements": len(elements), "named": named, "nodes": visited,
               "seconds": round(seconds, 2), "size": [w, h]}
        print(row, flush=True)
        return row
    finally:
        subprocess.run(["wmctrl", "-ic", wid])
        time.sleep(1)
        if proc.poll() is None and name != "nemo":
            proc.terminate()


def main(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    # Folder berisi file dummy, supaya screenshot Nemo tidak memuat file pribadi user
    dummy = Path(tempfile.mkdtemp(prefix="miku_spike_"))
    for f in ("catatan_kuliah.txt", "jadwal.odt", "foto_liburan.png", "laporan.docx"):
        (dummy / f).write_text("dummy")
    (dummy / "Tugas").mkdir()
    cases = [
        ("calculator", ["gnome-calculator"]),
        ("text_editor", ["xed", "--new-window"]),
        ("nemo", ["nemo", str(dummy)]),
        ("settings_sound", ["cinnamon-settings", "sound"]),
        ("system_monitor", ["gnome-system-monitor"]),
    ]
    rows = [r for r in (run_case(n, a, out) for n, a in cases) if r]
    (out / "summary.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
