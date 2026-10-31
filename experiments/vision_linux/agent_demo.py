"""
Fase 0 Linux - percobaan agent kecil: qwen3-vl menggerakkan mouse dan keyboard.

Loop amati -> pilih aksi -> bertindak -> amati ulang, pada jendela uji yang dibuka
sendiri oleh skrip ini (Kalkulator, Xed). Model memilih ELEMEN bernomor; koordinat
klik diambil dari kotak AT-SPI elemen itu, bukan tebakan piksel model.

Kill switch: gerakkan mouse ke pojok kiri atas layar untuk menghentikan agent.

Strategi:
  step - tiap langkah model memilih SATU aksi berikutnya
  plan - model menulis seluruh urutan aksi dulu, lalu dijalankan sambil diamati;
         bila urutan habis tapi tujuan belum tercapai, model menyusun rencana baru (maks. 2 kali)
  names - seperti plan, tetapi model hanya menyebut NAMA tombol berurutan, TANPA gambar;
          kode yang mencocokkannya ke elemen AT-SPI (nama yang tidak ada diketik lewat keyboard)

Jalankan dengan Python sistem (pyatspi):
    /usr/bin/python3 experiments/vision_linux/agent_demo.py [model] [folder_output] [step|plan]
"""

import base64
import io
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pyatspi
from PIL import ImageGrab

sys.path.insert(0, str(Path(__file__).parent))
from atspi_spike import collect, draw_som, find_frame, wait_new_window, window_geometry, windows  # noqa: E402

OLLAMA = "http://localhost:11434/api/chat"
MAX_STEPS = 10
PROMPT = """You control a Linux desktop with the mouse and keyboard. Goal: {goal}
Current window: {title}
{state}Actions done so far: {history}
Elements on screen are marked with numbers in the image:
{elements}
Choose the NEXT single action. Answer ONLY with one JSON object:
{{"click": <element number>}} or {{"type": "<text>"}} or {{"key": "<key like Return or ctrl+a>"}} or {{"done": true}}"""
PLAN_PROMPT = """You control a Linux desktop with the mouse and keyboard. Goal: {goal}
Current window: {title}
{state}Actions done so far: {history}
Elements on screen are marked with numbers in the image:
{elements}
Write ALL remaining actions needed to reach the goal, in order. Answer ONLY with a JSON list, e.g.
[{{"click": 4}}, {{"type": "hello"}}, {{"key": "Return"}}]. Each item is one click, one typed text, or one key."""
NAMES_PROMPT = """You control a Linux desktop. Goal: {goal}
Current window: {title}
{state}Actions done so far: {history}
Buttons and fields on screen: {names}
Think about which buttons must be pressed, in order, to reach the goal. Answer ONLY with a JSON list of
button names exactly as written above, e.g. ["File", "Save"]. To type text instead, write {{"type": "<text>"}}."""
MAX_PLANS = 2

TASKS = [
    # (nama, perintah, tujuan, cek berhasil dari teks elemen)
    ("kalkulator", ["gnome-calculator"], "Calculate 12 + 7 using the calculator buttons and show the result.",
     lambda texts: any(re.fullmatch(r"\s*19\s*", t) for t in texts)),
    ("xed", ["xed", "--new-window"], "Write the text 'Halo dari Miku' in the document.",
     lambda texts: any("Halo dari Miku" in t for t in texts)),
]


def chat(model, prompt, image_png=None):
    message = {"role": "user", "content": prompt}
    if image_png:
        message["images"] = [base64.b64encode(image_png).decode()]
    body = json.dumps({
        "model": model, "stream": False,
        "messages": [message],
        "options": {"temperature": 0.2, "num_predict": 60, "num_ctx": 8192},
    }).encode()
    request = urllib.request.Request(OLLAMA, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read())["message"]["content"]


def frame_texts(frame, limit=500):
    """
    Isi semua field yang bisa diedit, termasuk yang tidak punya aksi (tampilan Kalkulator
    berperan "editbar"). Label sengaja dilewati: riwayat Kalkulator tersimpan antar-sesi.
    """
    out, stack, seen = [], [frame], 0
    while stack and seen < limit:
        acc = stack.pop()
        seen += 1
        try:
            if acc.getState().contains(pyatspi.STATE_EDITABLE):
                text = acc.queryText()
                value = text.getText(0, text.characterCount)
                if value.strip():
                    out.append(value)
        except NotImplementedError:
            pass
        except Exception:  # elemen bisa hilang saat dibaca
            continue
        stack.extend(acc[i] for i in reversed(range(acc.childCount)))
    return out


def parse_plan(reply):
    match = re.search(r"\[.*\]", reply or "", re.DOTALL)
    try:
        items = json.loads(match.group(0)) if match else []
    except json.JSONDecodeError:
        return []
    return [a for a in (parse_action(json.dumps(i)) for i in items if isinstance(i, dict)) if a]


def parse_action(reply):
    """JSON aksi pertama dari balasan; nomor elemen dirapikan ("12", [12] -> 12)."""
    match = re.search(r"\{.*?\}", reply or "", re.DOTALL)
    try:
        action = json.loads(match.group(0)) if match else None
    except json.JSONDecodeError:
        return None
    if not isinstance(action, dict):
        return None
    if "click" in action:
        value = action["click"]
        value = value[0] if isinstance(value, list) and value else value
        try:
            action["click"] = int(value)
        except (TypeError, ValueError):
            return None
    return action


def mouse_in_corner():
    out = subprocess.run(["xdotool", "getmouselocation", "--shell"], capture_output=True, text=True).stdout
    pos = dict(line.split("=") for line in out.split() if "=" in line)
    return int(pos.get("X", 99)) < 5 and int(pos.get("Y", 99)) < 5


def act(action, elements, wid):
    subprocess.run(["xdotool", "windowactivate", "--sync", wid])
    if "click" in action:
        x, y, w, h = elements[int(action["click"]) - 1]["rect"]
        subprocess.run(["xdotool", "mousemove", str(x + w // 2), str(y + h // 2), "click", "1"])
    elif "type" in action:
        subprocess.run(["xdotool", "type", "--delay", "40", str(action["type"])])
    elif "key" in action:
        subprocess.run(["xdotool", "key", str(action["key"]).replace(" ", "")])
    time.sleep(0.6)


def observe(frame, wid, name, step, out):
    bounds = window_geometry(wid)
    elements, _ = collect(frame, bounds, keep_accessible=True)
    texts = frame_texts(frame)
    x, y, w, h = bounds
    shot = ImageGrab.grab(bbox=(x, y, x + w, y + h))
    som = out / f"{name}_step{step}.png"
    draw_som(shot, elements, (x, y), som)
    listing = "\n".join(f"{i}: {e['type']} '{e['name']}'" for i, e in enumerate(elements, 1))
    state = "Text fields now: " + " | ".join(repr(t) for t in texts) + "\n" if texts else ""
    return elements, texts, som, listing, state


def describe(action, elements):
    label = json.dumps(action, ensure_ascii=False)
    if "click" in action:
        n = action["click"]
        label += f" ({elements[n - 1]['type']} '{elements[n - 1]['name']}')" if 0 < n <= len(elements) else " (nomor tidak ada)"
    return label


def names_to_actions(reply, elements):
    """["1", "+", {"type": ".."}] -> klik elemen bernama sama; nama yang tidak ada diketik."""
    match = re.search(r"\[.*\]", reply or "", re.DOTALL)
    try:
        items = json.loads(match.group(0)) if match else []
    except json.JSONDecodeError:
        return []
    by_name = {e["name"]: i for i, e in enumerate(elements, 1) if e["name"].strip()}
    actions = []
    for item in items:
        if isinstance(item, dict) and "type" in item:
            actions.append({"type": str(item["type"])})
        elif isinstance(item, (str, int)) and str(item) in by_name:
            actions.append({"click": by_name[str(item)]})
        elif isinstance(item, (str, int)):
            actions.append({"type": str(item)})
    return actions


def run_plan(model, name, goal, title, succeeded, frame, wid, out, strategy):
    """Strategi plan: susun urutan aksi, jalankan sambil mengamati, susun ulang bila perlu."""
    history, steps, step = [], [], 0
    for attempt in range(1, MAX_PLANS + 1):
        elements, texts, som, listing, state = observe(frame, wid, name, step, out)
        if succeeded(texts):
            return True, steps
        t0 = time.time()
        if strategy == "names":
            names = sorted({e["name"] for e in elements if e["name"].strip()})
            reply = chat(model, NAMES_PROMPT.format(goal=goal, title=title, state=state,
                                                    history=", ".join(history) or "none",
                                                    names=json.dumps(names, ensure_ascii=False)))
            plan = names_to_actions(reply, elements)
        else:
            reply = chat(model, PLAN_PROMPT.format(goal=goal, title=title, state=state,
                                                   history=", ".join(history) or "none", elements=listing),
                         som.read_bytes())
            plan = parse_plan(reply)
        seconds = time.time() - t0
        print(f"  rencana {attempt}: {[describe(a, elements) for a in plan]} [{seconds:.1f} s]", flush=True)
        steps.append({"plan": plan, "llm_seconds": round(seconds, 2)})
        for action in plan[:MAX_STEPS]:
            if mouse_in_corner():
                print("  kill switch: mouse di pojok, berhenti")
                return False, steps
            if "click" in action and not 0 < action["click"] <= len(elements):
                history.append(f"invalid element {action['click']}")
                break
            step += 1
            act(action, elements, wid)
            history.append(describe(action, elements))
            if succeeded(frame_texts(frame)):
                return True, steps
    return False, steps


def run_task(model, name, argv, goal, succeeded, out: Path, strategy="step"):
    if name == "xed" and subprocess.run(["pgrep", "-x", "xed"], capture_output=True).returncode == 0:
        print(f"{name}: dilewati, xed milik user sedang terbuka")
        return None
    before = windows()
    proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    wid, (pid, title) = wait_new_window(before)
    history, steps, started = [], [], time.time()
    ok = False
    try:
        frame = find_frame(pid, title)
        if strategy in ("plan", "names"):
            ok, steps = run_plan(model, name, goal, title, succeeded, frame, wid, out, strategy)
        for step in range(1, MAX_STEPS + 1) if strategy == "step" else ():
            if mouse_in_corner():
                print("  kill switch: mouse di pojok, berhenti")
                break
            elements, texts, som, listing, state = observe(frame, wid, name, step, out)
            if succeeded(texts):
                ok = True
                break
            t0 = time.time()
            reply = chat(model, PROMPT.format(goal=goal, title=title, state=state,
                                              history=", ".join(history) or "none", elements=listing),
                         som.read_bytes())
            seconds = time.time() - t0
            action = parse_action(reply)
            label = describe(action, elements) if action else f"tidak terbaca: {reply[:80]!r}"
            print(f"  langkah {step}: {label} [{seconds:.1f} s]", flush=True)
            steps.append({"step": step, "action": action, "llm_seconds": round(seconds, 2)})
            if not action or action.get("done"):
                break
            if "click" in action and not 0 < action["click"] <= len(elements):
                history.append(f"invalid element {action['click']}")
                continue
            act(action, elements, wid)
            history.append(label)
        if not ok:  # aksi terakhir mungkin sudah menyelesaikan tujuan
            ok = succeeded(frame_texts(frame))
    finally:
        if name == "xed":
            proc.terminate()  # tanpa dialog "simpan perubahan?"
        else:
            subprocess.run(["wmctrl", "-ic", wid])
    row = {"task": name, "strategy": strategy, "success": ok, "llm_calls": len(steps),
           "seconds": round(time.time() - started, 1),
           "llm_median_s": sorted(s["llm_seconds"] for s in steps)[len(steps) // 2] if steps else 0}
    print(row, flush=True)
    return row


def main(model):
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/tmp")
    strategy = sys.argv[3] if len(sys.argv) > 3 else "step"
    out.mkdir(parents=True, exist_ok=True)
    rows = [run_task(model, *task, out, strategy=strategy) for task in TASKS]
    print(json.dumps([r for r in rows if r]))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "qwen3-vl:4b-instruct")
