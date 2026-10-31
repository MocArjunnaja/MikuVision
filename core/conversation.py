"""
Conversation Turn - alur satu giliran yang dipakai mode teks, mode suara, dan GUI:

    think -> eksekusi tool -> catat hasil tool ke memori -> (opsional) laporkan hasil -> log

"Simpan ini sebagai skill" tidak lewat think: skill disusun dari giliran-giliran sebelumnya
(core/skill_builder.py), ditunjukkan, dan disimpan setelah user setuju.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core import skill_builder
from core.ai_brain import AIBrain
from core.turn_log import TurnLogger

# Langkah tambahan maksimal per giliran untuk skill buatan user dengan beberapa tool
MAX_SKILL_STEPS = 3


@dataclass
class ToolResult:
    action: str
    params: Dict[str, Any]
    success: bool
    message: str


@dataclass
class TurnResult:
    user_text: str
    reply: str
    emotion: str
    tool_results: List[ToolResult] = field(default_factory=list)
    latency_seconds: float = 0.0


def run_turn(
    brain: AIBrain,
    system_control: Any,
    user_text: str,
    *,
    source: str,
    report_results: bool = True,
    on_tool_result: Optional[Callable[[ToolResult], None]] = None,
    logger: Optional[TurnLogger] = None,
) -> TurnResult:
    """
    Jalankan satu giliran.

    report_results=True meminta LLM merangkum hasil tool (satu panggilan tambahan);
    mode teks mematikannya agar lebih cepat.
    """
    started = time.time()
    results: List[ToolResult] = []
    if skill_builder.wants_to_save(user_text):
        saved = skill_builder.save_from_chat(brain, user_text, getattr(system_control, "confirm_callback", None))
        result = ToolResult("save_skill", {"name": saved.skill.name if saved.skill else ""},
                            saved.status == "saved", saved.message)
        results.append(result)
        if on_tool_result:
            on_tool_result(result)
        reply, emotion = skill_builder.reply_for(saved, getattr(brain.current_character, "lang", "id"))
        brain.record_exchange(user_text, reply, emotion)
        return _finish_turn(brain, user_text, reply, emotion, results, started, source, logger)

    reply, calls, emotion = brain.think(user_text)
    # Skill user terpicu tapi model hanya mengobrol: ucapan seperti "mode fokus dong" tidak berisi
    # kata kerja aksi, jadi retry di think() tidak jalan. Minta langkah skill-nya, kecuali skill
    # itu memang sedang menanyakan detail ("kegiatanmu hari ini apa?").
    if not calls and system_control and getattr(brain, "turn_user_skills", None) \
            and not brain.awaiting_skill_details:
        calls = brain.next_skill_calls([])
        if calls and not report_results:
            reply = ""  # balasan tadi (sering berupa pertanyaan) sudah tidak berlaku

    if calls and system_control:
        for _ in range(1 + MAX_SKILL_STEPS):
            batch: List[ToolResult] = []
            for call in calls:
                action, params = call.get("action", ""), call.get("params") or {}
                success, message = system_control.execute_action(action, params)
                result = ToolResult(action, params, success, message)
                batch.append(result)
                if on_tool_result:
                    on_tool_result(result)
            results.extend(batch)
            brain.record_tool_results(
                [(r.action, f"{'SUKSES' if r.success else 'GAGAL'} - {r.message}") for r in batch]
            )
            # Lanjut ke langkah skill berikutnya hanya bila semua tool barusan berhasil
            if not all(r.success for r in batch):
                break
            calls = brain.next_skill_calls([r.action for r in results])
            if not calls:
                break
        if report_results:
            reply, emotion = brain.think_observation()

    return _finish_turn(brain, user_text, reply, emotion, results, started, source, logger)


def _finish_turn(brain: AIBrain, user_text: str, reply: str, emotion: str, results: List[ToolResult],
                 started: float, source: str, logger: Optional[TurnLogger]) -> TurnResult:
    turn = TurnResult(user_text, reply, emotion, results, round(time.time() - started, 2))
    if logger:
        logger.log({
            "session_id": brain.memory.session_id if brain.memory else None,
            "source": source,
            "model": brain.model,
            "user": user_text,
            "reply": reply,
            "emotion": emotion,
            "tools": [vars(r) for r in results],
            "usage": brain.turn_usage.as_dict(),
            "context_tokens": brain.turn_usage.prompt_tokens,
            "latency_seconds": turn.latency_seconds,
        })
    return turn
