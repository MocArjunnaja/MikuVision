# T2 "Oke Miku": Hasil Uji

Diukur 1 Nov 2026 di laptop pengembang: RTX 4050 Laptop 6 GB, Linux Mint 22.3, faster-whisper `large-v3-turbo` int8_float16, webrtcvad. Kode: [`core/wake.py`](../../core/wake.py). Rencana: [`docs/PLAN_VISION_AGENT.md`](../../docs/PLAN_VISION_AGENT.md) bagian T2.

## Set uji

`make_set.py` (edge-tts ≥ 7.3.1, tidak ada di venv aplikasi; lihat docstring untuk perintah `uv run`) membuat:

| Isi | Jumlah |
|---|---|
| Wake phrase (10 ucapan × 2 suara × 3 kondisi): "Oke Miku.", "Oke Miku, buka Notepad.", "Okay Miku, putar lagu di YouTube.", 「オッケー、ミク、メモ帳を開いて。」, "OK Miku.", dan lainnya; 4 di antaranya dengan perintah | 60 klip |
| Kalimat biasa (26 ucapan × 2 suara × 2 kondisi), termasuk yang mirip: "Oke, nanti saja ya", "Miku lagi nyanyi lagu baru", "Aku mikir dulu deh", 「オッケー、わかった」, 「初音ミクが大好きです」, "OK, see you tomorrow", dan perintah tanpa wake phrase | 104 klip, 7,7 menit bila disambung |
| Derau ruangan tanpa ucapan | 5 menit |

Kondisi: **bersih**; **mic laptop** (derau pink SNR 12 dB + dengung 120 Hz, puncak 0,08, sama dengan `experiments/stt_eval`); **sangat berisik** (SNR 5 dB, hanya untuk wake phrase).

`run_eval.py` memasukkan audio ke `WakeListener` per potongan 100 ms, persis seperti dari mikrofon, dengan Whisper dan webrtcvad sungguhan. Tiap klip wake phrase harus memicu **tepat sekali**, dan perintahnya harus memuat kata kunci (misalnya "notepad").

## Hasil

| Cek wake phrase | Bersih | Mic laptop | Sangat berisik | Perintah ikut terbawa | Whisper per klip | Waktu Whisper selama 7,7 menit obrolan |
|---|---|---|---|---|---|---|
| Deteksi bahasa ja/id (seperti transkripsi biasa) | 20/20 | 20/20 | 17/20 | 26/30 | 0,76 s | 118 s (±26%) |
| Bahasa tetap `ja` | 20/20 | 18/20 | 15/20 | 24/30 | 0,82 s | 125 s |
| Bahasa tetap `id`, sebelum ejaan tambahan | 17/20 | 20/20 | 16/20 | 26/30 | 0,27 s | 68 s |
| **Bahasa tetap `id`** + ejaan tambahan, VAD 3 (dipakai) | **20/20** | **20/20** | 16/20 | 26/30 | **0,26 s** | **66 s (±14%)** |

Di semua varian:
- **0 pemicu palsu**: 104 klip kalimat biasa satu per satu, dan 7,7 menit obrolan yang disambung.
- **Derau ruangan 5 menit: 0 segmen, Whisper tidak pernah jalan.** GPU diam saat tidak ada yang bicara.

Temuan:
- Whisper tidak selalu menulis "Miku". Uji ini menghasilkan "Oke, migu", "Oke niku", "Oke, mitu", "Oke, migo", dan "OK, Miuku"; pola di `core/wake.py` menerima `[mn]iu?(kk|k|g|t)[uo]`. Kata yang mirip tapi berbeda tetap tidak cocok ("mikir", "minggu", "Mikuni").
- Cek dengan satu bahasa tetap (`id`, beam 1) tiga kali lebih cepat daripada deteksi bahasa, dengan akurasi sama. Wake phrase hampir sama bunyinya di semua bahasa; 「オッケー、ミク」 dengan bahasa `id` ditulis "Oke, Miku". Perintah sesudahnya ditranskripsi ulang dengan deteksi bahasa, sehingga 「メモ帳を開いて」 tetap Jepang.
- Kegagalan di kondisi sangat berisik: wake phrase tidak terdengar sama sekali ("Buka Note, Pak", "Okay, mute"). Itu batas Whisper pada SNR 5 dB, bukan pola frasa.
- VAD mode 3 sama akuratnya dengan mode 2 di set ini, tetapi jauh lebih tahan derau mikrofon (bagian berikut).

## Mikrofon sungguhan

`live_idle.py`: pendengar jalan di mikrofon internal laptop, di ruangan nyata, tanpa ada yang mengucapkan "Oke Miku". Audio tidak disimpan.

| VAD | Durasi | Segmen | Panggilan Whisper (total waktu) | Pemicu | CPU proses | GPU |
|---|---|---|---|---|---|---|
| mode 2 | 5 menit | 20 | 120 (2,5 s) | 0 | 3,8% | median 0% |
| mode 3 | 3 menit | 9 | 56 (1,2 s) | 0 | 3,0% | median 0% |

- Volume mikrofon internal laptop ini 100%, padahal base volume-nya 10% (−60 dB). Derau ruangan saja sudah RMS ±0,6, hampir penuh. Dengan sinyal seperti itu, webrtcvad mode 2 menganggap 100% frame sebagai ucapan, mode 3 hanya 5%.
- Panggilan Whisper tetap murah (±0,02 s), karena VAD internal Whisper langsung membuang derau. Jadi beban nyatanya kecil, tetapi "Oke Miku" juga sulit terdengar. Solusinya volume input diturunkan ke sekitar base volume di pengaturan Suara; ini pengaturan sistem, jadi tidak diubah oleh MikuVision.
- **Belum diuji:** "Oke Miku" yang diucapkan manusia ke mikrofon, musik yang sedang diputar, dan Windows.
