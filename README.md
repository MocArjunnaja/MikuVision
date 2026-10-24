# MikuWin V11

Asisten desktop Windows berwujud **Hatsune Miku**. Miku mendengarkan suara Anda, berpikir dengan LLM lokal (Ollama), menjalankan aksi di komputer (volume, membuka aplikasi/folder/situs, YouTube, Word/PowerPoint, WhatsApp/Telegram), lalu menjawab dengan suara dan maskot beranimasi. Semua berjalan lokal di komputer Anda.

## Alur kerja

```
Mic → WebRTC VAD + noise reduction → Faster-Whisper (STT)
    → Ollama LLM + tool calling → eksekusi tool (dengan konfirmasi untuk aksi berisiko)
    → MeloTTS (JP) → [RVC suara Miku, opsional] → speaker + maskot sprite
```

## Kebutuhan

| | Minimum | Teruji |
|---|---|---|
| OS | Windows 10/11 | Windows 11 |
| Python | 3.10 | 3.10 (conda) |
| GPU | Opsional (CPU bisa, tapi lambat) | NVIDIA RTX 4050 6 GB |
| Disk | ±8 GB (model Whisper, MeloTTS, LLM) | |
| Lainnya | [Git](https://git-scm.com/download/win), [Ollama](https://ollama.com/download), mikrofon | |

## Instalasi

1. **Clone repo**
   ```bash
   git clone https://github.com/MocArjunnaja/MikuWin_V11_Stable.git
   ```
   ```bash
   cd MikuWin_V11_Stable
   ```

2. **Buat environment Python 3.10** (contoh dengan Miniconda)
   ```bash
   conda create -n miku python=3.10 -y
   ```
   ```bash
   conda activate miku
   ```

3. **(Khusus GPU NVIDIA) install PyTorch versi CUDA dulu.** Ambil perintah yang sesuai dari https://pytorch.org/get-started/locally/. Contoh untuk CUDA 12.8:
   ```bash
   pip install torch --index-url https://download.pytorch.org/whl/cu128
   ```
   Tanpa GPU NVIDIA, lewati langkah ini; torch versi CPU akan terpasang di langkah berikutnya.

4. **Install dependency**
   ```bash
   pip install -r requirements.txt
   ```
   ```bash
   python -m unidic download
   ```
   Perintah kedua mengunduh kamus bahasa Jepang yang dibutuhkan MeloTTS (sekali saja).

5. **Siapkan LLM di Ollama**
   ```bash
   ollama pull qwen3:4b-instruct
   ```
   Model lain bisa dipakai dengan mengubah `OLLAMA_MODEL` di `config.py` (lihat [Pilihan model](#pilihan-model)).

6. **Cek instalasi**
   ```bash
   python miku.py --test
   ```
   Harus berakhir dengan `[Test mode - Initialization successful!]`. Jalankan pertama kali butuh internet: Whisper `large-v3-turbo` (±1,6 GB) dan model MeloTTS diunduh otomatis.

## Menjalankan

| Mode | Perintah | Keterangan |
|---|---|---|
| Suara + maskot | `python miku.py` | Seret (drag) maskot Miku di layar untuk mulai bicara |
| Teks (terminal) | `python miku.py --text` | Paling mudah untuk mencoba pertama kali |
| GUI | `python gui.py` | Jendela chat + tombol "Hold to Speak" |
| Lanjutkan sesi | `python miku.py --text --resume` | Memuat sesi terakhir (atau `--resume <SESSION_ID>`); di GUI: tombol **↺ Sesi lalu** |

Contoh perintah: "buka notepad", "kecilkan volume ke 30", "carikan lagu Yorushika di YouTube", "buka folder Downloads".

Aksi berisiko (kirim WhatsApp/Telegram, menutup aplikasi) **selalu meminta konfirmasi** dulu: `y/n` di mode teks, jawaban suara "ya/はい" di mode suara, atau dialog Yes/No di GUI.

## Routine & perintah cepat

**Routine** menjalankan beberapa aksi dengan satu perintah. Contoh bawaan ada di `routines.example.yaml` ("mode belajar", "mode istirahat"). Untuk membuat routine sendiri, salin file itu ke `data/routines.yaml` lalu ubah isinya. Jalankan dengan ucapan ("jalankan mode belajar", "勉強モードにして") atau `/routine mode belajar`. Langkah berisiko tetap meminta konfirmasi.

**Slash command** (mode teks dan GUI, tanpa LLM):

| Perintah | Fungsi |
|---|---|
| `/help` | Daftar perintah |
| `/memory`, `/forget <key>` | Lihat / hapus memori jangka panjang |
| `/routines`, `/routine <nama>` | Daftar / jalankan routine |
| `/skills` | Kelompok kemampuan Miku |
| `/sessions`, `/resume [id]` | Sesi tersimpan / lanjutkan sesi |
| `/usage` | Pemakaian token sesi ini |
| `/clear` | Hapus riwayat sesi ini |

**Skill on-demand:** 25 tool dikelompokkan menjadi 9 skill (`core/skills.py`). Hanya skill yang cocok dengan permintaan yang dikirim ke LLM, sehingga prompt turun dari ±3.400 ke ±1.550 token tanpa menurunkan akurasi. Matikan dengan `SKILL_ROUTING = False` di `config.py`.

## Memori & pemakaian token

- **Konteks:** setiap balasan menampilkan pemakaian konteks LLM yang diambil langsung dari Ollama (`prompt_eval_count`), misalnya `konteks 3.2k / 8.2k token`. Di GUI angka ini ada di bawah status.
- **Memori jangka panjang:** fakta yang disimpan dengan tool `remember` disisipkan ke system prompt (maksimal `MEMORY_PROMPT_MAX_FACTS`, default 15). Miku tetap ingat setelah aplikasi ditutup.
- **Agent loop:** tool call dan hasilnya disimpan dalam format resmi Ollama (`tool_calls` + pesan `role: tool`), sehingga Miku tahu apa yang sudah dilakukannya di giliran sebelumnya.

## Pilihan model

Hasil benchmark di RTX 4050 6 GB: 10 perintah (JP/ID), 3–5 kali ulang, tool tidak dieksekusi.

| `OLLAMA_MODEL` | Tool call tepat | Latensi median | Catatan |
|---|---|---|---|
| `qwen3:4b-instruct` (default) | 50/50 | 0,9 s | Paling responsif untuk asisten suara; di tengah percakapan 8/8 |
| `qwen3:4b` | 30/30 | 11,5 s | Varian Thinking-2507: paling akurat, tapi berpikir dulu sebelum menjawab |
| `granite4.2:3b` | 25/30 | 4,6 s | IBM Granite; bahasa Indonesia tidak didukung resmi |

Model kecil kadang hanya *berjanji* melakukan aksi tanpa memanggil tool; MikuWin otomatis meminta ulang (maksimal 2 kali) bila user meminta aksi tapi tidak ada tool yang dipanggil. Angka `qwen3:4b-instruct` sudah termasuk mekanisme ini; dua model lain diukur sebelum mekanisme ini ditambahkan.

Biarkan `OLLAMA_THINK = None` di `config.py`. Mengirim `think=False` ke `qwen3:4b` justru membuat penalarannya ikut terucap.

## Suara Miku (RVC, opsional)

Tanpa RVC, Miku tetap bicara memakai suara dasar MeloTTS Jepang. Untuk timbre khas Miku, siapkan model RVC v2 milik Anda sendiri (tidak disertakan di repo):

1. Simpan file bobot ke `models/miku_default_rvc/weights/miku_default_rvc.pth`
2. Simpan file index ke `models/miku_default_rvc/logs/miku_default_rvc/added_IVF4457_Flat_nprobe_1_miku_default_rvc_v2.index` (atau ubah `index_path` di `config.py` sesuai nama file Anda)
3. Install `rvc-python` di environment yang sama (dependency-nya sering bentrok; lihat dokumentasi rvc-python).

File `.pth` adalah file pickle yang bisa menjalankan kode saat dimuat. Hanya pakai model dari sumber yang Anda percayai.

## Data & privasi

- Riwayat percakapan tersimpan di `data/conversations/` (tidak ikut ke git).
- Log per giliran (input, tool + hasil, token, latensi) di `data/logs/turns_YYYYMMDD.jsonl`.
- Memori jangka panjang di `data/long_term_memory.json`. Isi lewat ucapan seperti "ingat ya, aku kuliah di ITS" atau "誕生日を覚えておいて", hapus dengan "lupakan …" / "…を忘れて".
- Dokumen buatan Miku tersimpan di `Desktop/Miku_Documents/` milik user yang sedang login.
- Fitur WhatsApp memakai `data/contacts_db.json` berformat `{"nama": "62812xxxx"}` (buat sendiri; tidak ikut ke git).
- Rekaman mic tidak disimpan. Untuk debugging audio, set `DEBUG_DUMP_AUDIO = True` di `config.py`.

## Pengembangan

```bash
pip install pytest
```
```bash
pytest
```

Test tidak membutuhkan mikrofon, GPU, maupun Ollama.

## Troubleshooting

| Gejala | Solusi |
|---|---|
| `Model 'qwen3:4b-instruct' tidak ditemukan` | Jalankan `ollama pull qwen3:4b-instruct`, pastikan aplikasi Ollama sedang berjalan |
| `Gagal connect ke Ollama` | Buka aplikasi Ollama (ikon di system tray) |
| Error MeloTTS / `unidic` | Jalankan `python -m unidic download` |
| `webrtcvad` gagal di-install | Pastikan memakai paket `webrtcvad-wheels` dari `requirements.txt` |
| Whisper sangat lambat | Tanpa GPU, ganti `WHISPER_MODEL` di `config.py` ke `small` |
| `RVC unavailable` | Normal jika model RVC tidak dipasang |

## Kredit

Hatsune Miku © Crypton Future Media, INC. www.piapro.net. Proyek non-komersial.
