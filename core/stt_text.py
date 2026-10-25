"""
Pembersihan teks hasil Whisper dan pemilihan bahasa, tanpa dependency model.

Diadopsi dari alat transkrip Tugas Akhir (``pdf_transkrip.bersihkan``): buang frasa
halusinasi derau, pengulangan beruntun, dan huruf di luar aksara bahasa target.
"""

import re
import unicodedata
from typing import Dict, Iterable, List, Optional, Tuple

# Kalimat yang sering "didengar" Whisper dari derau atau hening (data latihnya video YouTube)
HALLUCINATION_PHRASES = (
    "ご視聴ありがとうございました",
    "最後までご視聴いただきありがとうございます",
    "チャンネル登録よろしくお願いします",
    "チャンネル登録お願いします",
    "字幕は自動生成されています",
    "terima kasih telah menonton",
    "terima kasih sudah menonton",
    "terima kasih telah menyaksikan",
    "jangan lupa like dan subscribe",
    "thank you for watching",
    "thanks for watching",
    "subtitles by the amara.org community",
)

# Salah dengar yang sering muncul untuk perintah. Dicocokkan per kata utuh,
# supaya "volume" tidak menjadi "volumee" dan "sejak" tidak menjadi "sEdgeak".
CORRECTIONS = {
    "krom": "Chrome",
    "crom": "Chrome",
    "google krom": "Google Chrome",
    "google crom": "Google Chrome",
    "bolum": "volume",
    "folum": "volume",
    "volum": "volume",
    "bukal": "buka",
    "bukak": "buka",
    "skrinshot": "screenshot",
    "screen shot": "screenshot",
    "notpad": "Notepad",
    "yutub": "YouTube",
    "spotifai": "Spotify",
    "wasap": "WhatsApp",
    "watsap": "WhatsApp",
    "hegum": "hukum",  # "Hukum Newton" terdengar "Hegum Newton" (sesi GUI 25 Okt)
}

_CORRECTION_PATTERNS = [
    (re.compile(rf"(?<!\w){re.escape(wrong)}(?!\w)", re.IGNORECASE), right)
    # frasa panjang dulu, supaya "google krom" diganti utuh sebelum "krom"
    for wrong, right in sorted(CORRECTIONS.items(), key=lambda item: -len(item[0]))
]

_JAPANESE_RANGES = (
    (0x3000, 0x303F),  # tanda baca Jepang
    (0x3040, 0x30FF),  # hiragana + katakana
    (0x31F0, 0x31FF),  # katakana tambahan
    (0x4E00, 0x9FFF),  # kanji
    (0xFF00, 0xFFEF),  # huruf lebar penuh
)

# Bahasa yang sering tertukar oleh deteksi Whisper: Indonesia sering dianggap Melayu
LANGUAGE_ALIASES = {"id": ("ms", "jw", "su")}


def _is_japanese_char(char: str) -> bool:
    code = ord(char)
    return any(low <= code <= high for low, high in _JAPANESE_RANGES)


def _allowed_char(char: str, language: Optional[str]) -> bool:
    if ord(char) < 0x250 or char in "–—‘’“”…":
        return True  # Latin, angka, tanda baca umum
    if language == "ja" or language is None:
        return _is_japanese_char(char)
    return False


def _strip_hallucinations(text: str) -> str:
    for phrase in HALLUCINATION_PHRASES:
        text = re.sub(re.escape(phrase) + r"[。.!！]*", " ", text, flags=re.IGNORECASE)
    return text


def _collapse_repeats(text: str) -> str:
    """Potongan yang diulang tiga kali atau lebih beruntun disisakan satu ("開いて開いて開いて")."""
    return re.sub(r"(.{2,}?)(?:[\s、。,.!?！？]*\1){2,}", r"\1", text)


def apply_corrections(text: str) -> str:
    def keep_capital(match: "re.Match[str]", right: str) -> str:
        # "Hegum" -> "Hukum", "hegum" -> "hukum"; nama produk ("Chrome") tetap apa adanya
        return right[0].upper() + right[1:] if match.group(0)[0].isupper() else right

    for pattern, right in _CORRECTION_PATTERNS:
        text = pattern.sub(lambda m, r=right: keep_capital(m, r), text)
    return text


def clean_transcript(text: str, language: Optional[str] = None) -> str:
    """Rapikan hasil Whisper. Mengembalikan "" bila yang tersisa hanya artefak."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = _strip_hallucinations(text)
    text = "".join(c for c in text if _allowed_char(c, language))
    text = _collapse_repeats(text)
    text = apply_corrections(text)
    text = re.sub(r"\s{2,}", " ", text).strip(" 、。,.")
    # Sisa tanda baca saja (mis. "。" atau "...") dianggap tidak ada ucapan
    if not any(c.isalnum() for c in text):
        return ""
    return text


def rank_languages(
    probabilities: Iterable[Tuple[str, float]], languages: Iterable[str]
) -> List[Tuple[str, float]]:
    """Peluang deteksi Whisper dibatasi ke bahasa yang dipakai user, dinormalisasi jadi 0..1.

    Peluang bahasa yang sering tertukar (Melayu untuk Indonesia) dijumlahkan ke bahasa tujuannya.
    """
    probs: Dict[str, float] = dict(probabilities)
    scores = {}
    for lang in languages:
        scores[lang] = probs.get(lang, 0.0) + sum(probs.get(a, 0.0) for a in LANGUAGE_ALIASES.get(lang, ()))
    total = sum(scores.values())
    if total <= 0:
        return [(lang, 1.0 / len(scores)) for lang in scores]
    return sorted(((lang, s / total) for lang, s in scores.items()), key=lambda item: -item[1])
