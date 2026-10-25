# Uji tool dokumen Word

Diukur 25 Okt 2026, `qwen3:4b-instruct`, routing skill ON. Tool tidak dieksekusi.
Skrip: `python experiments/word_tool/bench_docs.py 3` dari root repo.

## Latar

Di sesi GUI 25 Okt, permintaan "Bisa buatkan dokumen Word, kemudian masukkan rumus-rumus Hukum Newton 1, 2, dan 3…" hanya dijawab obrolan 「Wordで作るんだね！」. Saat diulang ("Buatkan dokumen Word"), model memanggil `open_application("Word")`, sehingga yang terbuka hanya Word kosong.

## Kriteria lulus

- Permintaan dokumen: `create_word_document` terpanggil, isi ≥ 150 karakter, dan memuat kata topik (misalnya "newton", "1945", "olahraga"). Kata topik berbahasa Indonesia sekaligus mengecek bahwa isi dokumen tidak ditulis dalam bahasa Jepang.
- Kontrol ("Buka Word", 「ワードを開いて」): `open_application` terpanggil, tanpa `create_word_document`.

## Hasil (× 3 percobaan)

| Skenario | Sebelum | Sesudah |
|---|---|---|
| Buatkan dokumen Word … Hukum Newton 1, 2, 3 | 2/3 | 3/3 |
| Bikin dokumen Word berisi ringkasan sejarah kemerdekaan | 3/3 | 3/3 |
| Buat file Word tentang manfaat olahraga pagi | 2/3 | 3/3 |
| Tulis surat izin tidak masuk kuliah karena sakit di Word | 0/3 | 2/3 |
| ニュートンの運動の法則についてWordで文書を作って | 0/3 | 3/3 |
| ワードで自己紹介の文書を作って | 0/3 | 3/3 |
| **Total permintaan dokumen** | **7/18** | **17/18** |
| Kontrol buka Word | 6/6 | 6/6 |
| Lanjutan "Buatkan dokumen Word" setelah obrolan | 3/3 | 3/3 |
| Benchmark tool umum (10 perintah × 5) | 50/50 | 50/50 |
| Multi-turn `close_application` | 8/8 | 8/8 |
| Latensi median permintaan dokumen | 2,2 s | 9,2 s |

Latensi naik karena model sekarang benar-benar menulis isi dokumen (median 500–2.100 karakter). Sebelumnya model sering hanya bertanya 「どんな内容に…」 tanpa menulis apa pun.

Kasus lanjutan dari sesi GUI sudah lulus juga di kode lama dengan riwayat sependek ini, jadi kegagalan aslinya (riwayat lebih panjang) belum terulang di benchmark. Perbaikan di giliran pertama mengurangi kemungkinan situasi itu muncul.

## Yang dicoba

1. **Deskripsi tool + deskripsi parameter.** Sebelumnya semua parameter hanya berlabel "Parameter: content". Ditambah regex retry untuk 作って / buatkan / bikin / tulis. Hasil: 7 → 13/18. Sisa kegagalan: isi dokumen ditulis dalam bahasa Jepang (bahasa persona) untuk permintaan berbahasa Indonesia.
2. **Petunjuk bahasa di system prompt, lalu tepat setelah pesan user:** tetap 13/18. Persona Jepang lebih kuat bagi model 4B.
3. **Terjemahan sekali:** bila permintaan tidak berbahasa Jepang tetapi ≥ 30% huruf isi dokumen adalah huruf Jepang, isi diterjemahkan ke bahasa Indonesia dengan satu panggilan tanpa tool. Hasil: 17/18.
