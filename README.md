# MikuWin v4 - Hatsune Miku Edition

MikuWin v4 adalah versi fokus Hatsune Miku dari v3.
Backend tetap sama, tetapi UI ditingkatkan menjadi avatar sprite animasi Miku.

## Highlight

- Miku-only mode (tanpa switch karakter)
- Animated sprite avatar dari sheet Miku yang sudah diproses
- Pipeline tetap: Whisper -> Ollama -> Edge-TTS -> RVC (opsional) -> Playback
- Fallback aman:
  - Tanpa RVC: tetap jalan pakai Edge-TTS
  - Tanpa sprite sheet: GUI fallback ke emoji

## Struktur Utama

- gui.py: GUI utama v4 + animator sprite Miku
- config.py: konfigurasi Miku-only + path sprite sheet
- core/: modul backend (voice_input, ai_brain, voice_output, system_control, memory, dll)
- assets/avatar/miku_smart_sheet.png: sprite sheet Miku

## Prasyarat

- Windows 10/11
- Python 3.9+
- Ollama aktif (model tersedia)
- Environment Python sudah aktif

Opsional:
- rvc-python (untuk konversi suara Miku)

## Instalasi

```bash
cd v4
pip install -r requirements.txt
```

Opsional RVC:

```bash
pip install rvc-python
```

## Menjalankan

GUI:

```bash
cd v4
python gui.py
```

CLI:

```bash
cd v4
python miku.py --text
```

## Catatan

- v4 mempertahankan kompatibilitas perilaku backend dari v3.
- Perbedaan utama ada pada pengalaman visual dan mode karakter tunggal (Miku).
