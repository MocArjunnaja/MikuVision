"""
Skills - kelompok tool yang hanya dikirim ke LLM saat relevan.

Mirip skill Claude: yang selalu ada hanyalah nama + deskripsi singkat; isi
(skema tool) dimuat saat permintaan user cocok dengan pemicu skill. Untuk model
4B dengan konteks 8k, skema 25 tool (±2.300 token) adalah bagian terbesar prompt.
"""

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    description: str
    tools: Tuple[str, ...]
    triggers: "re.Pattern[str]"


def _p(pattern: str) -> "re.Pattern[str]":
    return re.compile(pattern, re.IGNORECASE)


SKILLS: Tuple[Skill, ...] = (
    Skill("audio", "Audio & media", "Volume, mute, play/pause/next",
          ("get_volume", "set_volume", "mute", "media_control"),
          _p(r"音量|ボリューム|ミュート|音を|再生|停止|一時停止|次の曲|前の曲"
             r"|volume|suara|\bmute|unmute|lagu|musik|play|pause|next|prev")),
    Skill("apps", "Aplikasi & folder", "Buka/tutup aplikasi, jendela, tab browser, dan folder",
          ("open_application", "close_application", "close_window", "close_browser_tab", "open_folder"),
          _p(r"開いて|開けて|閉じて|起動|終了|アプリ|フォルダ|メモ帳|電卓|ウィンドウ|タブ"
             r"|\bbuka|tutup|aplikasi|folder|jendela|\bopen|\bclose|\btab\b|window|notepad|calculator|kalkulator"
             r"|chrome|edge|firefox|brave|word|excel|powerpoint|vscode|explorer|spotify|discord|whatsapp|telegram"
             r"|terminal|settings")),
    Skill("web", "Web & pencarian", "Situs, Google, YouTube, Spotify, kontrol tab browser",
          ("open_website", "google_search", "youtube_search", "spotify_search", "browser_media_control",
           "close_browser_tab"),
          _p(r"検索|探して|サイト|ユーチューブ|グーグル|ブラウザ|動画"
             r"|youtube|google|spotify|website|situs|\bcari|carikan|browser|video|\burl")),
    Skill("keyboard", "Keyboard", "Mengetik, tombol, shortcut",
          ("type_text", "press_key", "hotkey"),
          _p(r"入力|タイプ|キー|ショートカット|コピー|貼り付け"
             r"|ketik|tekan|tombol|shortcut|hotkey|copy|paste|\btype")),
    Skill("office", "Dokumen Office", "Membuat/membaca/mengedit Word dan PowerPoint",
          ("create_word_document", "read_word_document", "edit_word_document", "create_powerpoint"),
          _p(r"ワード|文書|ドキュメント|パワポ|プレゼン"
             r"|\bword|dokumen|docx|powerpoint|\bppt|presentasi|slide")),
    Skill("messaging", "Pesan", "Kirim WhatsApp/Telegram (selalu dengan konfirmasi)",
          ("send_whatsapp_message", "send_telegram_message"),
          _p(r"メッセージ|送って|whatsapp|\bwa\b|telegram|kirim pesan|\bpesan|\bchat")),
    Skill("memory", "Memori", "Mengingat, mencari, dan melupakan fakta tentang user",
          ("remember", "recall_memory", "forget"),
          _p(r"覚え|忘れ|思い出|ingat|lupakan|remember|forget|recall")),
    Skill("screen", "Layar", "Membaca layar: aplikasi yang terbuka, pesan error, tulisan, tombol",
          ("describe_screen", "find_on_screen"),
          _p(r"画面|スクリーン|エラー|表示|書いてある|何て書|読んで|ボタン"
             r"|layar|\berror|\beror|tulisan|tertulis|\bbaca|tombol|jendela ini"
             r"|\bscreen|\bbutton|what does it say")),
    Skill("system", "Info sistem", "CPU, RAM, baterai",
          ("get_system_info",),
          _p(r"システム|バッテリー|メモリ|\bcpu|\bram\b|baterai|battery|sistem|spesifikasi")),
    Skill("routines", "Routine", "Menjalankan rangkaian aksi tersimpan (mode belajar, dll.)",
          ("run_routine", "list_routines"),
          _p(r"ルーティン|モード|routine|rutinitas|\bmode\b")),
)

# Selalu dikirim: fakta tentang user bisa muncul di kalimat apa pun
ALWAYS_ON: Tuple[str, ...] = ("memory",)


def select_skills(text: str, skills: Sequence[Skill] = SKILLS, fallback_all: bool = True) -> List[Skill]:
    """
    Skill yang relevan untuk teks user. Bila tidak ada pemicu yang cocok
    (obrolan biasa atau kalimat tak terduga), semua skill dikirim supaya
    tidak ada kemampuan yang hilang. fallback_all=False dipakai bila skill
    buatan user sudah cocok: cukup skill ALWAYS_ON ditambah tool skill itu.
    """
    matched = [s for s in skills if s.triggers.search(text or "")]
    if not [s for s in matched if s.id not in ALWAYS_ON]:
        if not fallback_all:
            return [s for s in skills if s.id in ALWAYS_ON]
        return list(skills)
    always = [s for s in skills if s.id in ALWAYS_ON and s not in matched]
    return always + matched


def tool_names(skills: Iterable[Skill]) -> List[str]:
    names: List[str] = []
    for skill in skills:
        names.extend(t for t in skill.tools if t not in names)
    return names


def find_skill(skill_id: str) -> Optional[Skill]:
    return next((s for s in SKILLS if s.id == skill_id), None)
