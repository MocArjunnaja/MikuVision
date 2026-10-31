"""Skill buatan user (SKILL.md): parsing, pemicu, routing ke LLM, prompt, slash command."""

from unittest.mock import MagicMock

import pytest

import core.macro_tools  # noqa: F401  (tool Office yang dipakai contoh skill)
from core import user_skills
from core.ai_brain import AIBrain
from core.commands import handle_command
from core.conversation import run_turn
from core.memory import MemoryManager
from core.user_skills import load_user_skills, parse_skill, select_user_skills


def _write(folder, dirname, text):
    path = folder / dirname / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


VOLUME_SKILL = """---
name: mode malam
description: Volume pelan untuk malam hari
triggers: [mode malam, 夜モード]
tools: [set_volume]
---
Panggil set_volume dengan level 15.
"""


# ── Parsing ──

def test_parse_valid_skill(tmp_path):
    skill, error = parse_skill(_write(tmp_path, "malam", VOLUME_SKILL))
    assert error is None
    assert skill.name == "mode malam"
    assert skill.tools == ("set_volume",)
    assert skill.triggers == ("mode malam", "夜モード")
    assert skill.instructions == "Panggil set_volume dengan level 15."


@pytest.mark.parametrize("text, reason", [
    ("tanpa front matter", "front matter"),
    ("---\ndescription: x\ntools: [set_volume]\n---\nisi", "'name'"),
    ("---\nname: a\n---\nisi", "'tools'"),
    ("---\nname: a\ntools: [format_disk]\n---\nisi", "tidak dikenal"),
    ("---\nname: a\ntools: [run_routine]\n---\nisi", "run_routine"),
    ("---\nname: a\ntools: [set_volume]\n---\n", "petunjuk"),
    ("---\nname: a\ntools: [set_volume]\n---\n" + "kata " * 400, "terlalu panjang"),
    ("---\nname: [a\n---\nisi", "tidak valid"),
])
def test_invalid_skill_is_rejected_with_reason(tmp_path, text, reason):
    skill, error = parse_skill(_write(tmp_path, "rusak", text))
    assert skill is None
    assert reason in error


def test_crlf_and_bom_are_accepted(tmp_path):
    text = "﻿" + VOLUME_SKILL.replace("\n", "\r\n")
    skill, error = parse_skill(_write(tmp_path, "malam", text))
    assert error is None and skill.tools == ("set_volume",)


def test_user_folder_overrides_example_with_same_name(tmp_path):
    example, user = tmp_path / "example", tmp_path / "user"
    _write(example, "malam", VOLUME_SKILL)
    _write(user, "malam", VOLUME_SKILL.replace("level 15", "level 5"))
    _write(user, "rusak", "tanpa front matter")

    skills, errors = load_user_skills((example, user))

    assert list(skills) == ["mode malam"]
    assert "level 5" in skills["mode malam"].instructions
    assert errors == ["rusak/SKILL.md: tidak diawali front matter '---'"]


def test_shipped_example_skills_are_valid():
    skills, errors = load_user_skills()
    assert errors == []
    assert {"laporan harian", "musik mood"} <= set(skills)


# ── Pemicu ──

@pytest.fixture
def examples():
    return list(load_user_skills()[0].values())


@pytest.mark.parametrize("text, expected", [
    ("buatkan laporan harian dong", ["laporan harian"]),
    ("Laporan hariannya tolong", ["laporan harian"]),
    ("日報を作って", ["laporan harian"]),
    ("putar lagu buat belajar", ["musik mood"]),
    ("作業用BGMかけて", ["musik mood"]),
    ("buka notepad", []),
    ("こんにちは", []),
])
def test_select_user_skills(examples, text, expected):
    assert [s.name for s in select_user_skills(text, examples)] == expected


def test_trigger_must_start_a_word(tmp_path):
    skill, _ = parse_skill(_write(tmp_path, "mood", VOLUME_SKILL.replace("[mode malam, 夜モード]", "[bgm]")))
    assert select_user_skills("putar bgm", [skill]) == [skill]
    assert select_user_skills("abgm", [skill]) == []


def test_at_most_two_skills_and_longest_trigger_first(tmp_path):
    skills = []
    for i, trigger in enumerate(["musik", "musik santai sore", "musik santai"]):
        text = VOLUME_SKILL.replace("mode malam", f"skill {i}").replace("[skill %d, 夜モード]" % i, f"[{trigger}]")
        skills.append(parse_skill(_write(tmp_path, f"s{i}", text))[0])
    picked = select_user_skills("putar musik santai sore", skills)
    assert [s.name for s in picked] == ["skill 1", "skill 2"]


# ── Routing dan prompt di AIBrain ──

def _brain(tmp_path, *messages):
    memory = MemoryManager(tmp_path)
    brain = AIBrain(memory)
    memory.start_session("miku")
    brain.client = MagicMock()
    brain.client.chat.side_effect = [{"message": m} for m in messages]
    return brain


def _sent_tools(brain, call=-1):
    return {t["function"]["name"] for t in brain.client.chat.call_args_list[call].kwargs["tools"]}


def _system_prompt(brain, call=-1):
    return brain.client.chat.call_args_list[call].kwargs["messages"][0]["content"]


def test_active_skill_sends_its_tools_and_instructions_only(tmp_path):
    brain = _brain(tmp_path, {"content": "", "tool_calls": [
        {"function": {"name": "create_word_document", "arguments": {"filename": "a", "content": "b"}}}]})

    brain.think("buatkan laporan harian: tadi belajar fisika")

    # Tidak ada skill bawaan yang cocok, jadi bukan semua tool yang dikirim
    assert _sent_tools(brain) == {"create_word_document", "open_folder", "remember", "recall_memory", "forget"}
    prompt = _system_prompt(brain)
    assert "## Active skill: laporan harian" in prompt
    assert "Laporan_Harian" in prompt
    # Skill lain hanya disebut nama dan deskripsinya
    assert "- musik mood:" in prompt
    assert "lofi hip hop" not in prompt


def test_user_skill_tools_join_matching_builtin_skills(tmp_path):
    brain = _brain(tmp_path, {"content": "[EMOTION:happy] OK"})
    brain.think("putar lagu buat belajar")
    assert {"youtube_search", "set_volume", "media_control"} <= _sent_tools(brain)


def test_without_active_skill_prompt_lists_skills_but_no_instructions(tmp_path):
    brain = _brain(tmp_path, {"content": "[EMOTION:happy] Halo!"})
    brain.think("こんにちは")
    prompt = _system_prompt(brain)
    assert "Active skill" not in prompt
    assert "- laporan harian:" in prompt and "- musik mood:" in prompt


def test_skill_that_asks_stays_active_for_the_answer(tmp_path):
    brain = _brain(
        tmp_path,
        {"content": "[EMOTION:happy] Hari ini kamu ngapain saja?"},
        {"content": "", "tool_calls": [
            {"function": {"name": "create_word_document", "arguments": {"filename": "a", "content": "b"}}}]},
        {"content": "[EMOTION:happy] Oke!"},
    )

    brain.think("buatkan laporan harian")
    # Pertanyaan skill tidak dipaksa menjadi tool call oleh retry
    assert brain.client.chat.call_count == 1

    _, calls, _ = brain.think("tadi belajar fisika lalu rapat")
    assert calls[0]["action"] == "create_word_document"
    assert "## Active skill: laporan harian" in _system_prompt(brain)

    # Setelah tool dipanggil, skill tidak dibawa lagi
    brain.think("makasih")
    assert "Active skill" not in _system_prompt(brain)


def test_user_skill_from_data_folder_is_used(tmp_path):
    _write(user_skills.USER_SKILLS_DIR, "malam", VOLUME_SKILL)
    brain = _brain(tmp_path, {"content": "", "tool_calls": [
        {"function": {"name": "set_volume", "arguments": {"level": 15}}}]})

    brain.think("夜モードにして")

    assert "Panggil set_volume dengan level 15." in _system_prompt(brain)
    assert "set_volume" in _sent_tools(brain)


def test_only_skills_that_say_ask_may_skip_the_tool_retry(examples):
    by_name = {s.name: s for s in examples}
    assert by_name["laporan harian"].may_ask
    assert not by_name["musik mood"].may_ask


@pytest.mark.parametrize("text, expected", [
    ("buatkan laporan harian", False),
    ("tolong buatkan laporan harian ya miku", False),
    ("日報を作って", False),
    ("buatkan laporan harian: tadi kuliah kalkulus, praktikum fisika, lalu rapat", True),
    ("日報を作って。今日は数学の授業とアルバイトがあった", True),
])
def test_details_given(examples, text, expected):
    skill = next(s for s in examples if s.name == "laporan harian")
    assert user_skills.details_given(skill, text) is expected


def test_question_after_details_still_gets_the_tool_retry(tmp_path):
    brain = _brain(
        tmp_path,
        {"content": "[EMOTION:happy] 数学とアルバイトだったんだね！ほかに何かある？"},
        {"content": "", "tool_calls": [
            {"function": {"name": "create_word_document", "arguments": {"filename": "a", "content": "数学"}}}]},
    )
    _, calls, _ = brain.think("日報を作って。今日は数学の授業とアルバイトがあった")
    assert [c["action"] for c in calls] == ["create_word_document"]


def test_promise_while_asking_still_gets_the_tool_retry(tmp_path):
    brain = _brain(
        tmp_path,
        {"content": "[EMOTION:happy] 今日の日報を作りますね！ほかに何かある？"},
        {"content": "", "tool_calls": [
            {"function": {"name": "create_word_document", "arguments": {"filename": "a", "content": "数学"}}}]},
    )
    _, calls, _ = brain.think("日報を作って。今日は数学の授業があった")
    assert [c["action"] for c in calls] == ["create_word_document"]


# ── Langkah skill berikutnya (run_turn) ──

def _tool_call(name, **arguments):
    return {"content": "", "tool_calls": [{"function": {"name": name, "arguments": arguments}}]}


def _system_control(fail=()):
    control = MagicMock()
    control.execute_action.side_effect = lambda action, params: (action not in fail, f"{action} selesai")
    return control


def test_run_turn_asks_for_the_next_skill_tool(tmp_path):
    brain = _brain(tmp_path,
                   _tool_call("set_volume", level=30),
                   _tool_call("youtube_search", query="lofi hip hop study music"),
                   {"content": "[EMOTION:happy] Selamat belajar!"})
    control = _system_control()

    turn = run_turn(brain, control, "putar lagu buat belajar", source="text")

    assert [r.action for r in turn.tool_results] == ["set_volume", "youtube_search"]
    # Langkah kedua hanya ditawari tool skill yang belum dipakai
    assert _sent_tools(brain, call=1) == {"youtube_search"}
    assert "Continue the active skill" in brain.client.chat.call_args_list[1].kwargs["messages"][-1]["content"]
    # Semua tool skill sudah dipakai: langsung laporan, tanpa tanya langkah lagi
    assert brain.client.chat.call_count == 3
    assert turn.reply == "Selamat belajar!"


def test_run_turn_asks_for_skill_steps_when_the_model_only_chats(tmp_path):
    # "bgm dong" memicu skill musik mood tapi tidak berisi kata kerja aksi
    brain = _brain(tmp_path,
                   {"content": "[EMOTION:happy] Semangat belajar ya! Mau lagu apa?"},
                   _tool_call("set_volume", level=30),
                   _tool_call("youtube_search", query="lofi hip hop study music"))
    turn = run_turn(brain, _system_control(), "bgm dong", source="text", report_results=False)

    assert [r.action for r in turn.tool_results] == ["set_volume", "youtube_search"]
    assert turn.reply == ""  # pertanyaan tadi sudah tidak berlaku


def test_run_turn_lets_a_skill_ask_for_missing_details(tmp_path):
    brain = _brain(tmp_path, {"content": "[EMOTION:happy] Oke! Hari ini kegiatanmu apa saja?"})
    turn = run_turn(brain, _system_control(), "buatkan laporan harian", source="text")

    assert turn.tool_results == [] and brain.client.chat.call_count == 1
    assert brain.awaiting_skill_details


def test_run_turn_stops_skill_steps_after_a_failed_tool(tmp_path):
    brain = _brain(tmp_path, _tool_call("set_volume", level=30), {"content": "[EMOTION:sad] Gagal"})
    turn = run_turn(brain, _system_control(fail={"set_volume"}), "putar lagu buat belajar", source="text")
    assert [r.action for r in turn.tool_results] == ["set_volume"]
    assert brain.client.chat.call_count == 2


def test_run_turn_without_user_skill_makes_no_extra_call(tmp_path):
    brain = _brain(tmp_path, _tool_call("set_volume", level=30), {"content": "[EMOTION:happy] OK"})
    run_turn(brain, _system_control(), "音量を30にして", source="text")
    assert brain.client.chat.call_count == 2


def test_skill_step_reply_without_tool_ends_the_loop(tmp_path):
    brain = _brain(tmp_path,
                   _tool_call("create_word_document", filename="a", content="b"),
                   {"content": "Semua langkah selesai."},
                   {"content": "[EMOTION:happy] Sudah jadi!"})
    turn = run_turn(brain, _system_control(), "buatkan laporan harian: tadi belajar", source="text")
    assert [r.action for r in turn.tool_results] == ["create_word_document"]
    assert turn.reply == "Sudah jadi!"


# ── Skill bernilai tetap (buatan "simpan ini sebagai skill") ──

FOCUS_SKILL = """---
name: mode fokus
description: Volume pelan lalu musik lofi
triggers: [putar lofi, fokus belajar]
tools: [set_volume, youtube_search]
---
1. Jangan bertanya dulu: panggil semua tool ini berurutan dalam satu balasan: set_volume, youtube_search
2. Panggil set_volume: level = 20
3. Panggil youtube_search: query = "lofi music; study"
"""
FOCUS_CALLS = [{"action": "set_volume", "params": {"level": 20}},
               {"action": "youtube_search", "params": {"query": "lofi music; study"}}]


def _skill(tmp_path, text):
    skill, error = parse_skill(_write(tmp_path, "s", text))
    assert error is None, error
    return skill


def test_fixed_calls_of_a_saved_skill(tmp_path):
    assert _skill(tmp_path, FOCUS_SKILL).fixed_calls == FOCUS_CALLS


def test_fixed_calls_of_a_japanese_saved_skill(tmp_path):
    text = ("---\nname: ジャズタイム\ntools: [set_volume, youtube_search]\n---\n"
            "1. 確認なしで、次のツールを同じ返事の中で順番にすべて呼ぶ: set_volume, youtube_search\n"
            "2. set_volume を呼ぶ: level = 25\n3. youtube_search を呼ぶ: query = \"ジャズ\"\n")
    assert _skill(tmp_path, text).fixed_calls == [{"action": "set_volume", "params": {"level": 25}},
                                                 {"action": "youtube_search", "params": {"query": "ジャズ"}}]


def test_fixed_calls_use_the_default_of_a_user_value(tmp_path):
    # Isian dari user dengan nilai bawaan (skill_builder.DEFAULT_PARAMS); keterangannya boleh berkurung
    text = ("---\nname: ジャズタイム\ntools: [set_volume, youtube_search]\n---\n"
            "1. 確認なしで、次のツールを同じ返事の中で順番にすべて呼ぶ: set_volume, youtube_search\n"
            "2. set_volume を呼ぶ: level = 30\n"
            '3. youtube_search を呼ぶ: query = "jazz (smooth)" (ユーザーが別の内容を言えばそれを使う: ジャンル (例: ボサノバ))\n')
    skill = _skill(tmp_path, text)
    assert not skill.may_ask
    assert skill.fixed_calls == [{"action": "set_volume", "params": {"level": 30}},
                                 {"action": "youtube_search", "params": {"query": "jazz (smooth)"}}]


@pytest.mark.parametrize("steps", [
    # Isian dari permintaan user
    '1. Bila user sudah menyebut isinya, langsung panggil: create_word_document\n'
    '2. Panggil create_word_document: filename = "Belanja"; content = dari permintaan user saat ini (daftar barang)',
    '2. create_word_document を呼ぶ: filename = "Nikki"; content = 今回のユーザーの依頼から',
    # Petunjuk bebas yang ditulis sendiri
    "Panggil set_volume dengan level 15.",
    "2. Panggil set_volume: level = 20\nLalu tanyakan lagu apa yang diinginkan.",
    # Tool di luar daftar tools skill
    "2. Panggil open_application: app_name = \"Notepad\"",
])
def test_skills_that_need_the_model_have_no_fixed_calls(tmp_path, steps):
    text = f"---\nname: x\ntools: [set_volume, create_word_document]\n---\n{steps}\n"
    assert _skill(tmp_path, text).fixed_calls is None


def test_example_skills_still_go_through_the_model(examples):
    assert all(skill.fixed_calls is None for skill in examples)


def test_fixed_skill_runs_even_when_the_model_only_chats(tmp_path):
    _write(user_skills.USER_SKILLS_DIR, "mode-fokus", FOCUS_SKILL)
    brain = _brain(tmp_path, {"content": "[EMOTION:happy] モード fokus に切り替えますね！"})

    turn = run_turn(brain, _system_control(), "mode fokus dong", source="text", report_results=False)

    assert [(r.action, r.params) for r in turn.tool_results] == [(c["action"], c["params"]) for c in FOCUS_CALLS]
    # Langkahnya dari SKILL.md, tanpa panggilan model kedua
    assert brain.client.chat.call_count == 1


def test_fixed_skill_finishes_the_steps_the_model_skipped(tmp_path):
    _write(user_skills.USER_SKILLS_DIR, "mode-fokus", FOCUS_SKILL)
    # Model memakai nilai lain dari ucapan user; langkah itu tidak diulang dengan nilai skill
    brain = _brain(tmp_path, _tool_call("set_volume", level=35))

    turn = run_turn(brain, _system_control(), "mode fokus dong, volume 35 aja", source="text",
                    report_results=False)

    assert [(r.action, r.params) for r in turn.tool_results] == [
        ("set_volume", {"level": 35}), ("youtube_search", {"query": "lofi music; study"})]
    assert brain.client.chat.call_count == 1


def _routine_call(routine_name):
    return {"content": "", "tool_calls": [{"function": {"name": "run_routine", "arguments": {"name": routine_name}}}]}


def test_unknown_routine_named_like_the_skill_is_dropped(tmp_path):
    # "mode fokus dong" juga memicu skill routine (kata "mode"); routine "mode fokus" tidak ada
    _write(user_skills.USER_SKILLS_DIR, "mode-fokus", FOCUS_SKILL)
    brain = _brain(tmp_path, _routine_call("mode fokus"))

    turn = run_turn(brain, _system_control(), "mode fokus dong", source="text", report_results=False)

    assert [r.action for r in turn.tool_results] == ["set_volume", "youtube_search"]


def test_existing_routine_still_runs_with_a_user_skill_active(tmp_path):
    _write(user_skills.USER_SKILLS_DIR, "mode-fokus", FOCUS_SKILL)
    brain = _brain(tmp_path, _routine_call("mode belajar"))

    _, calls, _ = brain.think("putar lofi lalu jalankan mode belajar")

    assert [c["params"]["name"] for c in calls] == ["mode belajar"]


def test_negated_request_does_not_run_fixed_steps(tmp_path):
    _write(user_skills.USER_SKILLS_DIR, "mode-fokus", FOCUS_SKILL)
    brain = _brain(tmp_path, {"content": "[EMOTION:happy] Oke, tidak jadi."},
                   {"content": "Tidak ada langkah."})

    turn = run_turn(brain, _system_control(), "mode fokus jangan dulu ya", source="text", report_results=False)

    assert turn.tool_results == []
    # Model yang memutuskan, seperti skill biasa
    assert "Continue the active skill" in brain.client.chat.call_args_list[1].kwargs["messages"][-1]["content"]


# ── Permintaan berurutan tanpa skill ("… lalu …") ──

@pytest.mark.parametrize("text, parts", [
    ("kecilkan volume ke 20 lalu putar lofi di youtube", 2),
    ("buka notepad, terus buka kalkulator", 2),
    ("音量を20にして、ローファイを流して", 2),
    ("kecilkan volume ke 20", 1),
    ("carikan lagu buat tidur", 1),
    ("buka notepad dan kalkulator", 1),
    ("halo miku, apa kabar", 0),
])
def test_action_parts(text, parts):
    from core.ai_brain import _action_parts
    assert len(_action_parts(text)) == parts


def test_rest_of_a_sequential_request_is_asked_once(tmp_path):
    brain = _brain(tmp_path,
                   _tool_call("set_volume", level=20),
                   # Model mengulang set_volume dan menambah youtube_search: yang sama persis dibuang
                   {"content": "", "tool_calls": [
                       {"function": {"name": "set_volume", "arguments": {"level": 20}}},
                       {"function": {"name": "youtube_search", "arguments": {"query": "lofi"}}}]})

    turn = run_turn(brain, _system_control(), "kecilkan volume ke 20 lalu putar lofi di youtube",
                    source="text", report_results=False)

    assert [r.action for r in turn.tool_results] == ["set_volume", "youtube_search"]
    instruction = brain.client.chat.call_args_list[1].kwargs["messages"][-1]["content"]
    assert "several actions" in instruction and 'set_volume({"level": 20})' in instruction
    assert brain.client.chat.call_count == 2


def test_rest_of_a_sequential_request_is_asked_again_without_used_tools(tmp_path):
    brain = _brain(tmp_path,
                   _tool_call("set_volume", level=20),
                   _tool_call("set_volume", level=20),  # hanya mengulang: dibuang
                   _tool_call("youtube_search", query="lofi"))

    turn = run_turn(brain, _system_control(), "kecilkan volume ke 20 lalu putar lofi di youtube",
                    source="text", report_results=False)

    assert [r.action for r in turn.tool_results] == ["set_volume", "youtube_search"]
    assert "set_volume" in _sent_tools(brain, call=1)
    assert "set_volume" not in _sent_tools(brain, call=2) and "youtube_search" in _sent_tools(brain, call=2)
    assert brain.client.chat.call_count == 3


def test_sequential_request_done_in_one_reply_needs_no_extra_call(tmp_path):
    brain = _brain(tmp_path, {"content": "", "tool_calls": [
        {"function": {"name": "set_volume", "arguments": {"level": 20}}},
        {"function": {"name": "youtube_search", "arguments": {"query": "lofi"}}}]})

    run_turn(brain, _system_control(), "kecilkan volume ke 20 lalu putar lofi di youtube",
             source="text", report_results=False)

    assert brain.client.chat.call_count == 1


# ── Slash command ──

def test_skills_command_lists_user_skills_and_errors(tmp_path):
    _write(user_skills.USER_SKILLS_DIR, "rusak", "---\nname: x\ntools: [format_disk]\n---\nisi")
    out = handle_command("/skills", _brain(tmp_path), None)
    assert "Audio & media" in out
    assert "laporan harian" in out and "musik mood" in out
    assert "rusak/SKILL.md: tool 'format_disk' tidak dikenal" in out


def test_skill_command_shows_one_skill(tmp_path):
    out = handle_command("/skill musik", _brain(tmp_path), None)
    assert "Skill 'musik mood'" in out
    assert "youtube_search, set_volume" in out
    assert "lofi hip hop" in out
    assert "tidak ditemukan" in handle_command("/skill tidak-ada", _brain(tmp_path), None)
