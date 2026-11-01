"""Apakah qwen3:4b memilih tool tutup yang benar (tab browser, jendela, aplikasi) dalam bahasa Jepang dan Indonesia?

Sama seperti bench_skills.py: satu giliran lewat run_turn dengan kontrol sistem palsu, jadi tidak
ada yang benar-benar ditutup. Regresi memakai daftar REGRESSION dari bench_skills.py. Jalankan dari root repo:
    python experiments/skills/bench_close.py [runs] [close|regression]
"""
import json
import sys

from bench_skills import REGRESSION, run

TAB, WINDOW, APP = "close_browser_tab", "close_window", "close_application"

# (ucapan, tool yang diharapkan, kata yang harus ada di parameternya)
CLOSE = [
    ("YouTube閉じて", TAB, "youtube"),
    ("YouTubeのタブを閉じて", TAB, "youtube"),
    ("ユーチューブを閉じて", TAB, "youtube"),
    ("Netflixのタブ閉じて", TAB, "netflix"),
    ("tutup youtube", TAB, "youtube"),
    ("tutup tab youtube", TAB, "youtube"),
    ("Miku, tolong tutup tab youtube yang lagi muter", TAB, "youtube"),
    ("tutup tab netflix dong", TAB, "netflix"),
    ("tutup jendela Downloads", WINDOW, "downloads"),
    ("tutup jendela laporan.docx", WINDOW, "laporan"),
    ("「レポート」のウィンドウを閉じて", WINDOW, "レポート"),
    ("メモ帳を閉じて", APP, ""),
    ("tutup notepad", APP, ""),
    ("tutup aplikasi spotify", APP, "spotify"),
]


def judge(want_tool, word, calls):
    names = [c["action"] for c in calls]
    if want_tool not in names:
        return False, f"calls={names}"
    params = next(c.get("params") or {} for c in calls if c["action"] == want_tool)
    text = " ".join(str(v) for v in params.values()).lower()
    if word and word not in text:
        return False, f"params={params}"
    return True, ""


def main(runs: int, only: str = ""):
    summary = {}
    for label, cases in (("close", CLOSE), ("regression", [(t, w, "") for t, w in REGRESSION])):
        if only and only != label:
            continue
        ok = 0
        per_tool = {}
        for text, want, word in cases:
            for _ in range(runs):
                _, reply, calls = run(text)
                hit, note = judge(want, word, calls)
                ok += hit
                good, total = per_tool.get(want, (0, 0))
                per_tool[want] = (good + hit, total + 1)
                print(f"   {'ok  ' if hit else 'MISS'} {text!r} {note or ''} {'' if calls else repr(reply[:50])}",
                      flush=True)
        summary[label] = {"correct": f"{ok}/{len(cases) * runs}",
                          **({t: f"{g}/{n}" for t, (g, n) in per_tool.items()} if label == "close" else {})}
        print(label, summary[label], flush=True)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 1, sys.argv[2] if len(sys.argv) > 2 else "")
