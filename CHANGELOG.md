# Changelog

Catatan perubahan, pengujian, dan keputusan teknis MikuWin V11.
Format mengikuti [Keep a Changelog](https://keepachangelog.com/id/1.1.0/). Entri terbaru di atas.
Angka benchmark diukur di laptop pengembang: RTX 4050 Laptop 6 GB, Windows 11, Ollama 0.40.10.

---

## [Belum dirilis] (PR terbuka)

### Paket B: skill on-demand, routine, slash command ([#10](https://github.com/MocArjunnaja/MikuWin_V11_Stable/pull/10))
**Ditambahkan**
- `core/skills.py`: 25 tool dikelompokkan menjadi 9 skill (Audio, Aplikasi, Web, Keyboard, Office, Pesan, Memori, Info sistem, Routine). Hanya skill yang cocok dengan permintaan user yang dikirim ke LLM; obrolan tanpa pemicu tetap mengirim semua tool. Bisa dimatikan dengan `SKILL_ROUTING = False`.
- `core/routines.py` + `routines.example.yaml`: routine = rangkaian tool dengan satu perintah ("jalankan mode belajar"). Routine milik user di `data/routines.yaml` menimpa contoh. Setiap langkah tetap lewat gerbang konfirmasi; routine tidak boleh memanggil routine lain.
- `core/commands.py`: slash command tanpa LLM di mode teks dan GUI: `/help /clear /usage /memory /forget /skills /routines /routine /sessions /resume`.
- Daftar routine disisipkan ke system prompt hanya saat skill Routine aktif.
- `docs/PLAN_VISION_AGENT.md`: rencana agent visi (screenshot → paham → mouse/keyboard, dengan iterasi).

**Pengujian**
- 129 unit test lulus.
- Routing skill ON vs OFF (10 perintah × 5):

  | | Akurasi tool | Token prompt (median) | Latensi median | p90 |
  |---|---|---|---|---|
  | OFF | 49/50 | 3.401 | 0,7 s | 4,8 s |
  | ON | 50/50 | 1.545 | 1,0 s | 1,5 s |

- Routine lewat bahasa alami ("テストモードを実行して", "jalankan mode tes"): 3/3. Semua slash command diuji end-to-end di `miku.py --text`.

### Paket A: token meter, log, sesi, memori jangka panjang ([#9](https://github.com/MocArjunnaja/MikuWin_V11_Stable/pull/9))
**Ditambahkan**
- **Penghitung token:** angka asli dari Ollama (`prompt_eval_count` / `eval_count`). Ditampilkan setelah tiap balasan di CLI dan di bawah status GUI.
- `core/conversation.py`: `run_turn()`, satu alur think → tool → catat hasil → laporan → log untuk mode teks, suara, dan GUI (sebelumnya tiga salinan kode).
- `core/turn_log.py`: log JSONL per giliran di `data/logs/`.
- **Melanjutkan sesi:** `miku.py --resume [ID]` dan tombol **↺ Sesi lalu** di GUI. Sesi kosong tidak lagi disimpan.
- `core/long_term_memory.py`: tool `remember` / `recall_memory` / `forget`; 15 fakta terbaru disisipkan ke system prompt.

**Diperbaiki**
- Client Ollama diberi timeout 120 s. Sebelumnya request yang tersendat membuat app menunggu selamanya (terjadi sekali saat uji).

**Pengujian**
- 104 unit test.
- `remember` terpanggil 28/30 pada 6 variasi kalimat Jepang/Indonesia. Hanya contoh Indonesia → bahasa Jepang 0/5; contoh dua bahasa diperlukan.
- Fakta disimpan di satu proses, lalu dijawab benar di proses baru.
- GUI: label token dan tombol Sesi lalu dicek lewat screenshot.

**Keterbatasan diketahui**
- Setelah `--resume`, model kadang meniru balasan lamanya sendiri (misalnya "belum ada di ingatan") walaupun riwayat sudah ada di konteks.

### Model default qwen3:4b-instruct + agent loop yang benar ([#8](https://github.com/MocArjunnaja/MikuWin_V11_Stable/pull/8))
**Diubah**
- `OLLAMA_MODEL = "qwen3:4b-instruct"`.
- Giliran tool call disimpan dalam format resmi Ollama (`tool_calls` + pesan `role: tool`).
- `think_observation()` memakai hasil tool yang tercatat, bukan pesan "System Observation" palsu.
- Retry dua tahap saat user meminta aksi tapi model tidak memanggil tool.
- `initialize()` mengecek tag model persis.

**Pengujian (10 perintah JP/ID, tool tidak dieksekusi)**

| Model | Akurasi tool | Median | p90 |
|---|---|---|---|
| qwen3:4b-instruct (dengan retry) | 50/50 | 0,9 s | 1,2 s |
| qwen3:4b (Thinking-2507) | 30/30 | 11,5 s | 30,4 s |
| granite4.2:3b | 25/30 | 4,6 s | 57,7 s |

- Percakapan bertingkat (buka lalu tutup Notepad): 0/4 sebelum perbaikan → 8/8.
- Menyimpan tool call sebagai teks biasa tidak membantu (0/4); format `tool_calls` diperlukan (4/4).

---

## 2026-10-24

### Bug dari pengujian end-to-end ([#7](https://github.com/MocArjunnaja/MikuWin_V11_Stable/pull/7))
**Diperbaiki**
- **Segfault** saat dua balasan diputar bersamaan (`sounddevice.play()` dari dua thread). Pemutaran audio sekarang antre.
- **Access violation saat keluar**: audio yang masih antre diputar ketika PortAudio sedang ditutup.
- **GUI tidak pernah "Ready"** bila stdout bukan konsol (`print("初音ミク")` → `UnicodeEncodeError`); juga membuat `initialize()` keliru melapor "Gagal connect ke Ollama".
- Input Jepang lewat stdin non-konsol rusak (surrogate) → semua request ke Ollama gagal.
- qwen3:4b mengucapkan penalarannya dan membuka Notepad 6×. Parameter `think` tidak dikirim lagi, isi sampai `</think>` dibuang, tool call kembar dihapus.
- Miku mengaku sudah melakukan aksi padahal tidak memanggil tool. Daftar tool manual dengan nama salah dihapus dari prompt persona.
- `close_application` mematikan paksa semua jendela, termasuk milik user. Sekarang memakai `WM_CLOSE` (seperti tombol ✕), sehingga aplikasi sempat menawarkan simpan.
- Kode wake mati di `miku.py` (memakai 4 atribut yang tidak pernah dibuat) dihapus.

**Pengujian**
- 61 unit test.
- Pipeline MeloTTS → Whisper → MeloTTS → RVC diuji: RVC aktif, konversi ±1,6 s, pitch +6 semitone.
- GUI dicek lewat screenshot `PrintWindow`.

### Supaya bisa dijalankan di laptop lain ([#6](https://github.com/MocArjunnaja/MikuWin_V11_Stable/pull/6))
- Folder output yang ditulis langsung sebagai `C:/Users/Arjun/...` (crash di akun lain) diganti `Path.home()`.
- `DEBUG_DUMP_AUDIO` default `False` (sebelumnya setiap rekaman mic disimpan).
- `pytest.ini`, README baru dengan langkah instalasi yang sudah teruji.
- **Pengujian:** clone baru dari GitHub → `pytest` + `python miku.py --test` lulus.

### Avatar memakai frame sprite kosong ([#5](https://github.com/MocArjunnaja/MikuWin_V11_Stable/pull/5))
- `thinking`/`confused` menunjuk ke frame transparan, sehingga avatar menghilang. `MIKU_FRAME_H` salah (265, seharusnya 213).
- Ditambah peta emosi bersama `MIKU_EMOTION_FRAMES` dan test yang memverifikasi setiap frame terhadap gambar sprite.

### Integrasi PR #2 dengan perbaikan bug ([#4](https://github.com/MocArjunnaja/MikuWin_V11_Stable/pull/4))
- Parser JSON untuk tool bersarang, tanpa `shell=True`, pelacakan PID, `set_volume` lewat pycaw. Kredit: @nashirabbash.
- Diperbaiki: tool call palsu dari objek bersarang, teks balasan terpotong, `Popen(["chrome"])` gagal (App Paths), pencocokan nama proses sebagian.
- PR #2 ditutup dengan komentar penjelasan.

### Perbaikan P0 ([#3](https://github.com/MocArjunnaja/MikuWin_V11_Stable/pull/3))
- Pesan user tidak pernah disimpan ke memori.
- Gerbang konfirmasi untuk WhatsApp, Telegram, dan menutup aplikasi.
- Skema `hotkey` (list → array), `num_ctx` 8192, `requirements.txt` disesuaikan dengan import.
- NameError `automation_layer` saat playwright tidak terpasang.

### Pembersihan riwayat repo
- `data/` (percakapan, 10 rekaman WAV mic, `contacts_db.json`) dihapus dari **seluruh** history dengan `git filter-repo`, lalu di-force-push. Backup lokal: `D:\02_Research\MikuWin_backup_20261024\`.
- Belum dilakukan: permintaan penghapusan cache commit lama ke GitHub Support.

---

## Evaluasi tanpa perubahan kode

### ASR: Whisper large-v3-turbo vs Qwen3-ASR-0.6B (2026-10-25)
| | Whisper turbo | Qwen3-ASR-0.6B |
|---|---|---|
| CER Jepang sintetis (8 klip) | 23,5% | 24,0% |
| Kesalahan fatal | 0 | 2 |
| Rekaman asli bahasa Indonesia | 1 halusinasi | benar |
| Latensi per klip | 0,59 s | 0,46 s |
| VRAM | +1,1 GB | +1,6 GB |

**Keputusan:** tetap memakai Whisper. Sampelnya kecil, jadi perlu diuji ulang dengan rekaman suara pengguna sebelum diputuskan pindah.

### Perubahan lingkungan lokal (bukan isi repo)
- Env conda `miku`: `faiss-cpu` 1.7.3 → 1.9.0.post1, supaya RVC bisa jalan dengan NumPy 2.
- Env `D:\conda_envs\qwenasr` (5 GB) dan cache `D:\hf_cache` (1,5 GB) untuk uji ASR.
- Model Ollama dipindah ke `D:\ollama_models`, dengan variabel user `OLLAMA_MODELS`. Ruang kosong C naik 2,1 → 18,9 GB.
- Cache Hugging Face dipindah ke `D:\hf_home`, dengan variabel user `HF_HOME`. Robocopy mengubah symlink `snapshots` menjadi file 0 byte; dipulihkan sebagai hardlink ke `blobs` tanpa unduh ulang. Diverifikasi offline: `miku.py --test` + TTS→STT.
- Bersih-bersih (25 Okt):
  - Cache pip dibersihkan (6,0 GB) dan cache conda dibersihkan (`conda clean --all`, 2,0 → 1,1 GB).
  - Dipindah ke Recycle Bin: Whisper large-v3 lama (2,9 GB), cache torch (1,9 GB), env `Mikuve`, `OllamaSetup.exe`, `A Miku Research.rar`.
  - Ruang kosong C: 2,1 GB → 26,1 GB (±31 GB setelah Recycle Bin dikosongkan).
  - Belum dihapus (perlu dihapus manual): `D:\conda_envs\qwenasr` dan `D:\hf_cache` dari uji ASR.
