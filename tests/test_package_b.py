"""Paket B: skill on-demand, routine, slash command."""

from unittest.mock import MagicMock

import pytest

from core import ai_brain as ai_brain_module
from core import long_term_memory, routines
from core.ai_brain import AIBrain
from core.commands import handle_command
from core.memory import MemoryManager
from core.skills import SKILLS, select_skills, tool_names
from core.tools import registry


# ── B1: skill routing ──

@pytest.mark.parametrize("text, expected", [
    ("音量を30にして", {"memory", "audio"}),
    ("メモ帳を閉じて", {"memory", "apps"}),
    ("Kecilkan volume ke 30", {"memory", "audio"}),
    ("buka youtube lalu kecilkan volume", {"memory", "apps", "web", "audio"}),
    ("勉強モードにして", {"memory", "routines"}),
])
def test_select_skills_matches_triggers(text, expected):
    assert {s.id for s in select_skills(text)} == expected


@pytest.mark.parametrize("text", ["こんにちは、ミク！", "Kamu siapa?", "さっき私は何を聞いた？"])
def test_no_trigger_sends_every_skill(text):
    assert len(select_skills(text)) == len(SKILLS)


def test_tool_names_are_unique_and_registered():
    import core.macro_tools  # noqa: F401  (tool Office & pesan, di-import oleh miku.py)
    names = tool_names(SKILLS)
    assert len(names) == len(set(names))
    registered = {t["function"]["name"] for t in registry.get_all_tools_schema()}
    assert set(names) <= registered


def test_get_tools_schema_filters():
    schema = registry.get_tools_schema(["set_volume", "mute", "does_not_exist"])
    assert [t["function"]["name"] for t in schema] == ["set_volume", "mute"]


def _brain(tmp_path, *messages):
    memory = MemoryManager(tmp_path)
    brain = AIBrain(memory)
    memory.start_session("miku")
    brain.client = MagicMock()
    brain.client.chat.side_effect = [{"message": m} for m in messages]
    return brain


def test_think_sends_only_routed_tools(tmp_path):
    brain = _brain(tmp_path, {"content": "", "tool_calls": [
        {"function": {"name": "set_volume", "arguments": {"level": 30}}}]})

    brain.think("音量を30にして")

    sent = {t["function"]["name"] for t in brain.client.chat.call_args.kwargs["tools"]}
    assert sent == {"get_volume", "set_volume", "mute", "media_control", "remember", "recall_memory", "forget"}


def test_routing_can_be_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_brain_module, "SKILL_ROUTING", False)
    brain = _brain(tmp_path, {"content": "[EMOTION:happy] OK"})

    brain.think("音量を30にして")

    assert len(brain.client.chat.call_args.kwargs["tools"]) == len(registry.get_all_tools_schema())


# ── B2: routine ──

@pytest.fixture
def routine_files(tmp_path, monkeypatch):
    example, user = tmp_path / "example.yaml", tmp_path / "user.yaml"
    example.write_text(
        "routines:\n"
        "  - name: mode belajar\n    description: contoh\n    steps:\n"
        "      - {action: set_volume, params: {level: 30}}\n"
        "  - name: mode rusak\n    steps:\n      - {action: hapus_semua}\n",
        encoding="utf-8")
    user.write_text(
        "routines:\n"
        "  - name: mode belajar\n    description: milik user\n    steps:\n"
        "      - {action: set_volume, params: {level: 20}}\n"
        "      - {action: open_application, params: {app_name: vscode}}\n",
        encoding="utf-8")
    monkeypatch.setattr(routines, "ROUTINES_EXAMPLE_FILE", example)
    monkeypatch.setattr(routines, "ROUTINES_FILE", user)
    original = routines.load_routines
    monkeypatch.setattr(routines, "load_routines", lambda files=(example, user): original(files))
    return example, user


def test_user_routine_overrides_example(routine_files):
    loaded = routines.load_routines()
    assert loaded["mode belajar"].description == "milik user"
    assert len(loaded["mode belajar"].steps) == 2


def test_validate_rejects_unknown_and_recursive_steps():
    assert "tidak dikenal" in routines.validate(routines.Routine("x", steps=[{"action": "hapus_semua"}]))
    assert "tidak boleh" in routines.validate(routines.Routine("x", steps=[{"action": "run_routine"}]))
    assert "tidak punya langkah" in routines.validate(routines.Routine("x"))


def test_run_routine_executes_steps_through_system_control(routine_files):
    system_control = MagicMock()
    system_control.execute_action.return_value = (True, "ok")

    ok, msg = routines.run_routine(system_control, "belajar")

    assert ok and "selesai" in msg
    assert [c.args for c in system_control.execute_action.call_args_list] == [
        ("set_volume", {"level": 20}), ("open_application", {"app_name": "vscode"})]


def test_run_routine_stops_at_failed_step(routine_files):
    system_control = MagicMock()
    system_control.execute_action.side_effect = [(False, "audio error"), (True, "ok")]

    ok, msg = routines.run_routine(system_control, "mode belajar")

    assert not ok and "berhenti" in msg
    assert system_control.execute_action.call_count == 1


def test_invalid_routine_is_not_run(routine_files):
    system_control = MagicMock()
    ok, msg = routines.run_routine(system_control, "mode rusak")
    assert not ok and "tidak dikenal" in msg
    system_control.execute_action.assert_not_called()


def test_shipped_example_routines_are_valid():
    shipped = routines._read_file(routines.ROUTINES_EXAMPLE_FILE)
    assert shipped and all(routines.validate(r) is None for r in shipped)


# ── B3: slash command ──

def test_non_command_returns_none(tmp_path):
    assert handle_command("メモ帳を開いて", _brain(tmp_path), None) is None


def test_unknown_command(tmp_path):
    assert "tidak dikenal" in handle_command("/abc", _brain(tmp_path), None)


def test_memory_and_forget_commands(tmp_path):
    long_term_memory.store.remember("kampus", "ITS")
    brain = _brain(tmp_path)

    assert "kampus: ITS" in handle_command("/memory", brain, None)
    assert "Dilupakan" in handle_command("/forget kampus", brain, None)
    assert "Belum ada" in handle_command("/memory", brain, None)


def test_routine_command_goes_through_system_control(tmp_path):
    system_control = MagicMock()
    system_control.execute_action.return_value = (True, "Routine 'mode belajar' selesai")

    out = handle_command("/routine mode belajar", _brain(tmp_path), system_control)

    system_control.execute_action.assert_called_once_with("run_routine", {"name": "mode belajar"})
    assert out.startswith("✅")


def test_help_and_skills_commands(tmp_path):
    brain = _brain(tmp_path)
    assert "/routine <nama>" in handle_command("/help", brain, None)
    assert "Audio & media" in handle_command("/skills", brain, None)


def test_clear_command_empties_history(tmp_path):
    brain = _brain(tmp_path)
    brain.memory.add_message("user", "halo")
    handle_command("/clear", brain, None)
    assert brain.memory.get_context_for_prompt() == []


def test_routine_names_in_prompt_only_when_routine_skill_active(tmp_path):
    brain = _brain(tmp_path)
    brain.turn_tool_names = ["set_volume"]
    assert "Saved routines" not in brain._build_system_prompt()
    brain.turn_tool_names = ["run_routine", "list_routines"]
    assert "mode belajar" in brain._build_system_prompt()
