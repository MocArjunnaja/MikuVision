"""
Model visi (qwen3-vl) bergantian dengan LLM utama di VRAM.

GPU 6 GB tidak muat qwen3:4b + qwen3-vl + Whisper + RVC sekaligus, jadi satu pertanyaan visi:
lepas LLM utama → qwen3-vl menjawab (lalu dilepas) → muat LLM utama lagi.
Kedua pemuatan memaksa semua layer ke GPU (VISION_NUM_GPU): dengan Whisper + RVC di VRAM,
Ollama sendiri hanya menaruh 76% qwen3-vl dan 85% qwen3:4b di GPU, dan sisa sesi melambat
dari 67 ke 45 token/s (experiments/vision_linux/swap_bench.py). Chat biasa sesudahnya
(tanpa num_gpu) tidak membuat Ollama memuat ulang model.
"""

import time
from typing import Dict, List, Tuple

from ollama import Client, ResponseError

from config import (
    OLLAMA_BASE_URL, OLLAMA_KEEP_ALIVE, OLLAMA_MODEL, OLLAMA_NUM_CTX, OLLAMA_TIMEOUT_SEC,
    VISION_MODEL, VISION_NUM_CTX, VISION_NUM_GPU,
)

UNLOAD_TIMEOUT_SEC = 10.0


def _client() -> Client:
    return Client(host=OLLAMA_BASE_URL, timeout=OLLAMA_TIMEOUT_SEC)


def _loaded(client: Client) -> List[str]:
    return [m["model"] for m in client.ps()["models"]]


def _wait_unloaded(client: Client, model: str):
    """Ollama melepas model di latar; pemuatan penuh berikutnya butuh VRAM-nya benar-benar kosong."""
    deadline = time.time() + UNLOAD_TIMEOUT_SEC
    while model in _loaded(client) and time.time() < deadline:
        time.sleep(0.05)


def _release(client: Client, model: str, num_ctx: int):
    client.chat(model=model, messages=[], keep_alive=0, options={"num_ctx": num_ctx})
    _wait_unloaded(client, model)


def _chat_on_gpu(client: Client, options: Dict, **kwargs):
    """Chat dengan semua layer di GPU; bila VRAM benar-benar kurang, Ollama yang memutuskan."""
    if VISION_NUM_GPU is not None:
        try:
            return client.chat(options={**options, "num_gpu": VISION_NUM_GPU}, **kwargs)
        except ResponseError as e:
            if e.status_code == 404:
                raise
            print(f"[Vision] {kwargs.get('model')} tidak muat penuh di GPU ({e}); dimuat otomatis")
    return client.chat(options=options, **kwargs)


def restore_main_model(client: Client):
    _chat_on_gpu(client, {"num_ctx": OLLAMA_NUM_CTX}, model=OLLAMA_MODEL, messages=[],
                 keep_alive=OLLAMA_KEEP_ALIVE)


def ask(prompt: str, image_jpeg: bytes) -> Tuple[bool, str]:
    """Tanyakan satu hal tentang gambar ke model visi. (berhasil, jawaban atau alasan gagal)."""
    try:
        client = _client()
        client.show(VISION_MODEL)
    except ResponseError:
        return False, f"Model visi {VISION_MODEL} belum terpasang. Jalankan: ollama pull {VISION_MODEL}"
    except Exception as e:
        return False, f"Ollama tidak terhubung: {e}"

    started = time.time()
    try:
        _release(client, OLLAMA_MODEL, OLLAMA_NUM_CTX)
        # keep_alive=0: model visi langsung dilepas setelah menjawab
        reply = _chat_on_gpu(
            client, {"num_ctx": VISION_NUM_CTX, "temperature": 0.2, "num_predict": 250},
            model=VISION_MODEL, keep_alive=0,
            messages=[{"role": "user", "content": prompt, "images": [image_jpeg]}],
        )
        answer = (reply.message.content or "").strip()
        return (True, answer) if answer else (False, "Model visi tidak memberi jawaban")
    except Exception as e:
        return False, f"Model visi gagal: {e}"
    finally:
        try:
            _wait_unloaded(client, VISION_MODEL)
            restore_main_model(client)
        except Exception as e:
            print(f"[Vision] Gagal memuat ulang {OLLAMA_MODEL}: {e}")
        print(f"[Vision] Tukar model + jawaban: {time.time() - started:.1f} s")
