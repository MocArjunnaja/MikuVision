"""
Confirmation Gate - aksi berisiko wajib disetujui user sebelum dieksekusi.

LLM bisa salah dengar (STT) atau salah tafsir, jadi aksi yang berdampak ke
luar komputer (kirim pesan) atau mematikan proses tidak boleh jalan otomatis.
"""

import re
from typing import Any, Callable, Dict

# Callback UI: terima ringkasan aksi, kembalikan True jika user setuju.
ConfirmCallback = Callable[[str], bool]

CONFIRM_REQUIRED_ACTIONS = {
    "send_whatsapp_message",
    "send_telegram_message",
    "close_application",
}

# Negasi dicek lebih dulu karena "いいえ" mengandung "いい".
_NEGATIVE_JA = ["いいえ", "だめ", "ダメ", "やめ", "いや", "キャンセル", "違う"]
_POSITIVE_JA = ["はい", "うん", "いいよ", "お願い", "オーケー", "送って", "どうぞ"]
_NEGATIVE_WORDS = {"tidak", "nggak", "gak", "enggak", "jangan", "batal", "no", "cancel", "stop"}
_POSITIVE_WORDS = {"ya", "iya", "yes", "boleh", "oke", "ok", "okay", "lanjut", "kirim", "betul", "benar", "silakan", "y"}


def requires_confirmation(action: str) -> bool:
    return action in CONFIRM_REQUIRED_ACTIONS


def describe_action(action: str, params: Dict[str, Any]) -> str:
    """Ringkasan aksi yang mudah dibaca user."""
    if action == "send_whatsapp_message":
        return f"Kirim WhatsApp ke '{params.get('contact_name', '?')}': \"{params.get('message', '')}\""
    if action == "send_telegram_message":
        return f"Kirim Telegram ke '{params.get('contact_name', '?')}': \"{params.get('message', '')}\""
    if action == "close_application":
        return (
            f"Tutup aplikasi '{params.get('app_name', '?')}' "
            "(SEMUA jendelanya ikut ditutup, termasuk yang tidak dibuka Miku)"
        )
    return f"{action} {params}"


def is_affirmative(text: str) -> bool:
    """True hanya jika jawaban jelas 'ya'. Jawaban kosong/ambigu dianggap tidak."""
    if not text:
        return False

    if any(token in text for token in _NEGATIVE_JA):
        return False

    words = set(re.findall(r"[a-z]+", text.lower()))
    if words & _NEGATIVE_WORDS:
        return False

    if any(token in text for token in _POSITIVE_JA):
        return True
    return bool(words & _POSITIVE_WORDS)
