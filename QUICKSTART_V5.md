# MikuWin v5 — Quick Start & Feature Demo

## 🚀 Installation (2 steps)

### Step 1: Install Dependencies

```bash
cd v5
pip install -r requirements.txt
pip install playwright yt-dlp spotipy
python -m playwright install chromium
```

### Step 2: Run Miku

```bash
python miku.py
```

---

## 🎤 Voice Mode Demo

```
$ python miku.py

[MikuWin v4] Selected character: Hatsune Miku
[MikuWin v4] Language: ja

=== Initializing MikuWin v5 ===

[1/5] Initializing memory...
[2/5] Loading Faster-Whisper...
      ✓ Whisper loaded
[3/5] Connecting to Ollama...
      ✓ Ollama connected
[4/5] Loading RVC voice converter...
      ✓ RVC ready: Miku voice conversion enabled
[5/5] Initializing voice output...
      ✓ Voice output ready
      ✓ System control ready

✓ All systems ready!

[avatar_window] Miku frame started in background
Miku [neutral]: Halo! Saya Hatsune Miku. Ada yang bisa saya bantu?

Voice mode - Options:
  • Press Enter to record voice (push-to-talk)
  • Type 'wake' to enable 'Oke Miku' wake phrase mode
  • Type "quit" to exit

(Press Enter to speak, or type command):
```

### Conversation Example 1: YouTube

```
(Press Enter to speak, or type command): [ENTER → Record speech]
[Listening...]
[Press Enter to stop listening...]
You: Main Hatsune Miku di YouTube

[System] ✅ Memutar Hatsune Miku di YouTube
Miku [excited]: OK, Miku sekarang putar lagunya di YouTube! 🎵

(Press Enter to speak, or type command):
```

### Conversation Example 2: Wake Mode

```
(Press Enter to speak, or type command): wake

🗣️  Wake Phrase Mode: Listening for 'Oke Miku'...
(Type "exit" to leave wake mode)

Miku: Siap dengarkan. Katakan 'Oke Miku' untuk mulai.

[Listening for wake phrase...]
You: Oke Miku
[Wake] Deteksi 'Oke Miku'!

Miku [excited]: Hai! Miku siap. Silakan lanjut bicara ya.

You [listening]: Cari lagu Taylor Swift di Spotify
[System] ✅ Opening Spotify: "Taylor Swift"
Miku [happy]: Ketemu! Putar lagunya di Spotify.

[Idle timeout - kembali mendengarkan]

(Press Enter to speak, or type command):
```

### Conversation Example 3: System Control

```
(Press Enter to speak, or type command): Setel volume 70 persen

[System] ✅ Volume diatur ke 70%
Miku [neutral]: Sudah, saya atur volume ke 70%.

(Press Enter to speak, or type command): Buka Google Chrome

[System] ✅ Membuka chrome...
Miku [thinking]: Sedang membuka Chrome untuk Anda.
```

---

## 📱 Available Actions in v5

### YouTube

```python
# "Main Hatsune Miku di YouTube"
"action": "youtube_search"
"params": {"query": "Hatsune Miku"}

# "Pause"
"action": "youtube_play_pause"

# "Skip ke video berikutnya"
"action": "youtube_next"

# "Cari maju 30 detik"
"action": "youtube_seek_forward"
"params": {"seconds": 30}
```

### Spotify

```python
# "Main lagu Taylor Swift di Spotify"
"action": "spotify_search"
"params": {"query": "Taylor Swift"}

# "Pause"
"action": "spotify_play_pause"
```

### System

```python
# "Setel volume 50%"
"action": "set_volume"
"params": {"level": 50}

# "Buka Google Chrome"
"action": "open_app"
"params": {"name": "chrome"}

# "Buka Google"
"action": "open_website"
"params": {"url": "https://google.com"}

# "Cari kucing di Google"
"action": "google_search"
"params": {"query": "kucing"}
```

---

## 🎬 Architecture Highlights

### Automation Flow

```
┌──────────────────────────┐
│    Your Voice Input      │
│  "Main YouTube Vocaloid" │
└────────┬─────────────────┘
         │
    ┌────▼──────────────────────┐
    │  Faster-Whisper (STT)     │
    │  Converts speech → text   │
    └────┬──────────────────────┘
         │
    ┌────▼──────────────────────────┐
    │  Ollama (AIBrain)             │
    │  Understands & plans actions  │
    │  Output: {action, params}     │
    └────┬──────────────────────────┘
         │
    ┌────▼──────────────────────────┐
    │  SystemControl                │
    │  Routes to automation layer   │
    └────┬──────────────────────────┘
         │
    ┌────▼──────────────────────────┐
    │  AutomationManager (NEW)      │
    │  • YouTubeAutomation          │
    │  • SpotifyAutomation          │
    │  • BrowserAutomation          │
    │  • UIAutomation               │
    └────┬──────────────────────────┘
         │
    ┌────▼──────────────────────────┐
    │  Execute:                     │
    │  • yt-dlp search              │
    │  • Playwright clicks          │
    │  • PyAutoGUI type/press       │
    │  • API calls                  │
    └─────────────────────────────────

Output: AvatarWindow (Sprite animating) + VoiceOutput (Miku speaking)
```

---

## ⚙️ Configuration

### Spotify Setup (Optional)

1. Go to https://developer.spotify.com/dashboard
2. Create an app → get `Client ID` and `Client Secret`
3. In `config.py` (v5):
   ```python
   SPOTIFY_CLIENT_ID = "your_id_here"
   SPOTIFY_CLIENT_SECRET = "your_secret_here"
   ```
4. Restart miku.py

---

## 🐛 Troubleshooting

| Issue                        | Solution                                                          |
| ---------------------------- | ----------------------------------------------------------------- |
| "yt-dlp not found"           | `pip install yt-dlp`                                              |
| "Playwright not found"       | `pip install playwright && python -m playwright install chromium` |
| YouTube/Spotify not working  | Check internet connection                                         |
| No audio output              | Check Windows volume, ensure Edge-TTS/RVC configured              |
| Sprite window doesn't appear | Check `assets/avatar/miku_smart_sheet.png` exists                 |

---

## 📊 What's Different from v4?

| Feature                   | v4  | v5         |
| ------------------------- | --- | ---------- |
| Voice chat                | ✅  | ✅ Same    |
| Sprite avatar             | ✅  | ✅ Same    |
| Wake phrase "Oke Miku"    | ✅  | ✅ Same    |
| Set volume/open apps      | ✅  | ✅ Same    |
| **Search & play YouTube** | ❌  | ✅ **NEW** |
| **Search & play Spotify** | ❌  | ✅ **NEW** |
| **Browser automation**    | ❌  | ✅ **NEW** |

---

## 🎯 Cool Things You Can Ask Miku

1. **Music Streaming**
   - "Main lagu Hatsune Miku di YouTube"
   - "Cari Ariana Grande di Spotify"
   - "Pause" / "Play next"

2. **System Control**
   - "Setel volume 80 persen"
   - "Buka Chrome"
   - "Cari kucing di Google"

3. **Multi-step**
   - "Putar musik, terus setel volume 50%"
   - "Buka Spotify dan cari Taylor Swift"

4. **Wake Phrase Mode**
   - Type `wake` → "Oke Miku" → continuous conversation

---

## 🚀 Next Level (Future Possible Additions)

- **Screen Capture + Vision**: See what's on screen, click smart elements
- **Voice Commands**: "Click that red button on the right"
- **Workflow Automation**: Save & replay sequences
- **Multi-window Management**: Bring windows to focus, arrange layout
- **Email Integration**: Read & send emails

---

Happy using MikuWin v5! 🎵✨

Questions? Check `README_V5.md` for full documentation.
