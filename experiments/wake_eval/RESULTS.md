# T2 "Oke Miku": Hasil Uji

Diukur 1 Nov 2026 di laptop pengembang: RTX 4050 Laptop 6 GB, Linux Mint 22.3, faster-whisper 1.2.1 `large-v3-turbo` int8_float16, webrtcvad. Kode: [`core/wake.py`](../../core/wake.py). Rencana: [`docs/PLAN_VISION_AGENT.md`](../../docs/PLAN_VISION_AGENT.md) bagian T2.

## Ringkasan

| Uji | Hasil |
|---|---|
| Suara sungguhan (user, mic laptop 20%), live, putaran terakhir | "Oke Miku" **10/10**, perintah yang ikut terucap benar semua; kalimat biasa 5/5 tidak memicu |
| Rekaman putaran yang sama, diputar ulang 4× | **9/10** terdeteksi, 8/10 dengan perintah benar (Whisper berbeda dari live, lihat bawah) |
| Suara sintetis (edge-tts) | 20/20 bersih, 20/20 mic laptop, 19/20 sangat berisik |
| Pemicu palsu | **0**: 128 klip kalimat biasa termasuk jebakan ("Oke, menurut aku…", "Oke, minggu ini…"), 9,7 menit obrolan sambung, 20 kalimat biasa dari suara user, **20 menit musik/video dari speaker** |
| Tidak ada yang bicara | Whisper tidak jalan (5 menit derau sintetis); mic sungguhan: CPU proses 3–4%, GPU median 0% |

Pengaturan yang dipakai: VAD webrtcvad mode 3 dengan pre-roll 0,8 s; cek wake dengan Whisper bahasa tetap `id`, beam 1, prompt `"Oke Miku."`, dan cap waktu kata; perintah dipotong sesudah wake phrase lalu ditranskripsi dengan deteksi bahasa; perintah ditahan 0,6 s untuk lanjutan sesudah jeda.

## Set uji sintetis

`make_set.py` (edge-tts ≥ 7.3.1, tidak ada di venv aplikasi; lihat docstring untuk perintah `uv run`) membuat:

| Isi | Jumlah |
|---|---|
| Wake phrase (10 ucapan × 2 suara × 3 kondisi): "Oke Miku.", "Oke Miku, buka Notepad.", "Okay Miku, putar lagu di YouTube.", 「オッケー、ミク、メモ帳を開いて。」, "OK Miku.", dan lainnya; 5 di antaranya dengan perintah | 60 klip |
| Kalimat biasa (32 ucapan × 2 suara × 2 kondisi), termasuk yang mirip: "Oke, nanti saja ya", "Miku lagi nyanyi lagu baru", 「オッケー、わかった」, 「初音ミクが大好きです」, "OK, see you tomorrow", perintah tanpa wake phrase, dan 6 jebakan dari salah dengar suara sungguhan ("Oke, menurut aku itu sudah bagus", "Oke, minggu ini aku sibuk sekali", "Oke, mie ayamnya dua ya", …) | 128 klip, 9,7 menit bila disambung |
| Derau ruangan tanpa ucapan | 5 menit |

Kondisi: **bersih**; **mic laptop** (derau pink SNR 12 dB + dengung 120 Hz, puncak 0,08, sama dengan `experiments/stt_eval`); **sangat berisik** (SNR 5 dB, hanya untuk wake phrase).

`run_eval.py` memasukkan audio ke `WakeListener` per potongan 100 ms, persis seperti dari mikrofon, dengan Whisper dan webrtcvad sungguhan. Tiap klip wake phrase harus memicu **tepat sekali**, dan perintahnya harus memuat kata kunci (misalnya "notepad").

| Cek wake phrase | Bersih | Mic laptop | Sangat berisik | Perintah benar | Whisper per klip | Waktu Whisper selama obrolan |
|---|---|---|---|---|---|---|
| Deteksi bahasa ja/id (seperti transkripsi biasa) | 20/20 | 20/20 | 17/20 | 26/30 | 0,76 s | 118 s / 7,7 menit (±26%) |
| Bahasa tetap `ja` | 20/20 | 18/20 | 15/20 | 24/30 | 0,82 s | 125 s / 7,7 menit |
| Bahasa tetap `id`, prompt kosakata | 17/20 | 20/20 | 16/20 | 26/30 | 0,27 s | 68 s / 7,7 menit |
| `id` + ejaan tambahan, VAD 3 | 20/20 | 20/20 | 16/20 | 26/30 | 0,26 s | 66 s / 7,7 menit |
| + pre-roll, tanpa prompt, tunggu lanjutan | 20/20 | 20/20 | 18/20 | 28/30 | 0,48 s | 57 s / 7,7 menit |
| **+ prompt "Oke Miku.", perintah dipotong** (dipakai; set dengan jebakan) | **20/20** | **20/20** | **19/20** | 27/30 | 0,49 s | 71 s / 9,7 menit (±12%) |

Semua varian: 0 pemicu palsu, dan derau ruangan 5 menit tidak pernah sampai ke Whisper.

Temuan:
- Cek dengan satu bahasa tetap (`id`, beam 1) tiga kali lebih cepat daripada deteksi bahasa, dengan akurasi sama: wake phrase hampir sama bunyinya di semua bahasa.
- Ejaan Whisper yang diterima pola `[ae]?[mn]iu?(kk|k|g|t)[uo]`: "migu", "niku", "mitu", "migo", "Miuku", "emigu", "amiku". Kata sungguhan yang mirip tetap tidak cocok: "mikir", "minggu", "Mikuni", "menurut", "emang".
- Kegagalan di kondisi sangat berisik umumnya karena perintahnya, bukan wake phrase: "Hoping you too" dari "open YouTube" pada SNR 5 dB.
- VAD mode 3 sama akuratnya dengan mode 2, tetapi jauh lebih tahan derau mikrofon (bagian berikut).

## Mikrofon sungguhan tanpa ucapan

`live_idle.py`: pendengar jalan di mikrofon internal laptop di ruangan nyata, tanpa ada yang mengucapkan "Oke Miku". Audio tidak disimpan.

| VAD | Durasi | Segmen | Panggilan Whisper (total waktu) | Pemicu | CPU proses | GPU |
|---|---|---|---|---|---|---|
| mode 2 | 5 menit | 20 | 120 (2,5 s) | 0 | 3,8% | median 0% |
| mode 3 | 3 menit | 9 | 56 (1,2 s) | 0 | 3,0% | median 0% |

Saat itu volume mikrofon internal 100%, sementara base volume-nya 10%. Mixer ALSA menunjukkan Capture +30 dB dan Internal Mic Boost +30 dB. Derau ruangan saja sudah RMS ±0,6, hampir penuh: webrtcvad mode 2 menganggap 100% frame sebagai ucapan, mode 3 hanya 5%. `WakeListener` kini memberi peringatan bila derau 3 detik pertama di atas RMS 0,05.

## Suara sungguhan

`live_guided.py` memberi 15 aba-aba di terminal; user mengucapkannya ke mikrofon internal laptop. Isinya 10 dengan "Oke Miku" (5 tanpa perintah, 4 dengan perintah, 1 dengan jeda 2 detik) dan 5 kalimat biasa yang mirip. Tidak ada aksi yang dijalankan. `--record` menyimpan audio tiap aba-aba (hanya putaran 6, atas permintaan user, di folder sementara di luar repo) untuk diputar ulang dengan `replay.py`.

| Putaran | Mic (derau RMS) | Kode | "Oke Miku" | Kalimat biasa tidak memicu |
|---|---|---|---|---|
| 1 | 30% (0,016) | `id` + ejaan tambahan, prompt kosakata | 5/10 | 5/5 |
| 2 | 30% (0,021) | + pre-roll, tanpa prompt, tunggu lanjutan | 2/8 (dihentikan user) | - |
| 3 | 30% (0,021) | sama | 2/10 | 5/5 |
| 4 | 20% (0,006) | + prompt "Oke Miku." | 9/10 | 5/5 |
| 6 (putaran 5 dibatalkan sebelum mulai) | 20% (0,007) | + perintah dipotong, ejaan ganda dibuang | **10/10**, semua perintah benar | 5/5 |

| Kegagalan | Yang ditulis Whisper | Perbaikan |
|---|---|---|
| Awal ucapan hilang | "Gimicu", "Lagi nyanyi" (dari "Miku lagi nyanyi"), "Buku itu penyanyi" | VAD mode 3 baru yakin setelah suku kata pertama: `pre_roll_ms` 800 (sebelumnya 0,3 s) |
| Prompt kosakata ikut ke cek | "Buka Google Chrome, Timo" | Cek wake memakai prompt sendiri `"Oke Miku."`, bukan `WHISPER_PROMPTS["id"]` |
| "Miku" ditulis sebagai kata Indonesia/Inggris | "Oke, minggu", "Oke, menurut", "Oke, me too", "Okay, make it" | Prompt `"Oke Miku."`: rekaman putaran 6 diputar ulang tanpa prompt 4/10, dengan prompt 7/10 (8/10 setelah ejaan tambahan) |
| Perintah hilang | cek "Oke, Miku, putar lagu di Youtube", transkripsi lengkap "Gameku, putar lagu…" → kosong | Bug di jalur jendela (ucapan > 2,5 s): perintah hasil cek kini dipakai sebagai cadangan |
| Perintah terpotong saat jeda | "kecilkan volume" dari "… ke tiga puluh" | Perintah ditahan 0,6 s; lanjutan digabung dan ditranskripsi ulang |
| Perintah ikut jadi Jepang | 「ブカ、Notepad」 dari "Oke Miku, buka Notepad" | Audio dipotong di akhir kata "Miku" (cap waktu kata Whisper), lalu perintah ditranskripsi sendiri dengan deteksi bahasa → "Buka, notepad" |
| Wake phrase ganda | 「OK、ミク、OK、ミク」 → perintah 「OK、ミク」 | Wake phrase berulang dibuang |

Rekaman putaran 6 diputar ulang 4×: 7/10 sebelum ejaan "emigu"/"amiku" diterima, 8/10 sesudahnya. "Oke Miku" tetap terdeteksi 9/10; satu sisanya "Oke, maybe", terlalu jauh untuk diterima tanpa risiko pemicu palsu. Perbedaan dengan live (10/10) datang dari batas segmen yang sedikit berbeda dan suhu cadangan Whisper.

**Volume mic penting.** Di 30% (derau RMS ±0,02) hasilnya 2–5/10; di 20% (±0,007) 9–10/10. Panduan untuk user: turunkan volume input sampai derau ruangan kecil, sekitar 20% di laptop ini.

## Musik dan video

`live_idle.py` dengan pengaturan aplikasi, mic laptop 20%. User memutar musik dan video dari speaker, tanpa mengucapkan "Oke Miku". Sesi kedua direkam (`--record`, di folder sementara di luar repo) untuk dianalisis ulang.

| Sesi | Ucapan terdengar | Panggilan Whisper (waktu) | Pemicu | CPU proses | GPU |
|---|---|---|---|---|---|
| 1 (10 menit) | 20 | 171 (16,7 s) | **0** | 2,8% | median 0% |
| 2 (10 menit, direkam) | 174 | 242 (72,5 s, ±12%) | **0** | 4,4% | median 0% |

- Whisper berhalusinasi pada musik: "Oke" saja 35×, "Terima kasih" 27×, "Jangan lupa like, share dan subscribe ya", dan "Miku" 5× (sebagian dari lirik). "Oke" diduga dipancing prompt `"Oke Miku."`. Keduanya tidak pernah muncul berurutan, jadi tidak ada yang cocok pola.
- Rekaman sesi 2 diputar ulang 2× (`confidence_scan.py`): 243 cek, 0 cocok pola.
- **Filter keyakinan tidak dipasang.** Peluang terendah Whisper di kata wake phrase pada "Oke Miku" sungguhan (rekaman putaran 6) hanya 0,02–0,52, median 0,25. Pada musik tidak ada satu pun kecocokan untuk dibandingkan. Ambang apa pun akan membuang "Oke Miku" sungguhan tanpa manfaat yang terukur. `wake_phrase_confidence` dan `confidence_scan.py` disimpan untuk data berikutnya.
- Risiko yang tersisa: lagu yang liriknya sungguh berbunyi "oke Miku" akan memicu, sama seperti orang yang mengucapkannya.

**Belum diuji:** suara orang lain, dan Windows.
