# Peta Jalan MikuVision

**Diperbarui:** 1 Nov 2026. Halaman ini hanya berisi urutan kerja untuk Windows dan Linux. Rinciannya ada di rencana masing-masing: [PLAN_LINUX](PLAN_LINUX.md), [PLAN_SKILLS](PLAN_SKILLS.md), [PLAN_VISION_AGENT](PLAN_VISION_AGENT.md).

---

## 0. Menunggu merge

- MikuVision Setup untuk Linux, bertumpuk: [#40](https://github.com/MocArjunnaja/MikuVision/pull/40) (IL1) → [#41](https://github.com/MocArjunnaja/MikuVision/pull/41) (IL2) → [#42](https://github.com/MocArjunnaja/MikuVision/pull/42) (IL3). Semuanya lulus uji terima di Mint, termasuk binary dari CI.
- "Oke Miku" (T2): [#43](https://github.com/MocArjunnaja/MikuVision/pull/43), dari `main`. Suara user 10/10 dan 4/4 permintaan di `python miku.py` di Linux.

**Keputusan user (1 Nov): tunggu cek ulang di Windows (bagian 2a) dulu**. Keempat PR digabung di branch lokal `test/v1.7.0`, supaya cukup sekali boot ke Windows. Sesudah lulus: merge #40 → #41 → #42 → #43, lalu rilis **v1.7.0** (Setup untuk Linux + "Oke Miku"). Sebelumnya: #21–#33 dirilis sebagai **v1.5.0** (31 Okt); #35–#38 (MikuVision Setup) sebagai **v1.6.0** (1 Nov).

## 1. Urutan berikutnya

| # | Pekerjaan | OS | Rencana | Alasan urutan |
|---|---|---|---|---|
| 1 | ~~Daftar cek di Windows~~ | Windows | bagian 2 di bawah | Selesai 31 Okt; dua baris yang gagal diperbaiki di #31–#33. Yang belum: suara oleh manusia, sebagian angka L4 |
| 2 | ~~Rilis v1.5.0~~ | keduanya | CHANGELOG | Dirilis 31 Okt, mengumpulkan #21–#33 |
| 3 | ~~**T1**: shortcut keyboard untuk mulai bicara~~ | keduanya | [VISION bagian 5, T1](PLAN_VISION_AGENT.md) | Selesai di Linux (31 Okt); Windows lewat daftar cek di bagian 2 |
| 4 | ~~Agent visi Fase 1: membaca layar~~ | keduanya | VISION Fase 1 | Selesai di Linux (31 Okt). Windows: `describe_screen` lewat daftar cek di bagian 2, `find_on_screen` (UI Automation) masuk Fase 2 |
| 5 | ~~S2: "simpan ini sebagai skill"~~ | keduanya | SKILLS S2 | Selesai (31 Okt); keputusan 2: ya, dengan konfirmasi |
| 6 | ~~T2: "Oke Miku" di mode suara~~ | keduanya | VISION T2 | Selesai di Linux (1 Nov; `feat/wake-phrase`): suara user 10/10, 0 pemicu palsu (termasuk 20 menit musik), GPU diam saat hening; butuh volume mic sekitar 20%. Belum: Windows |
| 7 | Agent visi Fase 2–3: Miku menggerakkan mouse/keyboard | keduanya | VISION Fase 2–3 | Memakai strategi gabungan dari spike Linux |
| 8 | L4: benchmark Linux vs Windows | keduanya | LINUX L4 | Butuh angka Windows dari bagian 2 |
| 9 | L5: uji di VM Fedora, Arch, Ubuntu | Linux | LINUX L5 | Installer sudah siap, belum dicoba di distro aslinya |
| 10 | W1: Wayland | Linux | VISION, LINUX L5 | Menunggu keputusan 3 di bagian 3 |
| 11 | **MikuVision Setup**: installer dengan antarmuka (`MikuVisionSetup.exe`), tanpa GitHub/terminal | Windows dulu, Linux menyusul | [PLAN_INSTALLER](PLAN_INSTALLER.md) | Untuk user yang repot lewat GitHub. Dikerjakan dari sesi Windows; I1 (opsi baru `install.ps1`) dan I2 (kerangka wizard, `python -m miku_setup.main --dry-run`) selesai 31 Okt; I3 (unduh rilis, runner `install.ps1`, progres, batal lalu lanjut), I4 ("Apps & features", Perbarui/Perbaiki/Hapus), dan I5 (`MikuVisionSetup.exe`, workflow rilis) selesai 1 Nov; exe pertama terbit di v1.6.0. Linux (IL): IL1 (opsi `install.sh`) dan IL2 (wizard yang sama jalan di Linux, uji terima di Mint lulus) selesai 1 Nov; IL3 (binary Linux di rilis, #42) selesai 1 Nov; menunggu cek ulang di Windows (bagian 2a), lalu merge #40–#42 dan rilis v1.7.0 |
| 12 | Cek pembaruan dari aplikasi: Miku memberi tahu bila ada rilis baru, satu klik ke Setup mode Perbarui | keduanya | [PLAN_INSTALLER bagian 6, fase I6](PLAN_INSTALLER.md) | Butuh `version.json` di rilis (I5) dan mode Perbarui (I4). Sekarang aplikasi bahkan belum punya nomor versi; menunggu keputusan 6 di bagian 3 |

## 2. Daftar cek di Windows

Dijalankan setelah boot ke Windows, di folder repo yang sama (`D:`). Lakukan setelah #22–#25 merge, atau checkout `feat/skill-from-chat` yang sudah memuat semuanya (termasuk T1, Fase 1, dan S2).

**Hasil 31 Okt** (Windows 11, RTX 4050, skala layar 125%; rincian dan log di CHANGELOG #30–#32 dan entri skill bernilai tetap):
- Lulus: install ulang, pytest, volume/mute/media, buka/tutup katalog, folder/dokumen/WhatsApp, maskot, buka aplikasi apa pun + cache, shortcut (setelah #31: bentrok dengan aplikasi lain kini diberi tahu).
- Lulus dengan catatan:
  - urutan muat VRAM: 100% GPU, panggilan LLM pertama 1,3 s, tapi giliran pertama 3,9 s bila model perlu diminta ulang memanggil tool;
  - membaca layar: teks terbaca persis di skala 125%, tukar model ±13 s, pemuatan pertama ±30 s.
- Skill buatan user: penyimpanan benar setelah #32, dan "mode fokus dong" menjalankan semua langkah skill bernilai tetap. Giliran "kecilkan volume ke 20 lalu putar lofi di youtube" masih hanya mengatur volume di ±1 dari 3 run (qwen3:4b), sehingga skill yang tersimpan pun hanya berisi volume. Keputusan user (31 Okt): diterima untuk v1.5.0, keterbatasannya dicatat di CHANGELOG.
- Belum diuji: bicara sungguhan ke mikrofon, dan sebagian angka L4.

**Persiapan**
1. `git pull`, lalu jalankan ulang `install.ps1` (langkah yang sudah beres dilewati).
2. `pytest`: hasilnya harus sama dengan CI Windows.

**Fitur yang belum pernah dijalankan di Windows**

| Fitur | Berubah di | Cara cek | Lulus bila |
|---|---|---|---|
| Volume, mute, media | v1.4.0: backend dipindah ke `core/desktop/windows.py` | "kecilkan volume ke 30", "mute", "lagu berikutnya" | Sama seperti v1.3.0 |
| Buka/tutup aplikasi katalog | v1.4.0 | "buka notepad", "tutup notepad", "buka kalkulator" | Ditutup lewat WM_CLOSE, setelah konfirmasi |
| Folder, dokumen, WhatsApp | v1.4.0 | "buka folder downloads", "buatkan dokumen Word berisi …", draf WhatsApp | Dokumen dibuat dan terbuka; pesan tidak terkirim tanpa konfirmasi |
| Maskot | #22: jendela lewat `_Win32Window` | `python miku.py`: transparan, seret untuk bicara, menu klik kanan | Sama seperti v1.3.0 |
| Buka aplikasi apa pun + cache | #23: `Get-StartApps`, `shell:AppsFolder` | Aplikasi di luar katalog, termasuk aplikasi Store (misalnya Paint, Photos); buka sekali lagi; `/apps` | Terbuka, tercatat di `/apps`, kedua kali dari cache. Catat lama `Get-StartApps` |
| Skill buatan user | #24, S2 | "buatkan laporan harian: tadi …", "putar lagu buat belajar", `/skills`. Lalu "kecilkan volume ke 20 lalu putar lofi di youtube" → "simpan ini sebagai skill, namanya mode fokus" → "mode fokus dong"; `/skill forget mode fokus` | Dokumen dibuat lalu foldernya terbuka; volume diatur lalu YouTube diputar. Pratinjau skill tampil di dialog Yes/No, file ada di `data\skills\mode-fokus\`, dan "mode fokus dong" mengulang kedua langkah |
| Urutan muat VRAM | v1.3.0, belum diukur di Windows | Waktu balasan pertama, `ollama ps` | Balasan pertama ≤ 3 s, model 100% di GPU |
| Shortcut `Ctrl+Shift+M` (T1) | `feat/hotkey-trigger`: library `keyboard`, named pipe untuk `--trigger` | `python miku.py`, tekan shortcut dari Notepad/browser 10×; GUI: tekan, bicara, tekan lagi; `python miku.py --trigger` di terminal lain | 10/10 mulai merekam tanpa jeda terasa; pesan jelas bila kombinasi sudah dipakai aplikasi lain; `--trigger` ≤ 1 s |
| Membaca layar (Fase 1) | `feat/vision-read-screen`: screenshot jendela aktif lewat `GetForegroundWindow`, tukar model dengan `num_gpu` | Simpan `qwen3-vl:4b-instruct` di D (`OLLAMA_MODELS`), lalu `ollama pull`. Buka dialog error atau Notepad berisi teks, tekan shortcut, "error apa ini?" / "bacakan tulisan di layar". Coba juga di layar dengan skala 125%; `python experiments/vision_linux/swap_bench.py --vl-ctx 4096 --vl-gpu 999 --reload-gpu 999` | Teks terbaca tepat dari jendela yang benar (bukan bergeser karena skala DPI); `ollama ps` 100% GPU setelah giliran; catat waktu tukar model |

**Angka untuk L4** (skrip yang sama dengan Linux)
- `python experiments/skills/bench_skills.py 3`
- benchmark tool calling 10 perintah JP/ID × 5, sama dengan Fase 0
- `experiments/stt_eval`, latensi MeloTTS/RVC, VRAM, waktu start

**Bahan untuk rencana berikutnya**
- Agent visi Fase 2: `find_on_screen` versi Windows butuh UI Automation (`uiautomation`, dipakai di spike Fase 0 Windows); catat apakah paket itu terpasang tanpa masalah. OCR tidak dibutuhkan di Fase 1 karena qwen3-vl membaca teks dari screenshot.

## 2a. Cek ulang di Windows sebelum v1.7.0 (#40–#43)

**Persiapan**
1. Folder repo bersama (`D:`) sudah di branch lokal **`test/v1.7.0`**: `feat/setup-linux-binary` (#40–#42) digabung dengan `feat/wake-phrase` (#43). Branch ini belum di GitHub, jadi jangan `git pull`; cukup pastikan `git branch --show-current` menunjukkan `test/v1.7.0`.
2. Jalankan ulang `install.ps1` (langkah yang sudah beres dilewati), lalu `pytest`. Hasilnya harus sama dengan CI Windows di #42 dan #43.
3. Catat hasil Setup di entri CHANGELOG IL3, dan hasil "Oke Miku" di entri T2 (bagian Pengujian).

**Sesudahnya**
- **Semua lulus:** merge #40 → #41 → #42, lalu perbarui #43 dengan `main` (konflik CHANGELOG sudah diselesaikan di `test/v1.7.0`: entri T2 di atas entri IL), merge #43, lalu rilis v1.7.0.
- **Ada yang gagal:** perbaiki di branch PR-nya (`feat/setup-linux-binary` untuk Setup, `feat/wake-phrase` untuk "Oke Miku"), gabungkan lagi ke `test/v1.7.0`, lalu cek lagi.

### Setup untuk Linux (#40–#42)

Setup untuk Linux menyentuh kode yang juga dipakai Windows. Di Linux semuanya lulus (CHANGELOG IL2 dan IL3), dan CI Windows lulus; yang berikut perlu dicoba dengan exe sungguhan. Exe-nya ada di artifact **rilis-uji** dari workflow `release-setup` di PR #42 (zip `0.0.0-pr42`, `version.json`, `SHA256SUMS`), atau bangun sendiri dengan `pyinstaller miku_setup.spec`.

| Cek | Kenapa | Lulus bila |
|---|---|---|
| Pasang → Perbarui → Perbaiki → Hapus → pasang lagi, seperti uji terima v1.6.0 | Tanda tangan beberapa fungsi bersama berubah (`install_args`, `install_command`, `validate_selection`, `default_install_dir` menerima `platform`); perilaku Windows seharusnya sama | Semua lulus seperti v1.6.0; argumen di log tetap `-Yes -Progress -StartMenu -SkipShortcut …` |
| Tombol **Tutup** dan **X** di halaman terakhir Hapus | Bug yang ditemukan di uji Linux: `finish()` hanya ada di halaman Selesai, jadi Tutup tidak menutup jendela (juga di Windows). Diperbaiki di #41 | Jendela tertutup |
| **Perbarui** dari "Apps & features" → Modify (`.tools\MikuVisionSetup.exe`) | Exe satu file PyInstaller berjalan sebagai dua proses dengan exe yang sama; proses bootloader-nya ada di dalam InstallDir. Di Linux #41 mengabaikannya, kode Windows tidak diubah | Tidak muncul "Tutup MikuVision dulu (MikuVisionSetup.exe masih berjalan)". Bila muncul, terapkan aturan yang sama di `running_processes` untuk Windows |
| Log Setup | Teks log memakai konstanta `ENTRY_PLACE`, jadi tertulis `Tercatat di "Apps & features"` (dengan tanda kutip) | Hanya beda kutip |

### "Oke Miku" (#43)

Dijalankan dari kode sumber di `test/v1.7.0` (`python miku.py`, mode suara, dan `python gui.py`). Di Windows mode suara kini **membuka mikrofon terus-menerus secara bawaan** (`WAKE_PHRASE_ENABLED`), dan itu belum pernah dicoba di Windows. Hasil Linux dan cara ujinya ada di `experiments/wake_eval/RESULTS.md`.

| Cek | Kenapa | Lulus bila |
|---|---|---|
| Level mic | Di Linux mic internal semula +60 dB: 30% input memberi 2–5/10, 20% memberi 9–10/10. Miku memberi peringatan bila derau 3 detik pertama terlalu tinggi | Tidak muncul `[Oke Miku] Volume mikrofon terlalu tinggi …`. Bila muncul, turunkan volume input di Settings → System → Sound → Input sampai hilang, lalu catat nilainya |
| Uji berpandu: `python experiments/wake_eval/live_guided.py --out hasil.json` | Angka yang sama dengan Linux (15 aba-aba; tidak ada aksi yang dijalankan) | "Oke Miku" ≥ 9/10, kalimat biasa 5/5 tidak memicu, perintah tertangkap (misalnya "buka Notepad") |
| `python miku.py`: "Oke Miku" saja | Alur sapa lalu rekam. Di Windows, pendengar dan perekam sama-sama membuka input mikrofon (dua stream), belum pernah dicoba | Miku menjawab 「はい、何でしょうか？」, lalu permintaan berikutnya ("buka Notepad") dijalankan |
| "Oke Miku, kecilkan volume ke tiga puluh" sekaligus | Perintah dipotong sesudah "Miku" (cap waktu kata Whisper) dan langsung diproses | Volume 30% tanpa sapaan; log `[Oke Miku] You: kecilkan volume ke 30` |
| Kalimat biasa, misalnya "nanti malam hujan ya" | Tidak boleh memicu | Hanya baris `(terdengar: '…')` |
| "Oke Miku" diucapkan saat Miku sedang bicara | Audio dibuang selama Miku merekam, memproses, atau bicara | Tidak memicu sesi baru |
| Shortcut `Ctrl+Shift+M`, menyeret maskot, dan `python miku.py --trigger` | Jalur lama di loop yang sama, yang dipecah ulang di #43 | Ketiganya tetap mulai merekam |
| GUI, tombol **Wake Phrase** ON lalu OFF | GUI memakai pendengar yang sama (bukan lagi potongan 1,8 s) | ON: "Oke Miku" → sapaan lalu rekam, atau perintah langsung jalan. OFF: tidak bereaksi lagi |
| Diam 3 menit dengan pendengar aktif | Whisper hanya jalan saat ada ucapan | Task Manager: CPU proses ±5% atau kurang, GPU diam |
| Keluar (Ctrl+C atau menu maskot → Exit) | Stream mikrofon pendengar ditutup | Tanpa error; aplikasi lain bisa memakai mikrofon |

## 3. Keputusan yang dibutuhkan dari user

1. Shortcut: `Ctrl+Shift+M`, atau kombinasi lain?
2. ~~S2: boleh Miku menyusun skill sendiri dari percakapan, dengan konfirmasi dulu?~~ Ya (31 Okt).
3. Wayland (W1): perlu dikerjakan, atau cukup X11?
4. Agent visi: tugas nyata apa yang paling ingin diotomatiskan, dan aplikasi apa yang tidak boleh disentuh (misalnya aplikasi bank)?
5. ~~Installer: nama, halaman lisensi, folder bawaan, halaman unduhan, dan code signing ([PLAN_INSTALLER](PLAN_INSTALLER.md) bagian 11).~~ Semua sesuai usulan (31 Okt): `MikuVision`, lisensi wajib dicentang, `%LOCALAPPDATA%\Programs\MikuVision`, cukup link Releases, tanpa code signing dulu.
6. Cek pembaruan: menyala sejak awal (bisa dimatikan di `config.py`), atau ditanyakan di halaman Selesai wizard? ([PLAN_INSTALLER](PLAN_INSTALLER.md) bagian 11, keputusan 6)
