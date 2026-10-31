"""
Fase 1 Linux - uji sungguhan tool membaca layar lewat satu giliran Miku (run_turn + qwen3:4b).

Meniru Miku yang sedang jalan: LLM dimuat dulu, lalu Whisper + RVC. Tiap kasus membuka jendela
berisi data dummy (dialog error zenity, Kalkulator, Xed, Nemo di folder dummy), lalu user bertanya.
Hanya describe_screen dan find_on_screen yang benar-benar dijalankan; tool lain hanya dicatat
(tidak membuka atau mengubah apa pun). Dicatat: tool yang dipanggil, balasan Miku, waktu,
dan penempatan qwen3:4b di GPU setelah tukar model.

Pakai (venv MikuVision): python experiments/vision_linux/screen_tools_demo.py [ulangan]
"""

import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8")

import core.macro_tools  # noqa: F401,E402  (mendaftarkan tool ke registry)
import core.system_control  # noqa: F401,E402
from ollama import Client  # noqa: E402

from config import CHARACTERS, OLLAMA_MODEL  # noqa: E402
from core.ai_brain import AIBrain  # noqa: E402
from core.conversation import run_turn  # noqa: E402
from core.memory import MemoryManager  # noqa: E402
from core.tools import registry  # noqa: E402
from core.voice_converter import VoiceConverter  # noqa: E402
from core.voice_input import VoiceInput  # noqa: E402

SCREEN_TOOLS = {"describe_screen", "find_on_screen"}
DUMMY = Path(tempfile.mkdtemp(prefix="miku_fase1_"))
for name in ("catatan_kuliah.txt", "jadwal_ujian.odt", "foto_wisuda.png"):
    (DUMMY / name).write_text("dummy")
(DUMMY / "Tugas Akhir").mkdir()
NOTE = DUMMY / "pengumuman.txt"
NOTE.write_text("Rapat himpunan dipindah ke hari Kamis jam 15.00 di ruang B201.\n", encoding="utf-8")

ERROR_DIALOG = ["zenity", "--error", "--title=Gagal menyimpan",
                "--text=Disk D: penuh. File laporan_akhir.docx tidak bisa disimpan."]
# (jendela, ucapan user, tool yang diharapkan, kata yang diharapkan di balasan/hasil tool)
CASES = [
    (ERROR_DIALOG, "Miku, error apa ini?", "describe_screen", ("laporan_akhir", "penuh", "D:", "満杯", "いっぱい")),
    (ERROR_DIALOG, "このエラー、何て書いてあるの？", "describe_screen", ("laporan_akhir", "D:", "満杯", "いっぱい")),
    (["xed", str(NOTE)], "bacakan tulisan di layar", "describe_screen", ("Kamis", "B201", "15")),
    (["nemo", str(DUMMY)], "画面に何が表示されてる？", "describe_screen", ("catatan_kuliah", "jadwal_ujian", "Tugas")),
    (["gnome-calculator"], "tombol apa saja yang ada di jendela ini?", "find_on_screen", ("√", "π", "=")),
    (["gnome-calculator"], "電卓に「π」のボタンはある？", "find_on_screen", ("π",)),
    (None, "Miku, apa kabar hari ini?", None, ()),
    (None, "buka notepad", "open_application", ()),
]


class Executor:
    """Pengganti SystemControl: tool layar dijalankan sungguhan, tool lain hanya dicatat."""

    def __init__(self):
        self.calls = []
        self.results = []

    def execute_action(self, action, params):
        self.calls.append(action)
        if action in SCREEN_TOOLS:
            ok, message = registry.execute(action, self, params)
            self.results.append(message)
            return ok, message
        return True, f"(uji: {action} tidak dijalankan)"


def windows():
    out = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True).stdout
    return {line.split()[0] for line in out.splitlines()}


def open_window(argv):
    before = windows()
    proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    deadline = time.time() + 15
    while time.time() < deadline:
        new = windows() - before
        if new:
            time.sleep(1.5)  # isi jendela selesai digambar dan fokus berpindah
            return proc, new.pop()
        time.sleep(0.2)
    return proc, None


def placement(client):
    for m in client.ps()["models"]:
        if m["model"] == OLLAMA_MODEL:
            return f"{100 * m['size_vram'] / m['size']:.0f}% GPU"
    return "tidak dimuat"


def main():
    client = Client()
    brain = AIBrain(MemoryManager(Path(tempfile.mkdtemp(prefix="miku_mem_"))))
    ok, msg = brain.initialize()
    assert ok, msg
    brain.set_character("miku")
    brain.preload_model()
    voice = VoiceInput()
    voice.initialize()
    VoiceConverter(CHARACTERS["miku"].rvc_config)
    print(f"Siap: LLM + Whisper + RVC, {OLLAMA_MODEL} {placement(client)}\n", flush=True)

    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    passed, vision_seconds = 0, []
    for argv, text, expected_tool, words in [case for case in CASES for _ in range(runs)]:
        brain.clear_history()
        proc, wid = open_window(argv) if argv else (None, None)
        executor = Executor()
        started = time.time()
        turn = run_turn(brain, executor, text, source="text", report_results=True)
        seconds = time.time() - started
        if wid:
            subprocess.run(["wmctrl", "-ic", wid])
            time.sleep(0.8)
        if proc and proc.poll() is None and argv[0] != "nemo":
            proc.terminate()
        tool_ok = (expected_tool in executor.calls) if expected_tool else not (set(executor.calls) & SCREEN_TOOLS)
        haystack = " ".join(executor.results + [turn.reply]).lower()
        word_ok = not words or any(w.lower() in haystack for w in words)
        passed += tool_ok and word_ok
        if "describe_screen" in executor.calls:
            vision_seconds.append(seconds)
        print(f"[{'LULUS' if tool_ok and word_ok else 'GAGAL'}] {text}")
        print(f"   tool {executor.calls or '-'} | {seconds:.1f} s | {OLLAMA_MODEL} {placement(client)}")
        for result in executor.results:
            print(f"   hasil tool: {result[:220]}")
        print(f"   Miku: {turn.reply[:200]}\n", flush=True)

    print(f"Lulus {passed}/{len(CASES) * runs}")
    if vision_seconds:
        vision_seconds.sort()
        print(f"Giliran dengan describe_screen: median {vision_seconds[len(vision_seconds) // 2]:.1f} s, "
              f"maks {vision_seconds[-1]:.1f} s")
    voice.cleanup()
    brain.cleanup()


if __name__ == "__main__":
    main()
