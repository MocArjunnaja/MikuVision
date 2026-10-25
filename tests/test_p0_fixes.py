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


# ── Retry saat model hanya berjanji melakukan aksi ──

def _brain_with_replies(tmp_path, *messages):
    memory = MemoryManager(tmp_path)
    brain = AIBrain(memory)
    memory.start_session("miku")
    brain.client = MagicMock()
    brain.client.chat.side_effect = [{"message": m} for m in messages]
    return brain


def test_action_claim_without_tool_is_retried_once(tmp_path):
    call = {"function": {"name": "open_application", "arguments": {"app_name": "notepad"}}}
    brain = _brain_with_replies(
        tmp_path,
        {"content": "[EMOTION:happy] わかりました！メモ帳を開きますね！"},
        {"content": "[EMOTION:happy] 開くね！", "tool_calls": [call]},
    )

    _, calls, _ = brain.think("メモ帳を開いて")

    assert calls == [{"action": "open_application", "params": {"app_name": "notepad"}}]
    assert brain.client.chat.call_count == 2
    nudge = brain.client.chat.call_args.kwargs["messages"][-1]
    sent = brain.client.chat.call_args.kwargs["messages"]
    assert sent[-1]["role"] == "system" and "did not call a tool" in sent[-1]["content"]


def test_plain_chat_is_not_retried(tmp_path):
    brain = _brain_with_replies(tmp_path, {"content": "[EMOTION:happy] こんにちは！ミクだよ！"})

    brain.think("こんにちは")

    assert brain.client.chat.call_count == 1


@pytest.mark.parametrize("text", ["メモ帳を開きますね！", "音量を30に設定しました！", "音量を30にしますよ！", "Oke, aku akan membuka Notepad"])
def test_action_claims_are_detected(text):
    from core.ai_brain import _claims_action
    assert _claims_action(text)


@pytest.mark.parametrize("text", ["こんにちは！", "Cドライブのファイルを消すことはできません。", "お手伝いしますよ！", "Halo, ada yang bisa dibantu?"])
def test_non_claims_are_not_detected(text):
    from core.ai_brain import _claims_action
    assert not _claims_action(text)


# ── initialize: cek tag model persis ──

@pytest.mark.parametrize("installed, ok", [
    (["qwen3:4b-instruct"], True),
    (["qwen3:4b", "granite4.2:3b"], False),   # nama dasar sama, tag berbeda
])
def test_initialize_requires_exact_model_tag(monkeypatch, tmp_path, installed, ok):
    from core import ai_brain as ai_brain_module
    fake_client = MagicMock()
    fake_client.list.return_value = {"models": [{"name": n} for n in installed]}
    created = {}
    monkeypatch.setattr(ai_brain_module, "Client", lambda **kw: created.update(kw) or fake_client)
    brain = AIBrain(MemoryManager(tmp_path))
    brain.model = "qwen3:4b-instruct"

    success, msg = brain.initialize()

    assert success is ok
    # Request ke Ollama selalu dibatasi waktu agar app tidak menunggu selamanya
    assert created["timeout"] == config.OLLAMA_TIMEOUT_SEC
    if not ok:
        assert "ollama pull qwen3:4b-instruct" in msg


# ── Tool call & hasilnya tersimpan dalam format resmi (agent loop) ──

def test_tool_turn_is_stored_as_tool_calls_with_results(tmp_path):
    call = {"function": {"name": "open_application", "arguments": {"app_name": "notepad"}}}
    brain, memory = _brain_with_reply(tmp_path, {"content": "", "tool_calls": [call]})

    brain.think("メモ帳を開いて")
    brain.record_tool_results([("open_application", "SUKSES - Membuka notepad")])

    context = memory.get_context_for_prompt()
    assert context[-2]["role"] == "assistant"
    assert context[-2]["tool_calls"] == [
        {"function": {"name": "open_application", "arguments": {"app_name": "notepad"}}}
    ]
    assert context[-1] == {"role": "tool", "content": "SUKSES - Membuka notepad", "tool_name": "open_application"}


def test_think_observation_uses_recorded_tool_results(tmp_path):
    call = {"function": {"name": "get_volume", "arguments": {}}}
    brain = _brain_with_replies(
        tmp_path,
        {"content": "", "tool_calls": [call]},
        {"content": "[EMOTION:happy] 今の音量は34だよ！"},
    )
    brain.think("今の音量は？")
    brain.record_tool_results([("get_volume", "SUKSES - 34")])

    reply, emotion = brain.think_observation()

    sent = brain.client.chat.call_args.kwargs["messages"]
    assert sent[-1]["role"] == "tool"            # tidak ada pesan "System Observation" palsu
    assert reply == "今の音量は34だよ！" and emotion == "happy"


def test_trimmed_context_does_not_start_with_orphan_tool_message(tmp_path):
    memory = MemoryManager(tmp_path)
    memory.start_session("miku")
    memory.add_message("tool", "SUKSES - 34", metadata={"tool_name": "get_volume"})
    memory.add_message("user", "ありがとう")

    assert memory.get_context_for_prompt()[0]["role"] == "user"


@pytest.mark.parametrize("text", ["電卓を閉じて", "音量を30にして", "Buka notepad", "tolong kecilkan volume", "open chrome",
                                  "誕生日を覚えておいてね", "tolong ingat ulang tahunku", "それは忘れて"])
def test_action_requests_are_detected(text):
    from core.ai_brain import _requests_action
    assert _requests_action(text)


@pytest.mark.parametrize("text", ["こんにちは、ミク！", "さっき私は何をお願いした？", "Kamu siapa?", "Halo Miku"])
def test_chat_is_not_an_action_request(text):
    from core.ai_brain import _requests_action
    assert not _requests_action(text)


def test_action_request_without_tool_call_is_retried(tmp_path):
    call = {"function": {"name": "close_application", "arguments": {"app_name": "calculator"}}}
    brain = _brain_with_replies(
        tmp_path,
        {"content": "[EMOTION:happy] 電卓は閉じたよ！"},     # klaim tanpa tool call
        {"content": "", "tool_calls": [call]},
    )

    _, calls, _ = brain.think("電卓を閉じて")

    assert [c["action"] for c in calls] == ["close_application"]


def test_second_retry_strategy_runs_when_first_fails(tmp_path):
    call = {"function": {"name": "close_application", "arguments": {"app_name": "notepad"}}}
    brain = _brain_with_replies(
        tmp_path,
        {"content": "[EMOTION:happy] メモ帳を閉じますね！"},
        {"content": "[EMOTION:happy] 閉じますね！"},          # retry 1 masih gagal
        {"content": "", "tool_calls": [call]},                # retry 2 berhasil
    )

    _, calls, _ = brain.think("メモ帳を閉じて")

    assert [c["action"] for c in calls] == ["close_application"]
    last = brain.client.chat.call_args
    assert last.kwargs["options"]["temperature"] == 0.2
    assert last.kwargs["messages"][-2]["content"].startswith("If the next user message")
    assert last.kwargs["messages"][-1] == {"role": "user", "content": "メモ帳を閉じて"}
