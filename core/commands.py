"""
Slash commands - perintah langsung tanpa melewati LLM (cepat dan pasti).

Dipakai mode teks (miku.py --text) dan kolom input GUI.
"""

from typing import Any, Callable, Dict, Optional

from core import long_term_memory
from core.ai_brain import AIBrain
from core.desktop.app_search import normalize
from core.routines import load_routines
from core.skills import SKILLS
from core.user_skills import find_user_skill, load_user_skills

HELP_TEXT = """Perintah:
  /help                 daftar perintah
  /clear                hapus riwayat percakapan sesi ini
  /usage                pemakaian token sesi ini
  /memory               fakta yang Miku ingat
  /forget <key>         hapus satu fakta
  /skills               kemampuan Miku (bawaan + skill buatan user)
  /skill <nama>         isi satu skill buatan user (petunjuk, pemicu, tool)
  /routines             daftar routine
  /routine <nama>       jalankan routine
  /sessions             5 sesi terakhir
  /resume [session_id]  lanjutkan sesi (default: terakhir)
  /apps                 aplikasi yang sudah Miku pelajari dari menu sistem
  /apps forget <nama>   lupakan satu aplikasi (bila Miku membuka yang salah)"""


def handle_command(text: str, brain: AIBrain, system_control: Any) -> Optional[str]:
    """Jalankan slash command dan kembalikan teks hasilnya; None bila bukan perintah."""
    text = (text or "").strip()
    if not text.startswith("/"):
        return None
    name, _, arg = text[1:].partition(" ")
    handler = COMMANDS.get(name.lower())
    if handler is None:
        return f"Perintah tidak dikenal: /{name}. Ketik /help."
    return handler(brain, system_control, arg.strip())


def _help(brain, system_control, arg) -> str:
    return HELP_TEXT


def _clear(brain, system_control, arg) -> str:
    brain.clear_history()
    return "Riwayat percakapan sesi ini dihapus."


def _usage(brain, system_control, arg) -> str:
    u = brain.session_usage
    return (f"Sesi ini: {u.calls} panggilan LLM, konteks terakhir {u.context_text()}, "
            f"{u.completion_tokens} token dihasilkan, {u.total_seconds:.1f} s waktu LLM.")


def _memory(brain, system_control, arg) -> str:
    facts = long_term_memory.store.recent_facts(limit=100)
    if not facts:
        return "Belum ada fakta yang diingat."
    return "Yang Miku ingat:\n" + "\n".join(f"  - {k}: {v}" for k, v in facts)


def _forget(brain, system_control, arg) -> str:
    if not arg:
        return "Pakai: /forget <key>"
    return long_term_memory.store.forget(arg)[1]


def _skills(brain, system_control, arg) -> str:
    lines = ["Kemampuan Miku:"]
    lines += [f"  - {s.name}: {s.description} ({', '.join(s.tools)})" for s in SKILLS]
    learned, errors = load_user_skills()
    lines.append("Skill buatan user:" if learned else
                 "Belum ada skill buatan user. Tulis data/skills/<nama>/SKILL.md (contoh: folder skills/).")
    lines += [f"  - {s.name}: {s.description} (pemicu: {', '.join(s.triggers)})" for s in learned.values()]
    if errors:
        lines.append("Tidak dimuat:")
        lines += [f"  - {e}" for e in errors]
    return "\n".join(lines)


def _skill(brain, system_control, arg) -> str:
    if not arg:
        return "Pakai: /skill <nama>. Lihat /skills."
    skill = find_user_skill(arg, load_user_skills()[0])
    if skill is None:
        return f"Skill '{arg}' tidak ditemukan. Lihat /skills."
    return (f"Skill '{skill.name}' ({skill.path})\n"
            f"  {skill.description}\n"
            f"  Pemicu: {', '.join(skill.triggers)}\n"
            f"  Tool: {', '.join(skill.tools)}\n"
            f"{skill.instructions}")


def _routines(brain, system_control, arg) -> str:
    routines = load_routines()
    if not routines:
        return "Belum ada routine. Salin routines.example.yaml ke data/routines.yaml."
    return "Routine:\n" + "\n".join(
        f"  - {r.name}: {r.description or ''} ({len(r.steps)} langkah)" for r in routines.values()
    )


def _routine(brain, system_control, arg) -> str:
    if not arg:
        return "Pakai: /routine <nama>. Lihat /routines."
    if system_control is None:
        return "Kontrol sistem belum siap."
    ok, msg = system_control.execute_action("run_routine", {"name": arg})
    return f"{'✅' if ok else '❌'} {msg}"


def _sessions(brain, system_control, arg) -> str:
    if not brain.memory:
        return "Memori tidak aktif."
    sessions = brain.memory.list_sessions(brain.current_character.name, limit=5)
    if not sessions:
        return "Belum ada sesi tersimpan."
    return "Sesi terakhir:\n" + "\n".join(
        f"  - {s['session_id']} ({s['message_count']} pesan): {s['title']}" for s in sessions
    )


def _resume(brain, system_control, arg) -> str:
    return brain.resume_session(arg or None)[1]


def _apps(brain, system_control, arg) -> str:
    cache = system_control.apps.cache
    action, _, name = arg.partition(" ")
    if action.lower() == "forget":
        if not name.strip():
            return "Pakai: /apps forget <nama>"
        if cache.drop(normalize(name)):
            return f"Miku lupa '{name.strip()}'; lain kali dicari lagi di menu aplikasi."
        return f"'{name.strip()}' tidak ada di daftar aplikasi yang dipelajari."
    items = cache.items()
    if not items:
        return "Belum ada aplikasi yang dipelajari. Minta Miku membuka aplikasi apa pun yang ada di menu."
    return "Aplikasi yang sudah Miku pelajari:\n" + "\n".join(
        f"  - {query} -> {record.get('name', '?')}" for query, record in items
    )


Handler = Callable[[AIBrain, Any, str], str]
COMMANDS: Dict[str, Handler] = {
    "help": _help, "clear": _clear, "usage": _usage, "memory": _memory, "forget": _forget,
    "skills": _skills, "skill": _skill, "routines": _routines, "routine": _routine, "sessions": _sessions,
    "resume": _resume, "apps": _apps,
}
