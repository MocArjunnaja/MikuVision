# Changelog

Catatan perubahan, pengujian, dan keputusan teknis MikuVision (dulu MikuWin V11).
Format mengikuti [Keep a Changelog](https://keepachangelog.com/id/1.1.0/). Entri terbaru di atas.
Angka benchmark diukur di laptop pengembang: RTX 4050 Laptop 6 GB, Windows 11, Ollama 0.40.10.

---

## [Belum dirilis] Dokumen Word dibuat beserta isinya

Detail: `experiments/word_tool/RESULTS.md`. Pemicunya sesi GUI 25 Okt: "buatkan dokumen Word … Hukum Newton" hanya dijawab obrolan, lalu ulangan singkatnya hanya membuka Word kosong.

### Diubah
- `create_word_document` diberi deskripsi yang tegas: langsung tulis isinya sendiri, jangan bertanya dulu, jangan `open_application`. Parameter `filename` dan `content` sekarang punya deskripsi; sebelumnya semua parameter tool hanya berlabel "Parameter: <nama>".
- `ToolRegistry.register(..., params={...})` untuk deskripsi per parameter.
- `open_application` merujuk ke `create_word_document` untuk dokumen berisi.
- Regex retry tool mengenali permintaan dokumen (作って, 書いて, buat/buatkan, bikin, tulis, create, write) dan janji 「作ります」.
- Bila permintaan tidak berbahasa Jepang tapi isi dokumen ditulis dalam bahasa Jepang (≥ 30% huruf), isinya diterjemahkan ke bahasa Indonesia dengan satu panggilan tanpa tool. Petunjuk bahasa di prompt tidak cukup untuk model 4B.
- Koreksi STT "hegum" → "hukum", dengan huruf kapital asli dipertahankan.

### Pengujian
| | Sebelum | Sesudah |
|---|---|---|
| Permintaan dokumen (6 × 3, isi ≥ 150 karakter sesuai topik) | 7/18 | **17/18** |
| Kontrol "Buka Word" / 「ワードを開いて」 | 6/6 | 6/6 |
| Tool umum / multi-turn | 50/50 / 8/8 | 50/50 / 8/8 |
| Latensi median permintaan dokumen | 2,2 s | 9,2 s (model kini menulis 500–2.100 karakter) |

- 172 unit test lulus (12 baru di `tests/test_word_document_tool.py`).

## [Belum dirilis] Akurasi STT: deteksi bahasa sekali, pembersihan teks Whisper

Detail, skrip uji, dan semua angka: `experiments/stt_eval/RESULTS.md`.

### Diubah
- `VoiceInput.transcribe()` mendeteksi bahasa sekali, dibatasi ke `WHISPER_LANGUAGES = ("ja", "id")` (Melayu/Jawa/Sunda dihitung sebagai Indonesia), lalu melakukan satu kali decoding. Sebelumnya setiap ucapan didecode paksa sebagai Jepang lalu Indonesia, dan pemenangnya dipilih dengan skor kata kunci.
- Dua bahasa hanya didecode bila deteksi ragu (< 0,8); yang dipilih adalah hasil dengan log-probability lebih baik.
- Segmen yang berulang (`compression_ratio > 2,4`) atau tanpa ucapan dibuang; suhu decoding naik (0 → 0,2 → 0,4) hanya bila hasil suhu 0 ragu.
- Level mic dinaikkan secara linear. `noisereduce` + soft-clip `tanh` dimatikan (`STT_DENOISE = False`).
- `_transcribe_best_effort` / `_score_transcript_intent` yang terduplikasi di `miku.py` dan `gui.py` dihapus; keduanya memanggil `voice_input.transcribe(audio, languages=[...])`.

### Ditambahkan
- `core/stt_text.py`, diadopsi dari alat transkrip TA (`pdf_transkrip.bersihkan`): buang frasa halusinasi ("ご視聴ありがとうございました", "Terima kasih telah menonton", …), pengulangan beruntun, dan huruf di luar aksara bahasa target.

### Diperbaiki
- Ucapan Indonesia seperti "Kecilkan volumenya" / "Matikan suaranya" menjadi 「音量を下げて、音量を下げて、…」 (isi prompt Jepang bocor).
- Koreksi salah dengar mengganti substring: "volume" → "volume**e**", "sejak" → "sEdgeak". Sekarang dicocokkan per kata utuh.
- Koreksi "tolong buka" → "buka" membuang kata dari ucapan user.
- Filter halusinasi lama membuang kalimat sah: semua kalimat pendek berisi "terima kasih", dan apa pun yang memuat 「字幕」 atau 「食べる前に」.

### Pengujian
- 54 klip edge-tts (Indonesia/Jepang, bersih + mic laptop berderau, derau tanpa ucapan):

  | | Lama | Baru |
  |---|---|---|
  | Indonesia bersih / mic laptop | 10/14 / 8/14 | **14/14 / 14/14** |
  | Jepang bersih / mic laptop | 9/10 / 8/10 | 9/10 / **9/10** |
  | Derau → teks palsu | 0/6 | 0/6 |
  | Latensi median | 0,68 s | **0,54 s** |

- 6 rekaman mic asli: hasil sama dengan pipeline lama.
- 160 unit test lulus (31 baru: `tests/test_stt_text.py`, `tests/test_voice_input.py`); `miku.py --test` lulus.

**Keterbatasan:** suara uji sintetis lebih jernih dari suara asli. Untuk mengumpulkan kasus gagal nyata, nyalakan `DEBUG_DUMP_AUDIO` sementara.

## 2026-10-25: installer satu langkah, RVC jalan di instalasi baru

### Ditambahkan
- `install.ps1` + `install.bat` (double-click): instalasi tanpa Anaconda.
  - [uv](https://docs.astral.sh/uv/) 0.11.2 diunduh ke `.tools\uv` dan checksum SHA-256-nya dicek.
  - Python 3.10 terisolasi di `.tools\python` (tanpa PATH/registry), env `.venv` dibuat dengan `python -m venv`, cache unduhan di `.tools\uv-cache`. Semua di folder aplikasi, tidak di profil C:.
  - PyTorch 2.11.0: build cu128 bila `nvidia-smi` melaporkan CUDA ≥ 12.8, cu126 untuk driver lama, CPU (dengan peringatan) tanpa GPU NVIDIA. Dipasang dalam satu resolusi bersama `requirements.txt` lewat `--torch-backend`, lalu dicek `torch.cuda.is_available()`.
  - `rvc-python==0.1.5` ikut resolusi yang sama bila model RVC ada di `models\miku_default_rvc` (atau `-WithRvc`). `overrides-rvc.txt` menimpa pin `numpy<=1.23.5` milik rvc-python yang bentrok dengan `requirements.txt`. Bila build `fairseq` gagal, instalasi lanjut tanpa RVC dengan petunjuk Build Tools.
  - Kamus `unidic`, cek import modul, Ollama (`winget install Ollama.Ollama` setelah konfirmasi), `ollama pull` model dari `OLLAMA_MODEL` di `config.py`.
  - Shortcut desktop **MikuVision** (`pythonw gui.py`, tanpa konsol) dengan ikon dari sprite.
  - Verifikasi akhir `miku.py --test`, termasuk peringatan bila rvc-python terpasang tapi RVC gagal dimuat.
  - Idempoten: langkah yang sudah beres dilewati; venv rusak atau buatan versi lain dibuat ulang. Log di `logs\install-<waktu>.log`; berhenti dengan pesan penyebab bila gagal.
  - Opsi `-Yes`, `-Cpu`, `-WithRvc`, `-SkipOllama`, `-SkipShortcut`, `-SkipTest`, `-PythonVersion`.
  - `HF_HOME` dan `OLLAMA_MODELS` dibaca dari variabel user bila proses installer belum melihatnya. Saat uji, proses dengan environment lama mengunduh Whisper + MeloTTS (1,75 GB) ke `C:\Users\<user>\.cache\huggingface` walau `HF_HOME` sudah diarahkan ke `D:\hf_home`.
- README ditulis ulang untuk GitHub: header + badge, screenshot GUI, tabel fitur, diagram alur (Mermaid), **Instalasi cepat**, bagian lipat untuk detail installer/manual, dan tabel **Lisensi & kredit** (PCL untuk karakter, status sprite, model RVC, lisensi dependency).

### Diubah
- `run.bat` memakai `.venv` dari installer bila ada.
- `gui.py`: lewat `pythonw.exe` (shortcut) stdout/stderr bernilai `None`; output sekarang ditulis ke `data/logs/gui.log`.
- README: URL clone memakai nama repo baru `MikuVision`.

### Diperbaiki
- **RVC tidak jalan di instalasi baru** (dua bug yang tertutup oleh patch manual di env conda `miku`):
  - torch ≥ 2.6 memuat checkpoint dengan `weights_only=True`, sehingga `hubert_base.pt` (berisi objek `fairseq Dictionary`) ditolak saat konversi pertama. Env `miku` ternyata memakai `fairseq/checkpoint_utils.py` yang diubah tangan menjadi `weights_only=False`. `core/voice_converter.py` kini mengizinkan hanya class `Dictionary` lewat `torch.serialization.add_safe_globals`, tanpa mematikan `weights_only` untuk checkpoint lain.
  - Tanpa pin, uv memilih `rvc-python 0.1.0` yang `load_model()`-nya tidak menerima `index_path`.
- GUI crash diam-diam saat dibuka tanpa konsol: transformers 4.27.4 (dipatok MeloTTS) memanggil `sys.stderr.flush` saat import.
- `tests/conftest.py`: stub `torch` diberi kelas `Tensor` asli. scipy ≥ 1.17 memanggil `issubclass(x, torch.Tensor)` sehingga `test_voice_output.py` gagal di-collect.

### Keputusan
- **Python 3.10, bukan 3.11.** Di 3.11, `fairseq 0.12.2` gagal saat import (`mutable default ... use default_factory`), jadi RVC mati. Python 3.10 berakhir masa dukungannya Oktober 2026; pindah versi menunggu pengganti `fairseq` di `rvc-python`.
- `uv venv` tidak dipakai: launcher `pythonw.exe`-nya identik dengan `python.exe` (uv 0.11.2), sehingga shortcut ikut membuka jendela konsol.

### Pengujian
Clone baru di `D:\02_Research\MikuVision_installtest`, Windows PowerShell 5.1, RTX 4050 (driver 581.86, CUDA 13.0), Ollama 0.40.10.

| Skenario | Hasil | Waktu |
|---|---|---|
| Instalasi pertama, Python 3.11 (unduh uv, Python, torch 2.11.0+cu128 2,6 GB, 180 paket, unidic) | lulus, `miku.py --test` OK | 12 menit |
| Pindah ke Python 3.10 + model RVC ada (unduh torch cp310, build `fairseq`) | lulus, `RVC model loaded in 0.5s (cuda:0)` | 8 menit |
| Jalankan ulang (semua sudah terpasang) | semua langkah dilewati, lulus | 55-58 s |
| Venv rusak (`pyvenv.cfg` hilang) | dibuat ulang dari cache uv, torch tidak diunduh ulang | 105 s |

- `pytest`: 129 lulus di env installer (Python 3.10 dan 3.11) dan env conda `miku`.
- MeloTTS → Whisper: "こんにちは、初音ミクです。今日はいい天気ですね。" terdengar "今日は初音ミクです。今日はいい天気ですね。".
- MeloTTS → RVC → Whisper: konversi pertama 19,5 s (unduh `hubert_base.pt`/`rmvpe.pt`), lalu 4,3 s dan 0,98 s; teks tetap terbaca sama.
- Shortcut desktop: hanya jendela GUI yang muncul (tanpa konsol), status **Ready**, **RVC: ready (0.4s)**, sapaan diputar lewat RVC.
- Belum teruji: mesin tanpa GPU NVIDIA (jalur CPU), mesin tanpa Git/Ollama (jalur `winget`), mesin tanpa Visual Studio Build Tools (build `fairseq` diperkirakan gagal; installer lanjut tanpa RVC), unduhan Whisper/MeloTTS pertama kali (cache Hugging Face mesin uji sudah terisi).

### Keterbatasan diketahui
- Model RVC tidak diunduh otomatis; pengguna menyiapkan sendiri (lihat README).
- Asal sprite maskot belum tercatat.
- Judul jendela GUI masih "MikuWin v4".

---

## 2026-10-25 (#8, #9, #10 sudah di-merge)

### Repo diganti nama: MikuWin_V11_Stable → MikuVision
- URL baru: https://github.com/MocArjunnaja/MikuVision. URL lama dialihkan otomatis oleh GitHub.
- Clone lama cukup menjalankan `git remote set-url origin https://github.com/MocArjunnaja/MikuVision.git`.
- Link PR di CHANGELOG dan perintah clone di README diperbarui. Nama aplikasi di kode tetap MikuWin.

### Paket B: skill on-demand, routine, slash command ([#10](https://github.com/MocArjunnaja/MikuVision/pull/10))
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

### Paket A: token meter, log, sesi, memori jangka panjang ([#9](https://github.com/MocArjunnaja/MikuVision/pull/9))
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

### Model default qwen3:4b-instruct + agent loop yang benar ([#8](https://github.com/MocArjunnaja/MikuVision/pull/8))
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

### Bug dari pengujian end-to-end ([#7](https://github.com/MocArjunnaja/MikuVision/pull/7))
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

### Supaya bisa dijalankan di laptop lain ([#6](https://github.com/MocArjunnaja/MikuVision/pull/6))
- Folder output yang ditulis langsung sebagai `C:/Users/Arjun/...` (crash di akun lain) diganti `Path.home()`.
- `DEBUG_DUMP_AUDIO` default `False` (sebelumnya setiap rekaman mic disimpan).
- `pytest.ini`, README baru dengan langkah instalasi yang sudah teruji.
- **Pengujian:** clone baru dari GitHub → `pytest` + `python miku.py --test` lulus.

### Avatar memakai frame sprite kosong ([#5](https://github.com/MocArjunnaja/MikuVision/pull/5))
- `thinking`/`confused` menunjuk ke frame transparan, sehingga avatar menghilang. `MIKU_FRAME_H` salah (265, seharusnya 213).
- Ditambah peta emosi bersama `MIKU_EMOTION_FRAMES` dan test yang memverifikasi setiap frame terhadap gambar sprite.

### Integrasi PR #2 dengan perbaikan bug ([#4](https://github.com/MocArjunnaja/MikuVision/pull/4))
- Parser JSON untuk tool bersarang, tanpa `shell=True`, pelacakan PID, `set_volume` lewat pycaw. Kredit: @nashirabbash.
- Diperbaiki: tool call palsu dari objek bersarang, teks balasan terpotong, `Popen(["chrome"])` gagal (App Paths), pencocokan nama proses sebagian.
- PR #2 ditutup dengan komentar penjelasan.

### Perbaikan P0 ([#3](https://github.com/MocArjunnaja/MikuVision/pull/3))
- Pesan user tidak pernah disimpan ke memori.
- Gerbang konfirmasi untuk WhatsApp, Telegram, dan menutup aplikasi.
- Skema `hotkey` (list → array), `num_ctx` 8192, `requirements.txt` disesuaikan dengan import.
- NameError `automation_layer` saat playwright tidak terpasang.

### Pembersihan riwayat repo
- `data/` (percakapan, 10 rekaman WAV mic, `contacts_db.json`) dihapus dari **seluruh** history dengan `git filter-repo`, lalu di-force-push. Backup lokal: `D:\02_Research\MikuWin_backup_20261024\`.
- Belum dilakukan: permintaan penghapusan cache commit lama ke GitHub Support.

---

## Evaluasi tanpa perubahan kode

### Agent visi Fase 0: spike & keputusan model (2026-10-25)
Detail dan skrip: `experiments/vision_phase0/RESULTS.md`.

| | qwen3:4b-instruct | qwen3-vl:4b-instruct | qwen3-vl:2b-instruct |
|---|---|---|---|
| Tool calling MikuWin (routing ON) | 50/50 | 42/50 | - |
| Multi-turn `close_application` | 8/8 | 4/8 | - |
| Pilih elemen, daftar UIA (15 × 3) | 39/45 | **44/45** | 21/45 |
| Pilih elemen, gambar + daftar | - | 43/45 | 31/45 |
| VRAM (`num_ctx` 8192) | 3,9 GB | 3,7 GB | 2,5 GB |
| Cold load | 3,6–4,3 s | 6,5–7,3 s | 4,3–4,6 s |

- UI Automation: 36/36, 34/35, dan 156/163 elemen bernama (Kalkulator, Settings, Explorer), dibaca dalam ≤ 0,34 s.
- Windows OCR: 0,03–0,06 s; hanya bahasa Inggris terpasang, OCR Jepang perlu paket bahasa Windows.
- **Keputusan:** opsi B. Chat dan tool tetap `qwen3:4b-instruct`; `qwen3-vl:4b-instruct` dimuat hanya saat sesi agent visi. Opsi A ditolak karena qwen3-vl:4b sering mengklaim aksi tanpa memanggil tool.

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
- Agent visi Fase 0: `qwen3-vl:4b-instruct` (3,3 GB) dan `qwen3-vl:2b-instruct` (1,9 GB) di `D:\ollama_models`; paket `uiautomation`, `mss`, `winrt-Windows.*` (OCR) di env `miku`.
