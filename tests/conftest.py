"""
Test setup: stub dependency berat (audio, GUI, Windows API) agar logika inti
bisa dites tanpa hardware dan tanpa Ollama.
"""

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Daftarkan package `core` tanpa menjalankan core/__init__.py,
# yang meng-import seluruh modul suara/GUI.
_core_pkg = types.ModuleType("core")
_core_pkg.__path__ = [str(ROOT / "core")]
sys.modules.setdefault("core", _core_pkg)

for _name in [
    "torch",
    "ollama",
    "comtypes",
    "pycaw",
    "pycaw.pycaw",
    "pyautogui",
    "pygetwindow",
    "keyboard",
]:
    sys.modules.setdefault(_name, MagicMock())
