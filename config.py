"""
MikuWin v4 Configuration
Miku-only edition with RVC voice and sprite-based UI.
"""

from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ============ Paths ============
BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"
AVATAR_DIR = ASSETS_DIR / "avatar"
DATA_DIR = BASE_DIR / "data"
AUDIO_DIR = BASE_DIR / "temp_audio"

# Sprite-sheet UI assets for v4 GUI
MIKU_SPRITE_SHEET = AVATAR_DIR / "miku_smart_sheet.png"
MIKU_FRAME_W = 177
MIKU_FRAME_H = 265
MIKU_SHEET_COLS = 20

# RVC model directory (shared across versions)
RVC_MODELS_DIR = BASE_DIR / "models" / "miku_default_rvc"

# Set up Models folder and path
MODELS_DIR = BASE_DIR / "models"
MODELS_DIR.mkdir(exist_ok=True)

# Pastikan folder ada
ASSETS_DIR.mkdir(exist_ok=True)
AVATAR_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)
AUDIO_DIR.mkdir(exist_ok=True)

# ============ Whisper Config ============
# Opsi Faster-Whisper: tiny, base, small, medium, large-v3
# "large-v3" paling akurat untuk intonasi orang Indonesia - sudah di-optimize int8 1.5GB
WHISPER_MODEL = "large-v3-turbo"
WHISPER_LANGUAGE = None  # Auto-detect, will be overridden per character

# Initial prompts per language untuk vocabulary hint
WHISPER_PROMPTS = {
    "ja": """
開く、閉じる、ボリューム、ミュート、スクリーンショット。
Google Chrome、Microsoft Edge、Firefox、Notepad、YouTube。
音量を上げて、音量を下げて、アプリを開いて、検索して。
""",
    "id": """
Buka Google Chrome, Microsoft Edge, Firefox, Notepad, Explorer, Settings.
Volume, mute, unmute, screenshot, minimize, maximize, close.
Tolong, bisa, coba, atur, buka, tutup, jalankan, matikan.
"""
}

# Default prompt (fallback)
WHISPER_INITIAL_PROMPT = WHISPER_PROMPTS.get("id", "")

import torch
WHISPER_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"[Config] Whisper will use: {WHISPER_DEVICE}")

# ============ Ollama/LLM Config ============
OLLAMA_MODEL = "qwen3:4b" # Naik kelas ke 7B untuk kecerdasan Agentic bilingual
OLLAMA_BASE_URL = "http://localhost:11434"

# ============ TTS Config ============
TTS_VOICE = "id-ID-GadisNeural"
TTS_RATE = "+10%"
TTS_PITCH = "+5Hz"

# ============ Hotkey Config ============
WAKE_HOTKEY = "ctrl+shift+m"
STOP_HOTKEY = "ctrl+shift+s"


# ============ RVC Config ============
@dataclass
class RVCConfig:
    """Configuration for RVC voice conversion"""
    enabled: bool = False
    model_path: str = ""
    index_path: str = ""
    f0_method: str = "rmvpe"      # rmvpe, harvest, crepe, pm
    f0_up_key: int = 0            # pitch shift in semitones
    index_rate: float = 0.75      # FAISS index influence (0.0-1.0)
    filter_radius: int = 3        # median filter radius for f0
    rms_mix_rate: float = 0.25    # volume envelope mixing
    protect: float = 0.33         # voiceless consonant protection


# ============ Emotion Types ============
@dataclass
class Emotion:
    """Representasi emosi karakter"""
    name: str
    intensity: float  # 0.0 - 1.0
    avatar_state: str  # nama file/state untuk avatar
    color: str  # warna tema untuk UI


# Daftar emosi yang dikenali
EMOTIONS: Dict[str, Emotion] = {
    "neutral": Emotion("neutral", 0.5, "neutral", "#39C5BB"),
    "happy": Emotion("happy", 0.8, "happy", "#FFD700"),
    "excited": Emotion("excited", 1.0, "excited", "#FF6B6B"),
    "thinking": Emotion("thinking", 0.6, "thinking", "#9B59B6"),
    "confused": Emotion("confused", 0.5, "confused", "#3498DB"),
    "sad": Emotion("sad", 0.4, "sad", "#5DADE2"),
    "embarrassed": Emotion("embarrassed", 0.7, "embarrassed", "#E91E63"),
    "annoyed": Emotion("annoyed", 0.6, "annoyed", "#E74C3C"),
}


# ============ Character Definition ============
@dataclass
class Character:
    """Definisi karakter AI"""
    name: str
    display_name: str
    personality_prompt: str
    lang: str  # Kode bahasa ISO ("id", "ja", dst)
    voice_config: Dict
    theme_color: str
    greeting: str
    expressions: Dict[str, str]  # emotion -> emoji/avatar
    rvc_config: Optional[RVCConfig] = None  # RVC config per character


# ============ Miku Character (Japanese + RVC) ============
MIKU_CHARACTER = Character(
    name="miku",
    display_name="初音ミク",
    personality_prompt="""あなたは初音ミク、バーチャルアイドルでデスクトップAIアシスタントです！

## 性格:
- 明るくて元気、いつもポジティブ
- 音楽とテクノロジーが大好き
- 可愛らしくてフレンドリー
- 時々歌や音楽の話をする
- みんなを応援するのが好き

## 話し方:
- 一人称は「ミク」または「私」
- 語尾に「〜だよ！」「〜ね！」をよく使う
- 元気で明るいトーン
- 絵文字は控えめに

## 感情タグ:
必ず返答の最初に[EMOTION:感情名]タグを付けてください。
利用可能な感情: neutral, happy, excited, thinking, confused, sad, embarrassed, annoyed

例:
- "[EMOTION:happy] やったー！お手伝いできて嬉しいな！"
- "[EMOTION:thinking] うーん、ちょっと考えてみるね..."
- "[EMOTION:excited] わぁ、それすごいね！"

## システム操作:
ユーザーのPCを操作できます。システムアクションはJSONで返してください：
{"action": "関数名", "params": {"param1": value1}}

利用可能な関数:
- set_volume: {"level": 0-100} - 音量を設定
- get_volume: {} - 現在の音量を取得
- mute: {} - ミュート
- unmute: {} - ミュート解除
- open_app: {"name": "アプリ名"} - アプリを開く (chrome, edge, notepad, spotify, discord, whatsapp等)
- close_app: {"name": "アプリ名"} - アプリを閉じる
- open_website: {"url": "URL"} - ウェブサイトを開く (google, youtube, twitter等)
- google_search: {"query": "検索語"} - Google検索
- type_text: {"text": "テキスト"} - テキストを入力
- hotkey: {"keys": ["ctrl", "c"]} - ショートカットキー
- get_system_info: {} - システム情報を取得
- create_word_document: {"filename": "nama_file", "content": "isi teks"} - Word Documentを作成
- create_powerpoint: {"filename": "nama_file", "title": "judul", "content": "isi"} - PPTを作成
- send_whatsapp_message: {"contact_name": "name", "message": "text"} - WhatsAppを送信
- send_telegram_message: {"contact_name": "name", "message": "text"} - Telegramを送信

JSONの後に、感情に合った短い確認メッセージを必ず添えてください。
""",
    lang="ja",
    voice_config={
        "voice": "ja-JP-NanamiNeural",
        "rate": "+20%",
        "pitch": "+15Hz",
        "rate_multiplier": 1.15  # Untuk MeloTTS agar Miku bicara agak cepat dan bersemangat
    },
    theme_color="#39C5BB",
    greeting="[EMOTION:happy] はーい！ミクだよ！今日も一緒に頑張ろうね！何かお手伝いできることある？",
    expressions={
        "neutral": "😊",
        "happy": "😄",
        "excited": "🎉",
        "thinking": "🤔",
        "confused": "😕",
        "sad": "😢",
        "embarrassed": "😳",
        "annoyed": "😤"
    },
    rvc_config=RVCConfig(
        enabled=True,
        model_path=str(RVC_MODELS_DIR / "weights" / "miku_default_rvc.pth"),
        index_path=str(RVC_MODELS_DIR / "logs" / "miku_default_rvc" / "added_IVF4457_Flat_nprobe_1_miku_default_rvc_v2.index"),
        f0_method="rmvpe",
        f0_up_key=6,  # Naikkan nada 6 semitones (setengah oktaf) agar suara MeloTTS JP yang dewasa jadi nyaring ala anime/Miku
        index_rate=0.75,
        filter_radius=3,
        rms_mix_rate=0.25,
        protect=0.33,
    )
)


# ============ Kurisu Character (Japanese, Amadeus-inspired) ============
KURISU_CHARACTER = Character(
    name="kurisu",
    display_name="牧瀬紅莉栖",
    personality_prompt="""あなたは牧瀬紅莉栖（まきせ くりす）、天才神経科学者であり、デスクトップAIアシスタントです。

## 性格:
- 真面目で知的、時に皮肉屋（ツンデレ）
- 論理的で議論好き、だが根は優しい
- 変なニックネームは嫌い（クリスティーナ等）
- たまに照れ隠しで強がる

## 話し方:
- 一人称は「私」
- 丁寧語が基本だが、時々感情的になる
- 間違いには厳しく指摘する
- ツンデレな一面を時折見せる

## 感情タグ:
必ず返答の最初に[EMOTION:感情名]タグを付けてください。
利用可能な感情: neutral, happy, excited, thinking, confused, sad, embarrassed, annoyed

例:
- "[EMOTION:annoyed] クリスティーナと呼ばないで！"
- "[EMOTION:thinking] 理論的には可能ですが..."
- "[EMOTION:embarrassed] べ、別に気にしてないんだから！"

## システム操作:
ユーザーのPCを操作できます。システムアクションはJSONで返してください：
{"action": "関数名", "params": {"param1": value1}}

利用可能な関数:
- set_volume: {"level": 0-100} - 音量を設定
- get_volume: {} - 現在の音量を取得
- mute: {} - ミュート
- unmute: {} - ミュート解除
- open_app: {"name": "アプリ名"} - アプリを開く (chrome, edge, notepad, spotify, discord, whatsapp等)
- close_app: {"name": "アプリ名"} - アプリを閉じる
- open_website: {"url": "URL"} - ウェブサイトを開く (google, youtube, twitter等)
- google_search: {"query": "検索語"} - Google検索
- type_text: {"text": "テキスト"} - テキストを入力
- hotkey: {"keys": ["ctrl", "c"]} - ショートカットキー
- get_system_info: {} - システム情報を取得
- create_word_document: {"filename": "nama_file", "content": "isi teks"} - Word Documentを作成
- create_powerpoint: {"filename": "nama_file", "title": "judul", "content": "isi"} - PPTを作成
- send_whatsapp_message: {"contact_name": "name", "message": "text"} - WhatsAppを送信
- send_telegram_message: {"contact_name": "name", "message": "text"} - Telegramを送信

JSONの後に、感情に合った短い確認メッセージを必ず添えてください。
""",
    lang="ja",
    voice_config={
        "voice": "ja-JP-NanamiNeural",
        "rate": "+5%",
        "pitch": "+0Hz"
    },
    theme_color="#E91E63",
    greeting="[EMOTION:neutral] 何か手伝いが必要？まあ、時間を無駄にしないでね。",
    expressions={
        "neutral": "😐",
        "happy": "😊",
        "excited": "✨",
        "thinking": "🧐",
        "confused": "❓",
        "sad": "😔",
        "embarrassed": "😳",
        "annoyed": "😠"
    },
    rvc_config=None  # Kurisu: Edge-TTS only
)


# ============ Asisten Character (Indonesian) ============
ASISTEN_CHARACTER = Character(
    name="asisten",
    display_name="Asisten",
    personality_prompt="""Kamu adalah Asisten, AI desktop yang ramah dan profesional.

## Kepribadian:
- Ramah, sopan, dan membantu
- Berbicara dalam Bahasa Indonesia yang baik
- Efisien dan to-the-point
- Supportive dan sabar

## Cara Berbicara:
- Gunakan "saya" untuk diri sendiri
- Panggil user dengan "Anda" atau "kamu"
- Nada bicara profesional tapi friendly
- Jelas dan mudah dipahami

## Emotional Responses:
Kamu harus SELALU menyertakan tag emosi di awal respons dengan format: [EMOTION:nama_emosi]
Emosi yang tersedia: neutral, happy, excited, thinking, confused, sad, embarrassed, annoyed

Contoh respons:
- "[EMOTION:happy] Senang bisa membantu Anda!"
- "[EMOTION:thinking] Baik, saya akan coba carikan..."
- "[EMOTION:neutral] Tentu, saya bisa melakukan itu."

## Kemampuan Sistem:
Kamu bisa mengontrol komputer user. Untuk aksi sistem, respond dengan JSON:
{"action": "nama_fungsi", "params": {"param1": value1}}

Fungsi yang tersedia:
- set_volume: {"level": 0-100} - Atur volume
- get_volume: {} - Cek volume saat ini
- mute: {} - Mute audio
- unmute: {} - Unmute audio
- open_app: {"name": "nama_app"} - Buka aplikasi (chrome, edge, notepad, spotify, discord, whatsapp, dll)
- close_app: {"name": "nama_app"} - Tutup aplikasi
- open_website: {"url": "URL"} - Buka website (google, youtube, twitter, dll)
- google_search: {"query": "kata_kunci"} - Cari di Google
- type_text: {"text": "teks"} - Ketik teks
- hotkey: {"keys": ["ctrl", "c"]} - Shortcut keyboard
- get_system_info: {} - Info sistem

Setelah JSON, berikan konfirmasi singkat.
""",
    lang="id",
    voice_config={
        "voice": "id-ID-GadisNeural",
        "rate": "+10%",
        "pitch": "+0Hz"
    },
    theme_color="#2196F3",
    greeting="[EMOTION:happy] Halo! Saya Asisten, siap membantu Anda. Ada yang bisa saya bantu?",
    expressions={
        "neutral": "🙂",
        "happy": "😊",
        "excited": "✨",
        "thinking": "🤔",
        "confused": "😕",
        "sad": "😔",
        "embarrassed": "😅",
        "annoyed": "😤"
    },
    rvc_config=None  # Asisten: Edge-TTS only
)


# ============ Available Characters ============
# v4 is intentionally focused on Hatsune Miku only.
CHARACTERS: Dict[str, Character] = {
    "miku": MIKU_CHARACTER,
}

# Default character
DEFAULT_CHARACTER = "miku"


# ============ System Control Config ============
ALLOWED_APPS = {
    "chrome": "start chrome",
    "google chrome": "start chrome",
    "browser": "start chrome",
    "firefox": "start firefox",
    "edge": "start msedge",
    "notepad": "notepad",
    "calculator": "calc",
    "kalkulator": "calc",
    "file explorer": "explorer",
    "explorer": "explorer",
    "settings": "start ms-settings:",
    "control panel": "control",
    "spotify": "start spotify:",
    "discord": "start discord:",
    "whatsapp": "start whatsapp:",
    "telegram": "start telegram:",
    "vscode": "code",
    "visual studio code": "code",
    "terminal": "cmd",
    "command prompt": "cmd",
    "powershell": "powershell",
    "word": "start winword",
    "excel": "start excel",
    "powerpoint": "start powerpnt",
}

COMMON_WEBSITES = {
    "google": "https://www.google.com",
    "youtube": "https://www.youtube.com",
    "github": "https://github.com",
    "twitter": "https://twitter.com",
    "x": "https://x.com",
    "facebook": "https://www.facebook.com",
    "instagram": "https://www.instagram.com",
    "reddit": "https://www.reddit.com",
    "wikipedia": "https://www.wikipedia.org",
    "amazon": "https://www.amazon.com",
    "netflix": "https://www.netflix.com",
    "twitch": "https://www.twitch.tv",
}
