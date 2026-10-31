# Rencana: Skill buatan user (Miku belajar kemampuan baru)

**Tujuan:** user bisa menambah kemampuan Miku tanpa mengubah kode: cukup satu file teks berisi petunjuk, daftar tool, dan pemicu. Miku memuatnya hanya saat relevan, lalu tetap berpikir sendiri: mengisi parameter dari ucapan user, bertanya bila ada yang kurang, dan menyesuaikan dengan situasi.

**Status:** rencana, belum dimulai (31 Okt 2026).

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
5. **Slash command:** `/skills` (sudah ada) ikut menampilkan skill user; `/skill <nama>` menjalankan; `/skill forget <nama>` menghapus.
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

1. Format file Markdown + front matter seperti contoh di atas, oke?
2. Boleh Miku membuat skill sendiri dari percakapan ("simpan ini sebagai skill"), dengan konfirmasi dulu?
3. Skill pertama apa yang paling ingin dibuat?
