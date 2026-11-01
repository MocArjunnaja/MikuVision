# Menyesuaikan MikuVision

MikuVision dirancang untuk laptop dengan GPU NVIDIA 6 GB, tetapi model dan pengaturannya bisa diganti sesuai komputer Anda. Halaman ini menjelaskan apa yang bisa diganti tanpa mengubah kode, apa yang perlu diperhatikan, dan di mana kodenya bila ingin mengembangkan lebih jauh.

Angka **terukur** berasal dari laptop pengembang (Windows 11 / Linux Mint 22.3, Intel i5-13450HX, RAM 16 GB, RTX 4050 Laptop 6 GB). Angka **perkiraan** belum diukur; laporan dari komputer lain sangat membantu (lihat [Melaporkan hasil](#melaporkan-hasil)).

## 1. Pengaturan user: `data/settings.yaml`

Jangan mengubah `config.py` untuk pilihan pribadi: file itu ditimpa saat Perbarui (MikuVision Setup) dan bisa bentrok saat `git pull`. Pakai file pengaturan user:

1. Salin [`settings.example.yaml`](../settings.example.yaml) ke `data/settings.yaml` di folder aplikasi.
   - Lewat Setup: `%LOCALAPPDATA%\Programs\MikuVision\data\settings.yaml` (Windows) atau `~/.local/share/mikuvision/app/data/settings.yaml` (Linux).
   - Lewat git: `data/settings.yaml` di folder repo.
2. Hapus tanda `#` di depan baris yang ingin diubah, lalu ganti nilainya. Contoh model lebih besar:
   ```yaml
   OLLAMA_MODEL: qwen3:8b
   OLLAMA_THINK: false
   ```
3. Bila mengganti model Ollama: jalankan **Setup → Perbaiki** (atau `install.bat` / `./install.sh`) supaya modelnya diunduh. Installer membaca `OLLAMA_MODEL` dan `VISION_MODEL` dari file ini.
4. Buka ulang MikuVision. Konsol mencetak `[Config] Pengaturan user dari settings.yaml: …`; kunci yang salah tipe atau tidak dikenal dilewati dengan alasannya.

`data/` tidak pernah ditimpa oleh Perbarui dan diabaikan git, jadi pengaturan Anda tetap ada. Daftar lengkap kunci dan nilai bawaannya ada di `settings.example.yaml`.

## 2. Otak Miku (LLM)

Syarat model:
- tersedia di [Ollama](https://ollama.com/library) dan **mendukung tool calling** (semua aksi Miku adalah tool);
- cukup baik berbahasa Indonesia dan/atau Jepang.

Prompt sistem, contoh, dan batas konteks disetel untuk `qwen3:4b-instruct`. Model lain bisa bekerja, tetapi ukur dulu (bagian [Mengukur](#mengukur-model-baru)).

| Model | Unduhan | Ukuran saat dimuat (`ollama ps`, konteks 8192) | Hasil di laptop uji (RTX 4050 6 GB) |
|---|---|---|---|
| `qwen3:4b-instruct` (bawaan) | 2,5 GB | 3,9 GB terukur, 100% GPU | regresi 45/50, median 3,0 s per giliran¹ |
| `qwen3:8b` (isi `OLLAMA_THINK: false`) | 5,2 GB | 6,6 GB terukur, **37% di CPU** | regresi 40/50, median 4,3 s per giliran¹ |
| `qwen3:4b` | 2,5 GB | ±3,9 GB | 30/30, tetapi berpikir dulu (median 11,5 s)² |
| `granite4.2:3b` | 2,2 GB | ±3,6 GB | 25/30; bahasa Indonesia tidak resmi² |
| `qwen3:14b` (isi `OLLAMA_THINK: false`) | 9,3 GB | ±10,7 GB perkiraan | belum diuji; butuh GPU 12 GB+ |
| `llama3.1:8b` | 4,9 GB | ±6,3 GB perkiraan | belum diuji |

Ukuran unduhan dari registry Ollama. Perkiraan = ukuran unduhan + ±1,4 GB (selisih yang terukur pada `qwen3:4b-instruct` dan `qwen3:8b`).

¹ `bench_skills.py` mode regresi: 10 perintah Jepang/Indonesia × 5, latensi satu giliran penuh termasuk balasan (diukur 1 November 2026). ² Benchmark awal dengan set perintah lain (angkanya sama dengan README).

**Lebih besar tidak selalu lebih baik di sini.** Miku juga memuat Whisper dan RVC (±1,7 GB bersama) di GPU yang sama. Bila LLM tidak muat penuh di VRAM, Ollama menaruh sebagian layer di CPU dan balasan melambat. Contoh terukur: di GPU 6 GB, `qwen3:8b` tidak muat (37% layer di CPU), sehingga lebih lambat *dan* lebih sering meleset dibanding bawaan. Cek dengan `ollama ps`: kolom PROCESSOR harus `100% GPU`.

Panduan kasar per VRAM (semua fitur menyala; LLM + Whisper/RVC ±1,7 GB):

| VRAM GPU NVIDIA | LLM yang disarankan |
|---|---|
| 6 GB | `qwen3:4b-instruct` (bawaan); `qwen3:8b` terbukti tidak muat |
| 8 GB | `qwen3:4b-instruct`; `qwen3:8b` kemungkinan masih sebagian di CPU (6,6 + 1,7 GB) |
| 12 GB | `qwen3:8b` (perkiraan) |
| 16 GB+ | `qwen3:14b` (perkiraan) |
| Tanpa GPU | `qwen3:4b-instruct` di CPU (lambat; belum diukur) |

Kunci lain: `OLLAMA_NUM_CTX` (konteks; lebih besar = lebih banyak VRAM), `OLLAMA_THINK` (`false` untuk model hybrid seperti `qwen3:8b`; `null` = tidak dikirim), `OLLAMA_KEEP_ALIVE` (`-1` = model ditahan di VRAM selama Miku jalan), `OLLAMA_BASE_URL` (Ollama di komputer lain di jaringan Anda).

## 3. Membaca layar (model visi)

`VISION_MODEL` dimuat hanya saat Anda bertanya tentang layar; LLM dilepas dulu lalu dimuat lagi. Pilihan: `qwen3-vl:2b-instruct` (1,9 GB), `qwen3-vl:4b-instruct` (3,3 GB, bawaan), `qwen3-vl:8b-instruct` (6,2 GB). Unduh dengan Setup (komponen "Membaca layar") atau `install.bat -WithVision` / `./install.sh --with-vision` setelah mengganti `VISION_MODEL`.

## 4. Pendengaran (Whisper)

`WHISPER_MODEL`: `tiny`, `base`, `small`, `medium`, `large-v3`, `large-v3-turbo` (bawaan), atau path folder model CTranslate2. Diunduh otomatis dari Hugging Face saat pertama dipakai.

| Model | Unduhan (perkiraan) | Catatan |
|---|---|---|
| `large-v3-turbo` (bawaan) | ±1,6 GB | 0,53–0,58 s per klip 3,3 s di RTX 4050 (terukur); STT Indonesia 28/28, Jepang 18/20 |
| `medium` | ±1,5 GB | lebih lambat dari turbo di GPU |
| `small` | ±0,5 GB | pilihan untuk CPU; akurasi lebih rendah |

Tanpa GPU NVIDIA, isi `WHISPER_DEVICE: cpu` dan pertimbangkan `small`. `WHISPER_LANGUAGES` membatasi deteksi bahasa (bawaan `[ja, id]`; tambahkan `en` untuk bahasa Inggris).

## 5. Suara (MeloTTS + RVC)

- **MeloTTS** berjalan di CPU dan membuat suara dasar Jepang. Mengganti mesin TTS berarti mengubah kode (`core/voice_output.py`).
- **RVC** mengubah suara itu menjadi suara karakter, di GPU. Model RVC v2 apa pun bisa dipakai: `RVC_MODEL_PATH` (`.pth`) dan `RVC_INDEX_PATH` (`.index`), path relatif dihitung dari folder aplikasi. `RVC_PITCH` menaikkan nada (semitone), `RVC_ENABLED: false` mematikannya.
- Di Windows RVC butuh compiler C++ (Visual Studio Build Tools); MikuVision Setup memasangnya bila RVC dicentang.
- Repo tidak menyertakan atau menunjuk ke model suara tertentu; ikuti lisensi pembuat model (README, "Lisensi & kredit").

## 6. Kebutuhan perangkat per komponen

| Komponen | Disk | VRAM / RAM | Terukur di laptop uji |
|---|---|---|---|
| Aplikasi + PyTorch CUDA | ±8,8 GB | - | instalasi dari nol 9,5–10 menit |
| LLM `qwen3:4b-instruct` | 2,5 GB | 3,6–3,9 GB VRAM | 59 token/s |
| Whisper `large-v3-turbo` + MeloTTS | ±1,8 GB | Whisper + RVC ±1,7 GB VRAM; MeloTTS di CPU | 0,5 s per ucapan 3 s |
| RVC (opsional) | ±0,8 GB + model 0,1–0,6 GB | (lihat baris Whisper); dipotong per 6 s | 0,7–1,4 s per kalimat |
| Membaca layar (opsional) | 3,3 GB | dimuat bergantian dengan LLM | ±10–15 s per pertanyaan |
| **Semua dimuat** | ±16 GB (+3,3 GB membaca layar) | **5,5–5,9 GB dari 6 GB** | proses MikuVision ±3,4 GB RAM |

Minimum yang sudah terbukti: **GPU NVIDIA 6 GB, RAM 16 GB**, Windows 10/11 64-bit atau Linux x86_64 (X11). Tanpa GPU NVIDIA MikuVision tetap jalan dengan PyTorch CPU, tetapi belum diukur.

## Mengukur model baru

1. `python miku.py --test`: model termuat tanpa error.
2. `ollama ps` saat Miku jalan: `100% GPU`.
3. `python experiments/skills/bench_skills.py 5 regression`: 10 perintah umum lewat LLM tanpa menjalankan aksinya (kontrol sistem palsu); hasilnya jumlah tool call yang tepat (`correct`) dan median latensi per giliran. Bandingkan dengan model bawaan di komputer yang sama.
4. Coba percakapan nyata dengan `python miku.py --text`.

## Melaporkan hasil

Buka issue di GitHub dengan: GPU dan VRAM, RAM, OS, model yang dipakai, hasil `bench_skills.py`, dan isi `ollama ps`. Hasil yang dilaporkan akan ditambahkan ke tabel di atas.

## 7. Untuk pengembang: peta kode

| Bagian | File |
|---|---|
| Nilai bawaan dan pengaturan user | `config.py`, `settings.example.yaml` |
| LLM, prompt, pemanggilan tool | `core/ai_brain.py`, `core/conversation.py` |
| Daftar tool (aksi Miku) | `core/tools.py` (registry), `core/system_control.py`, `core/macro_tools.py`, `core/desktop/` |
| Skill dan routine | `core/skills.py`, `core/user_skills.py`, `skills/`, `routines.example.yaml` |
| Mendengar, "Oke Miku" | `core/voice_input.py`, `core/stt_text.py`, `core/wake.py`, `core/hotkey.py` |
| Bicara | `core/voice_output.py` (MeloTTS), `core/voice_converter.py` (RVC) |
| Membaca layar | `core/vision/` |
| GUI dan maskot | `gui.py`, `core/avatar_window.py`, `core/avatar.py` |
| Installer | `install.ps1`, `install.sh`, `miku_setup/` (MikuVision Setup) |

Tambahkan test di `tests/` untuk setiap perubahan; `pytest` berjalan tanpa GPU, mikrofon, atau Ollama.
