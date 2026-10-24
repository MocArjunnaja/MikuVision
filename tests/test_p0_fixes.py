"""Regression tests untuk perbaikan P0."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import config
from core import system_control as sc_module
from core.ai_brain import AIBrain
from core.confirmation import describe_action, is_affirmative
from core.memory import MemoryManager
from core.system_control import SystemControl
from core.tools import Tool


# ── Confirmation ──

@pytest.mark.parametrize("answer", ["ya", "Iya, kirim", "yes", "はい", "うん、いいよ", "oke lanjut"])
def test_affirmative_answers(answer):
    assert is_affirmative(answer)


@pytest.mark.parametrize("answer", ["", "tidak", "jangan dikirim", "いいえ", "だめ", "saya bingung", "kaya gitu"])
def test_negative_or_ambiguous_answers(answer):
    assert not is_affirmative(answer)


def test_describe_whatsapp_action():
    summary = describe_action("send_whatsapp_message", {"contact_name": "Budi", "message": "Halo"})
    assert "Budi" in summary and "Halo" in summary


# ── SystemControl gate ──

@pytest.fixture
def system_control():
    return SystemControl()


def test_risky_action_denied_without_callback(system_control, monkeypatch):
    executed = MagicMock()
    monkeypatch.setattr(sc_module.registry, "execute", executed)

    success, msg = system_control.execute_action("close_application", {"app_name": "notepad"})

    assert not success
    assert "Dibatalkan" in msg
    executed.assert_not_called()


def test_risky_action_runs_after_approval(system_control, monkeypatch):
    monkeypatch.setattr(sc_module.registry, "execute", MagicMock(return_value=(True, "ok")))
    asked = []
    system_control.confirm_callback = lambda summary: asked.append(summary) or True

    assert system_control.execute_action("close_application", {"app_name": "notepad"}) == (True, "ok")
    assert asked and "notepad" in asked[0]


def test_risky_action_rejected_by_user(system_control, monkeypatch):
    executed = MagicMock()
    monkeypatch.setattr(sc_module.registry, "execute", executed)
    system_control.confirm_callback = lambda summary: False

    success, _ = system_control.execute_action("send_whatsapp_message", {"contact_name": "a", "message": "x"})

    assert not success
    executed.assert_not_called()


def test_safe_action_needs_no_confirmation(system_control, monkeypatch):
    monkeypatch.setattr(sc_module.registry, "execute", MagicMock(return_value=(True, "Volume 50%")))
    assert system_control.execute_action("set_volume", {"level": 50}) == (True, "Volume 50%")


def test_macro_failure_string_reported_as_failure(system_control, monkeypatch):
    monkeypatch.setattr(sc_module.registry, "execute", MagicMock(return_value="Gagal membuat dokumen"))
    success, _ = system_control.execute_action("create_word_document", {})
    assert not success


# ── close_application ──

def _fake_proc(name):
    proc = MagicMock()
    proc.info = {"name": name}
    return proc


@pytest.fixture(autouse=True)
def _no_real_wait(monkeypatch):
    # Proses palsu dianggap langsung tertutup setelah terminate
    monkeypatch.setattr(sc_module.psutil, "wait_procs", lambda procs, timeout: (procs, []))


def test_close_application_uses_exact_name(system_control, monkeypatch):
    notepad, notepadpp = _fake_proc("notepad.exe"), _fake_proc("notepad++.exe")
    monkeypatch.setattr(sc_module.psutil, "process_iter", lambda attrs: [notepad, notepadpp])

    success, _ = system_control.close_application("notepad")

    assert success
    notepad.terminate.assert_called_once()
    notepadpp.terminate.assert_not_called()


def test_close_application_single_letter_matches_nothing(system_control, monkeypatch):
    proc = _fake_proc("chrome.exe")
    monkeypatch.setattr(sc_module.psutil, "process_iter", lambda attrs: [proc])

    success, _ = system_control.close_application("c")

    assert not success
    proc.terminate.assert_not_called()


def test_close_application_refuses_protected_process(system_control, monkeypatch):
    proc = _fake_proc("explorer.exe")
    monkeypatch.setattr(sc_module.psutil, "process_iter", lambda attrs: [proc])

    success, _ = system_control.close_application("explorer")

    assert not success
    proc.terminate.assert_not_called()


# ── hotkey ──

def test_hotkey_schema_is_array_of_strings():
    schema = Tool("hotkey", "", SystemControl.hotkey).to_openai_schema()
    keys = schema["function"]["parameters"]["properties"]["keys"]
    assert keys["type"] == "array"
    assert keys["items"] == {"type": "string"}


@pytest.mark.parametrize("keys", ["ctrl+c", ["ctrl", "c"], ["Ctrl ", " C"]])
def test_hotkey_accepts_string_and_list(system_control, monkeypatch, keys):
    fake_gui = MagicMock()
    monkeypatch.setattr(sc_module, "pyautogui", fake_gui)

    success, _ = system_control.hotkey(keys)

    assert success
    fake_gui.hotkey.assert_called_once_with("ctrl", "c")


# ── AIBrain: memory + Ollama options ──

def _brain_with_reply(tmp_path, message):
    memory = MemoryManager(tmp_path)
    brain = AIBrain(memory)
    memory.start_session("miku")
    brain.client = MagicMock()
    brain.client.chat.return_value = {"message": message}
    return brain, memory


def test_think_stores_user_and_assistant_turns(tmp_path):
    brain, memory = _brain_with_reply(tmp_path, {"content": "[EMOTION:happy] はーい！"})

    brain.think("buka chrome")

    roles = [(m["role"], m["content"]) for m in memory.get_context_for_prompt()]
    assert roles[0] == ("user", "buka chrome")
    assert roles[1][0] == "assistant"


def test_chat_disables_thinking_and_sets_context(tmp_path):
    brain, _ = _brain_with_reply(tmp_path, {"content": "[EMOTION:happy] OK"})

    brain.think("halo")

    kwargs = brain.client.chat.call_args.kwargs
    # Default None: parameter think tidak dikirim sehingga Ollama memisahkan
    # penalaran ke field `thinking` alih-alih menaruhnya di content
    assert config.OLLAMA_THINK is None
    assert "think" not in kwargs
    assert kwargs["options"]["num_ctx"] == config.OLLAMA_NUM_CTX


def test_explicit_think_setting_is_forwarded(tmp_path, monkeypatch):
    from core import ai_brain as ai_brain_module
    monkeypatch.setattr(ai_brain_module, "OLLAMA_THINK", False)
    brain, _ = _brain_with_reply(tmp_path, {"content": "[EMOTION:happy] OK"})

    brain.think("halo")

    assert brain.client.chat.call_args.kwargs["think"] is False


def test_duplicate_tool_calls_in_one_response_run_once(tmp_path):
    call = {"function": {"name": "open_application", "arguments": {"app_name": "Notepad"}}}
    brain, _ = _brain_with_reply(tmp_path, {"content": "", "tool_calls": [call] * 6})

    _, calls, _ = brain.think("メモ帳を開いて")

    assert calls == [{"action": "open_application", "params": {"app_name": "Notepad"}}]


def test_thinking_text_is_never_spoken(tmp_path):
    brain, _ = _brain_with_reply(tmp_path, {"content": "", "thinking": "User wants X, so I should..."})

    response, _, _ = brain.think("halo")

    assert "User wants" not in response


# ── qwen3 Thinking-2507: penalaran di content diakhiri </think> ──

QWEN_THINKING_REPLY = (
    "Okay, the user wants Notepad. Maybe I should answer "
    '{"action": "close_application", "params": {"app_name": "notepad"}} hmm no.\n'
    "</think>\n\n[EMOTION:happy] メモ帳を開くね！"
)


def test_reasoning_before_think_close_tag_is_dropped(tmp_path):
    brain, memory = _brain_with_reply(tmp_path, {"content": QWEN_THINKING_REPLY})

    response, calls, emotion = brain.think("メモ帳を開いて")

    assert response == "メモ帳を開くね！"
    assert emotion == "happy"
    # JSON draf di dalam penalaran tidak boleh dieksekusi
    assert calls == []
    # Memori menyimpan jawaban saja, bukan penalaran panjang
    stored = memory.get_context_for_prompt()[-1]["content"]
    assert "Okay, the user" not in stored


def test_fallback_reply_follows_character_language(tmp_path):
    call = {"function": {"name": "get_volume", "arguments": {}}}
    brain, _ = _brain_with_reply(tmp_path, {"content": "", "tool_calls": [call]})

    response, _, _ = brain.think("今の音量は？")

    assert brain.current_character.lang == "ja"
    assert response == "オッケー、やってみるね！"


def test_blank_reply_is_confused_in_character_language(tmp_path):
    brain, _ = _brain_with_reply(tmp_path, {"content": ""})

    response, calls, emotion = brain.think("……")

    assert calls == []
    assert emotion == "confused"
    assert "ごめんね" in response
