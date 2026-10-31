"""S2: "simpan ini sebagai skill", /skill new, /skill forget."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import core.macro_tools  # noqa: F401  (mendaftarkan tool Office)
import core.system_control  # noqa: F401  (mendaftarkan tool sistem)
from core import ai_brain as ai_brain_module, skill_builder, user_skills
from core.commands import handle_command
from core.conversation import run_turn
from core.skill_builder import Call, Draft, clean_triggers, recent_activity, save_from_chat, wants_to_save
from core.user_skills import load_user_skills, parse_skill_text, select_user_skills


@pytest.mark.parametrize("text", [
    "simpan ini sebagai skill", "jadikan skill ya", "tolong simpan cara tadi jadi skill",
    "Miku, bikin skill dari yang barusan", "save this as a skill", "turn this into a skill",
    "これをスキルとして保存して", "スキルにして", "スキルを登録して",
])
def test_save_requests(text):
    assert wants_to_save(text)


@pytest.mark.parametrize("text", [
    "skill apa saja yang kamu punya?", "buka notepad", "buatkan dokumen word tentang skill komunikasi",
    "simpan dokumen tentang skill komunikasi", "make a presentation about soft skills",
    "kamu punya skill apa?", "スキルは何がある？", "コミュニケーションスキルについて文書を作って保存して",
])
def test_not_save_requests(text):
    assert not wants_to_save(text)


def test_clean_triggers_drops_phrases_that_would_hijack_normal_commands():
    triggers = ["Volume 20", "putar lagu", "buka musik", "音量を20に", "電卓を開いて", "x",
                "LOFI study", "lofi study", "mode belajar", "dokumen rapat", "日報", "ジャズを流して"]

    assert clean_triggers(triggers, "mode belajar") == ["lofi study", "dokumen rapat", "日報", "ジャズを流して"]


def test_clean_triggers_drops_routine_names_and_save_words():
    triggers = ["simpan mode fokus", "mode belajar", "Mode belajar dong", "save focus mode", "集中モードを保存",
                "simpen fokus", "mode fokus sekarang"]

    assert clean_triggers(triggers, "mode fokus", taken=["Mode Belajar"]) == ["mode fokus sekarang"]


# ───────────────────────── riwayat percakapan ─────────────────────────

def _message(role, content, **meta):
    return SimpleNamespace(role=role, content=content, metadata=meta or None)


HISTORY = [
    _message("user", "kecilkan volume ke 20 lalu putar lofi di youtube"),
    _message("assistant", "[EMOTION:happy] Oke!", tool_calls=[
        {"function": {"name": "set_volume", "arguments": {"level": 20}}},
        {"function": {"name": "youtube_search", "arguments": {"query": "lofi hip hop"}}},
    ]),
    _message("tool", "SUKSES - Volume diatur ke 20%", tool_name="set_volume"),
    _message("tool", "SUKSES - Memutar 'lofi hip hop' di YouTube", tool_name="youtube_search"),
    _message("tool", "GAGAL - tidak ada tab", tool_name="browser_media_control"),
    _message("tool", "SUKSES - Routine dijalankan", tool_name="run_routine"),
    _message("assistant", "[EMOTION:happy] 音量を20にして、lofiを流したよ！"),
]


class FakeBrain:
    def __init__(self, messages=HISTORY, draft=None, lang="ja"):
        self.memory = SimpleNamespace(current_context=SimpleNamespace(messages=list(messages)))
        self.conversation_history = []
        self.current_character = SimpleNamespace(lang=lang)
        self.draft = draft if draft is not None else {
            "name": "Mode Belajar", "description": "Volume 20 lalu putar lofi di YouTube",
            "triggers": ["volume 20", "mode belajar", "lofi buat belajar", "勉強モード"],
            "steps": [{"call": 1, "from_user": [], "hint": ""}, {"call": 2, "from_user": [], "hint": ""},
                      {"call": 9, "from_user": [], "hint": ""}],  # nomor 9 tidak ada: diabaikan
        }
        self.prompts = []
        self.recorded = []

    def generate_json(self, prompt, schema):
        self.prompts.append((prompt, schema))
        if isinstance(self.draft, Exception):
            raise self.draft
        return self.draft

    def record_exchange(self, user_input, reply, emotion="neutral"):
        self.recorded.append((user_input, reply, emotion))

    def think(self, user_input):
        raise AssertionError("permintaan simpan skill tidak boleh lewat think()")


def test_recent_activity_pairs_calls_with_arguments_and_keeps_only_successful_ones():
    lines, calls = recent_activity(FakeBrain())

    # GAGAL dan run_routine (terlarang) tidak dihitung
    assert calls == [Call("set_volume", {"level": 20}), Call("youtube_search", {"query": "lofi hip hop"})]
    assert "Miku called set_volume(level=20)" in lines
    assert "Miku: 音量を20にして、lofiを流したよ！" in lines  # tag emosi dibuang
    assert lines[0] == "User: kecilkan volume ke 20 lalu putar lofi di youtube"


def test_recent_activity_without_memory_uses_history_dicts():
    brain = FakeBrain()
    brain.memory = None
    brain.conversation_history = [
        {"role": "user", "content": "buka folder downloads"},
        {"role": "tool", "content": "SUKSES - Folder dibuka", "tool_name": "open_folder"},
    ]

    assert recent_activity(brain)[1] == [Call("open_folder", {})]


# ───────────────────────── save_from_chat ─────────────────────────

def test_draft_is_previewed_and_saved_after_confirmation():
    brain, previews = FakeBrain(), []

    result = save_from_chat(brain, "simpan ini sebagai skill", lambda summary: previews.append(summary) or True)

    assert result.status == "saved"
    path = user_skills.USER_SKILLS_DIR / "mode-belajar" / "SKILL.md"
    assert result.path == path and path.exists()
    skill, error = parse_skill_text(path.read_text(encoding="utf-8"), path)
    assert error is None
    assert skill.name == "mode belajar"
    assert skill.tools == ("set_volume", "youtube_search")
    assert skill.triggers == ("mode belajar", "lofi buat belajar", "勉強モード")  # "volume 20" dibuang
    # Langkah disusun dari tool call yang benar-benar terjadi, lengkap dengan nilainya
    assert skill.instructions.splitlines() == [
        "1. Jangan bertanya dulu: panggil semua tool ini berurutan dalam satu balasan: set_volume, youtube_search",
        "2. Panggil set_volume: level = 20",
        '3. Panggil youtube_search: query = "lofi hip hop"',
    ]
    assert previews[0].startswith(f"Simpan skill 'mode belajar' ke {path}?") and "tools: [set_volume" in previews[0]
    assert '2. youtube_search(query="lofi hip hop")' in brain.prompts[0][0]


DOC_HISTORY = [
    _message("user", "buatkan dokumen word daftar belanja: telur, susu, roti"),
    _message("assistant", "", tool_calls=[{"function": {"name": "create_word_document", "arguments": {
        "filename": "belanja_senin", "content": "Daftar Belanja Senin\n- telur\n- susu\n- roti tawar gandum"}}}]),
    _message("tool", "SUKSES - Dokumen dibuat", tool_name="create_word_document"),
    _message("assistant", "", tool_calls=[{"function": {"name": "open_folder",
                                                        "arguments": {"folder_name_or_path": "Miku_Documents"}}}]),
    _message("tool", "SUKSES - Folder dibuka", tool_name="open_folder"),
]


def test_one_time_content_is_never_copied_into_the_skill():
    # LLM lupa menandai content: teks panjang tetap diambil dari user, dan nama file diganti nama skill
    draft = {"name": "daftar belanja", "description": "Dokumen daftar belanja", "triggers": ["daftar belanja"],
             "steps": [{"call": 1, "from_user": [], "hint": "barang dari user, satu per baris"},
                       {"call": 2, "from_user": [], "hint": ""}]}

    result = save_from_chat(FakeBrain(messages=DOC_HISTORY, draft=draft), "jadikan skill", lambda s: True)

    lines = result.skill.instructions.splitlines()
    assert lines[0].startswith("1. Bila user sudah menyebut isinya, walau singkat")
    assert lines[1] == ('2. Panggil create_word_document: filename = "Daftar_Belanja"; '
                        "content = dari permintaan user saat ini (barang dari user, satu per baris)")
    assert lines[2] == '3. Panggil open_folder: folder_name_or_path = "Miku_Documents"'
    assert "telur" not in result.skill.instructions and "senin" not in result.skill.instructions


def test_fixed_values_stay_fixed_even_if_the_llm_marks_them_and_hints_are_short():
    history = [
        _message("user", "putar lagu yorushika di youtube lalu buka folder downloads"),
        _message("assistant", "", tool_calls=[
            {"function": {"name": "youtube_search", "arguments": {"query": "yorushika"}}},
            {"function": {"name": "open_folder", "arguments": {"folder_name_or_path": "Downloads"}}}]),
        _message("tool", "SUKSES - Memutar", tool_name="youtube_search"),
        _message("tool", "SUKSES - Folder dibuka", tool_name="open_folder"),
    ]
    long_hint = "nama penyanyi atau judul lagu yang diminta user, termasuk tanggal, waktu, tempat, dan peserta"
    draft = {"name": "lagu kerja", "description": "", "triggers": [],
             "steps": [{"call": 1, "from_user": ["query"], "hint": long_hint},
                       {"call": 2, "from_user": ["folder_name_or_path"], "hint": "nama folder"}]}

    result = save_from_chat(FakeBrain(messages=history, draft=draft), "simpan ini sebagai skill", lambda s: True)

    lines = result.skill.instructions.splitlines()
    assert lines[1] == ("2. Panggil youtube_search: query = dari permintaan user saat ini "
                        "(nama penyanyi atau judul lagu yang diminta user, termasuk)")
    assert lines[2] == '3. Panggil open_folder: folder_name_or_path = "Downloads"'


def test_wrong_step_numbers_fall_back_to_every_call_in_order():
    draft = dict(FakeBrain().draft, steps=[{"call": 0, "from_user": [], "hint": ""}, "x"])

    result = save_from_chat(FakeBrain(draft=draft), "simpan ini sebagai skill", lambda s: True)

    assert result.skill.tools == ("set_volume", "youtube_search")


def test_steps_follow_the_order_they_happened_and_the_cap_keeps_the_newest():
    calls = [_message("assistant", "", tool_calls=[{"function": {"name": "set_volume", "arguments": {"level": n}}}])
             for n in range(10, 70, 10)]
    history = [m for i, call in enumerate(calls)
               for m in (call, _message("tool", "SUKSES - ok", tool_name="set_volume"))]
    draft = dict(FakeBrain().draft, steps=[{"call": n, "from_user": [], "hint": ""} for n in (6, 2, 4, 1, 3, 5)])

    result = save_from_chat(FakeBrain(messages=history, draft=draft), "simpan ini sebagai skill", lambda s: True)

    lines = result.skill.instructions.splitlines()
    assert len(lines) == skill_builder.MAX_STEPS
    # Yang dibuang langkah terlama: tugas yang baru selesai ada di akhir
    assert [line.rsplit(" ", 1)[1] for line in lines[1:]] == ["30", "40", "50", "60"]


def _turn(text, *calls):
    """Satu giliran yang berhasil: ucapan user, tool call (nama, argumen), hasil SUKSES."""
    return [
        _message("user", text),
        _message("assistant", "", tool_calls=[{"function": {"name": n, "arguments": a}} for n, a in calls]),
        *[_message("tool", "SUKSES - ok", tool_name=n) for n, _ in calls],
        _message("assistant", "[EMOTION:happy] Sudah!"),
    ]


# Diulang dari miku.py --text di Windows (31 Okt 2026): dua tugas lewat skill contoh (laporan harian,
# musik mood) sebelum tugas yang disimpan. Dulu skill-nya berisi keempat tool dengan volume 30
MIXED_HISTORY = [
    *_turn("buatkan laporan harian: tadi aku belajar fisika bab gelombang dan mengerjakan tugas kalkulus",
           ("create_word_document", {"filename": "Laporan_Harian", "content":
                                     "Laporan Harian\n- Belajar fisika bab gelombang\n- Mengerjakan tugas kalkulus"}),
           ("open_folder", {"folder_name_or_path": "Miku_Documents"})),
    *_turn("putar lagu buat belajar", ("set_volume", {"level": 30}),
           ("youtube_search", {"query": "lofi hip hop study music"})),
    *_turn("kecilkan volume ke 20 lalu putar lofi di youtube", ("set_volume", {"level": 20}),
           ("youtube_search", {"query": "lofi"})),
]
MIXED_DRAFT = {
    "name": "mode fokus", "description": "Volume 20 lalu putar lofi",
    "triggers": ["simpan mode fokus", "mode fokus sekarang", "fokus belajar", "mode belajar", "simpan fokus",
                 "buat laporan harian fokus"],
    "steps": [{"call": n, "from_user": [], "hint": ""} for n in range(1, 7)],  # LLM memilih semuanya
}


def test_history_window_starts_at_a_user_message():
    # 12 pesan terakhir mulai di tengah giliran pertama: open_folder tanpa argumennya tidak ikut
    _, calls = recent_activity(FakeBrain(messages=MIXED_HISTORY), limit=12)

    assert [c.tool for c in calls] == ["set_volume", "youtube_search", "set_volume", "youtube_search"]
    assert calls[0].turn == "putar lagu buat belajar"


def test_saves_the_task_just_finished_not_earlier_skill_tasks_in_the_session():
    brain = FakeBrain(messages=MIXED_HISTORY, draft=MIXED_DRAFT, lang="id")

    result = save_from_chat(brain, "simpan ini sebagai skill, namanya mode fokus", lambda s: True)

    assert result.skill.tools == ("set_volume", "youtube_search")
    assert result.skill.instructions.splitlines()[1:] == [
        "2. Panggil set_volume: level = 20", '3. Panggil youtube_search: query = "lofi"']
    # Tanpa kata simpan, nama routine (dulu run_routine yang terpanggil), atau pemicu skill lain
    assert result.skill.triggers == ("mode fokus", "mode fokus sekarang", "fokus belajar")
    assert skill_builder.reply_for(result, "id")[0] == "Skill 'mode fokus' tersimpan! Lain kali cukup bilang 'mode fokus sekarang'."
    # Giliran yang dikerjakan skill contoh tetap ada di percakapan, tapi bukan calon langkah
    prompt = brain.prompts[0][0]
    calls = prompt.split("grouped by the user request")[1].split("Write the skill")[0]
    assert "User: buatkan laporan harian" in prompt and "create_word_document" not in calls
    assert 'Request 1 (latest): "kecilkan volume ke 20 lalu putar lofi di youtube"\n  1. set_volume(level=20)' in calls


# Tugas sebelumnya tanpa skill: LLM yang memutuskan ucapan mana yang termasuk
DOC_THEN_MUSIC = [
    *_turn("buatkan dokumen word daftar belanja: telur, susu",
           ("create_word_document", {"filename": "belanja", "content": "telur\nsusu"})),
    *_turn("putar jazz di youtube dengan volume 30", ("set_volume", {"level": 30}), ("youtube_search", {"query": "jazz"})),
]


@pytest.mark.parametrize("steps", [[2, 3], [1], [], [3, 2, 1, 9]])
def test_earlier_unrelated_task_is_left_out_unless_the_llm_picks_it_with_the_latest(steps):
    draft = {"name": "jazz", "description": "", "triggers": [], "steps": [{"call": n, "from_user": [], "hint": ""} for n in steps]}
    brain = FakeBrain(messages=DOC_THEN_MUSIC, draft=draft)

    result = save_from_chat(brain, "jadikan skill ya", lambda s: True)

    # Hanya tugas lama, atau pilihan tidak valid: tool call ucapan terakhir saja
    want = ("create_word_document", "set_volume", "youtube_search") if 1 in steps and 2 in steps else ("set_volume", "youtube_search")
    assert result.skill.tools == want
    assert "Always include the calls of the latest request (2)" in brain.prompts[0][0]
    assert "usually all of them" not in brain.prompts[0][0]


@pytest.mark.parametrize("request_text, name", [
    ("simpan ini sebagai skill, namanya mode fokus", "mode fokus"),
    ("simpan cara tadi sebagai skill siap kerja", "siap kerja"),
    ("simpan sebagai skill 'Mode Malam' ya", "mode malam"),
    ("これをスキルとして保存して。名前はジャズタイム", "ジャズタイム"),
    ("これを「朝のルーティン」ってスキルにして", "朝のルーティン"),
    ("save this as a skill called morning routine", "morning routine"),
    ("jadikan skill ya", ""),
    ("simpan ini sebagai skill", ""),
])
def test_name_given_by_the_user_wins(request_text, name):
    assert skill_builder.requested_name(request_text) == name
    if name:
        brain = FakeBrain()
        result = save_from_chat(brain, request_text, lambda summary: True)
        assert result.skill.name == name
        assert f'exactly "{name}"' in brain.prompts[0][0]


def test_japanese_request_gets_japanese_steps():
    result = save_from_chat(FakeBrain(), "これをスキルとして保存して", lambda summary: True)

    assert result.skill.instructions.splitlines()[:2] == [
        "1. 確認なしで、次のツールを同じ返事の中で順番にすべて呼ぶ: set_volume, youtube_search",
        "2. set_volume を呼ぶ: level = 20",
    ]


def test_japanese_opening_step_does_not_let_the_skill_ask_first():
    result = save_from_chat(FakeBrain(), "これをスキルとして保存して", lambda summary: True)

    assert not result.skill.may_ask


def test_trigger_that_is_one_step_of_a_multi_turn_skill_is_dropped():
    history = [
        _message("user", "buka folder downloads"),
        _message("assistant", "", tool_calls=[{"function": {"name": "open_folder",
                                                            "arguments": {"folder_name_or_path": "Downloads"}}}]),
        _message("tool", "SUKSES - Folder dibuka", tool_name="open_folder"),
        _message("user", "buka kalkulator"),
        _message("assistant", "", tool_calls=[{"function": {"name": "open_application",
                                                            "arguments": {"app_name": "Calculator"}}}]),
        _message("tool", "SUKSES - Kalkulator dibuka", tool_name="open_application"),
    ]
    draft = {"name": "siap kerja", "description": "",
             "triggers": ["buka folder downloads", "downloads dan kalkulator"],
             "steps": [{"call": 1, "from_user": [], "hint": ""}, {"call": 2, "from_user": [], "hint": ""}]}

    result = save_from_chat(FakeBrain(messages=history, draft=draft), "simpan cara tadi sebagai skill", lambda s: True)

    # Tugas dua giliran tetap utuh bila LLM memilih kedua ucapan
    assert result.skill.tools == ("open_folder", "open_application")
    assert result.skill.triggers == ("siap kerja", "downloads dan kalkulator")


def test_triggers_skip_save_words():
    draft = dict(FakeBrain().draft, triggers=["simpan cara tadi", "skill kerja", "siap kerja dong", "cara tadi"])

    result = save_from_chat(FakeBrain(draft=draft), "simpan ini sebagai skill", lambda summary: True)

    assert result.skill.triggers == ("mode belajar", "siap kerja dong")


def test_saved_skill_is_used_on_the_next_turn():
    save_from_chat(FakeBrain(), "simpan ini sebagai skill", lambda summary: True)

    skills, errors = load_user_skills()
    assert errors == []
    assert [s.name for s in select_user_skills("lofi buat belajar dong", skills.values())] == ["mode belajar"]


def test_cancelled_draft_is_not_written():
    result = save_from_chat(FakeBrain(), "simpan ini sebagai skill", lambda summary: False)

    assert result.status == "cancelled"
    assert not (user_skills.USER_SKILLS_DIR / "mode-belajar").exists()


def test_without_confirm_callback_nothing_is_saved():
    assert save_from_chat(FakeBrain(), "simpan ini sebagai skill", None).status == "cancelled"


def test_nothing_to_save_without_successful_tools():
    brain = FakeBrain(messages=[_message("user", "apa kabar?"), _message("assistant", "元気だよ！")])

    result = save_from_chat(brain, "simpan ini sebagai skill", lambda summary: True)

    assert result.status == "no_steps"
    assert brain.prompts == []  # LLM tidak dipanggil


@pytest.mark.parametrize("draft, reason", [
    (RuntimeError("Ollama mati"), "Ollama mati"),
    ({"name": "", "description": "", "triggers": [], "steps": []}, "nama"),
])
def test_failed_drafts_are_reported_not_saved(draft, reason):
    result = save_from_chat(FakeBrain(draft=draft), "simpan ini sebagai skill", lambda summary: True)

    assert result.status == "failed" and reason in result.message
    assert not user_skills.USER_SKILLS_DIR.exists() or not any(user_skills.USER_SKILLS_DIR.iterdir())


def test_markdown_round_trips_names_with_quotes_and_colons():
    draft = Draft("日報: 'kuliah'", 'Membuat "laporan": harian', ["daily report"], ["create_word_document"],
                  ["Panggil create_word_document."])

    skill, error = parse_skill_text(draft.to_markdown(), Path("x/SKILL.md"))

    assert error is None and skill.name == "日報: 'kuliah'" and skill.description == 'Membuat "laporan": harian'


def test_replies_follow_the_character_language():
    saved = save_from_chat(FakeBrain(), "simpan ini sebagai skill", lambda summary: True)

    assert skill_builder.reply_for(saved, "ja") == ("スキル『mode belajar』を保存したよ！次からは『lofi buat belajar』って言ってね。", "happy")
    assert skill_builder.reply_for(saved, "id")[0] == "Skill 'mode belajar' tersimpan! Lain kali cukup bilang 'lofi buat belajar'."


# ───────────────────────── run_turn ─────────────────────────

def test_run_turn_saves_without_calling_think():
    brain, shown = FakeBrain(), []
    system_control = SimpleNamespace(confirm_callback=lambda summary: True)

    turn = run_turn(brain, system_control, "これをスキルとして保存して", source="text",
                    on_tool_result=shown.append)

    assert turn.emotion == "happy" and turn.reply.startswith("スキル『mode belajar』を保存したよ")
    assert [(r.action, r.success) for r in shown] == [("save_skill", True)]
    assert brain.recorded == [("これをスキルとして保存して", turn.reply, "happy")]


# ───────────────────────── AIBrain.generate_json ─────────────────────────

def test_generate_json_uses_the_chat_context_size_and_schema():
    brain = ai_brain_module.AIBrain()
    brain.client = MagicMock()
    brain.client.chat.return_value = {"message": {"content": json.dumps({"name": "x"})},
                                      "prompt_eval_count": 900, "eval_count": 40}

    assert brain.generate_json("prompt", {"type": "object"}) == {"name": "x"}
    kwargs = brain.client.chat.call_args.kwargs
    assert kwargs["format"] == {"type": "object"} and "tools" not in kwargs
    assert kwargs["options"]["num_ctx"] == ai_brain_module.OLLAMA_NUM_CTX
    assert kwargs["keep_alive"] == ai_brain_module.OLLAMA_KEEP_ALIVE
    assert brain.turn_usage.prompt_tokens == 900


# ───────────────────────── /skill new, /skill forget ─────────────────────────

def test_skill_new_writes_a_template_that_loads_once_tools_are_filled():
    output = handle_command("/skill new rapat mingguan", MagicMock(), None)

    path = user_skills.USER_SKILLS_DIR / "rapat-mingguan" / "SKILL.md"
    assert f"Template dibuat: {path}" in output and "set_volume" in output and "run_routine" not in output
    assert "tidak punya 'tools'" in load_user_skills()[1][0]  # muncul di /skills sampai diisi

    path.write_text(path.read_text(encoding="utf-8").replace("tools: []", "tools: [open_folder]"), encoding="utf-8")
    assert "rapat mingguan" in load_user_skills()[0]
    assert "sudah ada" in handle_command("/skill new rapat mingguan", MagicMock(), None)


def test_skill_forget_deletes_only_after_confirmation():
    save_from_chat(FakeBrain(), "simpan ini sebagai skill", lambda summary: True)
    folder = user_skills.USER_SKILLS_DIR / "mode-belajar"
    asked = []

    refuse = SimpleNamespace(confirm_callback=lambda summary: asked.append(summary) or False)
    assert handle_command("/skill forget mode belajar", MagicMock(), refuse) == "Skill 'mode belajar' tidak dihapus."
    assert folder.exists() and asked == [f"Hapus skill 'mode belajar' ({folder / 'SKILL.md'})?"]

    accept = SimpleNamespace(confirm_callback=lambda summary: True)
    assert handle_command("/skill forget mode belajar", MagicMock(), accept) == "Skill 'mode belajar' dihapus."
    assert not folder.exists()


def test_skill_forget_leaves_examples_and_unknown_names_alone():
    accept = SimpleNamespace(confirm_callback=lambda summary: True)

    assert "contoh bawaan" in handle_command("/skill forget laporan harian", MagicMock(), accept)
    assert (Path("skills") / "laporan-harian" / "SKILL.md").exists()
    assert "tidak ada" in handle_command("/skill forget tidak ada", MagicMock(), accept)
