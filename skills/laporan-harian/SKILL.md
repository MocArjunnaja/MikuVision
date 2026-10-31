---
name: laporan harian
description: Membuat dokumen Word laporan harian dari cerita user tentang hari ini
triggers: [laporan harian, laporan hari ini, daily report, 日報, 今日の報告]
tools: [create_word_document, open_folder]
---
1. Bila user belum menyebutkan apa saja yang dikerjakan hari ini, tanyakan dulu dalam satu kalimat dan jangan memanggil tool.
2. Bila sudah, panggil create_word_document:
   - filename: "Laporan_Harian"
   - content: baris judul "Laporan Harian", lalu bagian "Kegiatan hari ini" (satu poin per kegiatan dari ucapan user), "Kendala" (tulis "-" bila tidak disebut), dan "Rencana besok".
   - Tulis dalam bahasa permintaan user. Jangan menambah kegiatan yang tidak disebut user.
3. Setelah itu panggil open_folder dengan folder_name_or_path "Miku_Documents".
