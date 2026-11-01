"""Apakah skill buatan user (skills/*/SKILL.md) terpilih dan diikuti oleh qwen3:4b?

Satu giliran berjalan lewat run_turn (termasuk langkah skill berikutnya), tetapi tool
TIDAK dieksekusi: kontrol sistem palsu hanya mencatat dan menjawab sukses. Jalankan dari root repo:
    python experiments/skills/bench_skills.py [runs] [laporan_harian|musik_mood|regression|call_or_ask]
"""
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

import core.system_control  # noqa: F401,E402  (mendaftarkan tool ke registry)
import core.macro_tools     # noqa: F401,E402
from core import user_skills  # noqa: E402
from core.ai_brain import AIBrain  # noqa: E402
from core.conversation import run_turn  # noqa: E402
from core.memory import MemoryManager  # noqa: E402

DOC, FOLDER, YT, VOL = "create_word_document", "open_folder", "youtube_search", "set_volume"
ASK = "ask"  # tidak ada tool call, balasan berupa pertanyaan

# (ucapan atau [ucapan, ...] untuk beberapa giliran, skill, hasil yang diharapkan)
REPORT = [
    ("buatkan laporan harian: hari ini aku kuliah kalkulus, praktikum fisika, lalu rapat himpunan", ("kalkulus",)),
    ("Miku, tolong bikin laporan harian ya. Tadi aku ngerjain tugas basis data dan belajar bahasa Jepang", ("basis data",)),
    ("laporan hari ini: revisi skripsi bab 2 dan bimbingan dengan dosen", ("skripsi",)),
    ("日報を作って。今日は数学の授業とアルバイトがあった", ("数学", "matematika")),
    ("daily report please: I fixed the login bug and wrote unit tests", ("login",)),
    ("buat laporan harian, hari ini aku olahraga pagi, belajar machine learning, dan nonton webinar", ("machine learning",)),
    ("buatkan laporan harian", ASK),
    ("Miku, laporan harian dong", ASK),
    ("日報を作って", ASK),
    (["buatkan laporan harian", "tadi aku belajar fisika dan rapat organisasi"], ("fisika",)),
]
# (ucapan, volume yang diharapkan atau None, kata yang harus ada di query atau ())
MUSIC = [
    ("putar lagu buat belajar", 30, ("lofi", "study")),
    ("Miku, aku mau tidur, putarkan musik santai", 25, ("relax", "piano", "sleep")),
    ("musik semangat buat olahraga dong", 60, ("upbeat", "energetic", "workout")),
    ("aku lagi galau, putar lagu sedih", 35, ("acoustic", "calm", "sad")),
    ("作業用BGMかけて", 30, ("lofi", "study")),
    ("リラックスできる曲を流して", 25, ("relax", "piano")),
    ("元気が出る曲かけて", 60, ("upbeat", "energetic")),
    ("putar musik buat fokus kerja, volume 20 aja", 20, ()),
    ("lagu buat belajar, yang jazz ya", None, ("jazz",)),
    ("mood music buat masak", None, ()),
]
# Regresi: perintah biasa tidak boleh mengaktifkan skill user, tool tetap benar
REGRESSION = [
    ("音量を30にして", VOL), ("メモ帳を開いて", "open_application"), ("電卓を閉じて", "close_application"),
    ("Kecilkan volume ke 20", VOL), ("buka youtube", "open_website"),
    ("cari resep nasi goreng di google", "google_search"), ("次の曲にして", "media_control"),
    ("ミュートして", "mute"), ("buka folder downloads", FOLDER), ("勉強モードにして", "run_routine"),
]

# Panggil vs tanya (When2Call, arXiv 2504.18851): tanya balik hanya benar bila tool yang cocok butuh
# informasi wajib yang tidak ada di ucapan. Perintah lengkap harus langsung memanggil tool.
MEDIA = ("media_control", "browser_media_control")
MUST_CALL = [
    ("ミュートして", ("mute",)), ("ミュート解除して", ("mute",)), ("mute dong", ("mute",)),
    ("一時停止して", MEDIA), ("音楽を止めて", MEDIA), ("pause lagunya", MEDIA),
    ("lanjutkan lagunya", MEDIA), ("前の曲に戻して", MEDIA), ("skip lagu ini", MEDIA), ("次の曲にして", MEDIA),
]
# Penerima, isi pesan, atau kata kunci tidak disebut: menebaknya berarti mengarang parameter
MUST_ASK = ["メッセージを送って", "kirim pesan WhatsApp dong", "tolong carikan video di youtube",
            "グーグルで検索して", "Telegramで連絡して"]


def new_brain():
    brain = AIBrain(MemoryManager(Path(tempfile.mkdtemp())))
    assert brain.initialize()[0], "Ollama/model tidak siap"
    return brain


class FakeControl:
    def execute_action(self, action, params):
        return True, f"{action} selesai"


def run(turns):
    """Giliran terakhir: (brain, balasan pertama, tool call)."""
    brain = new_brain()
    for text in turns if isinstance(turns, list) else [turns]:
        turn = run_turn(brain, FakeControl(), text, source="bench", report_results=False)
    calls = [{"action": r.action, "params": r.params} for r in turn.tool_results]
    return brain, turn.reply, calls


def judge_report(want, reply, calls):
    names = [c["action"] for c in calls]
    if want == ASK:
        return not calls and ("?" in reply or "？" in reply), f"calls={names}"
    docs = [c.get("params") or {} for c in calls if c["action"] == DOC]
    if not docs:
        return False, f"calls={names} reply={reply[:60]!r}"
    content = str(docs[0].get("content", "")).lower()
    if not any(k in content for k in want):
        return False, f"isi tanpa {want}: {content[:80]!r}"
    return True, "" if FOLDER in names else "tanpa open_folder"


def judge_music(volume, words, calls):
    params = {c["action"]: c.get("params") or {} for c in calls}
    if YT not in params or VOL not in params:
        return False, f"calls={list(params)}"
    got_volume = params[VOL].get("level")
    query = str(params[YT].get("query", "")).lower()
    if volume is not None and str(got_volume) != str(volume):
        return False, f"volume {got_volume} (harus {volume}), query {query!r}"
    if words and not any(w in query for w in words):
        return False, f"query {query!r} tanpa {words}"
    return True, ""


def bench_call_or_ask(runs: int) -> dict:
    """Akurasi per kategori; meleset dihitung per jenis: tanya balik, tool lain, atau parameter karangan."""
    result = {}
    for label, cases in (("must_call", MUST_CALL), ("must_ask", [(text, ASK) for text in MUST_ASK])):
        ok, misses = 0, {}
        for text, want in cases:
            for _ in range(runs):
                _, reply, calls = run(text)
                names = [c["action"] for c in calls]
                asked = not calls and ("?" in reply or "？" in reply)
                if want == ASK:
                    hit, miss = asked, "tool_call" if calls else "no_question"
                else:
                    hit, miss = any(n in want for n in names), "ask" if asked else "other"
                ok += hit
                if not hit:
                    misses[miss] = misses.get(miss, 0) + 1
                    print(f"   MISS [{label}] {text!r}: calls={names} reply={reply[:60]!r}", flush=True)
        result[label] = {"correct": f"{ok}/{len(cases) * runs}", "misses": misses}
        print(label, result[label], flush=True)
    return result


def main(runs: int, only: str = ""):
    summary, tokens = {}, {"with_skills": [], "without_skills": []}
    if only == "call_or_ask":
        print(json.dumps(bench_call_or_ask(runs), ensure_ascii=False))
        return

    for label, cases, judge in (
        ("laporan_harian", REPORT, lambda case, reply, calls: judge_report(case[1], reply, calls)),
        ("musik_mood", MUSIC, lambda case, reply, calls: judge_music(case[1], case[2], calls)),
    ):
        if only and only != label:
            continue
        skill_name = label.replace("_", " ")
        ok = picked = 0
        for case in cases:
            for _ in range(runs):
                brain, reply, calls = run(case[0])
                picked += [s.name for s in brain.turn_user_skills] == [skill_name]
                hit, note = judge(case, reply, calls)
                ok += hit
                mark = "ok  " if hit else "MISS"
                print(f"   {mark} {str(case[0])[:55]!r} {note}", flush=True)
        summary[label] = {"picked": f"{picked}/{len(cases) * runs}", "correct": f"{ok}/{len(cases) * runs}"}
        print(label, summary[label], flush=True)

    # Regresi, sekali dengan skill buatan user dan sekali tanpa (pembanding ukuran prompt dan akurasi)
    original = user_skills.load_user_skills
    variants = (("with_skills", original), ("without_skills", lambda dirs=None: ({}, [])))
    for label, loader in variants if not only or only == "regression" else ():
        user_skills.load_user_skills = loader
        ok = no_skill = 0
        latencies = []
        try:
            for text, want in REGRESSION:
                for _ in range(runs):
                    start = time.perf_counter()
                    brain, reply, calls = run(text)
                    latencies.append(time.perf_counter() - start)
                    names = [c["action"] for c in calls]
                    no_skill += not brain.turn_user_skills
                    ok += want in names
                    tokens[label].append(brain.turn_usage.prompt_tokens)
                    if want not in names:
                        print(f"   MISS [{label}] {text!r}: calls={names} reply={reply[:60]!r}", flush=True)
        finally:
            user_skills.load_user_skills = original
        summary[f"regression_{label}"] = {"no_user_skill": f"{no_skill}/{len(REGRESSION) * runs}",
                                          "correct": f"{ok}/{len(REGRESSION) * runs}",
                                          "latency_median_s": round(statistics.median(latencies), 2)}
    summary["prompt_tokens_median"] = {k: int(statistics.median(v)) for k, v in tokens.items() if v}
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 1, sys.argv[2] if len(sys.argv) > 2 else "")
