"""
Spike pemicu keyboard di Linux X11: shortcut global lewat XGrabKey (python-xlib).

Library `keyboard` butuh root di Linux, jadi dicoba XGrabKey di root window: tidak
butuh root, dan python-xlib sudah dipakai maskot. Skrip menangkap shortcut, menekannya
sendiri lewat xdotool (XTest), mengukur jeda sampai event diterima, lalu melepas grab.

Pakai (venv MikuVision): python experiments/triggers_linux/hotkey_spike.py [ctrl+shift+m] [kali]
"""

import statistics
import subprocess
import sys
import threading
import time

from Xlib import X, XK, display, error

MODIFIERS = {"ctrl": X.ControlMask, "shift": X.ShiftMask, "alt": X.Mod1Mask, "super": X.Mod4Mask}
# NumLock (Mod2) dan CapsLock (Lock) ikut di state event: grab semua kombinasinya
IGNORED = (0, X.LockMask, X.Mod2Mask, X.LockMask | X.Mod2Mask)


def parse(combo):
    *mods, key = combo.lower().split("+")
    mask = 0
    for m in mods:
        mask |= MODIFIERS[m]
    return mask, key


def main(combo, presses):
    disp = display.Display()
    root = disp.screen().root
    mask, key = parse(combo)
    keycode = disp.keysym_to_keycode(XK.string_to_keysym(key))
    failures = []
    catcher = error.CatchError(error.BadAccess)
    for extra in IGNORED:
        root.grab_key(keycode, mask | extra, True, X.GrabModeAsync, X.GrabModeAsync, onerror=catcher)
    disp.sync()
    if catcher.get_error():
        failures.append(str(catcher.get_error()))
    if failures:
        print(f"{combo}: GAGAL, sudah dipakai aplikasi lain ({failures[0][:60]})")
        return

    latencies, sent = [], []

    def press():
        for _ in range(presses):
            time.sleep(0.5)
            sent.append(time.perf_counter())
            subprocess.run(["xdotool", "key", "--clearmodifiers", combo])

    threading.Thread(target=press, daemon=True).start()
    deadline = time.time() + presses * 0.5 + 5
    while len(latencies) < presses and time.time() < deadline:
        while disp.pending_events():
            event = disp.next_event()
            if event.type == X.KeyPress and event.detail == keycode:
                latencies.append((time.perf_counter() - sent[len(latencies)]) * 1000)
        time.sleep(0.005)
    for extra in IGNORED:
        root.ungrab_key(keycode, mask | extra)
    disp.sync()
    print(f"{combo}: diterima {len(latencies)}/{presses}, jeda median "
          f"{statistics.median(latencies):.1f} ms (termasuk proses xdotool)" if latencies
          else f"{combo}: tidak ada event diterima")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "ctrl+shift+m", int(sys.argv[2]) if len(sys.argv) > 2 else 5)
