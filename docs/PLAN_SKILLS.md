# Rencana: Skill buatan user (Miku belajar kemampuan baru)

**Tujuan:** user bisa menambah kemampuan Miku tanpa mengubah kode: cukup satu file teks berisi petunjuk, daftar tool, dan pemicu. Miku memuatnya hanya saat relevan, lalu tetap berpikir sendiri: mengisi parameter dari ucapan user, bertanya bila ada yang kurang, dan menyesuaikan dengan situasi.

**Status:** S1 selesai (31 Okt 2026, bagian 8). Berikutnya: S2 ("simpan ini sebagai skill"); urutannya terhadap rencana lain ada di [`ROADMAP.md`](ROADMAP.md).

---

## 1. Yang sudah ada

| Fitur | Isi | Batasan |
|---|---|---|
| **Skill bawaan** (`core/skills.py`) | 9 kelompok tool (Audio, Aplikasi, Web, Keyboard, Office, Pesan, Memori, Info sistem, Routine). Hanya kelompok yang cocok dengan permintaan yang dikirim ke LLM, sehingga prompt turun dari ±3.400 ke ±1.550 token | Ditulis di kode; user tidak bisa menambah |
| **Routine** (`data/routines.yaml`) | Rangkaian tool tetap dengan satu perintah ("jalankan mode belajar") | Tanpa LLM: parameter tetap, tidak bisa bertanya atau menyesuaikan |
| Slash command, memori jangka panjang, cache aplikasi (`/apps`) | Perintah tanpa LLM, fakta tentang user, aplikasi yang sudah dipelajari | Bukan cara menambah kemampuan baru |

## 2. Yang ditambahkan: skill buatan user

Skill = petunjuk + tool yang boleh dipakai + pemicu, dalam satu file Markdown. Bedanya dengan routine: LLM tetap ikut berpikir.

Contoh `data/skills/laporan-harian/SKILL.md`:

```markdown
---
name: laporan harian
description: Membuat dokumen laporan harian kuliah dari ucapan user
triggers: [laporan harian, daily report, 日報]
tools: [create_word_document, open_folder]
---
1. Bila user belum menyebutkan kegiatannya hari ini, tanyakan dulu.
2. Buat dokumen Word "Laporan_<tanggal>" berisi judul, daftar kegiatan, dan rencana besok.
3. Buka folder Miku_Documents.
```

## 3. Desain

1. **Lokasi:** `skills/` berisi contoh dan ikut repo; `data/skills/` milik user, tidak ikut git, dan menimpa contoh dengan nama yang sama (sama seperti routine).
2. **Dimuat saat relevan**, memakai mekanisme `select_skills` yang sudah ada:
   - nama dan deskripsi singkat semua skill selalu ada di prompt;
   - isi petunjuk dan skema tool-nya hanya dikirim bila pemicunya cocok.
3. **Aman:**
   - skill hanya bisa memakai tool yang sudah terdaftar, tidak bisa menambah kode atau perintah shell;
   - aksi berisiko tetap meminta konfirmasi dan tidak bisa dimatikan oleh skill;
   - skill hanya dibaca dari folder lokal.
4. **Cara membuat:**
   - menulis file sendiri;
   - mengucapkan "simpan ini sebagai skill" setelah sebuah percakapan berhasil: Miku menyusun `SKILL.md`, menunjukkannya dulu, lalu menyimpan setelah user setuju;
   - `/skill new <nama>`.
5. **Slash command:** `/skills` ikut menampilkan skill user dan file yang gagal dimuat; `/skill <nama>` menampilkan isi skill (S1); `/skill forget <nama>` menghapus (S2).
6. **Batas untuk model 4B dengan konteks 8k:** petunjuk satu skill maksimal ±400 token, dan maksimal 2 skill user aktif per giliran.

## 4. Tahapan

| Fase | Isi | Keluaran |
|---|---|---|
| **S1** | Format `SKILL.md`, loader, routing (skill user ikut `select_skills`), 2 contoh skill, test | Skill dari file terpilih dan dipakai dengan benar |
| **S2** | "Simpan ini sebagai skill": LLM menyusun `SKILL.md` dari percakapan → ditunjukkan → disimpan setelah user setuju | User bisa membuat skill tanpa menulis file |
| **S3** | Evaluasi: 10 permintaan per skill, dampak ke token dan latensi | Angka di CHANGELOG |

## 5. Evaluasi

| Metrik | Target |
|---|---|
| Skill yang tepat terpilih | ≥ 9/10 per skill |
| Tool calling umum (10 perintah JP/ID) | tetap 10/10 |
| Token prompt rata-rata | naik ≤ 300 |
| Aksi berisiko tanpa konfirmasi | 0 |

## 6. Risiko & mitigasi

| Risiko | Mitigasi |
|---|---|
| Petunjuk skill berisi instruksi jahat (file dari orang lain) | Hanya folder lokal; tool berisiko tetap dikonfirmasi; skill tidak bisa mematikan konfirmasi |
| Model 4B kesulitan mengikuti petunjuk panjang | Batas panjang petunjuk dan jumlah skill aktif |
| Tumpang tindih dengan routine | Routine = urutan tetap tanpa LLM; skill = dengan LLM. Skill boleh menyarankan routine, tidak menjalankannya berantai |

## 7. Keputusan yang dibutuhkan dari user

1. Format file Markdown + front matter seperti contoh di atas, oke? (S1 memakai format ini)
2. Boleh Miku membuat skill sendiri dari percakapan ("simpan ini sebagai skill"), dengan konfirmasi dulu? (S2)
3. Skill pertama apa yang paling ingin dibuat? (S1 membawa dua contoh: laporan harian dan musik mood)

## 8. Hasil S1 (31 Okt 2026)

**Yang dibuat**
- `core/user_skills.py`: membaca `skills/*/SKILL.md` (contoh, ikut repo) dan `data/skills/*/SKILL.md` (milik user, menimpa contoh bernama sama). File ditolak bila tanpa `name`/`tools`/petunjuk, memakai tool yang tidak terdaftar atau `run_routine`, atau petunjuknya lebih dari ±400 token. Alasannya tampil di `/skills`.
- Pemicu dicocokkan setelah huruf dikecilkan dan tanda baca dibuang; nama skill selalu ikut menjadi pemicu. Awal kata harus pas, akhiran boleh ("laporan hariannya"). Maksimal 2 skill aktif, pemicu terpanjang didahulukan.
- `AIBrain`: skill aktif menambah skema tool-nya ke skill bawaan yang cocok. Bila hanya skill user yang cocok, yang dikirim cukup tool skill itu + memori, bukan semua tool. Petunjuk skill aktif masuk system prompt; skill lain hanya disebut nama dan deskripsinya.
- Contoh: `skills/laporan-harian` (`create_word_document`, `open_folder`) dan `skills/musik-mood` (`set_volume`, `youtube_search`).

**Yang ditemukan saat uji LLM**
| Masalah | Perbaikan |
|---|---|
| qwen3:4b hanya memanggil satu tool per balasan (`set_volume`, lalu berhenti): musik mood 0/10 | `run_turn` meminta langkah skill berikutnya selama masih ada tool skill yang belum dipakai dan tool sebelumnya berhasil (maks. 3 langkah). Giliran tanpa skill user tidak berubah |
| Skill yang menyuruh bertanya dulu dipaksa memanggil tool oleh retry "missed tool" | Retry dilewati bila petunjuk skill menyuruh bertanya (`tanyakan`, `ask`, `聞`), balasannya berupa pertanyaan, dan user belum memberi detail |
| Jawaban user atas pertanyaan skill ("tadi belajar fisika") tidak memuat pemicu | Skill yang gilirannya berakhir dengan pertanyaan tetap aktif satu giliran lagi |
| 「作業用BGMかけて」, 「流して」 tidak dianggap permintaan aksi | `かけて` dan `流して` ditambahkan ke pola permintaan aksi |

**Angka** (`experiments/skills/bench_skills.py`, qwen3:4b-instruct, 3 percobaan per ucapan; giliran lewat `run_turn`, tool tidak dieksekusi)

| Metrik | Target | Hasil |
|---|---|---|
| Skill yang tepat terpilih | ≥ 9/10 | 60/60 |
| Laporan harian: tool dan isi benar, atau bertanya bila kegiatan belum disebut | ≥ 9/10 | 29/30 |
| Musik mood: `set_volume` + `youtube_search` dengan volume dan query sesuai tabel skill | ≥ 9/10 | 29/30 (23/30 sebelum skill diberi "jangan bertanya dulu") |
| Perintah umum (10 JP/ID): tidak mengaktifkan skill user | 0 salah aktif | 30/30 tidak aktif |
| Perintah umum: tool benar | sama dengan tanpa skill | 27/30 dengan skill, 25/30 tanpa skill |
| Token prompt (median) | naik ≤ 300 | 1.664 vs 1.610 (+54) |
| Aksi berisiko tanpa konfirmasi | 0 | 0; gerbang konfirmasi tidak bisa dilewati skill |

`次の曲にして` gagal di kedua versi (model bertanya "lagu apa?"), jadi itu kelemahan lama, bukan efek skill. Satu catatan dari hasil ini: skill yang gagal bisa diperbaiki dengan mengubah `SKILL.md` saja, tanpa mengubah kode.
