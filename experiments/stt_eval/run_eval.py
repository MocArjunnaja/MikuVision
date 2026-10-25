"""Ukur pipeline STT MikuVision pada set uji. Jalankan dari root repo: python run_eval.py <dir_set> <label>."""
import json, re, statistics, sys, time, types, unicodedata
from pathlib import Path
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")
import soundfile as sf

SET = Path(sys.argv[1]); LABEL = sys.argv[2]
NUM = {"30": "tiga puluh", "12": "dua belas"}

def norm(t):
    t = unicodedata.normalize("NFKC", t.lower())
    t = t.replace("%", " persen")
    for d, w in NUM.items():
        t = re.sub(rf"\b{d}\b", w, t)
    if re.search(r"[぀-ヿ]", t):  # nama aplikasi berhuruf Latin di kalimat Jepang dianggap sama
        for latin, kana in (("google chrome", "グーグルクローム"), ("youtube", "ユーチューブ")):
            t = t.replace(latin, kana)
    return re.sub(r"[\s\W_]+", "", t)

def cer(ref, hyp):
    r, h = norm(ref), norm(hyp)
    if not r:
        return 0.0 if not h else 1.0
    d = list(range(len(h) + 1))
    for i, rc in enumerate(r, 1):
        prev, d[0] = d[0], i
        for j, hc in enumerate(h, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (rc != hc))
    return min(d[-1] / len(r), 1.0)

def script_lang(t):
    if not t: return None
    return "ja" if re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", t) else "id"

from core.voice_input import VoiceInput
vi = VoiceInput(); assert vi.initialize()
import os, inspect, core.voice_input as vimod
if "languages" in inspect.signature(vi.transcribe).parameters:
    vimod.STT_DENOISE = os.environ.get("DENOISE") == "1"
    prompt = os.environ.get("PROMPT", "1") == "1"
    stt = lambda a: vi.transcribe(a, languages=("ja", "id"), use_initial_prompt=prompt, verbose_logging=False)
else:
    import miku
    fake = types.SimpleNamespace(voice_input=vi, character=types.SimpleNamespace(lang="ja"))
    fake._normalize_text = miku.MikuCLI._normalize_text
    fake._score_transcript_intent = types.MethodType(miku.MikuCLI._score_transcript_intent, fake)
    stt = lambda a: miku.MikuCLI._transcribe_best_effort(fake, a, language_order=["ja", "id"], wake_mode=False)

man = json.loads((SET / "manifest.json").read_text(encoding="utf-8"))
stt(sf.read(SET / "clips" / man[0]["file"], dtype="float32")[0])  # warmup
rows = []
for m in man:
    audio, _ = sf.read(SET / "clips" / m["file"], dtype="float32")
    t = time.time(); hyp = stt(audio); dt = time.time() - t
    rows.append({**m, "hyp": hyp, "cer": round(cer(m["ref"], hyp), 3), "lang_ok": script_lang(hyp) == m["lang"], "s": round(dt, 2)})
    print(f"{m['file']:16} {dt:4.2f}s cer={rows[-1]['cer']:.2f} {hyp!r}", flush=True)

def summary(sel):
    rs = [r for r in rows if sel(r)]
    return {"n": len(rs), "cer": round(statistics.mean(r["cer"] for r in rs), 3),
            "exact": sum(r["cer"] == 0 for r in rs), "lang_ok": sum(r["lang_ok"] for r in rs),
            "median_s": round(statistics.median(r["s"] for r in rs), 2)}
out = {"label": LABEL,
       "id_clean": summary(lambda r: r["lang"] == "id" and r["cond"] == "clean"),
       "id_noisy": summary(lambda r: r["lang"] == "id" and r["cond"] == "noisy"),
       "ja_clean": summary(lambda r: r["lang"] == "ja" and r["cond"] == "clean"),
       "ja_noisy": summary(lambda r: r["lang"] == "ja" and r["cond"] == "noisy"),
       "noise_false_text": sum(bool(r["hyp"]) for r in rows if r["cond"] == "noise"),
       "rows": rows}
(SET / f"result_{LABEL}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
for k, v in out.items():
    if k != "rows": print(k, v)
