"""Pemutaran audio tidak boleh tumpang tindih (sd.play paralel = segfault PortAudio)."""

import sys
import threading
import time
import types
from unittest.mock import MagicMock

import numpy as np
import pytest

from core.voice_output import VoiceOutput


@pytest.fixture
def fake_audio(monkeypatch):
    state = {"active": 0, "max_active": 0, "plays": 0}
    lock = threading.Lock()

    def play(data, samplerate):
        with lock:
            state["active"] += 1
            state["plays"] += 1
            state["max_active"] = max(state["max_active"], state["active"])

    def wait():
        time.sleep(0.05)
        with lock:
            state["active"] -= 1

    fake_sd = types.SimpleNamespace(play=play, wait=wait, stop=MagicMock())
    fake_sf = types.SimpleNamespace(read=lambda path: (np.zeros(10), 16000))
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)
    monkeypatch.setitem(sys.modules, "soundfile", fake_sf)
    return state


def test_concurrent_playback_is_serialized(fake_audio, tmp_path):
    output = VoiceOutput()
    threads = [
        threading.Thread(target=output._play_audio_sync, args=(str(tmp_path / f"a{i}.wav"),))
        for i in range(5)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert fake_audio["plays"] == 5
    assert fake_audio["max_active"] == 1


def test_no_playback_after_cleanup(fake_audio, tmp_path):
    output = VoiceOutput()
    output.cleanup()

    output._play_audio_sync(str(tmp_path / "late.wav"))

    assert fake_audio["plays"] == 0
