# Fase 0 Agent Visi: Hasil Spike & Keputusan Model

Diukur 25 Okt 2026 di laptop pengembang (RTX 4050 Laptop 6 GB, Windows 11, Ollama 0.40.10).
Rencana lengkap: [`docs/PLAN_VISION_AGENT.md`](../../docs/PLAN_VISION_AGENT.md).

## Keputusan

**Opsi B: auto-switch per tugas, dengan `qwen3-vl:4b-instruct` (bukan 2b) sebagai model visi.**

- Chat dan tool biasa tetap memakai `qwen3:4b-instruct`. qwen3-vl:4b turun di tool calling MikuWin (42/50 vs 50/50, multi-turn 4/8 vs 8/8), jadi tidak layak menjadi otak tunggal (opsi A ditolak).
- Model hanya ditukar saat **masuk dan keluar** sesi agent visi, bukan per langkah. Biayanya ±7 s saat masuk dan ±4 s saat kembali.
- Di dalam sesi visi, mode bawaan adalah **daftar elemen UIA (teks)**. Gambar Set-of-Mark ditambahkan hanya kalau pohon UIA miskin (game, canvas, aplikasi tanpa aksesibilitas).
- `qwen3-vl:2b` tidak dipakai: lebih hemat 1,2 GB VRAM, tapi akurasi pemilihan elemen paling baik hanya 31/45.

## 1. Cakupan UI Automation

Skrip: `uia_spike.py`. Hanya jendela uji yang baru dibuka yang ditangkap lalu ditutup.

| Jendela | Elemen interaktif | Bernama | Waktu baca pohon |
|---|---|---|---|
| Kalkulator | 36 | 36 | 0,11 s |
| Settings (Bluetooth) | 35 | 34 | 0,25 s |
| Explorer (Documents) | 163 | 156 | 0,34 s |

UIA cepat (< 0,4 s), tanpa GPU, dan memberi kotak elemen yang persis. Ini menjadi persepsi utama.

## 2. Windows OCR (winrt)

Skrip: `ocr_spike.py`.

- Latensi 0,03–0,06 s per jendela, tanpa GPU.
- Bahasa OCR yang terpasang hanya en-GB, en-US, dan ar-SA. **OCR Jepang perlu paket bahasa Jepang Windows** (Settings → Time & language → Language → Japanese → Optical character recognition).
- OCR melengkapi UIA, bukan menggantikannya. Contoh: UIA menamai tombol "Seven", sedangkan OCR membaca "7".

## 3. Pemilihan elemen (Set-of-Mark)

Skrip: `vlm_spike.py`. 15 tujuan (Kalkulator dan Settings; bahasa Indonesia dan Jepang) × 3 percobaan. Model harus menjawab nomor elemen yang benar.

| Model | Mode | Akurasi | Median | VRAM |
|---|---|---|---|---|
| qwen3:4b-instruct | text | 39/45 | 0,16 s | 3,9 GB |
| **qwen3-vl:4b-instruct** | **text** | **44/45** | 0,22 s | 3,7 GB |
| qwen3-vl:4b-instruct | image | 30/45 | 0,31 s | 3,7 GB |
| qwen3-vl:4b-instruct | both | 43/45 | 0,33 s | 3,7 GB |
| qwen3-vl:2b-instruct | text | 21/45 | 0,08 s | 2,5 GB |
| qwen3-vl:2b-instruct | image | 15/45 | 0,18 s | 2,5 GB |
| qwen3-vl:2b-instruct | both | 31/45 | 0,20 s | 2,5 GB |

Temuan:
- Daftar teks dari UIA lebih andal daripada gambar saja. qwen3-vl:4b paling bagus walaupun hanya diberi teks.
- Satu screenshot ±1.000 token visual.
- Label nomor Set-of-Mark saat ini terlalu kecil; model membaca "29" sebagai "5". Fase 1 perlu label lebih besar dengan kontras tinggi.
- qwen3-vl tidak lebih berat dari qwen3:4b-instruct (3,7 vs 3,9 GB pada `num_ctx` 8192).

## 4. Tool calling MikuWin pada qwen3-vl:4b-instruct

Skrip benchmark sama dengan PR #8/#10 (10 perintah JP/ID × 5, routing skill ON, tool tidak dieksekusi).

| Model | Akurasi tool | Bocor | Balasan JP | Median | p90 | Multi-turn |
|---|---|---|---|---|---|---|
| qwen3:4b-instruct | 50/50 | 0 | 50/50 | 1,0 s | 1,5 s | 8/8 |
| qwen3-vl:4b-instruct | 42/50 | 0 | 49/50 | 1,6 s | 6,7 s | 4/8 |

Kegagalan qwen3-vl:4b paling banyak berupa klaim aksi palsu tanpa memanggil tool, misalnya "音量を30に設定しました！" (5/5 gagal pada "音量を30にして") dan menjawab volume "50%" tanpa mengeceknya. Satu percobaan berhenti dengan `token repeat limit reached`.

## 5. Biaya tukar model (cold load dari D:)

| Model | Waktu load |
|---|---|
| qwen3:4b-instruct | 3,6–4,3 s |
| qwen3-vl:4b-instruct | 6,5–7,3 s |
| qwen3-vl:2b-instruct | 4,3–4,6 s |

Dua model 4B tidak muat bersamaan di 6 GB (3,9 + 3,7 GB), jadi model teks dibongkar saat sesi visi dimulai.

## 6. Bug yang ditemukan saat spike

- Parser jawaban VLM awalnya hanya menerima angka tanpa kutip. Model visi sering menulis `{"element": "20"}`, sehingga akurasinya tampak jauh lebih buruk. Sudah diperbaiki (`"?(\d+)`) dan semua angka di atas diukur ulang.
- Versi awal `uia_spike.py` mengambil jendela Explorer pertama yang ditemukan, termasuk jendela milik user. Sekarang hanya jendela yang **baru muncul** setelah perintah dijalankan yang disentuh.

## Langkah berikutnya (Fase 1)

1. `core/vision/` dengan UIA sebagai persepsi utama, OCR sebagai pelengkap, gambar hanya sebagai cadangan.
2. Pengalih model di `AIBrain` (`set_model` sudah ada): masuk sesi visi → qwen3-vl:4b, selesai → qwen3:4b-instruct.
3. Label Set-of-Mark lebih besar.
4. Tool hanya-baca dulu: `describe_screen()` dan `find_on_screen(query)`.
