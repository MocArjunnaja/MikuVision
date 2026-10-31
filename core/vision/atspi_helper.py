"""
Elemen jendela aktif dari pohon aksesibilitas Linux (AT-SPI2), sebagai JSON di stdout.

Dijalankan dengan Python sistem, bukan venv: pyatspi adalah paket sistem dan venv memakai
Python dari uv. Hanya library standar + pyatspi; dipanggil oleh core/vision/ui_tree.py.

    /usr/bin/python3 core/vision/atspi_helper.py [--exclude-pid PID]

Yang dibaca hanya nama, jenis, posisi, dan status elemen; isi field (termasuk password) tidak.
"""

import json
import sys
import time

MAX_NODES = 3000


def interactive_roles(pyatspi):
    return {
        pyatspi.ROLE_PUSH_BUTTON, pyatspi.ROLE_TOGGLE_BUTTON, pyatspi.ROLE_CHECK_BOX, pyatspi.ROLE_RADIO_BUTTON,
        pyatspi.ROLE_MENU_ITEM, pyatspi.ROLE_MENU, pyatspi.ROLE_COMBO_BOX, pyatspi.ROLE_ENTRY, pyatspi.ROLE_TEXT,
        pyatspi.ROLE_PASSWORD_TEXT, pyatspi.ROLE_LIST_ITEM, pyatspi.ROLE_PAGE_TAB, pyatspi.ROLE_LINK,
        pyatspi.ROLE_SLIDER, pyatspi.ROLE_SPIN_BUTTON, pyatspi.ROLE_TABLE_CELL, pyatspi.ROLE_ICON,
    }


def active_frame(pyatspi, exclude_pid):
    desktop = pyatspi.Registry.getDesktop(0)
    for app in desktop:
        if app is None:
            continue
        try:
            if app.get_process_id() == exclude_pid:
                continue
            for frame in app:
                if frame is not None and frame.getState().contains(pyatspi.STATE_ACTIVE):
                    return app, frame
        except Exception:  # aplikasi bisa tertutup saat dibaca
            continue
    return None, None


def collect(pyatspi, frame):
    roles = interactive_roles(pyatspi)
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
                action = acc.queryAction()
                has_action = action.nActions > 0
            except NotImplementedError:
                has_action = False
            if role in roles or has_action:
                box = acc.queryComponent().getExtents(pyatspi.DESKTOP_COORDS)
                if box.width > 0 and box.height > 0:
                    elements.append({
                        "role": acc.getRoleName(),
                        "name": (acc.name or "").strip(),
                        "rect": [box.x, box.y, box.width, box.height],
                        "enabled": state.contains(pyatspi.STATE_SENSITIVE),
                        "password": role == pyatspi.ROLE_PASSWORD_TEXT,
                    })
            stack.extend(acc[i] for i in reversed(range(acc.childCount)))
        except Exception:  # elemen bisa hilang saat dibaca
            continue
    return elements, visited


def main(argv):
    exclude_pid = int(argv[argv.index("--exclude-pid") + 1]) if "--exclude-pid" in argv else -1
    try:
        import pyatspi
    except ImportError:
        print(json.dumps({"error": "pyatspi tidak terpasang (paket python3-pyatspi)"}))
        return
    started = time.time()
    app, frame = active_frame(pyatspi, exclude_pid)
    if frame is None:
        print(json.dumps({"error": "tidak ada jendela aktif yang terbaca lewat AT-SPI"}))
        return
    elements, visited = collect(pyatspi, frame)
    print(json.dumps({
        "app": app.name or "",
        "title": frame.name or "",
        "pid": app.get_process_id(),
        "elements": elements,
        "nodes": visited,
        "seconds": round(time.time() - started, 3),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
