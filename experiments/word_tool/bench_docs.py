"""Apakah permintaan "buatkan dokumen Word berisi X" memanggil create_word_document dengan isi?

Tool TIDAK dieksekusi, hanya dicatat. Jalankan dari root repo:
    python experiments/word_tool/bench_docs.py [runs]
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
from core.ai_brain import AIBrain  # noqa: E402
from core.memory import MemoryManager  # noqa: E402

CREATE = "create_word_document"
# (ucapan, tool yang diharapkan, kata yang harus ada di isi dokumen)
SCENARIOS = [
    ("Bisa buatkan dokumen Word, kemudian masukkan rumus-rumus Hukum Newton 1, 2, dan 3, "
     "kemudian penjelasan masing-masingnya", CREATE, ("newton",)),
    ("Tolong bikin dokumen Word berisi ringkasan sejarah kemerdekaan Indonesia", CREATE, ("1945",)),
    ("Buat file Word tentang manfaat olahraga pagi", CREATE, ("olahraga",)),
    ("Tulis surat izin tidak masuk kuliah karena sakit di Word", CREATE, ("sakit",)),
    ("ニュートンの運動の法則についてWordで文書を作って", CREATE, ("ニュートン", "newton")),
    ("ワードで自己紹介の文書を作って", CREATE, ()),
    # Kontrol: hanya membuka aplikasi, tidak membuat dokumen
    ("Buka Word", "open_application", ()),
    ("ワードを開いて", "open_application", ()),
]
MIN_CONTENT = 150  # karakter; isi sependek ini dianggap kosong/placeholder

# Kasus nyata dari sesi GUI 25 Okt: permintaan pertama hanya dijawab obrolan,
# lalu user mengulang singkat dan model memanggil open_application
FOLLOW_UP_HISTORY = [
    ("user", "Bisa buatkan dokumen Word, kemudian masukkan rumus-rumus Hukum Newton 1, 2, dan 3, "
             "kemudian penjelasan masing-masingnya"),
    ("assistant", "わぁ、Hukum Newtonの法則をWordで作るんだね！それはとても面白いテーマだよ！"),
]
FOLLOW_UP = ("Buatkan dokumen Word", CREATE, ("newton",))


def judge(want, keywords, calls):
    names = [c["action"] for c in calls]
    if want != CREATE:
        return want in names and CREATE not in names, ""
    docs = [c.get("params") or {} for c in calls if c["action"] == CREATE]
    if not docs:
        return False, f"calls={names}"
    content = str(docs[0].get("content", ""))
    if len(content) < MIN_CONTENT:
        return False, f"isi {len(content)} karakter"
    if keywords and not any(k in content.lower() for k in keywords):
        return False, f"isi tanpa {keywords}"
    return True, ""


def main(runs: int):
    rows, latencies = [], []
    for text, want, keywords in SCENARIOS + [FOLLOW_UP]:
        hits, lengths = 0, []
        for _ in range(runs):
            brain = AIBrain(MemoryManager(Path(tempfile.mkdtemp())))
            assert brain.initialize()[0], "Ollama/model tidak siap"
            if (text, want, keywords) == FOLLOW_UP:
                for role, content in FOLLOW_UP_HISTORY:
                    brain.memory.add_message(role, content)
            t = time.time()
            reply, calls, _ = brain.think(text)
            latencies.append(time.time() - t)
            ok, why = judge(want, keywords, calls)
            hits += ok
            lengths += [len(str((c.get("params") or {}).get("content", ""))) for c in calls if c["action"] == CREATE]
            if not ok:
                print(f"   MISS {text[:40]!r}: {why} reply={reply[:70]!r}", flush=True)
        rows.append({"text": text[:50], "want": want, "hits": f"{hits}/{runs}",
                     "content_chars": int(statistics.median(lengths)) if lengths else 0})
        print(rows[-1], flush=True)
    create = [r for r in rows if r["want"] == CREATE]
    summary = {
        "create_ok": sum(int(r["hits"].split("/")[0]) for r in create),
        "create_total": len(create) * runs,
        "control_ok": sum(int(r["hits"].split("/")[0]) for r in rows if r["want"] != CREATE),
        "control_total": (len(rows) - len(create)) * runs,
        "latency_median_s": round(statistics.median(latencies), 1),
    }
    print(json.dumps(summary))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 3)
