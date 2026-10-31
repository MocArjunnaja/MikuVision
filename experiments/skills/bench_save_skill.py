"""S2: apakah "simpan ini sebagai skill" menghasilkan skill yang benar dan bisa dipakai ulang (qwen3:4b)?

Tiap skenario: user menyelesaikan tugas bersama Miku → minta disimpan sebagai skill (konfirmasi
otomatis disetujui) → di SESI BARU user memakai skill itu dengan isi berbeda. Tool TIDAK dieksekusi:
kontrol sistem palsu hanya mencatat dan menjawab sukses. Skill ditulis ke folder sementara.

Bawaan: riwayat tugas disuntikkan apa adanya (ucapan, tool call + argumen, hasil SUKSES), supaya yang
diukur hanya S2. --live: tugasnya dijalankan qwen3:4b sungguhan (bisa tidak lengkap, misalnya hanya
mengatur volume tanpa memutar YouTube; skill lalu ikut tidak lengkap).
Jalankan dari root repo (nama skenario opsional, misalnya campur_id):
    python experiments/skills/bench_save_skill.py [runs] [skenario ...] [--live]
"""
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

import core.macro_tools  # noqa: F401,E402  (mendaftarkan tool ke registry)
import core.system_control  # noqa: F401,E402
from core import user_skills  # noqa: E402
from core.ai_brain import AIBrain  # noqa: E402
from core.conversation import run_turn  # noqa: E402
from core.memory import MemoryManager  # noqa: E402

VOL, YT, DOC, FOLDER, APP = "set_volume", "youtube_search", "create_word_document", "open_folder", "open_application"


def has(calls, action, **want):
    """Ada tool call `action` yang parameternya memuat semua kata di `want` (huruf kecil)."""
    for call in calls:
        if call["action"] != action:
            continue
        params = {k: str(v).lower() for k, v in (call["params"] or {}).items()}
        if all(any(w in params.get(k, "") for w in (v if isinstance(v, tuple) else (v,))) for k, v in want.items()):
            return True
    return False


def lacks(calls, action, key, word):
    return all(word not in str((c["params"] or {}).get(key, "")).lower() for c in calls if c["action"] == action)


# (nama, [(ucapan, [(tool, argumen)], balasan)], permintaan simpan, tool skill yang diharapkan,
#  ucapan pakai ulang, cek pakai ulang)
SCENARIOS = [
    ("belajar_id", [("kecilkan volume ke 20 lalu putar lofi hip hop di youtube",
                     [(VOL, {"level": 20}), (YT, {"query": "lofi hip hop"})], "音量を20にして、lofiを流したよ！")],
     "simpan ini sebagai skill, namanya mode fokus", {VOL, YT},
     "mode fokus dong",
     lambda c: has(c, VOL, level="20") and has(c, YT, query="lofi")),
    ("belanja_id", [("buatkan dokumen word daftar belanja: telur, susu, roti",
                     [(DOC, {"filename": "daftar_belanja", "content": "Daftar Belanja\n- telur\n- susu\n- roti"})],
                     "買い物リストを作ったよ！")],
     "jadikan skill ya, namanya daftar belanja", {DOC},
     "buat daftar belanja: kopi, gula, teh",
     lambda c: has(c, DOC, content="kopi") and lacks(c, DOC, "content", "telur")),
    ("rapat_id", [("buatkan dokumen word catatan rapat: rapat himpunan membahas anggaran acara",
                   [(DOC, {"filename": "rapat_anggaran", "content":
                           "Catatan Rapat Himpunan\nTempat: Ruang B201\nTopik: anggaran acara\n"
                           "- Konsumsi Rp 2.000.000\n- Dekorasi Rp 1.500.000"})], "議事録を作ったよ！")],
     "simpan ini sebagai skill catatan rapat", {DOC},
     "buat catatan rapat: rapat dosen membahas jadwal ujian",
     lambda c: has(c, DOC, content="ujian") and lacks(c, DOC, "content", "anggaran")),
    ("jazz_ja", [("音量を30にして、YouTubeでジャズを流して",
                  [(VOL, {"level": 30}), (YT, {"query": "jazz"})], "ジャズを流したよ！")],
     "これをスキルとして保存して。名前はジャズタイム", {VOL, YT},
     "ジャズタイムにして",
     lambda c: has(c, VOL, level="30") and has(c, YT, query=("jazz", "ジャズ"))),
    ("kerja_id", [("buka folder downloads", [(FOLDER, {"folder_name_or_path": "Downloads"})], "開いたよ！"),
                  ("buka kalkulator", [(APP, {"app_name": "Calculator"})], "電卓を開いたよ！")],
     "simpan cara tadi sebagai skill siap kerja", {FOLDER, APP},
     "siap kerja",
     lambda c: has(c, FOLDER, folder_name_or_path="download") and has(c, APP, app_name=("calc", "kalkulator"))),
    # Dua tugas lain sebelum tugas yang disimpan, di sesi yang sama (gagal di Windows, 31 Okt 2026):
    # skill harus berisi volume 20 + lofi saja, tanpa dokumen dan volume 30 dari giliran sebelumnya
    ("campur_id", [("buatkan laporan harian: tadi aku belajar fisika bab gelombang dan mengerjakan tugas kalkulus",
                    [(DOC, {"filename": "Laporan_Harian", "content":
                            "Laporan Harian\n- Belajar fisika bab gelombang\n- Mengerjakan tugas kalkulus"}),
                     (FOLDER, {"folder_name_or_path": "Miku_Documents"})], "日報を作ったよ！"),
                   ("putar lagu buat belajar", [(VOL, {"level": 30}), (YT, {"query": "lofi hip hop study music"})],
                    "勉強用のlofiを流したよ！"),
                   ("kecilkan volume ke 20 lalu putar lofi di youtube", [(VOL, {"level": 20}), (YT, {"query": "lofi"})],
                    "音量を20にして、lofiを流したよ！")],
     "simpan ini sebagai skill, namanya mode fokus", {VOL, YT},
     "mode fokus dong",
     lambda c: has(c, VOL, level="20") and has(c, YT, query="lofi") and not any(x["action"] in (DOC, FOLDER) for x in c)),
]


class FakeControl:
    def __init__(self):
        self.confirm_callback = lambda summary: True

    def execute_action(self, action, params):
        return True, f"{action} selesai"


def new_brain():
    brain = AIBrain(MemoryManager(Path(tempfile.mkdtemp())))
    assert brain.initialize()[0], "Ollama/model tidak siap"
    brain.set_character("miku")
    return brain


def inject(brain, text, calls, reply):
    """Satu giliran tugas yang berhasil, persis seperti yang dicatat think() dan run_turn()."""
    brain.memory.add_message("user", text)
    brain.memory.add_message("assistant", "", metadata={"tool_calls": [
        {"function": {"name": tool, "arguments": args}} for tool, args in calls]})
    for tool, _ in calls:
        brain.memory.add_message("tool", f"SUKSES - {tool} selesai", metadata={"tool_name": tool})
    brain.memory.add_message("assistant", f"[EMOTION:happy] {reply}", "happy")


def run_scenario(name, task_turns, save_text, want_tools, reuse_text, reuse_ok, live=False):
    brain, control = new_brain(), FakeControl()
    for text, calls, reply in task_turns:
        if live:
            run_turn(brain, control, text, source="bench", report_results=False)
        else:
            inject(brain, text, calls, reply)
    started = time.time()
    saved = run_turn(brain, control, save_text, source="bench")
    save_seconds = time.time() - started
    result = saved.tool_results[0]
    if not result.success:
        return {"saved": False, "note": result.message}

    skills, errors = user_skills.load_user_skills()
    skill = skills.get(result.params["name"].lower())
    tools_ok = skill is not None and set(skill.tools) == want_tools

    # Sesi baru: skill dimuat dari folder, bukan dari riwayat
    reuse_brain = new_brain()
    turn = run_turn(reuse_brain, FakeControl(), reuse_text, source="bench", report_results=False)
    calls = [{"action": r.action, "params": r.params} for r in turn.tool_results]
    selected = [s.name for s in reuse_brain.turn_user_skills]
    return {
        "saved": True, "seconds": save_seconds, "tools_ok": tools_ok, "selected": skill.name in selected if skill else False,
        "reuse_ok": reuse_ok(calls), "skill": skill, "errors": errors, "calls": calls, "reply": saved.reply,
    }


def main(runs: int, live: bool, only: list):
    totals = {"saved": 0, "tools_ok": 0, "selected": 0, "reuse_ok": 0}
    seconds = []
    scenarios = [s for s in SCENARIOS if not only or s[0] in only]
    for name, *scenario in scenarios:
        for i in range(runs):
            user_skills.USER_SKILLS_DIR = Path(tempfile.mkdtemp(prefix="miku_skills_"))
            r = run_scenario(name, *scenario, live=live)
            if not r["saved"]:
                print(f"[{name} #{i + 1}] TIDAK TERSIMPAN: {r['note']}", flush=True)
                continue
            seconds.append(r["seconds"])
            for key in ("saved", "tools_ok", "selected", "reuse_ok"):
                totals[key] += bool(r[key])
            s = r["skill"]
            mark = "OK " if r["tools_ok"] and r["selected"] and r["reuse_ok"] else "MISS"
            print(f"[{mark}] {name} #{i + 1} ({r['seconds']:.1f} s) '{s.name}' tools={list(s.tools)} "
                  f"pemicu={list(s.triggers)}", flush=True)
            print(f"       Miku: {r['reply']}")
            for line in s.instructions.splitlines():
                print(f"       | {line}")
            print(f"       pakai ulang: terpilih={r['selected']} benar={r['reuse_ok']} calls={r['calls']}", flush=True)

    total = len(scenarios) * runs
    print("\n" + " | ".join(f"{k} {v}/{total}" for k, v in totals.items()))
    if seconds:
        print(f"giliran simpan: median {statistics.median(seconds):.1f} s, maks {max(seconds):.1f} s")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--live"]
    main(int(args[0]) if args else 3, "--live" in sys.argv, args[1:])
