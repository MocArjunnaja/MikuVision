# Peta Jalan MikuVision

**Diperbarui:** 1 Nov 2026. Halaman ini hanya berisi urutan kerja untuk Windows dan Linux. Rinciannya ada di rencana masing-masing: [PLAN_LINUX](PLAN_LINUX.md), [PLAN_SKILLS](PLAN_SKILLS.md), [PLAN_VISION_AGENT](PLAN_VISION_AGENT.md).

---

## 0. Menunggu merge

Tidak ada. #21–#33 dirilis sebagai **v1.5.0** (31 Okt); #35–#38 (MikuVision Setup) dirilis sebagai **v1.6.0** (1 Nov). Ringkasan di CHANGELOG.

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
| 11 | **MikuVision Setup**: installer dengan antarmuka (`MikuVisionSetup.exe`), tanpa GitHub/terminal | Windows dulu, Linux menyusul | [PLAN_INSTALLER](PLAN_INSTALLER.md) | Untuk user yang repot lewat GitHub. Dikerjakan dari sesi Windows; I1 (opsi baru `install.ps1`) dan I2 (kerangka wizard, `python -m miku_setup.main --dry-run`) selesai 31 Okt; I3 (unduh rilis, runner `install.ps1`, progres, batal lalu lanjut), I4 ("Apps & features", Perbarui/Perbaiki/Hapus), dan I5 (`MikuVisionSetup.exe`, workflow rilis) selesai 1 Nov; exe pertama terbit di v1.6.0. Berikutnya Linux (IL) |
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

## 3. Keputusan yang dibutuhkan dari user

1. Shortcut: `Ctrl+Shift+M`, atau kombinasi lain?
2. ~~S2: boleh Miku menyusun skill sendiri dari percakapan, dengan konfirmasi dulu?~~ Ya (31 Okt).
3. Wayland (W1): perlu dikerjakan, atau cukup X11?
4. Agent visi: tugas nyata apa yang paling ingin diotomatiskan, dan aplikasi apa yang tidak boleh disentuh (misalnya aplikasi bank)?
5. ~~Installer: nama, halaman lisensi, folder bawaan, halaman unduhan, dan code signing ([PLAN_INSTALLER](PLAN_INSTALLER.md) bagian 11).~~ Semua sesuai usulan (31 Okt): `MikuVision`, lisensi wajib dicentang, `%LOCALAPPDATA%\Programs\MikuVision`, cukup link Releases, tanpa code signing dulu.
6. Cek pembaruan: menyala sejak awal (bisa dimatikan di `config.py`), atau ditanyakan di halaman Selesai wizard? ([PLAN_INSTALLER](PLAN_INSTALLER.md) bagian 11, keputusan 6)
