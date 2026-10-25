"""
Conversation Turn - alur satu giliran yang dipakai mode teks, mode suara, dan GUI:

    think -> eksekusi tool -> catat hasil tool ke memori -> (opsional) laporkan hasil -> log
"""

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core.ai_brain import AIBrain
from core.turn_log import TurnLogger


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
    reply, calls, emotion = brain.think(user_text)

    results: List[ToolResult] = []
    if calls and system_control:
        for call in calls:
            action, params = call.get("action", ""), call.get("params") or {}
            success, message = system_control.execute_action(action, params)
            result = ToolResult(action, params, success, message)
            results.append(result)
            if on_tool_result:
                on_tool_result(result)

        brain.record_tool_results(
            [(r.action, f"{'SUKSES' if r.success else 'GAGAL'} - {r.message}") for r in results]
        )
        if report_results:
            reply, emotion = brain.think_observation()

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
