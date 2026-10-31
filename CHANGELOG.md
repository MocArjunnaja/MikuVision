# Changelog

Catatan perubahan, pengujian, dan keputusan teknis MikuVision (dulu MikuWin V11).
Format mengikuti [Keep a Changelog](https://keepachangelog.com/id/1.1.0/). Entri terbaru di atas.
Angka benchmark diukur di laptop pengembang: RTX 4050 Laptop 6 GB, Windows 11, Ollama 0.40.10.

---

## Belum dirilis (2026-10-31): "simpan ini sebagai skill" menyimpan tugas yang baru selesai

Perbaikan S2 setelah baris "Skill buatan user" di checklist Windows ([`docs/ROADMAP.md`](docs/ROADMAP.md) bagian 2) gagal. Masalahnya bukan khusus Windows.

### Diperbaiki
- **Skill berisi tugas lama dari sesi yang sama.** Diulang di `miku.py --text`, satu sesi: "buatkan laporan harian: …", lalu "putar lagu buat belajar", lalu "kecilkan volume ke 20 lalu putar lofi di youtube", lalu "simpan ini sebagai skill, namanya mode fokus".
  - Hasilnya: skill berisi `create_word_document`, `open_folder`, `set_volume` (level 30, bukan 20), dan `youtube_search`.
  - "mode fokus dong" lalu memanggil `run_routine('mode fokus')`: "Routine 'mode fokus' tidak ditemukan".
  - Di sesi baru yang hanya berisi giliran ketiga, simpan dan pakai ulang berjalan benar.
- Penyebab dan perbaikannya (`core/skill_builder.py`):
  - **Ucapan yang sudah dikerjakan skill lain tidak ditawarkan sebagai langkah.** Giliran 1 dan 2 di atas dikerjakan skill contoh (pemicu "laporan harian" dan "lagu buat"). Tugas itu sudah punya skill, jadi bukan bagian skill baru. Giliran itu tetap ada di percakapan yang dibaca LLM. Ucapan terakhir selalu ditawarkan.
  - **Tool call dikelompokkan per ucapan user** di prompt, dengan ucapan terakhir ditandai `(latest)`. Prompt meminta tool call ucapan terakhir, plus ucapan sebelumnya hanya bila itu bagian lain dari tugas yang sama. Sebelumnya prompt menyebut langkahnya "biasanya semuanya".
  - **Bila tidak ada tool call dari ucapan terakhir yang dipilih**, termasuk bila nomornya salah semua, yang disimpan tool call ucapan terakhir saja. Sebelumnya cadangannya semua tool call di riwayat.
  - **Batas langkah membuang langkah terlama**, bukan yang terbaru. Sebelumnya `chosen[:MAX_STEPS - 1]` menyimpan empat tool call tertua, jadi tugas yang baru selesai yang terpotong.
  - Jendela riwayat 12 → 20 pesan, sama dengan memori chat, dan dimulai dari ucapan user. Tanpa itu, giliran yang terpotong di awal jendela menyisakan hasil tool tanpa argumennya, misalnya `open_folder()` kosong.
  - Tugas beberapa giliran tetap didukung: "siap kerja" (folder di satu giliran, aplikasi di giliran berikutnya).
- **Pemicu yang memuat nama routine, pemicu skill lain, atau kata simpan dibuang.**
  - Nama routine: "mode belajar" (`routines.example.yaml`, `data/routines.yaml`) menarik giliran ke `run_routine`.
  - Pemicu skill lain: "buat laporan harian" akan mengalahkan skill laporan harian karena lebih panjang.
  - Kata simpan: "simpan mode fokus", "save …", 「…を保存」. Balasan konfirmasi tidak lagi menyuruh user bilang "simpan mode fokus".
  - Contoh nama skill di prompt diganti dari "mode belajar" (nama routine) menjadi "persiapan rapat", karena nama skill selalu ikut menjadi pemicu.

### Pengujian
- `experiments/skills/bench_save_skill.py` mendapat skenario `campur_id`: ketiga giliran di atas dalam satu sesi, lalu "simpan ini sebagai skill, namanya mode fokus", lalu "mode fokus dong" di sesi baru. Benar bila skill hanya berisi `set_volume` + `youtube_search` dan pakai ulangnya volume 20 + lofi, tanpa dokumen. Skenario bisa dipilih lewat argumen: `bench_save_skill.py 3 campur_id`.

  | Riwayat tugas (6 skenario × 3) | Tersimpan | Tool skill tepat | Terpilih saat dipakai | Pakai ulang benar | Giliran simpan |
  |---|---|---|---|---|---|
  | Disuntikkan (yang diukur hanya S2) | 18/18 | **18/18** | 18/18 | **17/18** | median 3,4 s |
  | Dijalankan qwen3:4b (`--live`) | 18/18 | 10/18 | 18/18 | 9/18 | median 3,0 s |

  - Kedelapan "tool skill tepat" yang meleset di `--live` sama penyebabnya: di giliran tugas, qwen3:4b hanya mengatur volume tanpa memutar YouTube (mode fokus 3, ジャズタイム 2, `campur_id` 3). Skill-nya setia pada yang berhasil, jadi ikut hanya berisi `set_volume`. Ini keterbatasan lama yang sama dengan rilis S2.
  - Pakai ulang yang meleset di luar itu, penyebabnya juga lama:
    - satu mode fokus (disuntikkan): LLM menandai `query` sebagai isian, jadi skill bertanya dulu dan tidak memanggil tool;
    - satu catatan rapat (`--live`): petunjuk isian membawa detail lama ("anggaran total"), dan dokumen barunya ikut menyebut anggaran.
  - Lima skenario lama, dibanding hasil S2: disuntikkan 15/15 tool tepat dan 14/15 pakai ulang (sama); `--live` 10/15 dan 9/15 (sebelumnya 11/15 dan 11/15). Selisihnya dari giliran tugas yang tidak memutar YouTube, bukan dari penyusun skill.
  - Giliran simpan lebih lama ±1 s (median 2,4 → 3,4 s disuntikkan) karena jendela riwayat 20 pesan.
- `campur_id`, commit induk vs branch ini (3 run masing-masing):

  | | Skill tanpa tugas lama | Tool skill tepat | Pakai ulang benar |
  |---|---|---|---|
  | Commit induk, disuntikkan | 3/3 | 3/3 | 3/3 |
  | Commit induk, `--live` | **0/3** | 0/3 | 0/3 |
  | Branch ini, disuntikkan | 3/3 | 3/3 | 3/3 |
  | Branch ini, `--live` | **3/3** | 0/3 | 0/3 |

  - Commit induk `--live` mengulang kegagalan Windows persis: keempat tool, pemicu "simpan mode fokus" dan "mode belajar", lalu "mode fokus dong" memanggil `run_routine('mode fokus')` (1×) atau membuat dokumen "Mode_Fokus" (2×).
  - Commit induk lulus saat disuntikkan hanya karena jendela 12 pesan memotong giliran laporan harian, dan LLM kebetulan memilih tool call terakhir.
  - Branch ini `--live`: ketiga skill hanya berisi `set_volume` level 20, tanpa dokumen dan tanpa volume 30. YouTube tidak ada karena giliran tugasnya sendiri tidak memutarnya (lihat di atas).
- Varian yang dicoba dengan pemeriksaan langkah simpan saja (5 run per kasus), sebelum memilih yang sekarang:
  - LLM memilih nomor ucapan awal tugas (`first_request`, ditulis sebelum langkah): riwayat campur dan "dokumen lalu jazz" 5/5, tapi "siap kerja" 0/5 karena LLM selalu memilih ucapan terakhir.
  - Tanda `same_task` per ucapan: "siap kerja" 0/5, dan LLM tertukar antara nomor ucapan dan nomor tool call.
  - Langkah dipilih per tool call (yang dipakai): "siap kerja" 5/5 dan riwayat campur 5/5. Tetapi satu kalimat tambahan di prompt ("most skills are only those") menurunkan riwayat campur ke 2/5. Karena rapuh, ucapan yang dikerjakan skill lain kini tidak ditawarkan sama sekali; dengan itu riwayat campur 5/5 tanpa bergantung pada pilihan LLM.
- `tests/test_skill_builder.py` (+7 test):
  - regresi dari riwayat di atas, dengan LLM yang memilih keenam tool call seperti di Windows: skill hanya berisi `set_volume` 20 + `youtube_search`, pemicunya tanpa kata simpan, nama routine, atau pemicu skill lain, dan balasannya menyebut "mode fokus sekarang";
  - tugas lama tanpa skill (dokumen, lalu jazz): ikut hanya bila LLM memilihnya bersama ucapan terakhir; bila LLM hanya memilih tugas lama, tidak memilih apa pun, atau nomornya salah, yang disimpan ucapan terakhir;
  - penyaring pemicu untuk nama routine dan kata simpan;
  - jendela riwayat dimulai dari ucapan user;
  - test batas langkah kini mengharapkan langkah terbaru (30, 40, 50, 60), bukan terlama;
  - test "siap kerja" kini juga memeriksa kedua tool-nya tetap ada.
- `pytest`: 419 lulus, 31 dilewati (venv aplikasi); di Python sistem seperti CI 413 lulus, 37 dilewati.

### Keterbatasan diketahui
- **Tugas lama yang tidak dikerjakan skill masih bisa ikut** bila qwen3:4b memilihnya. Contoh: dokumen daftar belanja, lalu "putar jazz di youtube dengan volume 30", lalu "jadikan skill ya": skill berisi ketiga tool di 5/5 percobaan. Begitu juga lagu YouTube sebelum "siap kerja" (5/5). Pratinjau memperlihatkan tool-nya sebelum disetujui.
- **"mode fokus dong" bisa tersasar ke `run_routine`** bila skill "mode fokus" hanya berisi satu langkah. Kata "mode" mengaktifkan skill bawaan routine, sehingga `run_routine` ikut ditawarkan. Terjadi di 4 dari 6 pakai ulang `--live` dengan skill satu langkah, dan 0 dari 18 dengan skill dua langkah (disuntikkan). Perbaikannya di pemilihan skill (`AIBrain._select_turn_skills`, `core/skills.py`), di luar perubahan ini.

---

## Belum dirilis (2026-10-31): "simpan ini sebagai skill" (PLAN_SKILLS S2)

Rencana: S2 di [`docs/PLAN_SKILLS.md`](docs/PLAN_SKILLS.md). Keputusan 2 dari user: Miku boleh menyusun skill dari percakapan, dengan konfirmasi.

### Ditambahkan
- **"Simpan ini sebagai skill"** (`core/skill_builder.py`). Bisa diucapkan setelah Miku menyelesaikan tugas: "simpan ini sebagai skill, namanya mode fokus", 「これをスキルとして保存して」, "save this as a skill".
  - **Dipicu oleh kalimatnya, bukan oleh LLM**: harus ada "skill"/"スキル" bersama kata kerja simpan, jadi permintaan ini tidak pernah tersasar ke tool lain. Kalimat seperti "buatkan dokumen tentang skill komunikasi" tidak terpicu. Dari 42 ucapan di benchmark yang ada, tidak satu pun terpicu.
  - **Langkahnya disusun oleh kode dari tool call yang tadi berhasil**, lengkap dengan nilainya (`Panggil set_volume: level = 20`), jadi tidak ada tool karangan. LLM (satu panggilan, JSON schema) hanya memilih nama, deskripsi, pemicu, tool call mana yang termasuk tugas, dan parameter mana yang diambil dari ucapan user setiap kali.
  - **Isi sekali pakai tidak pernah tersalin.** Isi dokumen, pesan, judul, dan teks > 60 huruf selalu diambil dari permintaan berikutnya. Nama file diganti nama skill. Volume, folder, dan aplikasi selalu tetap, walaupun LLM menandainya sebagai isian.
  - **Nama dari ucapan user dipakai apa adanya**: "namanya X", "…skill X", 'X' dalam kutip, 名前はX, "called X".
  - **Langkah pertama ditambahkan otomatis**: "Jangan bertanya dulu: panggil semua tool ini berurutan dalam satu balasan". Bila ada isian dari user, kalimatnya menjadi "langsung jalankan bila isinya sudah disebut, walau singkat".
  - **Pemicu yang akan membajak perintah biasa dibuang**: "volume 20", "putar lagu", 「電卓を開いて」, kata dari permintaan simpan, dan ucapan yang hanya mencakup satu langkah dari skill beberapa langkah ("buka folder downloads" di skill "siap kerja").
  - **Pratinjau `SKILL.md` lengkap + konfirmasi** lewat jalur yang sudah ada (y/n, "ya/はい", atau dialog GUI). Baru setelah itu disimpan ke `data/skills/<nama>/`. Draf divalidasi dengan parser yang sama dengan skill dari file.
  - Bila belum ada tool yang berhasil di percakapan, Miku menjelaskan bahwa belum ada yang bisa disimpan, tanpa memanggil LLM.
- `/skill new <nama>`: template `SKILL.md` untuk diisi sendiri (tanpa LLM), beserta daftar tool yang boleh dipakai. `/skill forget <nama>`: menghapus skill di `data/skills/` setelah konfirmasi. Contoh bawaan di `skills/` tidak bisa dihapus.
- `AIBrain.generate_json`: satu panggilan tanpa tool dengan keluaran JSON schema, memakai `num_ctx`/`keep_alive` yang sama dengan chat supaya model tidak dimuat ulang. `AIBrain.record_exchange`: mencatat giliran yang dijawab tanpa `think()`.

### Diubah
- `run_turn`: bila skill user terpicu tapi model hanya mengobrol, langkah skill diminta lewat `next_skill_calls`. Ucapan seperti "mode fokus dong" tidak berisi kata kerja aksi, jadi retry di `think()` tidak jalan. Tidak berlaku bila skill sedang menanyakan detail ("kegiatanmu hari ini apa?").
- `user_skills.parse_skill_text`: memvalidasi isi `SKILL.md` tanpa harus menulis file dulu.

### Pengujian
- `experiments/skills/bench_save_skill.py`, qwen3:4b-instruct, 5 skenario × 3. Tiap skenario: tugas → simpan → pakai ulang di sesi baru dengan isi lain.
  - Skenario: mode fokus (volume + YouTube), daftar belanja dan catatan rapat (dokumen Word), ジャズタイム (Jepang), siap kerja (dua giliran: folder + aplikasi).

  | Riwayat tugas | Tersimpan | Tool skill tepat | Terpilih saat dipakai | Pakai ulang benar | Giliran simpan |
  |---|---|---|---|---|---|
  | Disuntikkan (yang diukur hanya S2) | 15/15 | 15/15 | 15/15 | **14/15** | median 2,4 s |
  | Dijalankan qwen3:4b (`--live`) | 15/15 | 11/15 | 15/15 | 11/15 | median 2,4 s |

  - Keempat kegagalan `--live` sama: di giliran tugas, qwen3:4b hanya mengatur volume tanpa memutar YouTube. Skill-nya ikut hanya berisi `set_volume`, dan pratinjau memperlihatkan itu. Ini keterbatasan lama: satu tool per balasan bila tidak ada skill.
  - Daftar belanja dan catatan rapat: isi dokumen saat dipakai ulang mengikuti permintaan baru, tanpa sisa isi lama.
- Perjalanan desain (angka pakai ulang yang sama):
  - **6/15** saat LLM menulis langkahnya sendiri. Ia mengarang tool `mengunduh_lagu_dari_youtube`, menyalin isi dokumen lama (ruang, tanggal, anggaran), mengabaikan nama dari user, dan mengubah "jalankan keduanya" menjadi "tanyakan mau yang mana".
  - **11/15** setelah langkah disusun dari tool call.
  - **14/15** setelah tiga perbaikan:
    - kalimat pembuka Jepang 「質問せずに」 diganti, karena 質問 dibaca parser S1 sebagai "skill ini boleh bertanya dulu";
    - `run_turn` meminta langkah skill bila model hanya mengobrol;
    - volume/folder/aplikasi tidak lagi bisa ditandai sebagai isian.
- Regresi S1 (`bench_skills.py 3`), commit induk vs branch ini:
  - laporan harian 26 vs 27/30, musik mood 27 vs 27/30;
  - perintah umum 24 vs 27/30 (dengan skill) dan 27 vs 26/30 (tanpa);
  - tidak ada perintah umum yang mengaktifkan skill user (30/30 di keduanya).
  - Yang meleset sama di keduanya (次の曲にして, ミュートして).
- `tests/test_skill_builder.py` (50 test):
  - pemicu dan bukan-pemicu;
  - penyaring pemicu;
  - pemasangan tool call dengan argumennya;
  - langkah dari tool call (isi tidak tersalin, nilai tetap tetap, urutan dan batas langkah, cadangan bila LLM salah pilih);
  - nama dari user;
  - bahasa langkah;
  - pratinjau/batal/tanpa konfirmasi;
  - `run_turn` tanpa `think()`;
  - `/skill new`, `/skill forget`.
  - Ditambah 2 test di `tests/test_user_skills.py` untuk langkah skill saat model hanya mengobrol.
- `pytest`: 443 lulus; di Python sistem seperti CI 437 lulus, 6 dilewati.

### Keterbatasan diketahui
- Skill hanya setia pada tool yang berhasil. Bila Miku tadi hanya mengerjakan sebagian tugas, skill-nya juga hanya sebagian, sehingga pratinjau perlu dibaca sebelum disetujui.
- Di mode suara, pratinjau hanya tampil di terminal; Miku bertanya "この操作を実行してもいい？" tanpa membacakan isinya.
- Skill tidak bisa disunting lewat suara; ubah `data/skills/<nama>/SKILL.md` langsung atau simpan ulang dengan nama yang sama.

---

## Belum dirilis (2026-10-31): Miku membaca layar (agent visi Fase 1)

Rencana: Fase 1 di [`docs/PLAN_VISION_AGENT.md`](docs/PLAN_VISION_AGENT.md). Hanya melihat; Miku belum mengklik atau mengetik.

### Ditambahkan
- Tool `describe_screen(question)`: "error apa ini?", "bacakan tulisan di layar", 「画面に何が表示されてる？」.
  - Screenshot jendela yang sedang aktif (`core/vision/capture.py`). Bila yang aktif jendela Miku sendiri (GUI), atau jendelanya tidak terbaca, seluruh layar yang diambil. Jendela dipotong, bukan seluruh layar, karena teks kecil sulit dibaca setelah gambar diperkecil.
  - Dijawab oleh model visi lokal `qwen3-vl:4b-instruct` (`VISION_MODEL`), lalu Miku merangkumnya dalam balasannya.
  - Bila model visi belum terpasang, Miku menyebut perintah `ollama pull`-nya tanpa menyentuh LLM utama.
- Tool `find_on_screen(query)`: "tombol apa saja di jendela ini?", 「電卓に「π」のボタンはある？」.
  - Membaca nama, jenis, dan status elemen jendela aktif dari pohon aksesibilitas Linux (AT-SPI2), tanpa model visi. Isi field, termasuk password, tidak dibaca.
  - `pyatspi` adalah paket sistem, jadi dibaca oleh `core/vision/atspi_helper.py` yang dijalankan dengan `/usr/bin/python3`, lalu hasilnya dikirim sebagai JSON.
  - Windows (UI Automation) menyusul.
- **Tukar model di VRAM** (`core/vision/model.py`). GPU 6 GB tidak muat qwen3:4b + qwen3-vl + Whisper + RVC sekaligus. Satu pertanyaan visi berjalan begini: qwen3:4b dilepas → qwen3-vl menjawab, lalu langsung dilepas → qwen3:4b dimuat lagi.
  - Kedua pemuatan memaksa semua layer ke GPU (`VISION_NUM_GPU`, opsi `num_gpu` Ollama). Bila VRAM benar-benar kurang, model dimuat otomatis.
  - Bila model visi gagal, qwen3:4b tetap dikembalikan.
- Skill bawaan "screen": tool layar dikirim ke LLM bila ada kata seperti 画面/エラー/ボタン, layar/error/tombol/baca, atau screen.
- Teks di layar adalah data, bukan perintah. Hasil tool diberi label begitu, prompt model visi menyatakannya, dan balasan setelah tool tidak pernah menjalankan tool call.

### Pengujian
- Tukar model dengan Whisper + RVC di VRAM (`experiments/vision_linux/swap_bench.py`):

  | | Otomatis (Ollama memutuskan) | `num_gpu` dipaksa |
  |---|---|---|
  | qwen3-vl, num_ctx 4096: di GPU, muat + jawab 150 token | 76%, 11,7 s | 100%, 8,8 s |
  | qwen3:4b setelah dimuat ulang | 85% di GPU, prompt penuh 45 token/s | 100%, 67 token/s (sama dengan sebelum tukar) |

  - qwen3-vl dengan num_ctx 8192 (17,6–26,7 s) jauh lebih lambat dari 4096, jadi dipakai `VISION_NUM_CTX = 4096`.
  - Chat biasa sesudahnya tidak membuat Ollama memuat ulang model.
- Uji sungguhan lewat `run_turn` + qwen3:4b, dengan Whisper + RVC di VRAM dan jendela berisi data dummy (`experiments/vision_linux/screen_tools_demo.py`, 8 kasus × 3): **24/24**.
  - Dialog error zenity (bahasa Indonesia dan Jepang), Xed dengan pengumuman, dan Nemo di folder dummy: `describe_screen` 12/12. Pesan error dan nama file terkutip tepat.
  - Kalkulator ("tombol apa saja…", 「π のボタンはある？」): `find_on_screen` 6/6.
  - Obrolan biasa dan "buka notepad" tidak memanggil tool layar (6/6).
  - Giliran dengan `describe_screen`: median 11,0 s (maks 12,5 s). Tool visinya 6–10 s, sisanya LLM. `find_on_screen` 1,4–3,4 s.
  - qwen3:4b 100% di GPU setelah setiap giliran.
- Percobaan pertama lulus 7/8. Dua deskripsi tool lalu diperbaiki:
  - Contoh parameter "What does the error message say?" dijiplak untuk semua pertanyaan.
  - 「電卓に「π」のボタンはある？」 sempat membuka Kalkulator, bukan melihat jendela yang sudah terbuka.
- Regresi tool calling (`bench_skills.py 3 regression`, 10 perintah × 3, dua kali): 25–28/30, sama dengan commit sebelumnya (24–27/30). Perintah yang meleset juga sama (次の曲にして, ミュートして tanpa tool call), dan tidak ada yang tersasar ke tool layar.
- `tests/test_vision_screen.py` (31 test):
  - potongan jendela dan cadangan seluruh layar (GUI Miku, jendela terlalu kecil, tidak terbaca);
  - Wayland dan tanpa DISPLAY tidak menyentuh X11;
  - helper AT-SPI dengan pyatspi palsu (elemen tersembunyi/tanpa ukuran dilewati, password ditandai, aplikasi Miku dilewati);
  - urutan tukar model dengan Ollama palsu, termasuk cadangan saat VRAM kurang, model visi gagal, dan model visi belum terpasang;
  - kedua tool dan pemicu skill.
  - `tests/conftest.py` melarang screenshot, helper AT-SPI, dan panggilan Ollama sungguhan.
- `pytest`: 391 lulus; di Python sistem seperti CI 385 lulus, 6 dilewati.

### Keterbatasan diketahui
- Giliran yang membaca layar butuh ±11 s, dan Miku belum memberi tanda suara saat mulai melihat (hanya ekspresi "thinking").
- `find_on_screen` hanya di Linux. Di Windows tool itu menjawab "belum tersedia" (UI Automation menyusul).
- `describe_screen` di Windows baru dites dengan mock; masuk daftar cek Windows.
- Wayland belum dicoba. Jendela aktif tidak terbaca (jadi seluruh layar yang diambil), dan screenshot bisa gagal tanpa portal Screenshot.
- Teks Jepang di layar belum diuji, karena semua jendela uji berbahasa Indonesia/Inggris.
- `qwen3-vl:4b-instruct` (3,3 GB) tidak dipasang oleh installer.

---

## Belum dirilis (2026-10-31): shortcut keyboard untuk mulai bicara (T1)

Rencana: T1 di [`docs/PLAN_VISION_AGENT.md`](docs/PLAN_VISION_AGENT.md).

### Ditambahkan
- `core/hotkey.py`: `Ctrl+Shift+M` (`WAKE_HOTKEY` di `config.py`) membuat Miku mendengarkan, dari aplikasi mana pun.
  - Linux X11: XGrabKey pada root window lewat python-xlib, tanpa root. Keempat variasi CapsLock/NumLock ikut di-grab.
  - Windows: library `keyboard` (sudah dependency).
  - Bila kombinasi sudah dipakai aplikasi lain, atau sesinya Wayland, Miku memberi tahu, menyarankan `--trigger`, dan tetap jalan tanpa shortcut.
  - Kombinasi tanpa Ctrl, Alt, atau Super ditolak (kecuali F1–F24), supaya ketikan biasa tidak tertelan. `HOTKEY_ENABLED = False` mematikan shortcut.
  - Tekan beruntun dalam 0,5 s (termasuk auto-repeat saat tombol ditahan) diabaikan. Tekan saat Miku sedang memproses atau bicara juga diabaikan.
- `python miku.py --trigger` meminta Miku yang sedang jalan (maskot atau GUI) untuk mendengarkan. Perintah ini dipasang user sebagai shortcut di pengaturan keyboard desktop, dan jalan juga di Wayland.
  - Lewat `multiprocessing.connection`: Unix socket di `$XDG_RUNTIME_DIR/mikuvision/`, named pipe di Windows.
  - Kunci acak dibuat per sesi dan disimpan di file yang hanya bisa dibaca user (0600). Pesan dibaca sebagai byte (`recv_bytes`, tanpa pickle), dan hanya "listen" yang diterima.
  - `core/hotkey.py` dimuat langsung dari file, tanpa `config.py` dan package `core` yang memuat torch dan Whisper (±20 s). Perintahnya selesai dalam 0,2–0,26 s.
  - Socket yang tertinggal karena Miku crash diganti otomatis. Miku kedua tidak mengambil alih socket Miku pertama.
- Mode suara (`miku.py`): shortcut langsung merekam, tanpa sapaan 「はい、何でしょうか？」 yang muncul saat maskot diseret. Sapaan itu butuh ±1–2 s TTS + RVC, dan selama itu ucapan user tidak terekam. Maskot berganti ekspresi "listening".
- GUI: tekan sekali untuk mulai merekam, sekali lagi untuk selesai, karena tombol GUI berupa "tahan untuk bicara".
  - Callback shortcut hanya mengisi antrean pesan; widget Tk tetap diubah di main thread.
  - Status shortcut tampil di chat dan tercatat di `gui.log`.
- Grab dan socket dilepas saat Miku keluar: Ctrl+C, menu maskot "Exit Miku", atau tombol ✕ di GUI. Menutup Miku tepat setelah `--trigger` tidak menggantung: koneksi yang membangunkan listener berjalan di thread sendiri.

### Pengujian
- `tests/test_hotkey.py` (35 test):
  - `parse_combo`;
  - backend X11 dengan Display palsu: 4 variasi grab, `BadAccess` melepas semua grab, Wayland dan tanpa DISPLAY tidak menyentuh X11;
  - backend Windows dengan `keyboard` palsu;
  - `--trigger` lewat socket sungguhan: kunci salah ditolak, pesan lain diabaikan, error di callback tidak mematikan listener, `stop()` tepat setelah satu pemicu tidak menggantung, socket basi diganti, Miku kedua ditolak, kunci ditulis byte demi byte;
  - debounce;
  - mode suara: shortcut tanpa sapaan, seret maskot tetap disapa, cleanup melepas shortcut;
  - GUI: callback hanya mengisi antrean, tekan-tekan memulai dan menghentikan rekaman.
  - `tests/conftest.py` melarang koneksi X11 sungguhan dan socket milik Miku yang sedang jalan.
- `pytest`: 360 lulus; di Python sistem seperti CI 354 lulus, 6 dilewati.
- `stop()` tepat setelah satu pemicu sempat menggantung (1 dari 10 putaran suite). Setelah diperbaiki: suite penuh 10/10 dan `test_hotkey.py` 30/30 tanpa hang; 200× pemicu lalu `stop()`: 200/200 diterima, `stop()` terlama 1 ms.
- Uji sungguhan di Linux Mint (Cinnamon, X11), shortcut ditekan lewat `xdotool`:

  | Uji | Hasil |
  |---|---|
  | `python miku.py`, 10 tekan | 10/10 mulai merekam, jeda median 30 ms (maks 38 ms, termasuk proses `xdotool`). Tekan saat Miku sedang merekam diabaikan |
  | Instance kedua saat Miku jalan | "Shortcut Ctrl+Shift+M tidak dipasang: sudah dipakai aplikasi lain…" dan "`--trigger` tidak aktif: Miku lain sudah jalan" |
  | `miku.py --trigger` saat Miku jalan / tidak jalan | Miku mendengarkan (0,26 s) / "Miku tidak sedang jalan…" (0,2 s) |
  | Setelah Ctrl+C | Shortcut dan socket bisa dipasang ulang (tidak ada yang tertinggal); model dilepas dari VRAM |
  | GUI, 5 putaran tekan-tekan | 5/5 mulai dan selesai merekam, jeda median 85 ms (antrean Tk dicek tiap 50 ms). Ditutup lewat ✕ tanpa sisa socket |

  Mic menangkap derau di setiap siklus: 10× gagal dikenali, dan sekali "Terima kasih" yang dibalas Miku tanpa tool. Tidak ada aksi yang jalan.

### Keterbatasan diketahui
- Bagian Windows (`keyboard`, named pipe) baru dites dengan mock dan di CI; masuk daftar cek Windows di `docs/ROADMAP.md`.
- `--trigger` baru dicoba dari terminal, belum dipasang sebagai shortcut di pengaturan keyboard Cinnamon.
- Dari shortcut desktop (tanpa terminal), pesan "Miku tidak sedang jalan" tidak terlihat.
- Wayland: tanpa shortcut global; hanya `--trigger`.

---

## Belum dirilis (2026-10-31): installer untuk Fedora, Arch, dan openSUSE

### Diubah
- `install.sh` memasang paket sistem lewat `apt`, `dnf`, `pacman`, atau `zypper`, tergantung distro (dibaca dari `ID`/`ID_LIKE` di `/etc/os-release`, cadangan `command -v`). Sebelumnya hanya `apt`; di distro lain installer menyebut nama paket Debian dan berhenti.
  - Nama paket dipetakan per distro dan dicek di repo resminya: PortAudio = `portaudio` di Fedora/Arch, `libportaudio2` di Debian/openSUSE; compiler C++ untuk RVC = `gcc-c++ make` atau `base-devel`.
  - Peringatan, pertanyaan konfirmasi, dan saran compiler saat RVC gagal memakai nama paket distro itu.
  - Konfirmasi dan `--yes` tetap sama: `sudo` tidak pernah dijalankan tanpa persetujuan.
- `install.sh` bisa di-source tanpa menjalankan instalasi (untuk test).

### Dokumentasi
- `docs/ROADMAP.md`: urutan kerja berikutnya untuk Windows dan Linux, daftar cek di Windows (fitur sejak v1.3.0 yang belum pernah dijalankan di Windows), dan keputusan yang dibutuhkan dari user.
- `PLAN_VISION_AGENT.md`: rencana rinci T1 (shortcut keyboard untuk mulai bicara): desain per OS, test, dan kriteria selesai.

### Pengujian
- `tests/test_install_sh.py` (26 test): deteksi dari 11 file `os-release` palsu, cadangan `command -v`, pemetaan nama, dan alur `check_system` dengan `sudo` palsu. Total `pytest` 325 lulus; Python sistem 320 lulus, 5 dilewati.
- Installer asli dijalankan sampai cek sistem pertama untuk memastikan `main` tetap jalan saat dipanggil langsung.

### Keterbatasan diketahui
- Belum diuji di VM Fedora/Arch/openSUSE sungguhan.
- RHEL/Rocky: `xdotool`, `wmctrl`, `playerctl`, dan `xclip` tersedia lewat EPEL; repo bawaannya kemungkinan tidak memuatnya.

---

## Belum dirilis (2026-10-31): skill buatan user, dan spike agent visi di Linux

Lanjutan [`docs/PLAN_SKILLS.md`](docs/PLAN_SKILLS.md) fase S1, dan Fase 0 Linux dari [`docs/PLAN_VISION_AGENT.md`](docs/PLAN_VISION_AGENT.md).

### Ditambahkan
- **Skill buatan user** (`core/user_skills.py`): satu file `SKILL.md` berisi nama, deskripsi, pemicu, daftar tool, dan petunjuk. Contoh ada di `skills/`; skill milik user ditaruh di `data/skills/<nama>/SKILL.md` dan menimpa contoh bernama sama.
  - Petunjuk dan skema tool skill hanya dikirim ke LLM saat pemicunya ada di ucapan user (maksimal 2 skill); skill lain cukup disebut nama dan deskripsinya.
  - Skill hanya bisa memakai tool yang sudah terdaftar, tidak bisa menjalankan routine, dan petunjuknya maksimal ±400 token. Aksi berisiko tetap dikonfirmasi.
  - Dua contoh: **laporan harian** (dokumen Word dari cerita user, lalu membuka foldernya) dan **musik mood** (volume + YouTube sesuai suasana).
- `run_turn`: selama skill user aktif dan masih ada tool-nya yang belum dipakai, Miku diminta langkah berikutnya (maks. 3), karena qwen3:4b biasanya hanya memanggil satu tool per balasan.
- `/skills` menampilkan skill user dan file yang gagal dimuat beserta alasannya; `/skill <nama>` menampilkan isi satu skill.
- Spike agent visi Linux di `experiments/vision_linux/` dan `experiments/triggers_linux/`: cakupan AT-SPI2, Qwen-VL memilih elemen dan membaca layar, percobaan agent yang menggerakkan mouse/keyboard, dan shortcut global lewat XGrabKey.

### Diubah
- Retry "tool terlewat" tidak memaksa tool call bila skill aktif menyuruh bertanya dulu dan user belum memberi detail.
- 「かけて」 dan 「流して」 kini dianggap permintaan aksi (memutar musik).
- `PLAN_VISION_AGENT.md`: backend per OS (Windows, Linux X11, Wayland), pemicu tanpa tangan (shortcut keyboard dan "Oke Miku"), fase T1/T2. `PLAN_LINUX.md`: kompatibilitas distro dan desktop lain (L5).

### Pengujian
- `pytest`: 299 lulus (40 test baru di `tests/test_user_skills.py`); di Python sistem seperti CI 294 lulus, 5 dilewati.
- Skill dengan qwen3:4b-instruct (`experiments/skills/bench_skills.py`, 3 percobaan):
  - skill tepat terpilih 60/60;
  - laporan harian 29/30, musik mood 29/30;
  - perintah umum tidak mengaktifkan skill user 30/30, dan tool calling-nya 27/30 dengan skill vs 25/30 tanpa skill;
  - prompt +54 token.
  - Rinciannya di `docs/PLAN_SKILLS.md` bagian 8.
- Agent visi Linux (`experiments/vision_linux/RESULTS.md`):
  - AT-SPI2 membaca 5 jendela dalam < 1 s;
  - qwen3-vl:4b memilih elemen yang benar 51/54 (daftar AT-SPI + gambar);
  - nama file di Nemo terbaca dari screenshot;
  - mengetik di Xed lewat keyboard 5/5;
  - menghitung 12 + 7 di Kalkulator dengan klik mouse 3/3 bila rencananya disusun dari daftar nama tanpa gambar (0/7 dengan gambar);
  - tukar model 2,4–2,6 s.
- Shortcut global XGrabKey (`experiments/triggers_linux/hotkey_spike.py`): `Ctrl+Shift+M` 5/5, ±24 ms; `Super+M` tidak sampai di Cinnamon.

### Keterbatasan diketahui
- `/skill forget`, `/skill new`, dan "simpan ini sebagai skill" belum ada (fase S2).
- Agent visi masih berupa eksperimen di `experiments/`; Miku belum bisa mengendalikan mouse/keyboard dari percakapan.

---

## Belum dirilis (2026-10-31): buka aplikasi apa pun dari menu sistem, dan Miku mengingatnya

Pemicunya sesi GUI: "libreOffice o haite kudasai" → "Aplikasi 'LibreOffice' tidak dikenali", karena hanya aplikasi di katalog `config.py` yang bisa dibuka.

### Ditambahkan
- `core/desktop/app_search.py`: `open_application` kini mencari di menu aplikasi sistem bila nama tidak ada di katalog atau aplikasinya tidak terpasang.
  - Urutan: katalog alias → **cache** aplikasi yang sudah dipelajari → menu sistem → nama-nama yang paling mirip.
  - Linux: file `.desktop` dari folder XDG, flatpak, dan snap, sama dengan yang dibaca menu aplikasi. Entri tersembunyi, khusus desktop lain, atau yang programnya tidak ada dilewati. Dibuka dengan `gtk-launch`.
  - Windows: `Get-StartApps` (termasuk aplikasi Store), cadangan shortcut Start Menu. Dibuka dengan `shell:AppsFolder`.
  - Cocok dengan nama, nama terjemahan (Indonesia/Jepang), kata kunci, dan salah ketik ("librofice" → LibreOffice). Bila beberapa aplikasi sama cocoknya (misalnya "writer"), tidak ada yang dibuka dan Miku menanyakan yang mana.
  - Aplikasi berisi kata "uninstall" di namanya tidak pernah dibuka lewat pencarian.
- **Cache** `data/app_cache.json`: aplikasi yang ditemukan di menu dan benar-benar berhasil dibuka disimpan, dipisah per OS (folder `data/` bisa dipakai bersama Windows saat dual-boot). Bila aplikasinya sudah dihapus, entri dilupakan dan dicari ulang. Nama prosesnya ikut disimpan, sehingga "tutup LibreOffice" juga jalan.
- Slash command `/apps` (daftar aplikasi yang dipelajari) dan `/apps forget <nama>`.
- 30 test (`tests/test_app_search.py`).

### Diubah
- Deskripsi tool `open_application`: aplikasi terpasang apa pun, dan nama dikirim dalam bahasa Inggris/nama di menu (「カレンダー」 → "Calendar"), karena aplikasi GNOME tidak menyimpan nama Jepang di file menunya.
- Menutup aplikasi yang jendelanya sudah tertutup tapi prosesnya lanjut di latar (layanan GApplication GNOME, aplikasi di system tray) kini dilaporkan "Menutup …", bukan "masih terbuka". Prosesnya tetap tidak di-kill.

### Diperbaiki
- Brave di Linux: program `brave-browser-stable` dipetakan ke proses `brave`.

### Pengujian
- `pytest`: 259 lulus; di Python sistem seperti CI 254 lulus, 5 dilewati.
- Di Linux Mint (101 aplikasi di menu, dibaca dalam 90 ms):
  - LibreOffice: ditemukan di menu dan dibuka (0,16 s), ditutup, lalu dibuka lagi dari cache (0,07 s).
  - Calendar: dibuka dari menu, lalu ditutup dengan benar walau prosesnya lanjut di latar.
  - "Photoshop" (tidak terpasang): "tidak dikenali", tanpa membuka apa pun.
- Tool calling: 8/8 permintaan aplikasi JP/ID ("libreOffice o haite kudasai", 「カレンダーを開いて」, 「電卓を開いて」, "buka kalender", …), dan 10/10 perintah umum dari pengujian L2.

### Keterbatasan diketahui
- Bagian Windows (`Get-StartApps`, `shell:AppsFolder`) baru dites dengan mock, belum dijalankan di Windows.
- Aplikasi GNOME tanpa nama Jepang di file menunya hanya ditemukan bila LLM mengirim nama Inggrisnya (8/8 pada uji di atas).

## Belum dirilis (2026-10-31): maskot desktop di Linux (Fase L3)

### Ditambahkan
- `core/avatar_x11.py`: maskot `python miku.py` di Linux (X11) setara Windows, lewat python-xlib (sudah terpasang bersama pyautogui, tanpa dependency baru).
  - Transparan: bentuk jendela = piksel sprite (ekstensi SHAPE). Deretan piksel yang sama digabung, jadi satu frame ±90 persegi dan 4 ms; bentuk hanya dikirim saat frame berganti. Klik di area kosong jatuh ke jendela di bawahnya.
  - Selalu di atas, di semua workspace, tidak muncul di taskbar/pager.
  - Fokus keyboard dikembalikan ke jendela yang aktif sebelumnya (setara `SWP_NOACTIVATE`), jadi terminal tidak kehilangan fokus.
  - Diseret lewat X11; posisi awal langsung di pojok kanan bawah tanpa berkedip di tengah.
  - Menu klik kanan "Exit Miku" digambar sendiri (X11 tidak punya menu bawaan seperti `TrackPopupMenu`).
  - Peringatan di sesi Wayland.
- 10 test (`tests/test_avatar_linux.py`): bentuk dari piksel (persegi menutupi tepat piksel yang terisi, tanpa tumpang tindih), menu di dalam jendela, bentuk ikut menu.

### Diubah
- `SpriteAvatar` memindah jendela lewat objek jendela (`_Win32Window` atau `X11Window`), bukan memanggil Win32 langsung. Perilaku Windows sama.

### Diperbaiki
- GUI di Linux: emoji tidak lagi tampil sebagai kotak. Tk tidak bisa menggambar font emoji berwarna, jadi emoji (dan spasi sesudahnya) dibuang dari status, tombol, dan chat. Windows tidak berubah.

### Pengujian
- `pytest`: 229 lulus; di Python sistem seperti CI 224 lulus, 5 dilewati (butuh pygame asli).
- Uji sungguhan di Linux Mint: maskot transparan di atas jendela lain, tetap di atas, tidak di taskbar, fokus user tidak berpindah; diseret (-300, -200) dan callback "mulai bicara" terpanggil; klik kanan → "Exit Miku" menutup mode suara, cleanup jalan, dan model dilepas dari VRAM. Juga dicek lewat `python miku.py` sungguhan.

### Keterbatasan diketahui
- Wayland belum didukung (maskot tidak transparan dan tidak bisa dipindah).
- Belum diuji di monitor dengan skala HiDPI.

## v1.4.0 (2026-10-31): aksi komputer di Linux (Fase L2) dan ekspresi Miku baru

[#18](https://github.com/MocArjunnaja/MikuVision/pull/18) (frame emosi) dan [#19](https://github.com/MocArjunnaja/MikuVision/pull/19) (Fase L2). Rencana Linux: `docs/PLAN_LINUX.md`.

### Ditambahkan
- **Frame emosi Miku** untuk sedih, kesal, malu, bingung, dan berpikir. Sebelumnya kelima emosi ini meminjam frame dari animasi lain yang perasaannya berbeda (sedih memakai frame menari yang tersenyum, kesal memakai pose terkena pukulan).
  - `tools/make_emote_frames.py` membuat 11 frame dari frame asli Miku: beberapa piksel wajah diubah (alis, mulut, rona pipi), lalu diberi tanda emote (air mata, 💢, keringat, "?", "..."). Hasilnya ditulis ke sel kosong 106-116 sprite sheet; frame asli tidak berubah, dan script bisa dijalankan ulang (`--preview` tanpa menulis).
  - sedih 106-107 (air mata menetes), kesal 108-109 (💢 berdenyut), malu 110-111 (rona pipi, mulut bergelombang, keringat), bingung 112-113 ("?" naik-turun), berpikir 114-116 ("." → ".." → "...").
  - Test baru memastikan sheet sama dengan keluaran script dan `config.py` memakai frame baru.
- `core/desktop/`: aksi yang berbeda per OS dalam satu antarmuka, dipilih otomatis. Tool di `core/system_control.py` dan `core/macro_tools.py` tidak lagi memanggil `os.startfile`, pycaw, atau win32 langsung.
  - `windows.py`: kode Windows lama dipindah tanpa perubahan perilaku (App Paths/ShellExecute, pycaw, `WM_CLOSE`).
  - `linux.py`, semua tanpa sudo:
    - volume dan mute: `wpctl`, cadangan `pactl`
    - buka aplikasi: katalog `LINUX_APPS` di `config.py`, tiap alias punya beberapa kandidat (`xed`/`gnome-text-editor`, Nemo/Nautilus, flatpak, browser default, versi web sebagai cadangan); aplikasi dijalankan di sesinya sendiri
    - tutup aplikasi: `wmctrl -c` (`_NET_CLOSE_WINDOW`, sopan seperti tombol ✕)
    - file dan folder: `xdg-open`, nama folder dari `xdg-user-dir`
    - media: `playerctl`, cadangan tombol media
    - teks Jepang: lewat clipboard (`xclip`) + Ctrl+V, karena pyautogui hanya bisa mengetik ASCII
    - peringatan bila sesi Wayland
- Linux: WhatsApp lewat WhatsApp Web (hanya draf; Enter ditekan user; grup belum didukung). Telegram lewat `tg://` bila Telegram Desktop terpasang, selain itu pesan jelas.
- CI GitHub Actions (`.github/workflows/tests.yml`): `pytest` di Ubuntu dan Windows. `tests/conftest.py` men-stub paket suara/GUI/Office yang tidak terpasang.
- 35 test backend Linux (`tests/test_desktop_linux.py`). Perintah desktop sungguhan dilarang di semua test.

### Diubah
- `open_website` dengan nama tanpa titik ("brave") membuka aplikasinya. Sebelumnya membuka alamat `https://brave` (terjadi di sesi GUI: "buka Brave web browser").
- Brave di whitelist Windows, di atas kata umum "browser" (sebelumnya "Brave web browser" membuka Chrome di Windows). Skill aplikasi mengenali brave/terminal/settings.
- Deskripsi tool `open_application`/`open_folder` tidak lagi menyebut "Windows".
- Menutup aplikasi multi-proses (browser): bila ada proses yang berjendela, hanya jendelanya yang ditutup; proses pembantu tanpa jendela tidak lagi di-terminate karena ikut selesai bersama aplikasinya. Berlaku di kedua OS.

### Diperbaiki
- Dokumen Word/PowerPoint yang sudah tersimpan tidak lagi dilaporkan "Gagal…" bila hanya gagal dibuka (LLM bisa membuat ulang). Berlaku di kedua OS.
- Linux: folder dokumen Miku memakai Desktop dari `xdg-user-dir` (namanya bisa diterjemahkan).

### Pengujian
- `pytest`: 219 lulus setelah #18 dan #19 digabung, di venv dan di Python sistem tanpa paket suara/GUI. CI lulus di Ubuntu dan Windows.
- `install.sh` dijalankan ulang di atas v1.4.0: 59 s, `miku.py --test` lulus.
- GUI: "bisa ubah volume ke 30%?" → `set_volume(30)`, volume sistem menjadi 30% (di v1.3.0: "Audio interface not available"). Pesan sedih menampilkan frame sedih yang baru.
- Uji sungguhan di Linux Mint lewat tool Miku:

  | Uji | Hasil |
  |---|---|
  | Volume 55 → 30 → mute → unmute → 55 | lulus |
  | Buka/tutup Kalkulator dan Notepad (xed) | lulus, ditutup sopan lewat `wmctrl -c` |
  | Buka folder Documents (jendela Downloads user tidak tersentuh) | lulus |
  | Dokumen Word dibuka di LibreOffice, lalu ditutup | lulus |

- Tool calling, 10 perintah JP/ID: 9/10 sekali jalan. Satu yang salah ("putar lagu … di YouTube" → `spotify_search`) diulang 5× bersama "carikan lagu …" 5×: 10/10 di branch ini, 8/10 di `main`, jadi itu variasi model yang sudah ada.
- Audit GUI: 12 fungsi yang jalan di thread lain tidak menyentuh widget Tk langsung.

### Keterbatasan diketahui
- Aplikasinya belum dijalankan di Windows. Perilaku Windows dijaga oleh test lama yang kini memakai backend Windows, dan test itu lulus di CI Windows.
- `type_text`/`press_key`/`hotkey` di Linux baru dicek lewat unit test.
- Maskot desktop (`miku.py`) belum transparan di Linux (Fase L3).

## v1.3.0 (2026-10-29): MikuVision jalan di Linux (Fase L1)

Rencana dan hasil audit: `docs/PLAN_LINUX.md`. Diuji di laptop yang sama (dual-boot), Linux Mint 22.3 Cinnamon X11, driver NVIDIA 595 (CUDA 13.2), Ollama 0.40.13.

### Ditambahkan
- `install.sh`, setara `install.ps1`: uv 0.11.2 (checksum SHA-256 dicek), Python 3.10, venv, torch 2.11.0 cu128/cu126/cpu sesuai `nvidia-smi`, `requirements.txt` + `rvc-python` bila model RVC ada, kamus unidic, Ollama dari skrip resminya, peluncur di menu aplikasi + Desktop, verifikasi `miku.py --test`. Paket `apt` dan Ollama ditanya dulu sebelum `sudo`. Idempoten, log di `logs/`.
  - Folder repo di partisi Windows (NTFS/FAT): uv, Python, dan venv disimpan di `~/.local/share/mikuvision/`, karena venv di NTFS lewat FUSE lambat. `MIKU_VENV` untuk lokasi lain.
  - Berhenti dengan pesan jelas bila driver NVIDIA terpasang tapi belum aktif (belum reboot).
- `run.sh`, setara `run.bat`; output dicatat ke `data/logs/gui.log` bila dibuka dari menu.
- `.gitattributes`: teks disimpan LF, `*.sh` LF, `*.bat`/`*.ps1` CRLF, supaya folder yang dipakai Windows dan Linux tidak rusak.
- README: bagian **Linux (eksperimental)** dan troubleshooting Linux.

### Diubah
- `requirements.txt`: `pycaw`, `comtypes`, `pygetwindow`, `pywin32`, `keyboard` hanya untuk Windows (`; sys_platform == "win32"`). Sebelumnya instalasi di Linux gagal total karena `pywin32`.
- `core/system_control.py`: `psutil` dan `pyautogui` di-import terpisah dari pycaw. Di Linux keduanya sebelumnya ikut tidak ter-import, sehingga `get_system_info` kehilangan RAM/CPU/baterai dan `type_text`/`press_key`/`hotkey` selalu menjawab "PyAutoGUI not available".
- `close_application` menolak dengan pesan jelas bila `WM_CLOSE` tidak tersedia (Linux). Tanpa ini, setelah perbaikan import di atas, aplikasi berjendela di Linux akan di-terminate tanpa sempat menawarkan simpan.
- `core/macro_tools.py`: import `pyautogui` tidak lagi crash tanpa DISPLAY (SSH, CI).
- **LLM dimuat lebih dulu** (`miku.py`, `gui.py`): Ollama → Whisper → RVC, bukan Whisper → Ollama → RVC. `AIBrain.preload_model()` memuat model dengan `num_ctx` yang sama dengan chat; setiap request membawa `keep_alive` (`OLLAMA_KEEP_ALIVE = -1` di `config.py`) sehingga model tidak dilepas setelah 5 menit menganggur; `cleanup()` melepasnya (`keep_alive=0`) saat aplikasi ditutup. Start ±1,5–3 s lebih lama. Berlaku juga di Windows.

### Diperbaiki
- **GUI segfault di Linux** saat selesai memuat: thread inisialisasi mengubah label avatar langsung (`_update_avatar`). Python 3.10 dari uv membawa Tcl/Tk 9.0, yang crash bila widget diubah dari luar main thread. Sekarang lewat antrean pesan GUI, seperti update lainnya.
- **Balasan pertama 49 s di Linux:** Whisper + RVC (±1,7 GB) sudah ada di VRAM saat Ollama memuat model, dan Ollama menyisakan cadangan 1 GB, sehingga hanya 29/37 layer masuk GPU (27% CPU). Hal yang sama terjadi setiap kali model dilepas setelah 5 menit menganggur.

  | Mode teks, 2 perintah | Sebelum | Sesudah |
  |---|---|---|
  | Balasan pertama / kedua | 49,4 s / 1,6 s | **1,3 s / 0,9 s** |
  | `ollama ps` | 27%/73% CPU/GPU | 100% GPU, `Forever` |
  | Kecepatan | 14–34 token/s | 59 token/s |
  | VRAM total | - | 5,5 / 6,1 GB; kembali 15 MB setelah keluar |

- **RVC kehabisan VRAM pada balasan panjang** (muncul setelah perbaikan di atas): LLM kini memegang VRAM lebih dulu sehingga sisanya ±300 MB, sedangkan RVC memproses audio sampai 65 s sekaligus di GPU > 4 GB. Balasan 18,7 s gagal (`CUDA out of memory`) dan Miku bersuara MeloTTS biasa. RVC sekarang memotong audio per 6 s di titik sunyi (`RVCConfig.chunk_sec`), mekanisme bawaan RVC untuk GPU kecil.

  | Potongan RVC (balasan 18,7 s, LLM + Whisper di VRAM) | Hasil | Puncak VRAM | Sisa |
  |---|---|---|---|
  | 65 s (bawaan) / 30 s | gagal | - | - |
  | 10 s | lulus | +267 MiB | 46 MiB |
  | **6 s** | lulus, 1,0–1,3 s (pertama 4,6 s) | +207 MiB | 116 MiB |

### Pengujian
- `pytest`: 181 lulus di venv Linux dengan paket asli (9 test baru). `miku.py --test` lulus.
- Instalasi pertama (tanpa Ollama) 7 menit, termasuk build `fairseq`; jalankan ulang 50 s. Ruang: ±11 GB env + cache uv, 1,8 GB cache Hugging Face.
- GUI terbuka dari `run.sh`: status **Ready**, **RVC: ready (0.3s)**, sapaan diputar lewat RVC (siap ±22 s).

  | Linux (s, setelah pemanasan) | Linux | Windows (CHANGELOG lama) |
  |---|---|---|
  | MeloTTS, 1 kalimat (CPU) | 0,90–1,01 | - |
  | RVC konversi | 0,67–0,77 (pertama 4,8) | ±1 (pertama 19,5 dengan unduhan) |
  | Whisper, klip 3,3 s | 0,53–0,58 | 0,54–0,59 |
  | LLM saja di GPU: muat dingin / balasan / kecepatan | 1,8 / 0,3–0,7 / 62–66 token/s | 3,6–4,3 / median 0,9 / - |

- MeloTTS → RVC → Whisper: 「今日は初音ミクです。こうはいい天気ですね」 (Windows: 「今日は初音ミクです。今日はいい天気ですね。」).
- Mode teks: "berapa persen baterai laptop saya" → `get_system_info` (baterai 79%), "kecilkan volume ke 30" → `set_volume` (gagal seperti diharapkan, menunggu Fase L2).

### Keterbatasan diketahui
- Sisa VRAM tipis (±100 MB setelah konversi RVC). Aplikasi lain yang memakai GPU NVIDIA bisa membuat RVC gagal; Miku lalu bersuara MeloTTS biasa. Belum diuji: KV cache Ollama `q8_0` (hemat ±0,5 GB).
- Bila MikuVision crash (tanpa `cleanup()`), model tetap di VRAM sampai Ollama di-restart (`sudo systemctl restart ollama`) atau dilepas dengan `ollama stop qwen3:4b-instruct`.
- Volume, buka aplikasi/folder, tutup aplikasi, WhatsApp/Telegram, dan membuka dokumen setelah dibuat masih khusus Windows (Fase L2). Maskot desktop belum transparan (Fase L3).
- Emoji berwarna di GUI tampil sebagai kotak (Tk di Linux).
- Belum teruji di Linux: mesin tanpa GPU (jalur `--cpu`), distro selain Mint, sesi Wayland, mode suara dengan mic sungguhan.

## v1.2.0 (2026-10-25): nama MikuVision di aplikasi, kode dibersihkan

### Diubah
- Judul jendela GUI "MikuWin v4 - Hatsune Miku" → "MikuVision - Hatsune Miku". Label versi lama (v3, v4, v5, v10, v11) di log, docstring, `--help`, dan `requirements.txt` diganti nama MikuVision; versi aplikasi cukup dicatat di tag rilis dan CHANGELOG.
- Screenshot GUI di README diperbarui.
- README: fitur STT/dokumen Word, contoh perintah dokumen, folder benchmark `experiments/`, troubleshooting salah dengar.

### Dihapus
- File sisa eksperimen di root repo: `inject.py` (menambal `config.py` di path `E:/` lama), `test_regex.py`, `test_yt.py`, `youtube_res.html` (halaman YouTube 1,1 MB), dan `setup.bat` (petunjuk lama: torch cu118, edge-tts; digantikan `install.bat`).
- Konfigurasi edge-tts yang tak terpakai (`TTS_VOICE`, `TTS_RATE`, `TTS_PITCH`).
- 25 import tak terpakai, 7 f-string tanpa placeholder, dan 3 variabel tak terpakai (temuan `ruff --select F`). Import untuk cek ketersediaan modul diberi `# noqa: F401`.

### Pengujian
- `ruff check --select F,E9`: bersih. 172 unit test lulus, `miku.py --test` lulus, judul jendela GUI dicek.

## v1.2.0 (2026-10-25): dokumen Word dibuat beserta isinya

Detail: `experiments/word_tool/RESULTS.md`. Pemicunya sesi GUI 25 Okt: "buatkan dokumen Word … Hukum Newton" hanya dijawab obrolan, lalu ulangan singkatnya hanya membuka Word kosong.

### Diubah
- `create_word_document` diberi deskripsi yang tegas: langsung tulis isinya sendiri, jangan bertanya dulu, jangan `open_application`. Parameter `filename` dan `content` sekarang punya deskripsi; sebelumnya semua parameter tool hanya berlabel "Parameter: <nama>".
- `ToolRegistry.register(..., params={...})` untuk deskripsi per parameter.
- `open_application` merujuk ke `create_word_document` untuk dokumen berisi.
- Regex retry tool mengenali permintaan dokumen (作って, 書いて, buat/buatkan, bikin, tulis, create, write) dan janji 「作ります」.
- Bila permintaan tidak berbahasa Jepang tapi isi dokumen ditulis dalam bahasa Jepang (≥ 30% huruf), isinya diterjemahkan ke bahasa Indonesia dengan satu panggilan tanpa tool. Petunjuk bahasa di prompt tidak cukup untuk model 4B.
- Koreksi STT "hegum" → "hukum", dengan huruf kapital asli dipertahankan.

### Pengujian
| | Sebelum | Sesudah |
|---|---|---|
| Permintaan dokumen (6 × 3, isi ≥ 150 karakter sesuai topik) | 7/18 | **17/18** |
| Kontrol "Buka Word" / 「ワードを開いて」 | 6/6 | 6/6 |
| Tool umum / multi-turn | 50/50 / 8/8 | 50/50 / 8/8 |
| Latensi median permintaan dokumen | 2,2 s | 9,2 s (model kini menulis 500–2.100 karakter) |

- 172 unit test lulus (12 baru di `tests/test_word_document_tool.py`).

## v1.2.0 (2026-10-25): akurasi STT, deteksi bahasa sekali dan pembersihan teks Whisper

Detail, skrip uji, dan semua angka: `experiments/stt_eval/RESULTS.md`.

### Diubah
- `VoiceInput.transcribe()` mendeteksi bahasa sekali, dibatasi ke `WHISPER_LANGUAGES = ("ja", "id")` (Melayu/Jawa/Sunda dihitung sebagai Indonesia), lalu melakukan satu kali decoding. Sebelumnya setiap ucapan didecode paksa sebagai Jepang lalu Indonesia, dan pemenangnya dipilih dengan skor kata kunci.
- Dua bahasa hanya didecode bila deteksi ragu (< 0,8); yang dipilih adalah hasil dengan log-probability lebih baik.
- Segmen yang berulang (`compression_ratio > 2,4`) atau tanpa ucapan dibuang; suhu decoding naik (0 → 0,2 → 0,4) hanya bila hasil suhu 0 ragu.
- Level mic dinaikkan secara linear. `noisereduce` + soft-clip `tanh` dimatikan (`STT_DENOISE = False`).
- `_transcribe_best_effort` / `_score_transcript_intent` yang terduplikasi di `miku.py` dan `gui.py` dihapus; keduanya memanggil `voice_input.transcribe(audio, languages=[...])`.

### Ditambahkan
- `core/stt_text.py`, diadopsi dari alat transkrip TA (`pdf_transkrip.bersihkan`): buang frasa halusinasi ("ご視聴ありがとうございました", "Terima kasih telah menonton", …), pengulangan beruntun, dan huruf di luar aksara bahasa target.

### Diperbaiki
- Ucapan Indonesia seperti "Kecilkan volumenya" / "Matikan suaranya" menjadi 「音量を下げて、音量を下げて、…」 (isi prompt Jepang bocor).
- Koreksi salah dengar mengganti substring: "volume" → "volume**e**", "sejak" → "sEdgeak". Sekarang dicocokkan per kata utuh.
- Koreksi "tolong buka" → "buka" membuang kata dari ucapan user.
- Filter halusinasi lama membuang kalimat sah: semua kalimat pendek berisi "terima kasih", dan apa pun yang memuat 「字幕」 atau 「食べる前に」.

### Pengujian
- 54 klip edge-tts (Indonesia/Jepang, bersih + mic laptop berderau, derau tanpa ucapan):

  | | Lama | Baru |
  |---|---|---|
  | Indonesia bersih / mic laptop | 10/14 / 8/14 | **14/14 / 14/14** |
  | Jepang bersih / mic laptop | 9/10 / 8/10 | 9/10 / **9/10** |
  | Derau → teks palsu | 0/6 | 0/6 |
  | Latensi median | 0,68 s | **0,54 s** |

- 6 rekaman mic asli: hasil sama dengan pipeline lama.
- 160 unit test lulus (31 baru: `tests/test_stt_text.py`, `tests/test_voice_input.py`); `miku.py --test` lulus.

**Keterbatasan:** suara uji sintetis lebih jernih dari suara asli. Untuk mengumpulkan kasus gagal nyata, nyalakan `DEBUG_DUMP_AUDIO` sementara.

## v1.1.0 (2026-10-25): installer satu langkah, RVC jalan di instalasi baru

### Ditambahkan
- `install.ps1` + `install.bat` (double-click): instalasi tanpa Anaconda.
  - [uv](https://docs.astral.sh/uv/) 0.11.2 diunduh ke `.tools\uv` dan checksum SHA-256-nya dicek.
  - Python 3.10 terisolasi di `.tools\python` (tanpa PATH/registry), env `.venv` dibuat dengan `python -m venv`, cache unduhan di `.tools\uv-cache`. Semua di folder aplikasi, tidak di profil C:.
  - PyTorch 2.11.0: build cu128 bila `nvidia-smi` melaporkan CUDA ≥ 12.8, cu126 untuk driver lama, CPU (dengan peringatan) tanpa GPU NVIDIA. Dipasang dalam satu resolusi bersama `requirements.txt` lewat `--torch-backend`, lalu dicek `torch.cuda.is_available()`.
  - `rvc-python==0.1.5` ikut resolusi yang sama bila model RVC ada di `models\miku_default_rvc` (atau `-WithRvc`). `overrides-rvc.txt` menimpa pin `numpy<=1.23.5` milik rvc-python yang bentrok dengan `requirements.txt`. Bila build `fairseq` gagal, instalasi lanjut tanpa RVC dengan petunjuk Build Tools.
  - Kamus `unidic`, cek import modul, Ollama (`winget install Ollama.Ollama` setelah konfirmasi), `ollama pull` model dari `OLLAMA_MODEL` di `config.py`.
  - Shortcut desktop **MikuVision** (`pythonw gui.py`, tanpa konsol) dengan ikon dari sprite.
  - Verifikasi akhir `miku.py --test`, termasuk peringatan bila rvc-python terpasang tapi RVC gagal dimuat.
  - Idempoten: langkah yang sudah beres dilewati; venv rusak atau buatan versi lain dibuat ulang. Log di `logs\install-<waktu>.log`; berhenti dengan pesan penyebab bila gagal.
  - Opsi `-Yes`, `-Cpu`, `-WithRvc`, `-SkipOllama`, `-SkipShortcut`, `-SkipTest`, `-PythonVersion`.
  - `HF_HOME` dan `OLLAMA_MODELS` dibaca dari variabel user bila proses installer belum melihatnya. Saat uji, proses dengan environment lama mengunduh Whisper + MeloTTS (1,75 GB) ke `C:\Users\<user>\.cache\huggingface` walau `HF_HOME` sudah diarahkan ke `D:\hf_home`.
- README ditulis ulang untuk GitHub: header + badge, screenshot GUI, tabel fitur, diagram alur (Mermaid), **Instalasi cepat**, bagian lipat untuk detail installer/manual, dan tabel **Lisensi & kredit** (PCL untuk karakter, status sprite, model RVC, lisensi dependency).

### Diubah
- `run.bat` memakai `.venv` dari installer bila ada.
- `gui.py`: lewat `pythonw.exe` (shortcut) stdout/stderr bernilai `None`; output sekarang ditulis ke `data/logs/gui.log`.
- README: URL clone memakai nama repo baru `MikuVision`.

### Diperbaiki
- **RVC tidak jalan di instalasi baru** (dua bug yang tertutup oleh patch manual di env conda `miku`):
  - torch ≥ 2.6 memuat checkpoint dengan `weights_only=True`, sehingga `hubert_base.pt` (berisi objek `fairseq Dictionary`) ditolak saat konversi pertama. Env `miku` ternyata memakai `fairseq/checkpoint_utils.py` yang diubah tangan menjadi `weights_only=False`. `core/voice_converter.py` kini mengizinkan hanya class `Dictionary` lewat `torch.serialization.add_safe_globals`, tanpa mematikan `weights_only` untuk checkpoint lain.
  - Tanpa pin, uv memilih `rvc-python 0.1.0` yang `load_model()`-nya tidak menerima `index_path`.
- GUI crash diam-diam saat dibuka tanpa konsol: transformers 4.27.4 (dipatok MeloTTS) memanggil `sys.stderr.flush` saat import.
- `tests/conftest.py`: stub `torch` diberi kelas `Tensor` asli. scipy ≥ 1.17 memanggil `issubclass(x, torch.Tensor)` sehingga `test_voice_output.py` gagal di-collect.

### Keputusan
- **Python 3.10, bukan 3.11.** Di 3.11, `fairseq 0.12.2` gagal saat import (`mutable default ... use default_factory`), jadi RVC mati. Python 3.10 berakhir masa dukungannya Oktober 2026; pindah versi menunggu pengganti `fairseq` di `rvc-python`.
- `uv venv` tidak dipakai: launcher `pythonw.exe`-nya identik dengan `python.exe` (uv 0.11.2), sehingga shortcut ikut membuka jendela konsol.

### Pengujian
Clone baru di `D:\02_Research\MikuVision_installtest`, Windows PowerShell 5.1, RTX 4050 (driver 581.86, CUDA 13.0), Ollama 0.40.10.

| Skenario | Hasil | Waktu |
|---|---|---|
| Instalasi pertama, Python 3.11 (unduh uv, Python, torch 2.11.0+cu128 2,6 GB, 180 paket, unidic) | lulus, `miku.py --test` OK | 12 menit |
| Pindah ke Python 3.10 + model RVC ada (unduh torch cp310, build `fairseq`) | lulus, `RVC model loaded in 0.5s (cuda:0)` | 8 menit |
| Jalankan ulang (semua sudah terpasang) | semua langkah dilewati, lulus | 55-58 s |
| Venv rusak (`pyvenv.cfg` hilang) | dibuat ulang dari cache uv, torch tidak diunduh ulang | 105 s |

- `pytest`: 129 lulus di env installer (Python 3.10 dan 3.11) dan env conda `miku`.
- MeloTTS → Whisper: "こんにちは、初音ミクです。今日はいい天気ですね。" terdengar "今日は初音ミクです。今日はいい天気ですね。".
- MeloTTS → RVC → Whisper: konversi pertama 19,5 s (unduh `hubert_base.pt`/`rmvpe.pt`), lalu 4,3 s dan 0,98 s; teks tetap terbaca sama.
- Shortcut desktop: hanya jendela GUI yang muncul (tanpa konsol), status **Ready**, **RVC: ready (0.4s)**, sapaan diputar lewat RVC.
- Belum teruji: mesin tanpa GPU NVIDIA (jalur CPU), mesin tanpa Git/Ollama (jalur `winget`), mesin tanpa Visual Studio Build Tools (build `fairseq` diperkirakan gagal; installer lanjut tanpa RVC), unduhan Whisper/MeloTTS pertama kali (cache Hugging Face mesin uji sudah terisi).

### Keterbatasan diketahui
- Model RVC tidak diunduh otomatis; pengguna menyiapkan sendiri (lihat README).
- Asal sprite maskot belum tercatat.
- Judul jendela GUI masih "MikuWin v4".

---

## 2026-10-25 (#8, #9, #10 sudah di-merge)

### Repo diganti nama: MikuWin_V11_Stable → MikuVision
- URL baru: https://github.com/MocArjunnaja/MikuVision. URL lama dialihkan otomatis oleh GitHub.
- Clone lama cukup menjalankan `git remote set-url origin https://github.com/MocArjunnaja/MikuVision.git`.
- Link PR di CHANGELOG dan perintah clone di README diperbarui. Nama aplikasi di kode tetap MikuWin.

### Paket B: skill on-demand, routine, slash command ([#10](https://github.com/MocArjunnaja/MikuVision/pull/10))
**Ditambahkan**
- `core/skills.py`: 25 tool dikelompokkan menjadi 9 skill (Audio, Aplikasi, Web, Keyboard, Office, Pesan, Memori, Info sistem, Routine). Hanya skill yang cocok dengan permintaan user yang dikirim ke LLM; obrolan tanpa pemicu tetap mengirim semua tool. Bisa dimatikan dengan `SKILL_ROUTING = False`.
- `core/routines.py` + `routines.example.yaml`: routine = rangkaian tool dengan satu perintah ("jalankan mode belajar"). Routine milik user di `data/routines.yaml` menimpa contoh. Setiap langkah tetap lewat gerbang konfirmasi; routine tidak boleh memanggil routine lain.
- `core/commands.py`: slash command tanpa LLM di mode teks dan GUI: `/help /clear /usage /memory /forget /skills /routines /routine /sessions /resume`.
- Daftar routine disisipkan ke system prompt hanya saat skill Routine aktif.
- `docs/PLAN_VISION_AGENT.md`: rencana agent visi (screenshot → paham → mouse/keyboard, dengan iterasi).

**Pengujian**
- 129 unit test lulus.
- Routing skill ON vs OFF (10 perintah × 5):

  | | Akurasi tool | Token prompt (median) | Latensi median | p90 |
  |---|---|---|---|---|
  | OFF | 49/50 | 3.401 | 0,7 s | 4,8 s |
  | ON | 50/50 | 1.545 | 1,0 s | 1,5 s |

- Routine lewat bahasa alami ("テストモードを実行して", "jalankan mode tes"): 3/3. Semua slash command diuji end-to-end di `miku.py --text`.

### Paket A: token meter, log, sesi, memori jangka panjang ([#9](https://github.com/MocArjunnaja/MikuVision/pull/9))
**Ditambahkan**
- **Penghitung token:** angka asli dari Ollama (`prompt_eval_count` / `eval_count`). Ditampilkan setelah tiap balasan di CLI dan di bawah status GUI.
- `core/conversation.py`: `run_turn()`, satu alur think → tool → catat hasil → laporan → log untuk mode teks, suara, dan GUI (sebelumnya tiga salinan kode).
- `core/turn_log.py`: log JSONL per giliran di `data/logs/`.
- **Melanjutkan sesi:** `miku.py --resume [ID]` dan tombol **↺ Sesi lalu** di GUI. Sesi kosong tidak lagi disimpan.
- `core/long_term_memory.py`: tool `remember` / `recall_memory` / `forget`; 15 fakta terbaru disisipkan ke system prompt.

**Diperbaiki**
- Client Ollama diberi timeout 120 s. Sebelumnya request yang tersendat membuat app menunggu selamanya (terjadi sekali saat uji).

**Pengujian**
- 104 unit test.
- `remember` terpanggil 28/30 pada 6 variasi kalimat Jepang/Indonesia. Hanya contoh Indonesia → bahasa Jepang 0/5; contoh dua bahasa diperlukan.
- Fakta disimpan di satu proses, lalu dijawab benar di proses baru.
- GUI: label token dan tombol Sesi lalu dicek lewat screenshot.

**Keterbatasan diketahui**
- Setelah `--resume`, model kadang meniru balasan lamanya sendiri (misalnya "belum ada di ingatan") walaupun riwayat sudah ada di konteks.

### Model default qwen3:4b-instruct + agent loop yang benar ([#8](https://github.com/MocArjunnaja/MikuVision/pull/8))
**Diubah**
- `OLLAMA_MODEL = "qwen3:4b-instruct"`.
- Giliran tool call disimpan dalam format resmi Ollama (`tool_calls` + pesan `role: tool`).
- `think_observation()` memakai hasil tool yang tercatat, bukan pesan "System Observation" palsu.
- Retry dua tahap saat user meminta aksi tapi model tidak memanggil tool.
- `initialize()` mengecek tag model persis.

**Pengujian (10 perintah JP/ID, tool tidak dieksekusi)**

| Model | Akurasi tool | Median | p90 |
|---|---|---|---|
| qwen3:4b-instruct (dengan retry) | 50/50 | 0,9 s | 1,2 s |
| qwen3:4b (Thinking-2507) | 30/30 | 11,5 s | 30,4 s |
| granite4.2:3b | 25/30 | 4,6 s | 57,7 s |

- Percakapan bertingkat (buka lalu tutup Notepad): 0/4 sebelum perbaikan → 8/8.
- Menyimpan tool call sebagai teks biasa tidak membantu (0/4); format `tool_calls` diperlukan (4/4).

---

## 2026-10-24

### Bug dari pengujian end-to-end ([#7](https://github.com/MocArjunnaja/MikuVision/pull/7))
**Diperbaiki**
- **Segfault** saat dua balasan diputar bersamaan (`sounddevice.play()` dari dua thread). Pemutaran audio sekarang antre.
- **Access violation saat keluar**: audio yang masih antre diputar ketika PortAudio sedang ditutup.
- **GUI tidak pernah "Ready"** bila stdout bukan konsol (`print("初音ミク")` → `UnicodeEncodeError`); juga membuat `initialize()` keliru melapor "Gagal connect ke Ollama".
- Input Jepang lewat stdin non-konsol rusak (surrogate) → semua request ke Ollama gagal.
- qwen3:4b mengucapkan penalarannya dan membuka Notepad 6×. Parameter `think` tidak dikirim lagi, isi sampai `</think>` dibuang, tool call kembar dihapus.
- Miku mengaku sudah melakukan aksi padahal tidak memanggil tool. Daftar tool manual dengan nama salah dihapus dari prompt persona.
- `close_application` mematikan paksa semua jendela, termasuk milik user. Sekarang memakai `WM_CLOSE` (seperti tombol ✕), sehingga aplikasi sempat menawarkan simpan.
- Kode wake mati di `miku.py` (memakai 4 atribut yang tidak pernah dibuat) dihapus.

**Pengujian**
- 61 unit test.
- Pipeline MeloTTS → Whisper → MeloTTS → RVC diuji: RVC aktif, konversi ±1,6 s, pitch +6 semitone.
- GUI dicek lewat screenshot `PrintWindow`.

### Supaya bisa dijalankan di laptop lain ([#6](https://github.com/MocArjunnaja/MikuVision/pull/6))
- Folder output yang ditulis langsung sebagai `C:/Users/Arjun/...` (crash di akun lain) diganti `Path.home()`.
- `DEBUG_DUMP_AUDIO` default `False` (sebelumnya setiap rekaman mic disimpan).
- `pytest.ini`, README baru dengan langkah instalasi yang sudah teruji.
- **Pengujian:** clone baru dari GitHub → `pytest` + `python miku.py --test` lulus.

### Avatar memakai frame sprite kosong ([#5](https://github.com/MocArjunnaja/MikuVision/pull/5))
- `thinking`/`confused` menunjuk ke frame transparan, sehingga avatar menghilang. `MIKU_FRAME_H` salah (265, seharusnya 213).
- Ditambah peta emosi bersama `MIKU_EMOTION_FRAMES` dan test yang memverifikasi setiap frame terhadap gambar sprite.

### Integrasi PR #2 dengan perbaikan bug ([#4](https://github.com/MocArjunnaja/MikuVision/pull/4))
- Parser JSON untuk tool bersarang, tanpa `shell=True`, pelacakan PID, `set_volume` lewat pycaw. Kredit: @nashirabbash.
- Diperbaiki: tool call palsu dari objek bersarang, teks balasan terpotong, `Popen(["chrome"])` gagal (App Paths), pencocokan nama proses sebagian.
- PR #2 ditutup dengan komentar penjelasan.

### Perbaikan P0 ([#3](https://github.com/MocArjunnaja/MikuVision/pull/3))
- Pesan user tidak pernah disimpan ke memori.
- Gerbang konfirmasi untuk WhatsApp, Telegram, dan menutup aplikasi.
- Skema `hotkey` (list → array), `num_ctx` 8192, `requirements.txt` disesuaikan dengan import.
- NameError `automation_layer` saat playwright tidak terpasang.

### Pembersihan riwayat repo
- `data/` (percakapan, 10 rekaman WAV mic, `contacts_db.json`) dihapus dari **seluruh** history dengan `git filter-repo`, lalu di-force-push. Backup lokal: `D:\02_Research\MikuWin_backup_20261024\`.
- Belum dilakukan: permintaan penghapusan cache commit lama ke GitHub Support.

---

## Evaluasi tanpa perubahan kode

### Agent visi Fase 0: spike & keputusan model (2026-10-25)
Detail dan skrip: `experiments/vision_phase0/RESULTS.md`.

| | qwen3:4b-instruct | qwen3-vl:4b-instruct | qwen3-vl:2b-instruct |
|---|---|---|---|
| Tool calling MikuWin (routing ON) | 50/50 | 42/50 | - |
| Multi-turn `close_application` | 8/8 | 4/8 | - |
| Pilih elemen, daftar UIA (15 × 3) | 39/45 | **44/45** | 21/45 |
| Pilih elemen, gambar + daftar | - | 43/45 | 31/45 |
| VRAM (`num_ctx` 8192) | 3,9 GB | 3,7 GB | 2,5 GB |
| Cold load | 3,6–4,3 s | 6,5–7,3 s | 4,3–4,6 s |

- UI Automation: 36/36, 34/35, dan 156/163 elemen bernama (Kalkulator, Settings, Explorer), dibaca dalam ≤ 0,34 s.
- Windows OCR: 0,03–0,06 s; hanya bahasa Inggris terpasang, OCR Jepang perlu paket bahasa Windows.
- **Keputusan:** opsi B. Chat dan tool tetap `qwen3:4b-instruct`; `qwen3-vl:4b-instruct` dimuat hanya saat sesi agent visi. Opsi A ditolak karena qwen3-vl:4b sering mengklaim aksi tanpa memanggil tool.

### ASR: Whisper large-v3-turbo vs Qwen3-ASR-0.6B (2026-10-25)
| | Whisper turbo | Qwen3-ASR-0.6B |
|---|---|---|
| CER Jepang sintetis (8 klip) | 23,5% | 24,0% |
| Kesalahan fatal | 0 | 2 |
| Rekaman asli bahasa Indonesia | 1 halusinasi | benar |
| Latensi per klip | 0,59 s | 0,46 s |
| VRAM | +1,1 GB | +1,6 GB |

**Keputusan:** tetap memakai Whisper. Sampelnya kecil, jadi perlu diuji ulang dengan rekaman suara pengguna sebelum diputuskan pindah.

### Perubahan lingkungan lokal (bukan isi repo)
- Env conda `miku`: `faiss-cpu` 1.7.3 → 1.9.0.post1, supaya RVC bisa jalan dengan NumPy 2.
- Env `D:\conda_envs\qwenasr` (5 GB) dan cache `D:\hf_cache` (1,5 GB) untuk uji ASR.
- Model Ollama dipindah ke `D:\ollama_models`, dengan variabel user `OLLAMA_MODELS`. Ruang kosong C naik 2,1 → 18,9 GB.
- Cache Hugging Face dipindah ke `D:\hf_home`, dengan variabel user `HF_HOME`. Robocopy mengubah symlink `snapshots` menjadi file 0 byte; dipulihkan sebagai hardlink ke `blobs` tanpa unduh ulang. Diverifikasi offline: `miku.py --test` + TTS→STT.
- Bersih-bersih (25 Okt):
  - Cache pip dibersihkan (6,0 GB) dan cache conda dibersihkan (`conda clean --all`, 2,0 → 1,1 GB).
  - Dipindah ke Recycle Bin: Whisper large-v3 lama (2,9 GB), cache torch (1,9 GB), env `Mikuve`, `OllamaSetup.exe`, `A Miku Research.rar`.
  - Ruang kosong C: 2,1 GB → 26,1 GB (±31 GB setelah Recycle Bin dikosongkan).
  - Belum dihapus (perlu dihapus manual): `D:\conda_envs\qwenasr` dan `D:\hf_cache` dari uji ASR.
- Agent visi Fase 0: `qwen3-vl:4b-instruct` (3,3 GB) dan `qwen3-vl:2b-instruct` (1,9 GB) di `D:\ollama_models`; paket `uiautomation`, `mss`, `winrt-Windows.*` (OCR) di env `miku`.
