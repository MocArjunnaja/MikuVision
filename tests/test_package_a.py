"""Paket A: penghitung token, log per giliran, melanjutkan sesi, memori jangka panjang."""

import json
from unittest.mock import MagicMock

from core import long_term_memory
from core.ai_brain import AIBrain
from core.conversation import run_turn
from core.long_term_memory import LongTermMemory
from core.memory import MemoryManager
from core.tools import registry
from core.turn_log import TurnLogger


def _brain(tmp_path, *responses):
    memory = MemoryManager(tmp_path)
    brain = AIBrain(memory)
    memory.start_session("miku")
    brain.client = MagicMock()
    brain.client.chat.side_effect = list(responses)
    return brain, memory


# ── A4: memori jangka panjang ──

def test_remember_recall_forget(tmp_path):
    store = LongTermMemory(tmp_path / "m.json")

    assert store.remember("  Ulang Tahun ", "5 Mei")[0]
    assert store.recall("ulang tahun") == (True, "ulang tahun: 5 Mei")
    assert store.forget("ulang tahun")[0]
    assert store.recall("ulang tahun")[0] is False


def test_empty_fact_is_rejected(tmp_path):
    assert LongTermMemory(tmp_path / "m.json").remember("nama", "  ")[0] is False


def test_prompt_lists_newest_facts_only(tmp_path, monkeypatch):
    monkeypatch.setattr(long_term_memory, "MEMORY_PROMPT_MAX_FACTS", 2)
    store = LongTermMemory(tmp_path / "m.json")
    for i in range(3):
        store.remember(f"fakta {i}", f"nilai {i}")
    facts = store.recent_facts(limit=2)
    assert len(facts) == 2


def test_memory_tools_are_registered():
    names = {t["function"]["name"] for t in registry.get_all_tools_schema()}
    assert {"remember", "recall_memory", "forget"} <= names


def test_memory_tool_runs_without_system_control_instance():
    success, msg = registry.execute("remember", object(), {"key": "nama", "value": "Arjun"})
    assert success and "Arjun" in msg
    assert long_term_memory.store.recall("nama") == (True, "nama: Arjun")


def test_system_prompt_contains_remembered_facts(tmp_path):
    long_term_memory.store.remember("makanan favorit", "ramen")
    brain = AIBrain(MemoryManager(tmp_path))
    assert "makanan favorit: ramen" in brain._build_system_prompt()


# ── A1: token meter ──

def test_turn_and_session_usage_from_ollama_counts(tmp_path):
    brain, _ = _brain(
        tmp_path,
        {"message": {"content": "[EMOTION:happy] やあ"}, "prompt_eval_count": 3100, "eval_count": 20,
         "total_duration": 900_000_000},
        {"message": {"content": "[EMOTION:happy] うん"}, "prompt_eval_count": 3150, "eval_count": 5,
         "total_duration": 300_000_000},
    )

    brain.think("こんにちは")
    assert (brain.turn_usage.prompt_tokens, brain.turn_usage.completion_tokens) == (3100, 20)

    brain.think("元気？")
    assert brain.turn_usage.calls == 1                      # direset tiap giliran
    assert brain.session_usage.calls == 2
    assert brain.session_usage.completion_tokens == 25
    assert brain.turn_usage.context_text() == "3.1k / 8.2k token"


# ── A2: log per giliran ──

def test_turn_logger_appends_jsonl(tmp_path):
    logger = TurnLogger(tmp_path / "logs")
    logger.log({"user": "メモ帳を開いて", "tools": []})
    logger.log({"user": "閉じて", "tools": []})

    lines = next((tmp_path / "logs").glob("turns_*.jsonl")).read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["user"] for line in lines] == ["メモ帳を開いて", "閉じて"]
    assert "ts" in json.loads(lines[0])


def test_run_turn_executes_records_reports_and_logs(tmp_path):
    call = {"function": {"name": "get_volume", "arguments": {}}}
    brain, memory = _brain(
        tmp_path,
        {"message": {"content": "", "tool_calls": [call]}, "prompt_eval_count": 3000, "eval_count": 10},
        {"message": {"content": "[EMOTION:happy] 音量は34だよ！"}, "prompt_eval_count": 3050, "eval_count": 12},
    )
    system_control = MagicMock()
    system_control.execute_action.return_value = (True, "34")
    seen = []
    logger = TurnLogger(tmp_path / "logs")

    turn = run_turn(brain, system_control, "今の音量は？", source="text",
                    on_tool_result=seen.append, logger=logger)

    assert turn.reply == "音量は34だよ！" and turn.emotion == "happy"
    assert [r.action for r in seen] == ["get_volume"]
    assert memory.get_context_for_prompt()[-2] == {"role": "tool", "content": "SUKSES - 34", "tool_name": "get_volume"}
    record = json.loads(next((tmp_path / "logs").glob("*.jsonl")).read_text(encoding="utf-8"))
    assert record["tools"][0]["action"] == "get_volume" and record["tools"][0]["success"] is True
    assert record["usage"]["calls"] == 2 and record["context_tokens"] == 3050
    assert record["source"] == "text" and record["model"] == brain.model


def test_run_turn_without_report_skips_second_llm_call(tmp_path):
    call = {"function": {"name": "get_volume", "arguments": {}}}
    brain, _ = _brain(tmp_path, {"message": {"content": "", "tool_calls": [call]}})
    system_control = MagicMock()
    system_control.execute_action.return_value = (True, "34")

    run_turn(brain, system_control, "今の音量は？", source="text", report_results=False)

    assert brain.client.chat.call_count == 1


# ── A3: sesi ──

def test_empty_session_is_not_saved(tmp_path):
    memory = MemoryManager(tmp_path)
    memory.start_session("miku")
    memory.end_session(save=True)
    assert list((tmp_path / "conversations").glob("*.json")) == []


def _saved_session(tmp_path, session_id, character, text):
    memory = MemoryManager(tmp_path)
    memory.start_session(character)
    memory.session_id = session_id
    memory.add_message("user", text)
    memory.add_message("assistant", "[EMOTION:happy] OK")
    memory.end_session(save=True)


def test_list_sessions_newest_first_and_filtered(tmp_path):
    _saved_session(tmp_path, "20261020_100000", "miku", "pertama")
    _saved_session(tmp_path, "20261021_100000", "kurisu", "kurisu")
    _saved_session(tmp_path, "20261022_100000", "miku", "kedua")

    sessions = MemoryManager(tmp_path).list_sessions("miku")

    assert [s["title"] for s in sessions] == ["kedua", "pertama"]
    assert sessions[0]["message_count"] == 2


def test_resume_latest_session_restores_history(tmp_path):
    _saved_session(tmp_path, "20261022_100000", "miku", "ingat aku suka ramen")
    brain = AIBrain(MemoryManager(tmp_path))
    brain.memory.start_session("miku")

    ok, msg = brain.resume_session()

    assert ok and "20261022_100000" in msg
    assert brain.memory.get_context_for_prompt()[0]["content"] == "ingat aku suka ramen"


def test_resume_without_previous_session(tmp_path):
    brain = AIBrain(MemoryManager(tmp_path))
    brain.memory.start_session("miku")
    assert brain.resume_session() == (False, "Belum ada sesi sebelumnya")
