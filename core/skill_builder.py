"""
"Simpan ini sebagai skill" (docs/PLAN_SKILLS.md S2): Miku menyusun SKILL.md dari percakapan
yang baru selesai, menunjukkannya, dan menyimpannya ke data/skills/ setelah user setuju.

- Dipicu oleh kalimat berisi "skill"/"スキル" + kata kerja simpan, bukan oleh LLM, supaya
  permintaan ini tidak pernah tersasar ke tool lain.
- Langkah skill disusun oleh kode dari tool call yang tadi benar-benar berhasil, lengkap dengan
  parameternya, jadi tidak ada tool karangan. LLM (satu panggilan, JSON schema) hanya memilih nama,
  pemicu, tool call mana yang termasuk tugas, dan parameter mana yang diambil dari ucapan user setiap
  kali (isi dokumen) dan mana yang tetap (volume 20, folder Downloads). Saat LLM yang menulis langkahnya
  sendiri, qwen3:4b mengarang tool dan menyalin isi dokumen lama: pakai ulang benar 6/15.
- Draf divalidasi dengan parser yang sama dengan skill dari file (tool terdaftar, panjang petunjuk).
- Pemicu yang terlalu umum ("volume", "buka musik") dibuang supaya skill tidak membajak perintah biasa.

Juga untuk slash command: /skill new <nama> (template tanpa LLM) dan /skill forget <nama>.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml

from core.desktop.app_search import normalize
from core.skills import SKILLS
from core.tools import registry
from core import user_skills
from core.user_skills import FORBIDDEN_TOOLS, SKILL_FILE, UserSkill, load_user_skills, parse_skill_text

# "simpan ini sebagai skill", "jadikan skill", "save this as a skill", 「スキルとして保存して」, 「スキルにして」.
# Bukan "buatkan dokumen tentang skill komunikasi": kata kerja lemah (buat/bikin/make) hanya boleh
# diikuti kata pengisi sebelum "skill", dan kata kerja kuat tidak boleh melewati "tentang"/"about".
_FILLER = r"(?:\s+(?:ini|itu|tadi|barusan|yang|cara|langkah|jadi|jadiin|menjadi|sebagai|this|that|it|into|as|a|an))"
SAVE_REQUEST = re.compile(
    r"\b(?:simpan|simpen|jadikan|jadiin|save)\b(?:\s+(?!(?:tentang|about|mengenai|soal)\b)\S+){0,4}?\s+skills?\b"
    r"|\b(?:buat|buatkan|bikin|bikinin|make|turn)\b" + _FILLER + r"{0,3}\s+skills?\b"
    r"|スキル(?:を|として|に)?(?:保存|登録|作って)|スキルに(?:して|する)",
    re.IGNORECASE,
)
HISTORY_MESSAGES = 12
MAX_TRIGGERS = 6
MAX_STEPS = 5
# Isi dokumen, pesan, dan teks yang diketik selalu sekali pakai, begitu juga teks sepanjang LONG_VALUE:
# selalu diambil dari ucapan user, walaupun LLM lupa menandainya
FREE_TEXT_PARAMS = {"content", "title", "text", "message", "new_text", "target_text"}
LONG_VALUE = 60
# Hanya parameter ini yang boleh diambil dari user bila LLM menandainya. Sisanya (volume, folder,
# aplikasi) selalu tetap: qwen3:4b kadang menandai "Downloads" sebagai isian, lalu bertanya setiap kali
VARIABLE_PARAMS = FREE_TEXT_PARAMS | {"query", "contact_name", "key", "value"}
HINT_CHARS = 60

# Nama yang disebut user: "namanya mode fokus", "...sebagai skill siap kerja", 「名前はジャズタイム」, "called x"
_NAME = re.compile(
    r"[\"'「『](?P<q>[^\"'」』]{2,40})[\"'」』]"
    r"|(?:namanya|bernama|dengan nama|named|called|名前は|名前を)\s*[:：]?\s*(?P<a>[^\"'「」『』。.,!?！？]+)"
    r"|\bskills?\b\s+(?P<b>[^\"'「」『』。.,!?！？]+)$"
    r"|スキル(?:名|の名前)は\s*(?P<c>[^「」『』。、！？]+)",
    re.IGNORECASE,
)
_NAME_FILLER = {"ya", "dong", "deh", "aja", "saja", "please", "ok", "oke", "yah", "nya", "baru"}

SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "description": {"type": "string"},
        "triggers": {"type": "array", "items": {"type": "string"}},
        "steps": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "call": {"type": "integer"},
                "from_user": {"type": "array", "items": {"type": "string"}},
                "hint": {"type": "string"},
            },
            "required": ["call", "from_user", "hint"],
        }},
    },
    "required": ["name", "description", "triggers", "steps"],
}

PROMPT = """You turn a finished conversation between a user and Miku (a desktop assistant) into a reusable skill, so that next time the user can ask for the same kind of task in one short sentence.

Conversation (oldest first):
{transcript}

The user now says: "{request}"

Tool calls Miku made successfully, numbered:
{calls}

Write the skill as JSON:
- name: {name_rule}
- description: one sentence saying what the skill does.
- triggers: 2-5 short phrases (2-5 words) the user would say to ask for the whole task again, in the languages the user used. Not a plain request for only one of the steps (such as "buka folder downloads"), and no words from the save request.
- steps: the numbered calls that belong to the task, in order (usually all of them). For each step: "call" = its number; "from_user" = names of the parameters whose value must come from the user's new request every time (such as document content or a list the user dictates); every other parameter keeps the value used above. "hint" = for from_user parameters, at most 8 words saying what to put there, without this time's values (e.g. "daftar barang, satu per baris"); empty otherwise. Do not ask for details the user did not give."""


@dataclass
class Call:
    tool: str
    args: Dict[str, Any]
    turn: str = field(default="", compare=False)  # ucapan user yang memicu tool call ini

    def __str__(self) -> str:
        args = ", ".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in self.args.items())
        return f"{self.tool}({args})"


@dataclass
class Draft:
    name: str
    description: str
    triggers: List[str]
    tools: List[str]
    steps: List[str]

    def to_markdown(self) -> str:
        meta = {"name": self.name, "description": self.description,
                "triggers": self.triggers, "tools": self.tools}
        front = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, default_flow_style=None, width=1000)
        body = "\n".join(f"{i}. {step}" for i, step in enumerate(self.steps, 1))
        return f"---\n{front}---\n{body}\n"


@dataclass
class SaveResult:
    status: str  # saved | cancelled | no_steps | failed
    message: str  # untuk log/GUI ("✅ Skill disimpan: ...")
    skill: Optional[UserSkill] = None
    path: Optional[Path] = None
    used_tools: List[str] = field(default_factory=list)


def wants_to_save(text: str) -> bool:
    return bool(SAVE_REQUEST.search(text or ""))


def slugify(name: str) -> str:
    return re.sub(r"[^\w]+", "-", name.strip().lower()).strip("-_")[:40] or "skill"


def skill_path(name: str) -> Path:
    # Dibaca saat dipanggil (bukan diimpor dari config) supaya test bisa mengarahkannya ke folder sementara
    return user_skills.USER_SKILLS_DIR / slugify(name) / SKILL_FILE


def _strip_emotion(text: str) -> str:
    return re.sub(r"\[EMOTION:[^\]]*\]", "", text or "").strip()


def recent_activity(brain, limit: int = HISTORY_MESSAGES) -> Tuple[List[str], List[Call]]:
    """(baris percakapan terakhir, tool call yang berhasil berurutan beserta argumennya)."""
    if brain.memory and brain.memory.current_context:
        messages = [(m.role, m.content, m.metadata or {}) for m in brain.memory.current_context.messages[-limit:]]
    else:
        messages = [(m.get("role"), m.get("content", ""), m) for m in brain.conversation_history[-limit:]]
    lines: List[str] = []
    calls: List[Call] = []
    pending: List[Call] = []  # tool call yang hasilnya belum muncul, dipasangkan dengan pesan role tool
    user_text = ""
    for role, content, meta in messages:
        if role == "user":
            user_text = content.strip()
            lines.append(f"User: {user_text}")
        elif role == "assistant":
            for call in meta.get("tool_calls") or []:
                function = call.get("function", {})
                pending.append(Call(function.get("name", ""), dict(function.get("arguments") or {}), user_text))
                lines.append(f"Miku called {pending[-1]}")
            if _strip_emotion(content):
                lines.append(f"Miku: {_strip_emotion(content)[:300]}")
        elif role == "tool":
            name = meta.get("tool_name", "")
            lines.append(f"Result of {name}: {content[:200]}")
            call = next((c for c in pending if c.tool == name), Call(name, {}, user_text))
            if call in pending:
                pending.remove(call)
            if content.startswith("SUKSES") and name not in FORBIDDEN_TOOLS and registry.get_tool(name) \
                    and (not calls or str(calls[-1]) != str(call)):
                calls.append(call)
    return lines, calls


# Kata kerja dan kata pengisi yang ada di banyak perintah biasa; tanpa kata lain, pemicu terlalu umum
COMMON_WORDS = {
    "simpan", "skill", "cara", "tadi", "barusan", "sebelumnya",
    "putar", "putarkan", "buka", "bukakan", "tutup", "cari", "carikan", "buat", "buatkan", "bikin", "tolong",
    "dong", "yang", "aku", "saya", "mau", "ingin", "nyalakan", "matikan", "kecilkan", "besarkan", "atur",
    "dan", "lalu", "ini", "itu", "please", "play", "open", "the", "and", "set", "turn", "make",
}


def _too_generic(trigger: str) -> bool:
    """Pemicu yang akan membajak perintah biasa ("volume 20", "putar lagu", "電卓を開いて").

    Kata yang sudah memicu skill bawaan, angka, partikel hiragana, dan kata kerja umum dibuang;
    pemicu dipakai hanya bila masih tersisa kata yang khas ("dokumen rapat" → "rapat").
    """
    rest = trigger
    for skill in SKILLS:
        rest = skill.triggers.sub(" ", rest)
    rest = re.sub(r"[ぁ-ゖー]+", " ", re.sub(r"[\d_]+", " ", rest))
    distinctive = [w for w in rest.split()
                   if (w.isascii() and len(w) >= 3 and w not in COMMON_WORDS) or (not w.isascii() and len(w) >= 2)]
    return len(trigger) < (3 if trigger.isascii() else 2) or not distinctive


def clean_triggers(triggers: List[str], name: str, single_steps: List[str] = ()) -> List[str]:
    """single_steps: ucapan tugas yang hanya mencakup sebagian langkah skill ("buka folder downloads"
    dari skill "siap kerja"); pemicu yang ada di dalamnya akan membajak perintah biasa itu."""
    single_steps = [normalize(s) for s in single_steps]
    cleaned: List[str] = []
    for trigger in triggers:
        trigger = normalize(str(trigger).strip().strip("\"'「」『』"))
        if (trigger and trigger != normalize(name) and trigger not in cleaned and not _too_generic(trigger)
                and not wants_to_save(trigger) and "skill" not in trigger.split() and "スキル" not in trigger
                and not any(trigger in step for step in single_steps)):
            cleaned.append(trigger)
    return cleaned[:MAX_TRIGGERS]


def requested_name(request: str) -> str:
    """Nama skill yang disebut user di permintaan simpan, atau "" (LLM yang memberi nama)."""
    match = _NAME.search(request or "")
    if not match:
        return ""
    name = next(g for g in match.groups() if g is not None)
    name = re.sub(r"^(?:called|named|namanya|bernama|dengan nama|nama)\s+", "", name.strip(), flags=re.IGNORECASE)
    words = [w for w in name.split() if w.lower() not in _NAME_FILLER]
    return " ".join(words).strip().lower()[:40]


def _japanese(text: str) -> bool:
    return sum(1 for ch in text if ord(ch) > 0x3000) > len(text) / 4


def _opening_step(tools: List[str], may_ask: bool, japanese: bool) -> str:
    """Langkah pembuka yang pasti: model kecil cenderung bertanya dulu atau hanya memanggil satu tool."""
    names = ", ".join(dict.fromkeys(tools))
    if japanese:
        # 確認なしで, bukan 質問せずに: _ASK_STEP (user_skills) membaca 質問/聞 sebagai "skill ini boleh bertanya dulu"
        return (f"ユーザーが内容を少しでも言っていれば、確認なしで次のツールを同じ返事の中で順番にすべて呼ぶ: {names}。"
                f"内容がまったくなければ一文で聞く" if may_ask
                else f"確認なしで、次のツールを同じ返事の中で順番にすべて呼ぶ: {names}")
    return (f"Bila user sudah menyebut isinya, walau singkat, langsung panggil semua tool ini berurutan dalam "
            f"satu balasan, tanpa bertanya: {names}. Tanyakan dalam satu kalimat hanya bila isinya sama sekali "
            f"belum disebut" if may_ask
            else f"Jangan bertanya dulu: panggil semua tool ini berurutan dalam satu balasan: {names}")


def _short_hint(hint: str) -> str:
    """Petunjuk isian maksimal HINT_CHARS, dipotong di batas kata: petunjuk panjang ("tanggal, waktu,
    tempat, ...") membuat Miku menanyakan detail yang tidak perlu."""
    hint = re.sub(r"\s+", " ", hint).strip().strip(".")
    if len(hint) <= HINT_CHARS:
        return hint
    return hint[:HINT_CHARS].rsplit(" ", 1)[0].rstrip(",;:")


def _render_step(call: Call, from_user: List[str], hint: str, name: str, japanese: bool) -> str:
    parts = []
    for param in [p.name for p in registry.get_tool(call.tool).params]:
        if param in from_user:
            source = "今回のユーザーの依頼から" if japanese else "dari permintaan user saat ini"
            parts.append(f"{param} = {source}" + (f" ({hint})" if hint else ""))
        elif param == "filename" and param in call.args:
            # Nama file lama sering sekali pakai ("rapat_anggaran"); pakai nama skill
            parts.append(f'{param} = "{slugify(name).replace("-", "_").title()}"')
        elif param in call.args:
            parts.append(f"{param} = {json.dumps(call.args[param], ensure_ascii=False)}")
    return (f"{call.tool} を呼ぶ: " if japanese else f"Panggil {call.tool}: ") + "; ".join(parts)


def draft_skill(brain, request: str, transcript: List[str], calls: List[Call]) -> Tuple[Optional[Draft], str]:
    """Minta LLM memilih nama, pemicu, dan parameter dari user; langkahnya disusun dari tool call. (draf, "") atau (None, alasan)."""
    fixed_name = requested_name(request)
    name_rule = (f'exactly "{fixed_name}" (the user chose it).' if fixed_name else
                 "1-4 lowercase words in the user's language describing the whole task, "
                 "e.g. \"mode belajar\" or \"日報\".")
    numbered = "\n".join(f"{i}. {call}" for i, call in enumerate(calls, 1))
    prompt = PROMPT.format(transcript="\n".join(transcript), request=request, calls=numbered, name_rule=name_rule)
    try:
        data = brain.generate_json(prompt, SCHEMA)
    except Exception as e:
        return None, f"LLM gagal menyusun skill: {e}"

    name = fixed_name or re.sub(r"\s+", " ", str(data.get("name") or "")).strip().strip("\"'「」『』").lower()[:40]
    if not name:
        return None, "LLM tidak memberi nama skill"

    chosen: List[Tuple[Call, List[str], str]] = []
    for step in data.get("steps") or []:
        index = step.get("call") if isinstance(step, dict) else None
        if not isinstance(index, int) or not 1 <= index <= len(calls) or any(c is calls[index - 1] for c, _, _ in chosen):
            continue
        chosen.append((calls[index - 1], [str(p) for p in step.get("from_user") or []], str(step.get("hint") or "")))
    if not chosen:  # LLM tidak memilih dengan benar: semua tool call, berurutan
        chosen = [(call, [], "") for call in calls]
    chosen.sort(key=lambda item: calls.index(item[0]))
    chosen = chosen[:MAX_STEPS - 1]

    japanese = _japanese(request)
    steps: List[str] = []
    may_ask = False  # ada nilai yang harus datang dari user: skill boleh menanyakannya bila belum disebut
    for call, from_user, hint in chosen:
        params = [p.name for p in registry.get_tool(call.tool).params]
        from_user = [p for p in params if (p in from_user and p in VARIABLE_PARAMS)
                     or (p in FREE_TEXT_PARAMS and p in call.args)
                     or (isinstance(call.args.get(p), str) and len(call.args[p]) > LONG_VALUE)]
        may_ask = may_ask or bool(from_user)
        steps.append(_render_step(call, from_user, _short_hint(hint) if from_user else "", name, japanese))
    tools = [call.tool for call, _, _ in chosen]
    steps.insert(0, _opening_step(tools, may_ask, japanese))
    turns = list(dict.fromkeys(call.turn for call, _, _ in chosen))
    single_steps = turns if len(turns) > 1 else []
    return Draft(name, str(data.get("description") or "").strip(),
                 clean_triggers(data.get("triggers") or [], name, single_steps), list(dict.fromkeys(tools)), steps), ""


def save_from_chat(brain, request: str, confirm: Optional[Callable[[str], bool]]) -> SaveResult:
    """Susun skill dari percakapan terakhir, tunjukkan, dan simpan bila user setuju."""
    transcript, calls = recent_activity(brain)
    used = list(dict.fromkeys(call.tool for call in calls))
    if not calls:
        return SaveResult("no_steps", "Belum ada tool yang berhasil dijalankan di percakapan ini; tidak ada yang bisa disimpan.")

    draft, error = draft_skill(brain, request, transcript, calls)
    if draft is None:
        return SaveResult("failed", error, used_tools=used)
    path = skill_path(draft.name)
    text = draft.to_markdown()
    skill, error = parse_skill_text(text, path)
    if skill is None:
        return SaveResult("failed", f"Draf skill tidak valid: {error}", used_tools=used)

    replaces = " (menimpa skill dengan nama yang sama)" if path.exists() else ""
    summary = f"Simpan skill '{skill.name}' ke {path}{replaces}?\n\n{text}"
    if not (confirm and confirm(summary)):
        return SaveResult("cancelled", f"Skill '{skill.name}' tidak disimpan (tidak dikonfirmasi).", skill, used_tools=used)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return SaveResult("saved", f"Skill '{skill.name}' disimpan: {path}", skill, path, used)


REPLIES = {
    "ja": {
        "saved": ("スキル『{name}』を保存したよ！次からは『{trigger}』って言ってね。", "happy"),
        "cancelled": ("わかった、スキルは保存しないでおくね。", "neutral"),
        "no_steps": ("まだスキルにできる手順がないよ。先に一緒にやってみて、うまくいったら『スキルとして保存して』って言ってね。",
                     "confused"),
        "failed": ("ごめんね、スキルをうまくまとめられなかった…もう一回言ってみて。", "sad"),
    },
    "id": {
        "saved": ("Skill '{name}' tersimpan! Lain kali cukup bilang '{trigger}'.", "happy"),
        "cancelled": ("Oke, skill-nya tidak disimpan.", "neutral"),
        "no_steps": ("Belum ada langkah yang bisa dijadikan skill. Lakukan dulu tugasnya bersama Miku, "
                     "lalu bilang 'simpan ini sebagai skill'.", "confused"),
        "failed": ("Maaf, Miku belum berhasil menyusun skill-nya. Coba ulangi ya.", "sad"),
    },
}


def reply_for(result: SaveResult, lang: str) -> Tuple[str, str]:
    text, emotion = REPLIES.get(lang, REPLIES["id"])[result.status]
    name = result.skill.name if result.skill else ""
    trigger = next((t for t in result.skill.triggers if t != normalize(name)), name) if result.skill else ""
    return text.format(name=name, trigger=trigger), emotion


# ───────────────────────── Slash command ─────────────────────────

TEMPLATE = """---
name: {name}
description: Tulis satu kalimat tentang apa yang dilakukan skill ini
triggers: [{name}]
tools: []
---
1. Tulis langkahnya: tool apa yang dipanggil, dengan parameter apa.
"""


def new_template(name: str) -> str:
    """/skill new <nama>: template SKILL.md untuk diisi sendiri (tanpa LLM)."""
    name = name.strip()
    if not name:
        return "Pakai: /skill new <nama>. Atau bilang 'simpan ini sebagai skill' setelah Miku menyelesaikan tugas."
    path = skill_path(name)
    if path.exists():
        return f"Skill '{name}' sudah ada: {path}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(TEMPLATE.format(name=yaml.safe_dump(name, allow_unicode=True).splitlines()[0]), encoding="utf-8")
    available = sorted(t["function"]["name"] for t in registry.get_all_tools_schema()
                       if t["function"]["name"] not in FORBIDDEN_TOOLS)
    return (f"Template dibuat: {path}\n"
            f"Isi description, triggers, tools, dan langkahnya. Skill dimuat setelah 'tools' diisi (cek /skills).\n"
            f"Tool yang bisa dipakai: {', '.join(available)}")


def forget(name: str, confirm: Optional[Callable[[str], bool]]) -> str:
    """/skill forget <nama>: hapus skill buatan user (contoh bawaan di skills/ tidak bisa dihapus)."""
    name = name.strip()
    if not name:
        return "Pakai: /skill forget <nama>. Lihat /skills."
    folder = user_skills.USER_SKILLS_DIR
    mine, _ = load_user_skills([folder])
    skill = mine.get(name.lower())
    if skill is None:
        if name.lower() in load_user_skills()[0]:
            return (f"'{name}' adalah contoh bawaan di skills/ dan tidak dihapus. Buat skill dengan nama "
                    f"yang sama di data/skills/ untuk menggantinya.")
        return f"Skill '{name}' tidak ada di data/skills/. Lihat /skills."
    root = folder.resolve()
    if root not in skill.path.resolve().parents:
        return f"Skill '{skill.name}' tidak berada di {folder}; tidak dihapus."
    if not (confirm and confirm(f"Hapus skill '{skill.name}' ({skill.path})?")):
        return f"Skill '{skill.name}' tidak dihapus."
    skill.path.unlink()
    try:
        skill.path.parent.rmdir()  # hanya bila foldernya kosong
    except OSError:
        pass
    return f"Skill '{skill.name}' dihapus."
