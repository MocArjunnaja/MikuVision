"""Alur VoiceInput.transcribe() dengan model Whisper palsu (tanpa GPU)."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

# faster_whisper asli memeriksa torch, yang di-stub conftest; modelnya diganti FakeWhisper
sys.modules.setdefault("faster_whisper", MagicMock())

from core.voice_input import VoiceInput  # noqa: E402


def seg(text, avg_logprob=-0.2, no_speech_prob=0.01, compression_ratio=1.2, start=0.0, end=1.0):
    return SimpleNamespace(text=text, avg_logprob=avg_logprob, no_speech_prob=no_speech_prob,
                           compression_ratio=compression_ratio, start=start, end=end)


class FakeWhisper:
    def __init__(self, probs, outputs):
        self.probs = probs          # [(lang, p)] seperti detect_language Whisper
        self.outputs = outputs      # lang -> [segmen]
        self.decoded = []

    def detect_language(self, audio, vad_filter=False):
        best = max(self.probs, key=lambda x: x[1])
        return best[0], best[1], self.probs

    def transcribe(self, audio, language=None, **kwargs):
        self.decoded.append((language, kwargs.get("initial_prompt")))
        return iter(self.outputs.get(language, [])), SimpleNamespace(language=language)


def make(probs, outputs):
    vi = VoiceInput()
    vi.model = FakeWhisper(probs, outputs)
    return vi


SPEECH = (0.1 * np.sin(np.linspace(0, 2000, 16000))).astype(np.float32)


def test_confident_detection_decodes_once():
    vi = make([("id", 0.9), ("ja", 0.05)], {"id": [seg(" Buka Notepad.")]})
    assert vi.transcribe(SPEECH, languages=["ja", "id"], verbose_logging=False) == "Buka Notepad"
    assert [lang for lang, _ in vi.model.decoded] == ["id"]
    assert vi.last_language == "id"


def test_malay_detection_counts_as_indonesian():
    vi = make([("ms", 0.6), ("id", 0.3), ("ja", 0.05)], {"id": [seg(" Tutup Google Chrome")]})
    assert vi.transcribe(SPEECH, languages=["ja", "id"], verbose_logging=False) == "Tutup Google Chrome"
    assert [lang for lang, _ in vi.model.decoded] == ["id"]


def test_ambiguous_detection_picks_more_confident_decode():
    outputs = {
        "ja": [seg("ブカのテパー", avg_logprob=-1.4)],
        "id": [seg(" Buka Notepad", avg_logprob=-0.3)],
    }
    vi = make([("ja", 0.5), ("id", 0.45)], outputs)
    assert vi.transcribe(SPEECH, languages=["ja", "id"], verbose_logging=False) == "Buka Notepad"
    assert sorted(lang for lang, _ in vi.model.decoded) == ["id", "ja"]


def test_looping_segment_is_dropped():
    # Bug lama: prompt Jepang bocor jadi "音量を下げて、音量を下げて..." pada ucapan Indonesia
    loop = seg("音量を下げて、" * 30, compression_ratio=12.0)
    vi = make([("ja", 0.95), ("id", 0.05)], {"ja": [loop]})
    assert vi.transcribe(SPEECH, languages=["ja", "id"], verbose_logging=False) == ""


def test_no_speech_segment_is_dropped():
    vi = make([("ja", 0.95)], {"ja": [seg("次の動画でお会いしましょう", avg_logprob=-1.2, no_speech_prob=0.9)]})
    assert vi.transcribe(SPEECH, languages=["ja", "id"], verbose_logging=False) == ""


def test_forced_language_skips_detection():
    vi = make([("ja", 0.99)], {"id": [seg(" Ya, lanjutkan")]})
    assert vi.transcribe(SPEECH, lang="id", verbose_logging=False) == "Ya, lanjutkan"
    assert [lang for lang, _ in vi.model.decoded] == ["id"]


@pytest.mark.parametrize("audio", [np.zeros(16000, dtype=np.float32), SPEECH[:4000]])
def test_silent_or_short_audio_is_not_decoded(audio):
    vi = make([("ja", 0.99)], {"ja": [seg("ご視聴ありがとうございました")]})
    assert vi.transcribe(audio, verbose_logging=False) == ""
    assert vi.model.decoded == []


def test_prompt_can_be_disabled():
    vi = make([("ja", 0.99)], {"ja": [seg("メモ帳を開いて")]})
    vi.transcribe(SPEECH, languages=["ja", "id"], use_initial_prompt=False, verbose_logging=False)
    assert vi.model.decoded == [("ja", None)]
