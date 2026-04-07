# MikuWin v4 - Release Summary

## Overview
MikuWin v4 is a focused refinement of v3:
- Same backend pipeline
- Miku-only interaction mode
- Animated sprite avatar UI using prepared Miku sheet

## Key Differences from v3
- Removed multi-character selector from GUI
- Forced single character (miku) in configuration
- Added sprite animation engine with emotion-driven sequences
- Added per-emotion timing and smooth loop behavior

## Backend Compatibility
- Voice input: Faster-Whisper
- LLM: Ollama integration and function calling
- Voice output: Edge-TTS + optional RVC conversion
- Memory and system control flow retained

## Runtime Notes
- Works without RVC (fallback to Edge-TTS)
- Requires sprite sheet for full visual mode

## Recommendation
Use v4 as default GUI edition for Hatsune Miku experience.
