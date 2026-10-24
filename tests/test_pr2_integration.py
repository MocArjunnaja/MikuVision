"""Tests untuk bagian PR #2 yang diintegrasikan (parser JSON, peluncuran app, PID tracking)."""

from unittest.mock import MagicMock

import psutil
import pytest

from core import system_control as sc_module
from core.ai_brain import AIBrain, _find_json_objects
from core.automation_layer import AutomationManager
from core.system_control import SystemControl


# ── Parser JSON fallback ──

def _parse(content):
    return AIBrain()._parse_function_calls({"content": content})


def test_nested_params_yield_single_call_and_keep_text():
    calls, text = _parse('[EMOTION:happy] {"action": "open_app", "params": {"name": "chrome"}} Oke!')

    assert calls == [{"action": "open_app", "params": {"name": "chrome"}}]
    assert "Oke!" in text
    assert "chrome" not in text


def test_qwen_tool_call_tag_format():
    calls, text = _parse('<tool_call>\n{"name": "set_volume", "arguments": {"level": 30}}\n</tool_call>\nSiap!')

    assert calls == [{"action": "set_volume", "params": {"level": 30}}]
    assert "tool_call" not in text
    assert "Siap!" in text


def test_braces_inside_string_values_do_not_break_parsing():
    calls, _ = _parse('{"action": "type_text", "params": {"text": "a } b { c"}} done')

    assert calls == [{"action": "type_text", "params": {"text": "a } b { c"}}]


def test_multiple_calls_and_markdown_block_removed():
    content = (
        "```json\n"
        '{"action": "mute", "params": {}}\n'
        "```\n"
        '{"action": "set_volume", "params": {"level": 10}} Selesai'
    )
    calls, text = _parse(content)

    assert [c["action"] for c in calls] == ["mute", "set_volume"]
    assert "```" not in text
    assert text.endswith("Selesai")


def test_plain_object_with_name_key_is_not_a_tool_call():
    calls, text = _parse('Profil: {"name": "Miku", "age": 16}')

    assert calls == []
    assert "Miku" in text


def test_invalid_json_is_ignored():
    calls, text = _parse("Hmm {ini bukan json} ya")

    assert calls == []
    assert text == "Hmm {ini bukan json} ya"


def test_find_json_objects_returns_only_top_level():
    text = 'x {"a": {"b": 1}} y {"c": 2}'
    assert [text[s:e] for s, e in _find_json_objects(text)] == ['{"a": {"b": 1}}', '{"c": 2}']


# ── open_application ──

@pytest.fixture
def control(monkeypatch):
    monkeypatch.setattr(sc_module, "ALLOWED_APPS", {
        "chrome": "start chrome",
        "spotify": "start spotify:",
        "notepad": "notepad",
        "vscode": "code",
    })
    startfile = MagicMock()
    popen = MagicMock(return_value=MagicMock(pid=4242))
    monkeypatch.setattr(sc_module.os, "startfile", startfile, raising=False)
    monkeypatch.setattr(sc_module.subprocess, "Popen", popen)
    monkeypatch.setattr(sc_module.psutil, "Process", MagicMock(return_value=MagicMock(create_time=lambda: 100.0)))
    ctrl = SystemControl()
    ctrl.startfile, ctrl.popen = startfile, popen
    return ctrl


def test_uri_command_uses_startfile(control):
    success, _ = control.open_application("spotify")

    assert success
    control.startfile.assert_called_once_with("spotify:")
    control.popen.assert_not_called()


def test_exe_on_path_is_launched_without_shell_and_tracked(control, monkeypatch):
    monkeypatch.setattr(sc_module.shutil, "which", lambda name: r"C:\Windows\notepad.exe")

    success, msg = control.open_application("notepad")

    assert success and "4242" in msg
    args, kwargs = control.popen.call_args
    assert args[0] == [r"C:\Windows\notepad.exe"]
    assert not kwargs.get("shell")
    assert control._opened_apps["notepad"] == [(4242, 100.0)]


def test_app_not_on_path_falls_back_to_shell_execute(control, monkeypatch):
    # Chrome tidak ada di PATH; `start chrome` menemukannya lewat App Paths
    monkeypatch.setattr(sc_module.shutil, "which", lambda name: None)

    success, _ = control.open_application("chrome")

    assert success
    control.startfile.assert_called_once_with("chrome")
    control.popen.assert_not_called()


def test_cmd_script_on_path_uses_shell_execute(control, monkeypatch):
    code_cmd = r"C:\VSCode\bin\code.CMD"
    monkeypatch.setattr(sc_module.shutil, "which", lambda name: code_cmd)

    success, _ = control.open_application("vscode")

    assert success
    control.startfile.assert_called_once_with(code_cmd)


def test_unknown_app_is_rejected(control):
    success, _ = control.open_application("zzz-tidak-ada")

    assert not success
    control.startfile.assert_not_called()
    control.popen.assert_not_called()


def test_launch_error_reported_as_failure(control, monkeypatch):
    monkeypatch.setattr(sc_module.shutil, "which", lambda name: None)
    control.startfile.side_effect = FileNotFoundError("not found")

    success, msg = control.open_application("chrome")

    assert not success
    assert "Gagal" in msg


# ── close_application: PID tracking + terminate/kill ──

def _proc(pid, name, create_time=100.0):
    proc = MagicMock(pid=pid)
    proc.info = {"name": name}
    proc.create_time.return_value = create_time
    return proc


def test_tracked_pid_closed_even_if_name_differs(monkeypatch):
    ctrl = SystemControl()
    launcher = _proc(10, "notepad_launcher.exe")
    ctrl._opened_apps["notepad"] = [(10, 100.0)]
    monkeypatch.setattr(sc_module.psutil, "Process", lambda pid: launcher)
    monkeypatch.setattr(sc_module.psutil, "process_iter", lambda attrs: [])
    monkeypatch.setattr(sc_module.psutil, "wait_procs", lambda procs, timeout: (procs, []))

    success, _ = ctrl.close_application("notepad")

    assert success
    launcher.terminate.assert_called_once()
    assert "notepad" not in ctrl._opened_apps


def test_reused_pid_is_not_killed(monkeypatch):
    ctrl = SystemControl()
    other = _proc(10, "important.exe", create_time=999.0)
    ctrl._opened_apps["notepad"] = [(10, 100.0)]
    monkeypatch.setattr(sc_module.psutil, "Process", lambda pid: other)
    monkeypatch.setattr(sc_module.psutil, "process_iter", lambda attrs: [])

    success, _ = ctrl.close_application("notepad")

    assert not success
    other.terminate.assert_not_called()


def test_stubborn_process_is_killed_after_timeout(monkeypatch):
    ctrl = SystemControl()
    stubborn = _proc(20, "notepad.exe")
    monkeypatch.setattr(sc_module.psutil, "process_iter", lambda attrs: [stubborn])
    waited = {}

    def fake_wait(procs, timeout):
        waited["timeout"] = timeout
        return [], procs

    monkeypatch.setattr(sc_module.psutil, "wait_procs", fake_wait)

    success, _ = ctrl.close_application("notepad")

    assert success
    stubborn.terminate.assert_called_once()
    stubborn.kill.assert_called_once()
    assert waited["timeout"] == sc_module.CLOSE_TIMEOUT_SEC


def test_access_denied_reported_as_failure(monkeypatch):
    ctrl = SystemControl()
    locked = _proc(30, "notepad.exe")
    locked.terminate.side_effect = psutil.AccessDenied(30)
    monkeypatch.setattr(sc_module.psutil, "process_iter", lambda attrs: [locked])
    monkeypatch.setattr(sc_module.psutil, "wait_procs", lambda procs, timeout: (procs, []))

    success, _ = ctrl.close_application("notepad")

    assert not success


# ── automation_layer volume ──

def test_automation_volume_delegates_to_system_control():
    system_control = MagicMock()
    system_control.set_volume.return_value = (True, "Volume diatur ke 40%")
    manager = AutomationManager(system_control=system_control)

    assert manager.execute("set_volume", {"level": 40}) == (True, "Volume diatur ke 40%")
    system_control.set_volume.assert_called_once_with(40)


def test_automation_volume_without_system_control_fails():
    success, _ = AutomationManager().execute("set_volume", {"level": 40})
    assert not success


# ── close_application: jendela ditutup sopan, tidak di-kill ──

def test_window_process_gets_wm_close_not_terminate(monkeypatch):
    ctrl = SystemControl()
    proc = _proc(50, "notepad.exe")
    posted = []
    monkeypatch.setattr(sc_module.psutil, "process_iter", lambda attrs: [proc])
    monkeypatch.setattr(sc_module, "_windows_by_pid", lambda pids: {50: [111, 222]})
    monkeypatch.setattr(sc_module, "_post_close", posted.append)
    monkeypatch.setattr(sc_module.psutil, "wait_procs", lambda procs, timeout: (list(procs), []))

    success, _ = ctrl.close_application("notepad")

    assert success
    assert posted == [111, 222]
    proc.terminate.assert_not_called()
    proc.kill.assert_not_called()


def test_window_waiting_for_save_dialog_is_never_killed(monkeypatch):
    ctrl = SystemControl()
    proc = _proc(60, "notepad.exe")
    monkeypatch.setattr(sc_module.psutil, "process_iter", lambda attrs: [proc])
    monkeypatch.setattr(sc_module, "_windows_by_pid", lambda pids: {60: [333]})
    monkeypatch.setattr(sc_module.psutil, "wait_procs", lambda procs, timeout: ([], list(procs)))

    success, msg = ctrl.close_application("notepad")

    assert success
    assert "masih terbuka" in msg
    proc.kill.assert_not_called()
