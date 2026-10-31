"""
Agent visi (docs/PLAN_VISION_AGENT.md). Fase 1: Miku membaca layar, tanpa aksi apa pun.

- capture.py: screenshot jendela aktif (atau seluruh layar bila yang aktif jendela Miku sendiri)
- ui_tree.py + atspi_helper.py: elemen jendela aktif dari pohon aksesibilitas (Linux AT-SPI2)
- model.py: menukar LLM utama dengan model visi di VRAM, lalu mengembalikannya
- screen_tools.py: tool describe_screen dan find_on_screen
"""
