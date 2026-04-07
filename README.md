# MikuWin v11 🎤💻 

MikuWin adalah asisten virtual desktop interaktif berbasis AI yang berwujud **Hatsune Miku**. Proyek ini menggunakan 100% LLM (Ollama) lokal yang dipadukan dengan pengenalan suara (STT), pemrosesan suara AI (RVC), dan antarmuka interaktif.

Versi ke-11 (`v11`) ini berfokus pada fitur **Agentic** — artinya Miku dapat memikirkan dan mengeksekusi instruksi sistem (Macro) secara otonom (mandiri) di komputer Anda, lalu memberikan hasil laporan secara real-time.

## ✨ Fitur Utama (v11)

1. **Native Offline LLM Intelligence (Ollama)**
   - Menggunakan LLM open-source (seperti `llama3.2` atau `qwen`) yang berjalan *offline* untuk menjamin respons cepat dan perlindungan privasi data.

2. **Advanced Audio Pipeline V2 (Microphone Input)**
   - **Google WebRTC VAD**: Pendeteksi aktivitas suara tingkat agresi tinggi untuk memotong jeda dengan presisi instan (1.5 detik!). Bebas lag/ZCR jadul.
   - **Gating Spektral Otomatis & Safe Auto-Gain**: Membersihkan statik/noise background kipas atau mikrofon (Prop Decrease: 0.85) secara otomatis lalu menormalkan suara manusia tanpa *hard-clipping*.
   - **Multi-pass STT**: Memakai model `faster-whisper` dengan anti-hallucination engine.

3. **Miku Sprite GUI (Animated)**
   - Antarmuka *CustomTkinter* bersih yang menampilkan Miku dalam bentuk sprite. Sprite Miku bisa bergerak layaknya avatar hidup dan berganti ekspresi berdasarkan metadata konteks emosi (`[EMOTION:happy]`, `[EMOTION:confused]`) dari AI.
   - Live transcription chat, log status tools, dan push-to-talk button (`🎤 Hold to Speak`).

4. **Agentic System Control (Macro Tools)**
   - AI memiliki akses ke sistem eksekusi Python. Apabila Anda berkata, *"Kirim pesan ke grup Whatsapp PKM bersi Halo, saya Miku"*, maka Miku secara otomatis merakit Action JSON yang menjalankan `send_whatsapp_message`.
   - Tool bisa ditambahkan di folder `core/macro_tools.py` secara modular (Automasi Microsoft Word, System Volume, YouTube Search, dll).

5. **Voice Cloning (RVC x Edge-TTS)**
   - Modul RVC bawaan menggunakan `rvc_python` sehingga jawaban yang dikeluarkan AI memiliki timbre khas Hatsune Miku beraksen Jepang. Tersedia opsi `Wake Phrase` ("Oke Miku!").

---

## 🛠️ Instalasi & Prasyarat

1. Pastikan Anda telah menginstal [Anaconda/Miniconda](https://docs.anaconda.com/), Python 3.10+, dan Git.
2. Diperlukan GPU (CUDA) dari NVIDIA yang kompatibel (Rekomendasi VRAM minimal 6GB) untuk menjalankan model LLM, Whisper, dan RVC secara *real-time*.
3. Install model bahasa melalui terminal Ollama:
   ```bash
   ollama pull qwen3:4b
   ```
   *(Atau ubah LLM di file `config.py` ke model pilihan Anda).*

### Menjalankan MikuWin:
Gunakan environment conda miku jika Anda menggunakan setup conda:
```bash
conda activate miku
```

Ada dua versi cara berinteraksi:
1. **GUI (Recommended)**  
   Membuka antarmuka interaktif berserta sprite avatar Miku:
   ```bash
   python gui.py
   ```
2. **Terminal (CLI Console)**  
   Mode murni konsol terminal tanpa GUI. Ringan, bagus untuk debug:
   ```bash
   python miku.py
   ```

---

## 📂 Struktur Direktori Utama

- `assets/` : Gambar, file UI, dan spritesheet avatar.
- `core/`   : Kumpulan modul logika.
  - `ai_brain.py`      : Menghubungkan Ollama, mendeteksi emosi, parse `tool calls`.
  - `voice_input.py`   : Sistem Mic, *Faster-Whisper*, WebRTC VAD, Noisereduce.
  - `macro_tools.py`   : Koleksi function/system calls yang bisa di-_invoke_ LLM.
- `data/`   : Penyimpanan history percakapan dan database kontak JSON.
- `miku.py` & `gui.py` : Skrip peluncuran asisten utama.
- `config.py`          : Pengaturan tuning parameter (Model, Warna, Hotkeys).

*(Backup dan Sinkronisasi Repositori v11 di-handle mandiri oleh Git).*