"""
Fase 1 Linux - tukar qwen3:4b <-> qwen3-vl saat Whisper dan RVC sudah di VRAM.

Masalahnya (CHANGELOG v1.3.0): bila Ollama memuat qwen3:4b setelah Whisper + RVC (±1,7 GB)
menempati VRAM, sebagian layer jatuh ke CPU. Skrip ini meniru Miku yang sedang jalan
(LLM dimuat dulu, lalu Whisper dan RVC), lalu menjalankan satu "giliran visi":
lepas qwen3:4b -> qwen3-vl menjawab satu pertanyaan tentang screenshot -> lepas qwen3-vl
-> muat ulang qwen3:4b. Dicatat: waktu, dan berapa bagian model di GPU (`ollama ps`).

Screenshot layar diambil di memori dan tidak disimpan.

Pakai (venv MikuVision):
    python experiments/vision_linux/swap_bench.py [--vl-ctx 4096 8192] [--vl-gpu 999] [--reload-gpu 999]
--vl-gpu / --reload-gpu: paksa jumlah layer di GPU (opsi num_gpu Ollama) untuk qwen3-vl / muat ulang qwen3:4b.
"""

import argparse
import base64
import io
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ollama import Client  # noqa: E402
from PIL import ImageGrab  # noqa: E402

from config import CHARACTERS, OLLAMA_MODEL, OLLAMA_NUM_CTX  # noqa: E402
from core.voice_converter import VoiceConverter  # noqa: E402
from core.voice_input import VoiceInput  # noqa: E402

VL_MODEL = "qwen3-vl:4b-instruct"
QUESTION = "Describe briefly what is on this screen: which application, and any visible text or error message."


def placement(client, model):
    for m in client.ps()["models"]:
        if m["model"] == model:
            size, vram = m["size"], m["size_vram"]
            return f"{vram / 1e9:.2f}/{size / 1e9:.2f} GB di GPU ({100 * vram / size:.0f}%)"
    return "tidak dimuat"


def gpu_used():
    import subprocess
    out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True).stdout.split(",")
    return f"{int(out[0])}/{int(out[1])} MiB"


def screenshot_b64(max_side=1280):
    img = ImageGrab.grab()
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def load_llm(client, extra):
    t0 = time.time()
    client.chat(model=OLLAMA_MODEL, messages=[], keep_alive=-1, options={"num_ctx": OLLAMA_NUM_CTX, **extra})
    return time.time() - t0


def release(client, model, num_ctx, extra=None):
    t0 = time.time()
    client.chat(model=model, messages=[], keep_alive=0, options={"num_ctx": num_ctx, **(extra or {})})
    # Ollama melepas di latar; tunggu sampai benar-benar hilang dari ps
    while any(m["model"] == model for m in client.ps()["models"]):
        time.sleep(0.05)
    return time.time() - t0


# ±3.500 token, seukuran persona + skema tool + history Miku: prefill-nya yang lambat bila sebagian layer di CPU
LONG_PROMPT = ("Catatan: " + "Miku adalah asisten desktop yang ramah dan membantu user di komputer. " * 230
               + "\n\nこんにちは！一言で返事して。")


def llm_reply(client, long=False):
    """Chat biasa seperti Miku (tanpa num_gpu): ikut mengecek apakah Ollama memuat ulang model."""
    t0 = time.time()
    content = LONG_PROMPT if long else "こんにちは！一言で返事して。"
    reply = client.chat(model=OLLAMA_MODEL, messages=[{"role": "user", "content": content}],
                        keep_alive=-1, options={"num_ctx": OLLAMA_NUM_CTX, "num_predict": 40})
    seconds = time.time() - t0
    tps = reply.eval_count / (reply.eval_duration / 1e9) if reply.eval_duration else 0
    prefill = reply.prompt_eval_count / (reply.prompt_eval_duration / 1e9) if reply.prompt_eval_duration else 0
    return f"{seconds:.2f} s, prefill {reply.prompt_eval_count} token @ {prefill:.0f}/s, {tps:.0f} token/s"


def main(vl_contexts, vl_extra, reload_extra):
    client = Client(timeout=300)
    for m in client.ps()["models"]:
        release(client, m["model"], OLLAMA_NUM_CTX)

    print(f"Awal: {gpu_used()}")
    print(f"Muat {OLLAMA_MODEL} dulu: {load_llm(client, {}):.1f} s, {placement(client, OLLAMA_MODEL)}")
    voice = VoiceInput()
    voice.initialize()
    converter = VoiceConverter(CHARACTERS["miku"].rvc_config)
    print(f"Whisper + RVC dimuat (RVC {'siap' if converter.is_available else 'TIDAK siap'}): {gpu_used()}")
    print(f"Balasan LLM sebelum tukar: pendek {llm_reply(client)} | panjang {llm_reply(client, long=True)}\n")

    image = screenshot_b64()
    for num_ctx in vl_contexts:
        print(f"--- qwen3-vl num_ctx {num_ctx} {vl_extra} | muat ulang qwen3:4b {reload_extra} ---")
        t_release = release(client, OLLAMA_MODEL, OLLAMA_NUM_CTX)
        t0 = time.time()
        try:
            reply = client.chat(model=VL_MODEL, messages=[{"role": "user", "content": QUESTION, "images": [image]}],
                                keep_alive=-1,
                                options={"num_ctx": num_ctx, "temperature": 0.2, "num_predict": 150, **vl_extra})
            answer = f"({reply.eval_count} token): {(reply.message.content or '')[:120]!r}"
        except Exception as e:
            answer = f"GAGAL: {e}"
        t_vl = time.time() - t0
        where_vl = placement(client, VL_MODEL)
        vram_peak = gpu_used()
        t_release_vl = release(client, VL_MODEL, num_ctx, vl_extra)
        t0 = time.time()
        try:
            load_llm(client, reload_extra)
        except Exception as e:
            print(f"muat ulang dengan {reload_extra} GAGAL: {e}; muat otomatis")
            load_llm(client, {})
        t_reload = time.time() - t0
        where_llm = placement(client, OLLAMA_MODEL)
        print(f"lepas qwen3:4b {t_release:.1f} s | qwen3-vl muat+jawab {t_vl:.1f} s, {where_vl}, VRAM {vram_peak}")
        print(f"jawaban VL {answer}")
        print(f"lepas qwen3-vl {t_release_vl:.1f} s | muat ulang qwen3:4b {t_reload:.1f} s, {where_llm}, VRAM {gpu_used()}")
        print(f"balasan LLM sesudah: pendek {llm_reply(client)} | panjang {llm_reply(client, long=True)}")
        print(f"sesudah chat biasa: {placement(client, OLLAMA_MODEL)}\n")

    voice.cleanup()
    release(client, OLLAMA_MODEL, OLLAMA_NUM_CTX)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--vl-ctx", type=int, nargs="+", default=[8192, 4096])
    parser.add_argument("--vl-gpu", type=int)
    parser.add_argument("--reload-gpu", type=int)
    args = parser.parse_args()
    main(args.vl_ctx,
         {"num_gpu": args.vl_gpu} if args.vl_gpu is not None else {},
         {"num_gpu": args.reload_gpu} if args.reload_gpu is not None else {})
