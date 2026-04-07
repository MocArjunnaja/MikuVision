# MikuWin v4 - Implementation Checklist

## Core
- [x] Base project cloned from v3 architecture
- [x] Core modules kept compatible (voice_input, ai_brain, voice_output, system_control)
- [x] RVC pipeline preserved

## Character mode
- [x] Set project to Miku-only in config
- [x] Default character set to miku
- [x] Removed multi-character switch workflow from GUI

## UI
- [x] Integrated miku_smart_sheet sprite asset
- [x] Added animated sprite avatar renderer
- [x] Added emotion -> sequence mapping
- [x] Added per-emotion animation timing and smooth loop mode

## Validation
- [x] Python syntax check for gui.py, config.py, miku.py
- [x] Asset path check for sprite sheet

## Remaining optional improvements
- [ ] Fine-tune emotion sequence mapping by manual UX pass
- [ ] Add settings panel for animation speed override
