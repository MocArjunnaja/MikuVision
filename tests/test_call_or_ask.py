"""Aturan "panggil tool vs tanya balik" di prompt sistem (When2Call, arXiv 2504.18851).

Isi aturan dipilih lewat A/B di experiments/skills/bench_skills.py (mode call_or_ask); test ini
menjaga supaya kriteria dan contohnya tidak hilang diam-diam saat prompt diubah.
"""

import pytest

from core.ai_brain import FUNCTION_CALL_PROMPT_ID, FUNCTION_CALL_PROMPT_JA
from core.skills import select_skills


@pytest.mark.parametrize("text", ["音楽を止めて", "曲を止めて", "スキップして", "一時停止して", "前の曲に戻して",
                                  "ミュート解除して", "pause lagunya", "skip lagu ini"])
def test_media_commands_load_the_audio_tools(text):
    # Tanpa pemicu semua skill dikirim (±4.500 token) dan 「音楽を止めて」 dijawab describe_screen
    assert [s.id for s in select_skills(text, fallback_all=False)] == ["memory", "audio"]


@pytest.mark.parametrize("prompt, needed", [
    (FUNCTION_CALL_PROMPT_ID, ("HANYA bila", "kirim pesan", "mute", "pause", "langsung dijalankan")),
    (FUNCTION_CALL_PROMPT_JA, ("ときだけ", "メッセージを送って", "ミュート", "一時停止", "すぐツールを呼び出して")),
])
def test_prompt_asks_only_when_required_information_is_missing(prompt, needed):
    for text in needed:
        assert text in prompt


def test_old_ask_when_ambiguous_rule_is_gone():
    # "tanya bila ambigu" tanpa batas membuat model bertanya "apa yang di-mute?" (v1.8.0)
    assert "terlalu ambigu" not in FUNCTION_CALL_PROMPT_ID
    assert "指示が曖昧" not in FUNCTION_CALL_PROMPT_JA


def _brain(tmp_path, *messages):
    from unittest.mock import MagicMock

    from core.ai_brain import AIBrain
    from core.memory import MemoryManager

    memory = MemoryManager(tmp_path)
    brain = AIBrain(memory)
    memory.start_session("miku")
    brain.client = MagicMock()
    brain.client.chat.side_effect = [{"message": m} for m in messages]
    return brain


def test_follow_up_question_is_not_forced_into_a_tool_call(tmp_path):
    # Retry "panggil tool sekarang" setelah "video apa?" membuat model mengarang query
    brain = _brain(tmp_path, {"content": "[EMOTION:thinking] どんなテーマの動画をさがすの？"},
                   {"content": "", "tool_calls": [{"function": {"name": "youtube_search",
                                                                "arguments": {"query": "人気の動画"}}}]})
    reply, calls, _ = brain.think("tolong carikan video di youtube")
    assert calls == [] and "動画" in reply
    assert brain.client.chat.call_count == 1


def test_promise_without_a_tool_call_still_gets_the_retry(tmp_path):
    brain = _brain(tmp_path, {"content": "[EMOTION:happy] ミュートしますね！"},
                   {"content": "", "tool_calls": [{"function": {"name": "mute", "arguments": {"mute": True}}}]})
    _, calls, _ = brain.think("ミュートして")
    assert [c["action"] for c in calls] == ["mute"]


@pytest.mark.parametrize("text, claims", [
    ("何を検索しますか？", False), ("音量を何にしますか？", False), ("どのアプリを開きますか？", False),
    ("検索しますね！", True), ("メモ帳を開きました！", True), ("音量を30にします", True),
])
def test_questions_are_not_action_claims(text, claims):
    from core.ai_brain import _claims_action

    assert _claims_action(text) is claims


def test_search_question_is_not_retried(tmp_path):
    # 「何を検索しますか？」 dulu dibaca sebagai janji "検索します" lalu dipaksa jadi google_search
    brain = _brain(tmp_path, {"content": "[EMOTION:thinking] はい！何を検索しますか？"},
                   {"content": "", "tool_calls": [{"function": {"name": "google_search",
                                                                "arguments": {"query": "検索"}}}]})
    _, calls, _ = brain.think("グーグルで検索して")
    assert calls == [] and brain.client.chat.call_count == 1
