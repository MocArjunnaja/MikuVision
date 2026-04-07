# MikuWin v5 — AI Desktop Assistant with Smart Automation

**Hatsune Miku Edition** with integrated YouTube, Spotify, and Browser automation.

> **"Miku, cari lagu Vocaloid di YouTube" → Miku searches & plays automatically** 🎵

---

## 🆕 What's New in v5?

### Automation Layer

v5 introduces **lightweight automation** without Computer Vision:

- **YouTube Automation**: Search, play, pause, skip, seek
- **Spotify Automation**: Search songs, play via API or web
- **Browser Automation**: Navigate, interact with web pages
- **Keyboard & Mouse**: System-level UI automation

### Key Features

✨ **Same as v4**, but with superpowers:

- All v4 features (voice input, emotions, sprite avatar)
- **+ YouTube search & playback**
- **+ Spotify integration**
- **+ Web browser control**
- **+ Smart function calling** (AI tells Miku what to do)

---

## 🎯 Usage Examples

### Voice Mode (with Sprite Avatar)

```bash
python miku.py
```

**Conversation:**

```
You: Oke Miku
Miku: Hai! Siap dengarkan.

You: Main lagu Hatsune Miku di YouTube
[Sprite updates to "listening" state]
Miku: Mencari dan memutar...
[Browser opens → YouTube → auto-plays video]

You: Pause
Miku: [Pauses video]

You: Skip ke video berikutnya
Miku: [Skips to next]
```

### Text Mode

```bash
python miku.py --text
```

---

## 🛠️ Technical Architecture

```
┌─────────────────────────────────────┐
│      Miku CLI / GUI (v4 backend)   │
│  • Voice Input (Whisper)            │
│  • AI Brain (Ollama)                │
│  • Voice Output (Edge-TTS + RVC)    │
│  • Sprite Avatar (Pygame)           │
└────────────┬────────────────────────┘
             │
      ┌──────▼──────────────────┐
      │  SystemControl (NEW)    │
      │  ┌────────────────────┐ │
      │  │ Automation Layer   │ │
      │  ├────────────────────┤ │
      │  │ • YouTubeAuto      │ │
      │  │ • SpotifyAuto      │ │
      │  │ • BrowserAuto      │ │
      │  │ • UIAuto           │ │
      │  └────────────────────┘ │
      └────────────────────────┘
             │
      ┌──────▼──────────────────┐
      │    Execute Actions      │
      │  • Open Browser         │
      │  • Click, Type, Press   │
      │  • API Calls            │
      └─────────────────────────┘
```

---

## 📦 Installation & Setup

### 1. Install Dependencies

```bash
# Navigate to v5
cd v5

# Install requirements
pip install -r requirements.txt

# Additional requirements for automation
pip install playwright yt-dlp spotipy
python -m playwright install chromium
```

### 2. Configure Spotify (Optional)

If you want full Spotify integration, get API credentials from [Spotify Dev Dashboard](https://developer.spotify.com/dashboard):

```python
# In config.py, add:
SPOTIFY_CLIENT_ID = "your_client_id"
SPOTIFY_CLIENT_SECRET = "your_client_secret"
```

Then in `system_control.py` init:

```python
self.system_control = SystemControl(
    spotify_client_id=SPOTIFY_CLIENT_ID,
    spotify_client_secret=SPOTIFY_CLIENT_SECRET
)
```

### 3. Run Miku

```bash
# Voice mode (default, with sprite avatar)
python miku.py

# Text mode (no sprite)
python miku.py --text

# In voice mode, type 'wake' to activate "Oke Miku" mode
```

---

## 🎮 Automation Actions

### YouTube Actions

| Action                 | Parameters             | Example            |
| ---------------------- | ---------------------- | ------------------ |
| `youtube_search`       | `query`                | "Hatsune Miku"     |
| `youtube_play_pause`   | —                      | Toggle play/pause  |
| `youtube_next`         | —                      | Skip to next video |
| `youtube_seek_forward` | `seconds` (default 10) | Seek +10s          |

### Spotify Actions

| Action               | Parameters | Example           |
| -------------------- | ---------- | ----------------- |
| `spotify_search`     | `query`    | "Ariana Grande"   |
| `spotify_play_pause` | —          | Toggle play/pause |

### Browser Actions

| Action         | Parameters | Example              |
| -------------- | ---------- | -------------------- |
| `browser_open` | `url`      | "https://google.com" |

### System Actions (v4 + new)

| Action         | Parameters      | Description           |
| -------------- | --------------- | --------------------- |
| `set_volume`   | `level` (0-100) | Set system volume     |
| `open_app`     | `name`          | Open application      |
| `open_website` | `url`           | Open website          |
| `type_text`    | `text`          | Type text on keyboard |
| `press_key`    | `key`           | Press single key      |

---

## 🧠 How AI Brain Uses Automation

When you ask Miku something like **"Play Vocaloid on YouTube"**:

1. **VoiceInput** captures your speech
2. **AIBrain** (Ollama) processes: "User wants to play Vocaloid on YouTube"
3. **AIBrain** generates function call:
   ```json
   {
     "action": "youtube_search",
     "params": { "query": "Vocaloid" }
   }
   ```
4. **SystemControl** receives action → delegates to **AutomationManager**
5. **YouTubeAutomation** executes:
   - Search for "Vocaloid" via yt-dlp
   - Get first video URL
   - Open in browser (web player)
   - Click play button (if using Playwright)
6. **VoiceOutput** speaks response: "Memutar Vocaloid di YouTube"
7. **AvatarWindow** updates emotion to "listening" → "excited"

---

## ⚙️ Configuration

### config.py (v5)

```python
# Add to config.py:
SPOTIFY_CLIENT_ID = ""          # Get from Spotify Dev
SPOTIFY_CLIENT_SECRET = ""      # Get from Spotify Dev

# YouTube/Spotify in automated function calls
ALLOWED_AUTOMATIONS = {
    "youtube_search": True,
    "youtube_play_pause": True,
    "spotify_search": True,
    "browser_open": True,
}
```

### Dependencies (requirements.txt)

```
customtkinter==5.2.0
Pillow==10.0.0
faster_whisper==0.10.0
ollama==0.1.0
edge-tts==6.1.6
sounddevice==0.4.6
soundfile==0.12.1
pycaw==20.0.1
pyautogui==0.9.53
keyboard==0.13.5
pygetwindow==0.3
psutil==5.9.5
pygame==2.5.2

# NEW for v5 automation
playwright==1.40.0
yt-dlp==2023.12.30
spotipy==2.23.0
```

---

## 🚀 Advanced Usage

### Using Playwright for Smart Clicks

If Playwright is installed, v5 can:

- Click specific elements on the page
- Fill form fields
- Extract text content
- Take screenshots for debugging

### Fallback Behavior

If a method fails (e.g., Playwright not available):

```python
youtube.search_and_play(query)
# Tries: Browser automation → yt-dlp + webbrowser → keyboard press
```

---

## 📊 Architecture Comparison

| Feature                       | v4  | v5               |
| ----------------------------- | --- | ---------------- |
| Voice Input                   | ✅  | ✅               |
| Sprite Avatar                 | ✅  | ✅               |
| Emotion System                | ✅  | ✅               |
| Memory (Conversation)         | ✅  | ✅               |
| Wake Phrase ("Oke Miku")      | ✅  | ✅               |
| System Control (volume, apps) | ✅  | ✅               |
| **YouTube Automation**        | ❌  | ✅ **NEW**       |
| **Spotify Automation**        | ❌  | ✅ **NEW**       |
| **Browser Automation**        | ❌  | ✅ **NEW**       |
| Computer Vision               | ❌  | ❌ (not needed!) |

---

## 🔧 Troubleshooting

### yt-dlp search fails

- Check internet connection
- Update yt-dlp: `pip install --upgrade yt-dlp`

### Playwright not working

- Reinstall: `pip install --upgrade playwright && python -m playwright install chromium`
- May need admin privileges on Windows

### Spotify API not found

- Check `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` in config
- Generate new credentials on Spotify Dev Dashboard

### No audio feedback

- Ensure Edge-TTS or RVC is working (same as v4)
- Check system volume is not muted

---

## 📝 Project Structure

```
v5/
├── miku.py                  # CLI entry point (voice/text modes)
├── gui.py                   # GUI entry point (customtkinter)
├── config.py                # Configuration (with Spotify keys)
├── requirements.txt         # Dependencies
├── README.md               # This file
├── core/
│   ├── voice_input.py          # Whisper STT
│   ├── voice_output.py         # Edge-TTS + RVC
│   ├── ai_brain.py             # Ollama LLM + function calling
│   ├── system_control.py       # System actions (UPDATED with automation)
│   ├── avatar_window.py        # Pygame sprite display
│   ├── emotion.py              # Emotion detection
│   ├── memory.py               # Conversation history
│   └── 🆕 automation_layer.py  # NEW: YouTube, Spotify, Browser, UI automation
├── assets/
│   └── avatar/
│       └── miku_smart_sheet.png
└── data/
    └── conversations/
        └── [memory files]
```

---

## 🎬 Next Steps

Future versions could add:

- **Vision mode**: Analyze screens for smart button clicking
- **Voice commands**: Direct voice control ("Click the red button")
- **Smart scheduling**: Schedule automation tasks
- **Custom workflows**: Save and replay automation sequences

---

## 📞 Support

If something breaks:

1. Check `requirements.txt` — install all dependencies
2. Run `python miku.py --test` to check initialization
3. Enable debug logging in `ai_brain.py`
4. Check console output for error messages

---

**Enjoy using MikuWin v5! Miku will now automate your favorite tasks.** 🎵✨
