"""VoiceConverter: RVC memotong audio panjang agar muat di VRAM yang tersisa."""

import sys
import types

import pytest

from config import RVCConfig
from core import voice_converter


class _FakeRVC:
    """Mencatat pengaturan potongan audio saat load_model, seperti pipeline RVC asli."""

    def __init__(self, device):
        self.device = device
        self.config = types.SimpleNamespace(x_pad=3, x_query=10, x_center=60, x_max=65)
        self.window_at_load = None

    def load_model(self, *args, **kwargs):
        c = self.config
        self.window_at_load = (c.x_pad, c.x_query, c.x_center, c.x_max)

    def set_params(self, **kwargs):
        pass


@pytest.fixture
def rvc_config(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "rvc_python", types.ModuleType("rvc_python"))
    monkeypatch.setitem(sys.modules, "rvc_python.infer", types.SimpleNamespace(RVCInference=_FakeRVC))
    monkeypatch.setattr(voice_converter, "_allow_hubert_checkpoint", lambda torch: None)
    model = tmp_path / "miku.pth"
    model.write_bytes(b"")
    return RVCConfig(enabled=True, model_path=str(model))


def _set_cuda(monkeypatch, available):
    # torch tersendiri per test; atribut MagicMock bersama yang di-patch hilang setelah undo
    fake_torch = types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda: available))
    monkeypatch.setitem(sys.modules, "torch", fake_torch)


def test_gpu_uses_short_chunks_before_load(rvc_config, monkeypatch):
    # Di GPU 6 GB balasan 19 s kehabisan VRAM bila RVC memproses sampai 65 s sekaligus
    _set_cuda(monkeypatch, True)

    converter = voice_converter.VoiceConverter(rvc_config)

    assert converter.is_available
    assert converter._rvc.window_at_load == (1, 2, 6, 8)


def test_chunking_can_be_disabled(rvc_config, monkeypatch):
    _set_cuda(monkeypatch, True)
    rvc_config.chunk_sec = 0

    converter = voice_converter.VoiceConverter(rvc_config)

    assert converter._rvc.window_at_load == (3, 10, 60, 65)


def test_cpu_keeps_rvc_defaults(rvc_config, monkeypatch):
    _set_cuda(monkeypatch, False)

    converter = voice_converter.VoiceConverter(rvc_config)

    assert converter._rvc.device == "cpu:0"
    assert converter._rvc.window_at_load == (3, 10, 60, 65)
