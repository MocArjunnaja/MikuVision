"""Pembersihan teks Whisper dan pemilihan bahasa (core/stt_text.py)."""

import pytest

from core.stt_text import apply_corrections, clean_transcript, rank_languages


@pytest.mark.parametrize("text", ["Atur volume ke 30", "Kecilkan volumenya", "Buka Edge"])
def test_correction_does_not_touch_correct_words(text):
    # Versi lama mengganti substring: "volume" -> "volumee"
    assert apply_corrections(text) == text


def test_correction_does_not_break_indonesian_words_containing_ej():
    # Versi lama: "ej" -> "Edge" di tengah kata ("sejak" -> "sEdgeak")
    assert apply_corrections("Sejak kemarin, kejar terus") == "Sejak kemarin, kejar terus"


@pytest.mark.parametrize("wrong, right", [
    ("buka google krom", "buka Google Chrome"),
    ("atur volum ke 20", "atur volume ke 20"),
    ("putar spotifai", "putar Spotify"),
])
def test_correction_fixes_whole_words(wrong, right):
    assert apply_corrections(wrong) == right


@pytest.mark.parametrize("text, language", [
    ("ご視聴ありがとうございました", "ja"),
    ("ご視聴ありがとうございました。", "ja"),
    ("Terima kasih telah menonton!", "id"),
    ("Thank you for watching.", None),
    ("。", "ja"),
    ("...", "id"),
])
def test_hallucination_only_becomes_empty(text, language):
    assert clean_transcript(text, language) == ""


def test_legit_thanks_is_kept():
    # Filter lama di miku.py/gui.py membuang semua kalimat pendek berisi "terima kasih"
    assert clean_transcript("Terima kasih, Miku!", "id") == "Terima kasih, Miku!"


def test_legit_japanese_with_old_blocklist_words_is_kept():
    # Filter lama membuang apa pun yang memuat "字幕" atau "食べる前に"
    assert clean_transcript("字幕をオンにして", "ja") == "字幕をオンにして"
    assert clean_transcript("食べる前に手を洗って", "ja") == "食べる前に手を洗って"


def test_hallucination_suffix_removed_but_command_kept():
    assert clean_transcript("メモ帳を開いて。ご視聴ありがとうございました。", "ja") == "メモ帳を開いて"


def test_repeated_phrase_collapsed():
    assert clean_transcript("開いて開いて開いて開いて", "ja") == "開いて"
    assert clean_transcript("buka buka buka buka notepad", "id") == "buka notepad"


def test_two_repeats_are_not_collapsed():
    assert clean_transcript("ya ya, lanjutkan", "id") == "ya ya, lanjutkan"


def test_foreign_script_dropped_for_indonesian():
    assert clean_transcript("Buka Notepad 你好", "id") == "Buka Notepad"


def test_japanese_keeps_kana_kanji_and_latin():
    assert clean_transcript("YouTubeで初音ミクの歌を検索して", "ja") == "YouTubeで初音ミクの歌を検索して"


def test_rank_languages_restricts_and_merges_malay_into_indonesian():
    probs = [("ms", 0.5), ("id", 0.2), ("ja", 0.2), ("en", 0.1)]
    ranked = rank_languages(probs, ["ja", "id"])
    assert [lang for lang, _ in ranked] == ["id", "ja"]
    assert ranked[0][1] == pytest.approx(0.7 / 0.9)


def test_rank_languages_without_probabilities_is_uniform():
    ranked = rank_languages([("en", 1.0)], ["ja", "id"])
    assert [p for _, p in ranked] == [0.5, 0.5]
