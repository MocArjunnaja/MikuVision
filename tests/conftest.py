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

# scipy >= 1.17 memanggil issubclass(x, torch.Tensor) bila torch ada di sys.modules;
# atribut MagicMock bukan class sehingga import librosa/MeloTTS gagal.
if isinstance(sys.modules["torch"], MagicMock):
    sys.modules["torch"].Tensor = type("Tensor", (), {})


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _no_real_windows(monkeypatch):
    """Test tidak boleh menemukan atau menutup jendela sungguhan di desktop."""
    from core import system_control
    # Logika tutup-jendela Windows tetap dites di Linux, dengan jendela palsu
    monkeypatch.setattr(system_control, "WINDOW_CLOSE_AVAILABLE", True)
    monkeypatch.setattr(system_control, "_windows_by_pid", lambda pids: {})
    monkeypatch.setattr(system_control, "_post_close", lambda hwnd: None)


@pytest.fixture(autouse=True)
def _isolated_long_term_memory(monkeypatch, tmp_path):
    """Test tidak boleh membaca/menulis memori jangka panjang asli di data/."""
    from core import long_term_memory
    monkeypatch.setattr(long_term_memory, "store", long_term_memory.LongTermMemory(tmp_path / "ltm.json"))
