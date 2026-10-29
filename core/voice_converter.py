"""
Voice Converter Module - RVC Voice Conversion
Mengkonversi output Edge-TTS menjadi suara khas karakter menggunakan RVC.

Pipeline: Edge-TTS (Nanami) -> MP3 -> RVC (Miku model) -> WAV

Requires: rvc-python (pip install rvc-python)
Gracefully degrades if not available.
"""

import os
import time
from pathlib import Path
from typing import Optional

from config import RVCConfig


def _allow_hubert_checkpoint(torch) -> None:
    """torch >= 2.6 memuat checkpoint dengan weights_only=True, sehingga hubert_base.pt
    (berisi objek fairseq Dictionary) ditolak saat konversi pertama. Izinkan hanya class
    itu, bukan mematikan weights_only untuk semua checkpoint."""
    add_safe_globals = getattr(torch.serialization, "add_safe_globals", None)
    if add_safe_globals is None:
        return
    try:
        from fairseq.data.dictionary import Dictionary
    except ImportError:
        return
    add_safe_globals([Dictionary])


class VoiceConverter:
    """
    RVC Voice Conversion wrapper.

    Converts TTS audio to character voice using RVC model.
    If rvc-python is not installed or model fails to load,
    conversion is skipped and original audio is used.
    """

    def __init__(self, rvc_config: Optional[RVCConfig] = None):
        self._rvc = None
        self._available = False
        self._config = rvc_config
        self._load_time = 0.0

        if rvc_config and rvc_config.enabled:
            self._initialize(rvc_config)

    def _initialize(self, config: RVCConfig):
        """Try to load RVC inference engine"""
        # Validate paths exist
        if not os.path.isfile(config.model_path):
            print(f"[VoiceConverter] Model not found: {config.model_path}")
            return

        try:
            from rvc_python.infer import RVCInference

            start = time.time()
            print("[VoiceConverter] Loading RVC model...")

            # Determine device
            device = "cuda:0"
            try:
                import torch
                if not torch.cuda.is_available():
                    device = "cpu:0"
                _allow_hubert_checkpoint(torch)
            except ImportError:
                device = "cpu:0"

            self._rvc = RVCInference(device=device)
            if device.startswith("cuda") and config.chunk_sec:
                # Dibaca pipeline RVC saat load_model, jadi harus diatur sebelumnya
                rvc_cfg = self._rvc.config
                rvc_cfg.x_pad, rvc_cfg.x_query = 1, 2
                rvc_cfg.x_center, rvc_cfg.x_max = config.chunk_sec, config.chunk_sec + 2
            self._rvc.load_model(
                config.model_path,
                index_path=config.index_path if os.path.isfile(config.index_path) else "",
                version="v2"
            )

            # Apply parameters
            self._rvc.set_params(
                f0method=config.f0_method,
                f0up_key=config.f0_up_key,
                index_rate=config.index_rate,
                filter_radius=config.filter_radius,
                rms_mix_rate=config.rms_mix_rate,
                protect=config.protect,
            )

            self._load_time = time.time() - start
            self._available = True
            print(f"[VoiceConverter] RVC model loaded in {self._load_time:.1f}s ({device})")

        except ImportError as e:
            # Bisa berarti belum terinstall, atau terinstall tapi dependency-nya rusak
            # (mis. faiss-cpu 1.7.x yang dikompilasi untuk NumPy 1 di env NumPy 2)
            print(f"[VoiceConverter] Cannot import rvc-python: {e}")
            print("[VoiceConverter] Check `pip install rvc-python` and that faiss-cpu matches your NumPy version.")
            print("[VoiceConverter] Voice conversion disabled, using MeloTTS voice only.")

        except Exception as e:
            print(f"[VoiceConverter] Failed to initialize RVC: {e}")
            print("[VoiceConverter] Voice conversion disabled, using MeloTTS voice only.")

    @property
    def is_available(self) -> bool:
        """Check if voice conversion is ready"""
        return self._available

    @property
    def status_text(self) -> str:
        """Human-readable status"""
        if not self._config or not self._config.enabled:
            return "RVC: disabled"
        if self._available:
            return f"RVC: ready ({self._load_time:.1f}s)"
        return "RVC: unavailable"

    def convert(self, input_path: str, output_path: str) -> bool:
        """
        Convert audio file through RVC model.

        Args:
            input_path: Path to input audio (MP3/WAV from Edge-TTS)
            output_path: Path to write converted audio (WAV)

        Returns:
            True if conversion succeeded, False otherwise.
            On failure, the caller should use the original input_path.
        """
        if not self._available or not self._rvc:
            return False

        try:
            start = time.time()
            self._rvc.infer_file(input_path, output_path)
            elapsed = time.time() - start

            # Verify output exists and has content
            if os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
                print(f"[VoiceConverter] Converted in {elapsed:.2f}s: {Path(output_path).name}")
                return True
            else:
                print("[VoiceConverter] Conversion produced empty output")
                return False

        except Exception as e:
            print(f"[VoiceConverter] Conversion failed: {e}")
            return False

    def update_params(self, **kwargs):
        """Update RVC parameters at runtime"""
        if self._rvc and self._available:
            self._rvc.set_params(**kwargs)
            print(f"[VoiceConverter] Parameters updated: {kwargs}")

    def cleanup(self):
        """Release resources"""
        self._rvc = None
        self._available = False
        print("[VoiceConverter] Cleaned up")
