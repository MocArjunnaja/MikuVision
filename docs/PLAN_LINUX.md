# Rencana Update: MikuVision di Linux

**Tujuan:** MikuVision jalan penuh di Linux dengan fitur setara Windows: suara dua arah, LLM lokal, aksi di komputer (buka/tutup aplikasi, volume, dokumen, pesan), dan maskot desktop. Windows tetap didukung dari kode yang sama.

**Status:** Audit, Fase L0, Fase L1, dan perbaikan urutan muat VRAM selesai 29 Okt 2026 (bagian 2.5); Fase L2 selesai 31 Okt 2026 (bagian 2.6). Berikutnya: Fase L3 (maskot). Urutan yang disarankan: L0 → L4 di dokumen ini, lalu agent visi Fase 1 ([`PLAN_VISION_AGENT.md`](PLAN_VISION_AGENT.md)) dengan backend Linux.

---

## 1. Lingkungan yang diaudit

Laptop yang sama dengan pengujian Windows (Lenovo LOQ 15IRX9), dual-boot. Folder repo berada di partisi NTFS yang di Windows menjadi `D:`.

| | Nilai | Dampak |
|---|---|---|
| OS | Linux Mint 22.3 Cinnamon (basis Ubuntu 24.04), kernel 7.0.0-31 | Paket `apt` mengikuti Ubuntu 24.04 |
| Sesi grafis | **X11** | pyautogui, xdotool, wmctrl bisa dipakai. Di Wayland tidak bisa |
| GPU | RTX 4050 Laptop 6 GB, driver `nvidia-driver-595-open` | Driver dipasang 29 Okt 22:18, setelah boot 21:26. Yang aktif masih `nouveau`, jadi `nvidia-smi` gagal. **Perlu reboot** |
| Python | 3.12.3 sistem, tanpa `pip`, `venv`/`ensurepip`, uv, maupun conda | RVC butuh 3.10 (`fairseq`), jadi tetap pakai Python 3.10 dari uv seperti di Windows |
| Ollama | Belum terpasang | |
| Audio | PipeWire 1.0.5 (`pactl`, `wpctl`), `libportaudio2` ada | `sounddevice` jalan; volume lewat `wpctl` |
| Tool desktop yang ada | `xdg-open`, `gio`, `gtk-launch`, `wmctrl`, `notify-send`, LibreOffice, AT-SPI2 + `python3-pyatspi`, font Noto CJK | |
| Tool yang belum ada | `xdotool`, `playerctl`, `xclip`, `scrot` | Dipasang di L0 |
| Aplikasi | `xed`, `gnome-calculator`, `nemo`, `cinnamon-settings`, `gnome-terminal`, `firefox`, `code`, browser default **Brave**. Tidak ada Chrome, Spotify, Discord, Telegram | Nama aplikasi berbeda dari Windows |
| Disk | Root ext4 69 GB kosong; partisi NTFS 111 GB kosong; RAM 15 GB | Cukup untuk venv (±6 GB), cache HF (±2 GB), model Ollama |

## 2. Hasil audit

### 2.1 Unit test

`pytest` dengan Python 3.12 sistem (paket audio/GUI yang belum terpasang di-stub): **172/172 lulus**.

Tetapi `tests/conftest.py` men-stub `pycaw`, `pyautogui`, dan `pygetwindow`, sehingga di dalam test Windows selalu dianggap tersedia. Kerusakan di Linux tidak terdeteksi oleh test yang ada.

Aplikasi belum bisa dijalankan utuh: dependency belum terpasang, Ollama belum ada, dan CUDA belum aktif. Angka performa Linux (latensi, VRAM, akurasi) baru bisa diukur setelah L0 dan L1.

### 2.2 Tool di Linux

Ke-27 tool dipanggil langsung dengan library Windows tidak terpasang (seperti instalasi Linux sungguhan). Aksi yang membuka sesuatu dicegat, jadi tidak ada yang benar-benar dijalankan.

| Status | Jumlah | Tool | Penyebab |
|---|---|---|---|
| Jalan | 12 | `open_website`, `google_search`, `youtube_search`, `spotify_search`, `browser_media_control`, `media_control`, `remember`, `recall_memory`, `forget`, `list_routines`, `run_routine`, `read_word_document` | Hanya memakai `webbrowser`, file, atau pyautogui di dalam fungsi |
| Sebagian | 4 | `create_word_document`, `create_powerpoint`, `edit_word_document` | File tersimpan, lalu `os.startfile` gagal sehingga hasilnya dilaporkan "Gagal…". LLM bisa mengulang dan membuat file ganda |
| | | `get_system_info` | RAM, CPU, dan baterai hilang tanpa pesan karena `psutil` tidak ter-import |
| Rusak | 11 | `get_volume`, `set_volume`, `mute` | pycaw (COM Windows) |
| | | `open_application` | `os.startfile` tidak ada di Linux; perintah di `ALLOWED_APPS` (`notepad`, `calc`, `ms-settings:`, `cmd`, `winword`) khusus Windows |
| | | `close_application` | `NameError: psutil`, lalu `EnumWindows` + `WM_CLOSE` (pywin32) |
| | | `open_folder` | `os.startfile`, `explorer` |
| | | `type_text`, `press_key`, `hotkey` | Dikunci `WINDOWS_AVAILABLE`, padahal pyautogui jalan di X11 |
| | | `send_whatsapp_message` | `os.startfile("whatsapp://")`; tidak ada WhatsApp Desktop resmi di Linux |
| | | `send_telegram_message` | `os.startfile("tg://…")` |

### 2.3 Penyebab utama

1. **`WINDOWS_AVAILABLE`** (`core/system_control.py`): pycaw, pyautogui, pygetwindow, dan psutil di-import dalam satu blok `try`. Di Linux pycaw gagal lebih dulu, sehingga psutil dan pyautogui ikut tidak ter-import. Selain itu `pygetwindow` di Linux melempar `NotImplementedError`, bukan `ImportError`, jadi blok itu akan crash bila urutan import berubah.
2. **`os.startfile`** dipakai di 10 tempat (`core/macro_tools.py` 6, `core/system_control.py` 4).
3. **`requirements.txt`**: `pywin32` tidak punya wheel maupun source untuk Linux, sehingga `pip install -r requirements.txt` gagal total. `pycaw`, `comtypes`, `pygetwindow`, dan `keyboard` tidak berguna di Linux (`keyboard` butuh root).
4. **`ALLOWED_APPS`** dan `PROTECTED_PROCESSES` berisi nama Windows.
5. **Maskot** (`core/avatar_window.py`): transparansi, always-on-top, drag, dan menu klik kanan semuanya lewat win32. Di Linux maskot tampil sebagai kotak magenta (`FUCHSIA`), tidak di atas jendela lain, dan tidak bisa dipindah karena posisi jendela diatur lewat `SetWindowPos`.
6. **Instalasi**: hanya `install.ps1`, `install.bat`, `run.bat`; shortcut berupa `.lnk`.
7. **Folder dokumen** `~/Desktop/Miku_Documents` ditulis langsung. Di mesin ini `xdg-user-dir DESKTOP` memang `~/Desktop`, tapi di sistem berbahasa lain namanya bisa berbeda.

### 2.4 Kondisi repo

- `git status` menunjukkan 54 file "modified". Isinya hanya beda akhir baris (CRLF dari checkout Windows). Dengan `git -c core.autocrlf=input status` hasilnya 0 (sudah dicek, belum diterapkan).
- Worktree lama `D:/02_Research/13_MikuWin_V11_Stable/.claude/worktrees/relaxed-montalcini-e26486` berstatus *prunable*.
- Repo ada di NTFS lewat FUSE (`ntfs-3g`). venv berisi torch (puluhan ribu file kecil) akan lambat di sana; venv sebaiknya di ext4.
- Python 3.10, yang dipakai demi `fairseq`/RVC, sudah habis masa dukungannya (Oktober 2026).

### 2.5 Setelah L0–L1 (29 Okt 2026)

Detail dan angka lengkap ada di CHANGELOG v1.3.0.

- Driver NVIDIA aktif setelah reboot (595, CUDA 13.2). Ollama 0.40.13 sebagai service systemd, `qwen3:4b-instruct` terpasang.
- `install.sh` lulus sampai `miku.py --test`; jalankan ulang 50 s. `pytest` 174 lulus dengan paket asli. GUI terbuka dan menyapa lewat RVC.
- Whisper (0,53–0,58 s) dan RVC (0,67–0,77 s) setara atau lebih cepat dari Windows. LLM sendirian di GPU: 62–66 token/s, balasan 0,3–0,7 s.
- Tool: 16/27 jalan (ditambah `get_system_info` lengkap, `type_text`, `press_key`, `hotkey`; tiga terakhir baru dicek lewat unit test), 3 sebagian (dokumen dibuat tapi tidak dibuka), 1 menolak dengan jelas (`close_application`), 7 belum jalan.

**Temuan baru:**

| Temuan | Dampak | Rencana |
|---|---|---|
| Aplikasi memuat Whisper + RVC (±1,7 GB) sebelum LLM; Ollama menyisakan cadangan 1 GB dan hanya menaruh 29/37 layer di GPU | Balasan pertama 49 s, berikutnya 1,6 s dengan 34 token/s | **Diperbaiki:** LLM dimuat lebih dulu dan ditahan (`keep_alive`), dilepas saat keluar. Balasan 1,3 s / 0,9 s, 100% GPU, 59 token/s, VRAM 5,5/6,1 GB |
| Setelah LLM dimuat lebih dulu, sisa VRAM ±300 MB; RVC memproses balasan panjang sekaligus | Balasan 18,7 s: `CUDA out of memory`, suara jatuh ke MeloTTS | **Diperbaiki:** RVC dipotong per 6 s (puncak +207 MiB). Sisa tetap tipis; uji KV cache Ollama `q8_0` (backlog) |
| Python 3.10 dari uv membawa Tcl/Tk 9.0; mengubah widget dari thread lain langsung segfault | GUI tertutup sendiri saat selesai memuat (sudah diperbaiki) | **Diaudit di L2:** 12 fungsi yang jalan di thread lain tidak menyentuh widget langsung; semua lewat antrean |
| Emoji berwarna tampil sebagai kotak di Tk Linux | Kosmetik | L3, bersama maskot |

### 2.6 Setelah L2 (31 Okt 2026)

Aksi OS sekarang lewat `core/desktop/` (`windows.py` berisi kode lama tanpa perubahan perilaku, `linux.py` baru). Semua jalan sebagai user biasa, tanpa sudo. Detail di CHANGELOG.

| Uji sungguhan di Mint (lewat tool Miku, tanpa LLM) | Hasil |
|---|---|
| Volume 55 → 30 → mute → unmute → 55 (`wpctl`) | lulus |
| Buka lalu tutup Kalkulator (`gnome-calculator`) dan Notepad (`xed`) | lulus; ditutup lewat `wmctrl -c` (sopan) |
| Buka folder Documents (Nemo); jendela Downloads milik user tidak tersentuh | lulus |
| Dokumen Word dibuat, dibuka di LibreOffice, lalu "tutup word" | lulus |
| "Brave web browser" → `/usr/bin/brave-browser` (sebelumnya membuka alamat `https://brave`) | lulus |

| Tool calling setelah deskripsi tool diubah (10 perintah JP/ID) | Hasil |
|---|---|
| Sekali jalan | 9/10; satu salah (`spotify_search` untuk "putar lagu … di YouTube") |
| Perintah itu diulang 5× + "carikan lagu …" 5× | L2: 10/10 `youtube_search`; `main`: 8/10 (variasi lama, bukan regresi) |

- Tool: 27/27 jalan atau menjawab jelas. Pengecualian yang disengaja: WhatsApp di Linux hanya menyiapkan draf di WhatsApp Web (user menekan Enter; grup belum didukung), Telegram butuh Telegram Desktop, dan `type_text`/`press_key`/`hotkey` baru dicek lewat unit test.
- `pytest`: 216 lulus (35 test baru untuk backend Linux), juga di Python sistem tanpa paket suara/GUI, seperti di CI.
- CI GitHub Actions (`.github/workflows/tests.yml`) menjalankan `pytest` di Ubuntu dan Windows.

## 3. Prinsip desain

1. **Satu kode, dua backend.** Semua aksi OS lewat `core/desktop/` (`windows.py`, `linux.py`). Tool tidak memanggil `os.startfile`, pycaw, atau win32 langsung, dan `sys.platform` tidak tersebar di banyak file.
2. **Keamanan tetap sama.** Aplikasi hanya dari whitelist, aksi berisiko tetap lewat gerbang konfirmasi, aplikasi ditutup dengan sopan (`WM_CLOSE` ↔ `_NET_CLOSE_WINDOW`), dan daftar proses yang dilindungi dibuat per OS.
3. **X11 dulu.** Di Wayland, input sintetis dan screenshot dibatasi. Aplikasi mendeteksi `XDG_SESSION_TYPE` dan memberi peringatan, bukan gagal diam-diam.
4. **Pakai standar freedesktop**: `xdg-open`, file `.desktop`, `wpctl`, MPRIS (`playerctl`), AT-SPI.
5. **Test per backend.** Backend Linux dites dengan `subprocess` yang di-mock (perintah yang dipanggil diperiksa), dan CI menjalankan `pytest` di Ubuntu dan Windows.

## 4. Pemetaan Windows → Linux

| Fitur | Windows (sekarang) | Linux (rencana) | Paket |
|---|---|---|---|
| Buka file / URI | `os.startfile` | `xdg-open` | ada |
| Volume, mute | pycaw | `wpctl set-volume @DEFAULT_AUDIO_SINK@ 0.30`, `wpctl set-mute …`; cadangan `pactl` | ada |
| Buka aplikasi | `ALLOWED_APPS` + App Paths | Alias → daftar kandidat perintah/`.desktop`, pakai yang pertama terpasang. Contoh: notepad → `xed`/`gnome-text-editor`, kalkulator → `gnome-calculator`, explorer → `nemo`/`nautilus`, settings → `cinnamon-settings`/`gnome-control-center`, terminal → `x-terminal-emulator`, word/excel/powerpoint → `libreoffice --writer/--calc/--impress`, browser → browser default | ada |
| Tutup aplikasi | `EnumWindows` + `WM_CLOSE` | `wmctrl -lp` (jendela per PID) + `wmctrl -ic <id>` (`_NET_CLOSE_WINDOW`) | ada |
| Jendela aktif, fokus | pygetwindow | `xdotool getactivewindow getwindowname`, `wmctrl -a` | `xdotool` |
| Ketik, tombol, hotkey | pyautogui | pyautogui (X11). Teks non-ASCII (Jepang) lewat clipboard `xclip` + Ctrl+V, karena `typewrite` hanya ASCII | `xclip` |
| Media | tombol media pyautogui | `playerctl play-pause/next/previous` (MPRIS) | `playerctl` |
| Folder | `explorer` | `xdg-open <dir>`, nama folder dari `xdg-user-dir` | ada |
| Dokumen | Word/PowerPoint | python-docx/pptx sama; dibuka LibreOffice lewat `xdg-open` | ada |
| WhatsApp | `whatsapp://` (WA Desktop) | `https://web.whatsapp.com/send?phone=…&text=…` di browser | - |
| Telegram | `tg://` | `tg://` lewat `xdg-open`, bila Telegram Desktop terpasang | opsional |
| Proses dilindungi | svchost, dwm, explorer, … | systemd, Xorg, cinnamon, pipewire, wireplumber, dbus-daemon, ollama, python | - |
| Maskot transparan | layered window + colorkey (win32) | X11 SHAPE (python-xlib, sudah ikut pyautogui) atau Qt translucent; dipilih lewat spike L3 | - |
| Shortcut | `.lnk` di Desktop | `~/.local/share/applications/mikuvision.desktop` | - |
| Installer | `install.ps1` | `install.sh` | - |
| Hotkey global | `keyboard` (di Linux butuh root) | `pynput` (X11), bila nanti dibutuhkan | - |

## 5. Tahapan

### Fase L0: Siapkan mesin (selesai 29 Okt 2026)
- Reboot, lalu `nvidia-smi` harus menampilkan RTX 4050. Bila masih gagal, cek `dkms status` dan log kernel.
- `git config core.autocrlf input` (54 file "modified" palsu hilang) dan `git worktree prune`.
- `sudo apt install xdotool playerctl xclip`.
- Pasang Ollama versi Linux (service systemd), lalu `ollama pull qwen3:4b-instruct`.
- Tentukan lokasi venv (lihat keputusan no. 1).
- **Keluaran:** `nvidia-smi` dan `ollama list` jalan.

### Fase L1: Bisa dipasang dan dijalankan (selesai 29 Okt 2026)
- `requirements.txt`: penanda `; sys_platform == "win32"` untuk `pycaw`, `comtypes`, `pywin32`, `pygetwindow`, `keyboard`.
- `install.sh`, setara `install.ps1`: uv 0.11.2 dengan cek SHA-256, Python 3.10 dari uv, venv, torch 2.11 cu128 lewat `--torch-backend`, kamus `unidic`, `rvc-python` bila model RVC ada, cek Ollama, entri `.desktop`, verifikasi `miku.py --test`. Idempoten, log di `logs/`.
- `run.sh`.
- `.gitattributes`: `* text=auto`, `*.sh text eol=lf`, `*.bat`/`*.ps1 text eol=crlf`, supaya folder yang dipakai bersama dua OS tidak rusak.
- Perbaikan cepat: import psutil dan pyautogui dipisah dari pycaw.
- README: bagian instalasi Linux.
- **Keluaran:** `pytest` dan `miku.py --test` lulus di Linux; GUI terbuka; suara masuk/keluar jalan dengan Whisper di CUDA.

### Sebelum L2: urutan muat VRAM (selesai 29 Okt 2026; di Windows belum diukur ulang)
- Muat LLM ke VRAM sebelum Whisper dan RVC (di `miku.py` dan `gui.py`), tahan dengan `keep_alive` selama aplikasi jalan, dan lepas (`keep_alive=0`) saat keluar.
- Berlaku juga untuk Windows. Ukur ulang balasan pertama dan `ollama ps` di kedua OS.
- **Keluaran:** balasan pertama ≤ 3 s, `ollama ps` 100% GPU selama aplikasi jalan.

### Fase L2: Aksi komputer di Linux (selesai 31 Okt 2026; hasil di bagian 2.6)
- `core/desktop/` (bukan `core/platform/`, supaya tidak tertukar dengan modul standar Python `platform`): antarmuka + backend Windows (kode lama dipindah tanpa mengubah perilaku) + backend Linux sesuai tabel bagian 4.
- Katalog aplikasi Linux di `config.py` (alias → kandidat), tetap whitelist.
- Tool memakai platform layer: `open_application`, `close_application`, `open_folder`, volume, mute, media, membuka dokumen, WhatsApp Web, Telegram.
- Perbaikan untuk dua OS: dokumen yang sudah tersimpan tidak lagi dilaporkan "Gagal" bila hanya gagal dibuka.
- Teks Jepang lewat clipboard; peringatan bila sesi Wayland.
- Test backend Linux dengan `subprocess` di-mock; conftest tidak lagi membuat Windows selalu "tersedia"; CI GitHub Actions (ubuntu-latest + windows-latest) menjalankan `pytest`.
- **Keluaran:** 27/27 tool jalan, atau menjawab jelas "belum didukung di Linux"; tanpa crash.

### Fase L3: Maskot desktop di Linux (1–2 hari)
- Spike: X11 SHAPE (python-xlib) vs Qt (PySide6) dengan latar transparan. Pilih satu.
- Transparan, always-on-top (`_NET_WM_STATE_ABOVE`), bisa diseret, menu klik kanan "Exit", tidak mencuri fokus.
- **Keluaran:** maskot tanpa kotak magenta, bisa diseret ke mana saja.

### Fase L4: Benchmark Linux vs Windows (1 hari)
- Ulangi benchmark yang sama dengan Windows: tool calling (10 perintah × 5), `experiments/stt_eval`, latensi MeloTTS/RVC, VRAM, waktu start.
- Hasil di `experiments/linux_eval/RESULTS.md` dan CHANGELOG, berdampingan dengan angka Windows.

### Sesudahnya: agent visi Fase 1 lintas OS
- Spike Fase 0 versi Linux: cakupan AT-SPI2 (pengganti UI Automation) di Nemo, Cinnamon Settings, Kalkulator, LibreOffice, Firefox, dan Brave (browser Chromium butuh `--force-renderer-accessibility`).
- OCR: RapidOCR (ONNX, CPU) bisa dipakai di dua OS, menggantikan Windows OCR yang hanya ada di Windows.
- Screenshot `mss` dan model `qwen3-vl:4b-instruct` sama dengan rencana Windows.

### Backlog
- Ruang VRAM: uji `OLLAMA_FLASH_ATTENTION=1` + `OLLAMA_KV_CACHE_TYPE=q8_0` di service Ollama (KV cache 1152 → ±576 MiB) dan ukur ulang tool calling.
- Pindah dari Python 3.10 (EOL): cari implementasi RVC tanpa `fairseq`.
- Dukungan Wayland (screenshot lewat portal, input sintetis).
- Rilis GitHub dengan petunjuk Linux.

## 6. Evaluasi

| Metrik | Sekarang | Target |
|---|---|---|
| `pytest` di Linux | 216/216 (35 test backend Linux), juga di CI Ubuntu + Windows | Lulus semua, ditambah test backend Linux, juga di CI |
| `miku.py --test` di Linux | lulus | lulus |
| Tool berfungsi di Linux | 27/27 (WhatsApp: draf di WhatsApp Web; Telegram butuh aplikasinya) | 27/27 (atau pesan jelas "belum didukung") |
| Tool calling, 10 perintah × 5 | 2/2 benar (uji singkat) | 50/50, sama dengan Windows |
| Latensi LLM di dalam aplikasi | 1,3 s pertama, 0,9 s berikutnya (sebelum perbaikan VRAM: 49 s / 1,6 s) | ≤ 1,1 s (Windows median 0,9 s) |
| STT (`experiments/stt_eval`) | belum diukur | Indonesia 14/14, Jepang 9/10 (sama dengan Windows) |
| Instalasi lewat `install.sh` | lulus: 7 menit pertama, 50 s jalankan ulang | lulus di instalasi bersih |

## 7. Risiko & mitigasi

| Risiko | Mitigasi |
|---|---|
| Sesi Wayland | X11 dulu; deteksi `XDG_SESSION_TYPE` dan beri peringatan |
| Folder NTFS dipakai dua OS | `.gitattributes` untuk akhir baris; venv per OS di luar folder bersama |
| Nama aplikasi beda antar distro (Mint `xed` vs Ubuntu `gnome-text-editor`) | Katalog berisi beberapa kandidat; dipakai yang pertama terpasang |
| Driver NVIDIA baru di kernel 7.0 | Cek `nvidia-smi` setelah reboot sebelum L1 |
| Python 3.10 sudah EOL | Dicatat di backlog; RVC tetap opsional |
| Salah tutup proses di Linux | Daftar proses dilindungi versi Linux; `_NET_CLOSE_WINDOW` (sopan), bukan kill |

## 8. Keputusan yang dibutuhkan dari user

1. **Lokasi repo**: tetap di partisi NTFS bersama (dipakai Windows dan Linux, venv Linux di ext4), atau clone terpisah ke ext4?
2. **Maskot**: X11 SHAPE (tanpa dependency baru) atau Qt/PySide6 (lebih rapi, dependency besar)?
3. **WhatsApp di Linux**: lewat WhatsApp Web di browser, oke?
4. **Urutan**: port Linux (L0–L4) dulu, baru agent visi Fase 1? (rekomendasi: ya)
5. **Wayland**: perlu didukung, atau cukup X11?
