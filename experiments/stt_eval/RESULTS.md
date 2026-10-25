# Uji STT: pipeline lama vs baru

Diukur 25 Okt 2026 (RTX 4050 Laptop 6 GB, faster-whisper 1.2.1, `large-v3-turbo` int8_float16).

## Set uji

`make_set.py` membuat 54 klip dengan edge-tts (perlu edge-tts ≥ 7.3.1; 7.2.8 ditolak server dengan 403):

- 14 perintah Indonesia dan 10 perintah Jepang, suara pria/wanita bergantian.
- Tiap frasa ada dua versi: **bersih** dan **mic laptop** (derau pink SNR 12 dB + dengung 120 Hz, volume puncak 0,08).
- 6 klip derau tanpa ucapan (harus menghasilkan teks kosong).

`run_eval.py <folder_set> <label>` dijalankan dari root repo. Kode lama diukur dari worktree `main` sebelum perubahan, lewat `MikuCLI._transcribe_best_effort` seperti di aplikasi.

## Hasil (jumlah tepat / jumlah klip, CER rata-rata)

| | Lama | Baru | Baru, tanpa prompt | Baru + noisereduce |
|---|---|---|---|---|
| Indonesia bersih | 10/14 (0,156) | **14/14 (0)** | 14/14 (0) | 14/14 (0) |
| Indonesia mic laptop | 8/14 (0,368) | **14/14 (0)** | 14/14 (0) | 14/14 (0) |
| Jepang bersih | 9/10 (0,008) | 9/10 (0,008) | 9/10 (0,008) | 9/10 (0,008) |
| Jepang mic laptop | 8/10 (0,036) | **9/10 (0,008)** | 9/10 (0,008) | 8/10 (0,036) |
| Derau → teks palsu | 0/6 | 0/6 | 0/6 | 0/6 |
| Latensi median | 0,68 s | **0,54 s** | 0,54 s | 0,59 s |

Satu-satunya salah Jepang yang tersisa adalah homofon 文書 → 文章.

## Kegagalan pipeline lama

| Ucapan | Keluaran lama | Penyebab |
|---|---|---|
| Kecilkan volumenya sedikit / Matikan suaranya | 「音量を下げて、音量を下げて、…」 sampai batas token | Pass bahasa Jepang dipaksa pada ucapan Indonesia; isi prompt Jepang bocor dan berulang; skor heuristik memilihnya karena berisi kata 音量 |
| Buat dokumen Word baru (mic laptop) | 「作品の作品の作品の…」 | Sama |
| Jangan, batalkan (mic laptop) | 「次の動画でお会いしましょう。」 | Halusinasi khas YouTube, tidak tersaring |
| Atur volume ke 30 persen | "Atur volume**e** ke 30%" | Koreksi `volum → volume` mengganti substring |
| Tolong buka YouTube … | "buka Youtube …" | Koreksi `tolong buka → buka` membuang kata |
| Atur volume … (mic laptop) | "" | Hasil noise gating + soft-clip |

Rekaman mic asli di `data/debug_audio/` (6 klip, tanpa label): kedua pipeline memberi teks yang sama, misalnya "Buka Microsoft Edge".

## Keputusan

- Bahasa dideteksi sekali, dibatasi ke `WHISPER_LANGUAGES` (Melayu/Jawa/Sunda dihitung sebagai Indonesia), lalu satu kali decoding. Dua bahasa hanya didecode bila deteksi < 0,8, dan yang dipilih adalah yang log-probability-nya lebih baik.
- Segmen dengan `compression_ratio > 2,4` atau tanda tanpa-ucapan dibuang; frasa halusinasi dan pengulangan dibersihkan (`core/stt_text.py`).
- `noisereduce` dimatikan (`STT_DENOISE = False`): tidak membantu, malah mengubah 「ミュート」 menjadi 「ユート」 dan menambah 50 ms.
- Prompt kosakata tetap dipakai: akurasinya sama, tapi ejaan nama aplikasi lebih konsisten ("Notepad", "YouTube").

## Keterbatasan

Suara edge-tts lebih jernih dari suara manusia di mic laptop, jadi angka 14/14 belum berarti sempurna di dunia nyata. Untuk mengumpulkan kasus gagal yang sebenarnya, nyalakan `DEBUG_DUMP_AUDIO = True` di `config.py` sementara waktu. Rekaman tersimpan di `data/debug_audio/`, yang tidak ikut git.
