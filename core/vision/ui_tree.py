"""
Elemen jendela aktif dari pohon aksesibilitas: nama, jenis, posisi, aktif/tidak.

Linux: AT-SPI2 lewat core/vision/atspi_helper.py yang dijalankan dengan Python sistem
(pyatspi tidak ada di venv). Windows (UI Automation) menyusul.
"""

import difflib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SYSTEM_PYTHON = "/usr/bin/python3"
HELPER = Path(__file__).with_name("atspi_helper.py")
TIMEOUT_SEC = 8.0

# Nama jenis AT-SPI → kata yang lebih pendek untuk LLM
ROLE_NAMES = {
    "push button": "button", "toggle button": "toggle", "check box": "checkbox", "radio button": "radio",
    "menu item": "menu item", "menu": "menu", "combo box": "dropdown", "entry": "text field",
    "text": "text field", "password text": "password field", "list item": "list item", "page tab": "tab",
    "link": "link", "slider": "slider", "spin button": "number field", "table cell": "cell", "icon": "icon",
}


def _run_helper(args: List[str], timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def active_window_elements(own_pid: Optional[int] = None, platform: str = sys.platform) -> Tuple[Optional[Dict], str]:
    """(data, "") dengan data = {app, title, pid, elements}, atau (None, alasan gagal)."""
    if platform == "win32":
        return None, "belum tersedia di Windows (UI Automation menyusul)"
    if not Path(SYSTEM_PYTHON).exists():
        return None, f"{SYSTEM_PYTHON} tidak ditemukan"
    own_pid = os.getpid() if own_pid is None else own_pid
    try:
        proc = _run_helper([SYSTEM_PYTHON, str(HELPER), "--exclude-pid", str(own_pid)], TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        return None, f"pohon aksesibilitas tidak menjawab dalam {TIMEOUT_SEC:.0f} s"
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        return None, f"helper AT-SPI gagal: {(proc.stderr or '').strip()[-200:] or 'tanpa keluaran'}"
    if "error" in data:
        return None, data["error"]
    return data, ""


def find_elements(elements: List[Dict], query: str = "") -> List[Dict]:
    """Elemen bernama yang cocok dengan query (bagian nama, tanpa beda huruf besar; cadangan: mirip)."""
    named = [e for e in elements if e.get("name")]
    query = query.strip().casefold()
    if not query:
        return named
    found = [e for e in named if query in e["name"].casefold()]
    if found:
        return found
    close = set(difflib.get_close_matches(query, [e["name"].casefold() for e in named], n=5, cutoff=0.75))
    return [e for e in named if e["name"].casefold() in close]


def summarize(elements: List[Dict], limit: int = 40) -> str:
    """'button: Undo, =, %; menu: File (nonaktif)' — dikelompokkan per jenis, urutan seperti di layar."""
    groups: Dict[str, List[str]] = {}
    for e in elements[:limit]:
        role = ROLE_NAMES.get(e.get("role", ""), e.get("role", "element"))
        label = e["name"] + ("" if e.get("enabled", True) else " (nonaktif)")
        if label not in groups.setdefault(role, []):
            groups[role].append(label)
    text = "; ".join(f"{role}: {', '.join(names)}" for role, names in groups.items())
    if len(elements) > limit:
        text += f"; dan {len(elements) - limit} elemen lain"
    return text
