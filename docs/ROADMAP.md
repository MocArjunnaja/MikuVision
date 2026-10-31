# Peta Jalan MikuVision

**Diperbarui:** 31 Okt 2026. Halaman ini hanya berisi urutan kerja untuk Windows dan Linux. Rinciannya ada di rencana masing-masing: [PLAN_LINUX](PLAN_LINUX.md), [PLAN_SKILLS](PLAN_SKILLS.md), [PLAN_VISION_AGENT](PLAN_VISION_AGENT.md).

---

## 0. Menunggu merge

| PR | Isi | Urutan |
|---|---|---|
| #22 | Maskot transparan di Linux (L3) | Pertama |
| #23 | Buka aplikasi apa pun dari menu sistem + cache; rencana skill | Setelah #22 |
| #24 | Skill buatan user (S1); spike agent visi di Linux | Setelah #23 |
| #25 | Installer untuk dnf/pacman/zypper (L5); peta jalan ini | Setelah #24 |
| #26 | T1: shortcut `Ctrl+Shift+M` dan `miku.py --trigger` | Setelah #25 |
| (baru) | Agent visi Fase 1: Miku membaca layar (branch `feat/vision-read-screen`) | Setelah #26 |
| #21 | README lebih ringkas | Kapan saja; bentrok kecil dengan #25 di teks instalasi Linux |

Setelah semuanya merge dan daftar cek Windows (bagian 2) lulus: rilis **v1.5.0**.

## 1. Urutan berikutnya

| # | Pekerjaan | OS | Rencana | Alasan urutan |
|---|---|---|---|---|
| 1 | Daftar cek di Windows | Windows | bagian 2 di bawah | Sejak v1.3.0, kode Windows berubah tanpa pernah dijalankan di Windows: backend dipindah (L2), jendela maskot dibungkus ulang (#22), pencarian aplikasi ditambah (#23). Selama ini hanya dites di CI |
| 2 | Rilis v1.5.0 | keduanya | CHANGELOG | Mengumpulkan #21–#25 |
| 3 | ~~**T1**: shortcut keyboard untuk mulai bicara~~ | keduanya | [VISION bagian 5, T1](PLAN_VISION_AGENT.md) | Selesai di Linux (31 Okt); Windows lewat daftar cek di bagian 2 |
| 4 | ~~Agent visi Fase 1: membaca layar~~ | keduanya | VISION Fase 1 | Selesai di Linux (31 Okt). Windows: `describe_screen` lewat daftar cek di bagian 2, `find_on_screen` (UI Automation) masuk Fase 2 |
| 5 | S2: "simpan ini sebagai skill" | keduanya | SKILLS S2 | Menunggu keputusan 2 di bagian 3 |
| 6 | T2: "Oke Miku" di mode suara | keduanya | VISION T2 | Perlu gerbang VAD dan pengukuran pemicu palsu |
| 7 | Agent visi Fase 2–3: Miku menggerakkan mouse/keyboard | keduanya | VISION Fase 2–3 | Memakai strategi gabungan dari spike Linux |
| 8 | L4: benchmark Linux vs Windows | keduanya | LINUX L4 | Butuh angka Windows dari bagian 2 |
| 9 | L5: uji di VM Fedora, Arch, Ubuntu | Linux | LINUX L5 | Installer sudah siap, belum dicoba di distro aslinya |
| 10 | W1: Wayland | Linux | VISION, LINUX L5 | Menunggu keputusan 3 di bagian 3 |

## 2. Daftar cek di Windows

Dijalankan setelah boot ke Windows, di folder repo yang sama (`D:`). Lakukan setelah #22–#25 merge, atau checkout `feat/vision-read-screen` yang sudah memuat semuanya (termasuk T1 dan Fase 1).

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
| Skill buatan user | #24 | "buatkan laporan harian: tadi …", "putar lagu buat belajar", `/skills` | Dokumen dibuat lalu foldernya terbuka; volume diatur lalu YouTube diputar |
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
2. S2: boleh Miku menyusun skill sendiri dari percakapan, dengan konfirmasi dulu?
3. Wayland (W1): perlu dikerjakan, atau cukup X11?
4. Agent visi: tugas nyata apa yang paling ingin diotomatiskan, dan aplikasi apa yang tidak boleh disentuh (misalnya aplikasi bank)?
