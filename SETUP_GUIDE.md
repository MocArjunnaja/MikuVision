# MikuWin v4 - Setup Guide

## 1. Prerequisites
- Windows 10/11
- Python 3.9+
- Existing venv/conda env already activated
- Ollama running with a usable model

## 2. Install
```bash
cd v4
pip install -r requirements.txt
```

Optional (RVC):
```bash
pip install rvc-python
```
If this fails, v4 still runs with Edge-TTS.

## 3. Run
```bash
python gui.py
```

## 4. What is different from v3
- Miku-only character mode
- Animated sprite avatar from miku_smart_sheet.png
- Same backend pipeline (Whisper -> Ollama -> TTS/RVC)

## 5. Troubleshooting
- Ollama error: start Ollama service and verify model exists.
- RVC unavailable: verify model path in config.py and optional package install.
- No audio output: verify Windows output device and volume.
