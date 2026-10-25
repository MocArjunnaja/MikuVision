"""Permintaan "buatkan dokumen Word berisi X" -> create_word_document dengan isi."""

from unittest.mock import MagicMock

import pytest

import core.macro_tools  # noqa: F401  (mendaftarkan tool Office)
from core.ai_brain import AIBrain, _claims_action, _japanese_ratio, _requests_action
from core.memory import MemoryManager
from core.stt_text import apply_corrections
from core.tools import registry

JA_CONTENT = "【朝の運動のメリット】\n1. エネルギーが上がる\n朝に運動すると集中力が高まります。"
ID_CONTENT = "Manfaat Olahraga Pagi\n1. Energi meningkat\nOlahraga pagi membuat tubuh lebih segar."


def _brain(tmp_path, *responses):
    memory = MemoryManager(tmp_path)
    memory.start_session("miku")
    brain = AIBrain(memory)
    brain.client = MagicMock()
    brain.client.chat.side_effect = list(responses)
    return brain


def _doc_call(content):
    return {"function": {"name": "create_word_document",
                         "arguments": {"filename": "manfaat_olahraga", "content": content}}}


def test_word_tool_schema_describes_content_parameter():
    schema = registry.get_tools_schema(["create_word_document"])[0]["function"]
    content = schema["parameters"]["properties"]["content"]["description"]
    assert "write yourself" in content
    assert "open_application" in schema["description"]


def test_open_application_points_to_word_tool():
    schema = registry.get_tools_schema(["open_application"])[0]["function"]
    assert "create_word_document" in schema["description"]


@pytest.mark.parametrize("text", [
    "Buatkan dokumen Word tentang Hukum Newton",
    "Tolong bikin dokumen Word berisi ringkasan sejarah",
    "Tulis surat izin di Word",
    "ワードで自己紹介の文書を作って",
])
def test_document_requests_trigger_missed_tool_retry(text):
    assert _requests_action(text)


def test_promise_to_make_document_counts_as_claim():
    assert _claims_action("すぐにWordファイルを作りますよ！")


def test_japanese_ratio():
    assert _japanese_ratio(JA_CONTENT) > 0.5
    assert _japanese_ratio(ID_CONTENT) == 0.0
    assert _japanese_ratio("") == 0.0


def test_japanese_content_for_indonesian_request_is_translated(tmp_path):
    brain = _brain(
        tmp_path,
        {"message": {"content": "", "tool_calls": [_doc_call(JA_CONTENT)]}},
        {"message": {"content": ID_CONTENT}},
    )
    _, calls, _ = brain.think("Buat file Word tentang manfaat olahraga pagi")

    assert calls[0]["params"]["content"] == ID_CONTENT
    translate_call = brain.client.chat.call_args_list[1].kwargs
    assert translate_call["tools"] is None
    assert translate_call["messages"][-1]["content"] == JA_CONTENT


def test_japanese_request_keeps_japanese_content(tmp_path):
    brain = _brain(tmp_path, {"message": {"content": "", "tool_calls": [_doc_call(JA_CONTENT)]}})
    _, calls, _ = brain.think("ワードで朝の運動の文書を作って")

    assert calls[0]["params"]["content"] == JA_CONTENT
    assert brain.client.chat.call_count == 1


def test_failed_translation_keeps_original_content(tmp_path):
    brain = _brain(
        tmp_path,
        {"message": {"content": "", "tool_calls": [_doc_call(JA_CONTENT)]}},
        {"message": {"content": "ごめんね、翻訳できなかった"}},  # masih bahasa Jepang
    )
    _, calls, _ = brain.think("Buat file Word tentang manfaat olahraga pagi")
    assert calls[0]["params"]["content"] == JA_CONTENT


def test_hegum_is_corrected_to_hukum():
    assert apply_corrections("rumus Hegum Newton") == "rumus Hukum Newton"
    assert apply_corrections("rumus hegum newton") == "rumus hukum newton"
