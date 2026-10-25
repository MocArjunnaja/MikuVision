"""
Slash commands - perintah langsung tanpa melewati LLM (cepat dan pasti).

Dipakai mode teks (miku.py --text) dan kolom input GUI.
"""

from typing import Any, Callable, Dict, Optional

from core import long_term_memory
from core.ai_brain import AIBrain
from core.routines import load_routines
from core.skills import SKILLS

HELP_TEXT = """Perintah:
  /help                 daftar perintah
  /clear                hapus riwayat percakapan sesi ini
  /usage                pemakaian token sesi ini
  /memory               fakta yang Miku ingat
  /forget <key>         hapus satu fakta
  /skills               kelompok kemampuan Miku
  /routines             daftar routine
  /routine <nama>       jalankan routine
  /sessions             5 sesi terakhir
  /resume [session_id]  lanjutkan sesi (default: terakhir)"""


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
    return "Kemampuan Miku:\n" + "\n".join(
        f"  - {s.name}: {s.description} ({', '.join(s.tools)})" for s in SKILLS
    )


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


Handler = Callable[[AIBrain, Any, str], str]
COMMANDS: Dict[str, Handler] = {
    "help": _help, "clear": _clear, "usage": _usage, "memory": _memory, "forget": _forget,
    "skills": _skills, "routines": _routines, "routine": _routine, "sessions": _sessions,
    "resume": _resume,
}
