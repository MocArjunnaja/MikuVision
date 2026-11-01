# Changelog

Catatan perubahan, pengujian, dan keputusan teknis MikuVision (dulu MikuWin V11).
Format mengikuti [Keep a Changelog](https://keepachangelog.com/id/1.1.0/). Entri terbaru di atas.
Angka benchmark diukur di laptop pengembang: RTX 4050 Laptop 6 GB, Windows 11, Ollama 0.40.10.

---

## Belum dirilis (2026-11-01): cek keamanan, folder Setup yang aman, README "Oke Miku"

### Diperbaiki
- **Setup tidak lagi memakai folder yang sudah berisi file lain.** Sebelumnya folder aplikasi boleh folder apa pun yang bisa ditulis (misalnya `D:\` atau `Documents`), dan Hapus lalu menghapus seluruh isinya kecuali `data/`. Folder model juga: "Hapus juga model" menghapus seluruh folder itu.
  - Halaman 4 sekarang menolak akar drive/filesystem dan folder home. Folder aplikasi harus baru, kosong, berisi MikuVision, atau sisa Hapus (`data/`, `logs/`); clone git ditolak (pakai `install.bat`/`install.sh`). Folder model harus baru, kosong, atau hanya berisi `ollama/` dan `huggingface/`.
  - Hapus menolak folder yang tidak tampak seperti MikuVision (tanpa `gui.py` dan `miku_setup/`), dan menghapus kedua tanda itu paling akhir, supaya Hapus yang diulang (file terkunci) tetap mengenali foldernya.
  - "Hapus juga model" hanya menghapus `ollama/` dan `huggingface/` di folder model, lalu foldernya bila sudah kosong.
- `.gitignore`: `logs/` (rekaman konsol uji seperti `logs/oke-miku-uji.txt` sebelumnya tidak ter-ignore karena bukan `*.log`), `hasil*.json` dari uji suara berpandu, `build/` dan `dist/` dari PyInstaller, `.ruff_cache/`, dan `.claude/worktrees/`.
- Exe Setup: Pillow 12.1.1 → 12.3.0 (versi terakhir yang mendukung Python 3.10). Pillow 13 butuh Python 3.11; Setup hanya membuka sprite PNG bawaannya, jadi celah decoder Pillow tidak terjangkau.
- Workflow `release-setup`: izin bawaan hanya baca; hanya job yang melampirkan ke rilis yang boleh menulis.
- README: "Oke Miku" di Fitur, Menjalankan, Data & privasi (mikrofon terbuka terus di mode suara, diproses lokal, tidak disimpan), dan Troubleshooting; aturan folder Setup.

### Pengujian dan cek
- 5 test baru (folder aplikasi/model, akar drive dan home, folder bukan MikuVision tidak dihapus, model hanya subfolder installer) dan 1 test diperluas (tanda dihapus terakhir). Tiga mutasi (validasi folder dimatikan, pengaman Hapus dimatikan, Hapus model seluruh folder) masing-masing membuat test gagal.
- Exe dibangun ulang dengan Pillow 12.3.0 dan terbuka di `--dry-run` (masih berjalan setelah 15 s).
- **Riwayat git (136 commit):** tidak ada token GitHub, Hugging Face, OpenAI, AWS, atau private key. Satu-satunya temuan adalah kunci API web YouTube publik dari `youtube_res.html` (dihapus di `ec09647`; 5 alert secret scanning sudah ditutup sebagai false positive). Tidak ada nomor telepon atau file data user yang pernah di-commit.
- **GitHub:** secret scanning dan push protection aktif. Dependabot alerts belum aktif.
- **`pip-audit`** pada venv aplikasi (202 paket): `transformers` 4.27.4 (dipatok MeloTTS/RVC; celahnya terutama saat memuat model tak tepercaya, sedangkan MikuVision hanya memuat model dari Hugging Face resmi), `pillow` 12.3.0, `filelock`, `setuptools`, dan `hydra-core`. Belum dinaikkan karena butuh uji ulang suara dan RVC.

---

## v1.7.0 (2026-11-01): ringkasan rilis

**MikuVision Setup untuk Linux** dan **"Oke Miku"**. Rilis ini melampirkan `MikuVisionSetup-linux-x86_64` di samping `MikuVisionSetup.exe`: user Linux cukup mengunduh, mengizinkannya dijalankan, lalu membukanya. Di mode suara dan GUI, Miku kini bisa dipanggil dengan mengucapkan "Oke Miku", sendiri atau langsung dengan perintahnya ("Oke Miku, kecilkan volume ke tiga puluh"); shortcut `Ctrl+Shift+M` dan menyeret maskot tetap jalan. Rinciannya ada di entri v1.7.0 di bawah, satu per bagian.

| PR | Isi |
|---|---|
| [#40](https://github.com/MocArjunnaja/MikuVision/pull/40) | Opsi `install.sh` untuk Setup di Linux (IL1) |
| [#41](https://github.com/MocArjunnaja/MikuVision/pull/41) | MikuVision Setup jalan di Linux (IL2); Setup yang dibuka dari "Apps & features" tidak lagi menolak dirinya sendiri di Windows |
| [#42](https://github.com/MocArjunnaja/MikuVision/pull/42) | Binary Linux di workflow rilis (IL3) |
| [#43](https://github.com/MocArjunnaja/MikuVision/pull/43) | "Oke Miku" di mode suara dan GUI (T2) |

**Uji:** Linux Mint 22.3 (pasang, batal lalu lanjut, Perbarui, Perbaiki, Hapus, pasang lagi; juga dengan binary dari CI) dan Windows 11 (pasang → Perbarui → Perbaiki dari Modify → Hapus → pasang lagi dengan exe dari CI; "Oke Miku" dengan suara user). "Oke Miku": Linux 10/10, Windows 9/10 wake phrase tertangkap; kalimat biasa tidak memicu di keduanya; 0 pemicu palsu selama 20 menit musik (Linux). CI hijau di Ubuntu dan Windows; 705 test lulus di venv aplikasi Windows.

**Diperbaiki dari v1.6.0:** di Windows, Perbarui/Perbaiki dari "Apps & features" → Modify selalu menjawab "Tutup MikuVision dulu (MikuVisionSetup.exe masih berjalan)". Unduh Setup v1.7.0 dari rilis ini untuk memperbarui instalasi v1.6.0.

**Keterbatasan yang diketahui**
- Mode suara kini membuka mikrofon terus-menerus secara bawaan (`WAKE_PHRASE_ENABLED` di `config.py`). Semua tetap diproses lokal; Whisper hanya jalan saat ada ucapan.
- Volume mic menentukan: bila muncul "Volume mikrofon terlalu tinggi", turunkan volume input (laptop uji Linux: ±20%; Windows: 45% sudah cukup).
- Lagu yang liriknya berbunyi "oke Miku" akan memicu Miku. Perintah berbahasa Jepang yang diucapkan sekaligus kadang tertulis katakana.
- Binary Linux baru diuji di Linux Mint; Fedora, Arch, dan openSUSE belum. Exe Windows dan binary Linux belum ditandatangani.

---

## v1.7.0 (2026-11-01): "Oke Miku" di mode suara (T2)

Cukup ucapkan **"Oke Miku"** untuk mulai bicara, tanpa menyeret maskot atau menekan shortcut. Perintah boleh langsung menyusul ("Oke Miku, buka Notepad"). Diuji dengan suara user: 10/10 di putaran terakhir.

### Ditambahkan
- `core/wake.py`:
  - **Gerbang suara.** Mikrofon terus terbuka, tetapi gerbang VAD (webrtcvad mode 3, CPU) memotong audio jadi segmen ucapan, dan Whisper hanya jalan untuk segmen itu; saat hening Whisper tidak jalan sama sekali. 0,8 s audio sebelum segmen ikut disimpan, supaya awal kata tidak terpotong.
  - **Pengecekan.** Tiap segmen dicek sekali; ucapan panjang tanpa jeda dicek per jendela 2,5 s (tumpang tindih 1 s). Cek memakai satu bahasa tetap (`WAKE_CHECK_LANGUAGE = "id"`), beam 1, dan prompt `WAKE_CHECK_PROMPT = "Oke Miku."`. Tanpa prompt itu, Whisper berbahasa Indonesia menulis "Miku" sebagai "minggu", "menurut", atau "me too".
  - **Perintah yang ikut terucap.**
    - Audio dipotong di akhir kata "Miku" (cap waktu kata Whisper), lalu ditranskripsi sendiri dengan deteksi bahasa. Tanpa ini, "Oke Miku, buka Notepad" ikut terdeteksi sebagai bahasa Jepang (「ブカ、Notepad」).
    - Perintah ditahan 0,6 s; bila user melanjutkan sesudah jeda singkat, kedua bagian digabung.
  - **Ejaan yang diterima:**
    - "Oke/OK/Okay/Okey Miku", 「オッケー、ミク」, 「オーケーミク」, "Miku-chan"/「ミクちゃん」;
    - salah dengar "migu", "niku", "mitu", "migo", "Miuku", "emigu", "amiku";
    - wake phrase yang tertulis dua kali dibuang.
  - **Tidak mendengar diri sendiri.** Selama Miku merekam, memproses, atau bicara (ditambah 0,5 s), audio dibuang.
  - **Peringatan mic.** Muncul sekali bila derau 3 detik pertama terlalu tinggi (RMS > 0,05): "turunkan volume input ke sekitar 20–30%".
  - **Yang terdengar ditampilkan.** Di mode suara, ucapan yang bukan "Oke Miku" dicetak sebagai `(terdengar: '…')` (`WAKE_SHOW_HEARD`), supaya kelihatan bahwa Miku mendengar tetapi tidak mengenali wake phrase-nya. Di uji pertama di aplikasi, 6 menit tanpa keluaran apa pun membuat tidak jelas apakah user belum mencoba atau tidak terdengar.
- `VoiceInput.transcribe`: `prompt` (menggantikan prompt kosakata) dan `word_timestamps` (mengisi `last_words` dengan kata, waktu, dan peluangnya).
- **Mode suara** (`python miku.py`): aktif bawaan (`WAKE_PHRASE_ENABLED` di `config.py`).
  - "Oke Miku" saja → Miku menjawab 「はい、何でしょうか？」 lalu merekam.
  - "Oke Miku, …" → perintahnya langsung diproses.
  - Pesan cara pakai menyebut ketiga cara: seret maskot, shortcut, atau "Oke Miku".
- `experiments/wake_eval/`:
  - set uji edge-tts dan evaluasinya (`make_set.py`, `run_eval.py`);
  - uji mikrofon tanpa ucapan (`live_idle.py`);
  - uji suara berpandu dengan opsi rekam (`live_guided.py`) dan pemutar ulang rekaman (`replay.py`);
  - hasil di `RESULTS.md`.

### Diubah
- **GUI, tombol Wake Phrase:** memakai pendengar yang sama.
  - Sebelumnya potongan tetap 1,8 s terus ditranskripsi Whisper walau tidak ada yang bicara, dan "Oke Miku" yang jatuh di batas potongan bisa terlewat.
  - "Jendela percakapan" 25 s dengan potongan 4 s dihapus: tiap permintaan diawali "Oke Miku", lalu direkam sampai user diam.
- `tests/conftest.py`: pendengar "Oke Miku" di test memakai stream mikrofon palsu. Sebelumnya, di venv aplikasi (`sounddevice` asli), test mode suara bisa membuka mikrofon sungguhan.

### Pengujian
- **Suara user, mic laptop:**
  - putaran 1 (mic 30%, belum diperbaiki) 5/10, putaran 4 (mic 20% + prompt) 9/10, putaran terakhir 10/10 dengan semua perintah benar ("Buka, notepad", "Kecilkan volume ke 30", 「メモ帳を開いて」);
  - kalimat biasa tidak pernah memicu (20/20 di semua putaran);
  - rekaman putaran terakhir yang diputar ulang: "Oke Miku" terdeteksi 9/10.
- **Set sintetis:**
  - wake phrase 20/20 bersih, 20/20 mic laptop, 19/20 sangat berisik (SNR 5 dB);
  - 0 pemicu palsu dari 128 kalimat biasa (termasuk jebakan "Oke, menurut aku…", "Oke, minggu ini…", "Oke, mie ayamnya…") dan 9,7 menit obrolan sambung;
  - 5 menit derau ruangan: Whisper tidak jalan.
- **Mic sungguhan, 3–5 menit tanpa "Oke Miku":** 0 pemicu, CPU proses 3–4%, GPU median 0%.
- **Musik dan video dari speaker, 2 × 10 menit:**
  - 0 pemicu, CPU proses 3–4%, GPU median 0%;
  - Whisper berhalusinasi "Oke" 35× dan "Miku" 5×, tetapi tidak pernah berurutan;
  - filter keyakinan Whisper tidak dipasang: pada "Oke Miku" sungguhan keyakinannya 0,02–0,52, dan pada musik tidak ada kecocokan untuk dibandingkan (`experiments/wake_eval/confidence_scan.py`).
- **Aplikasi sungguhan** (`python miku.py`, mic 20%), oleh user, semuanya lewat "Oke Miku" lalu perintah:
  - "Buka Youtube" → YouTube terbuka;
  - "Buka YouTube, dan carikan video dari …" → video diputar;
  - "Ubah volume ke 60%" → volume 60%;
  - "Buat dokumen yang berisi … tentang kamu" → dokumen Word dibuat.

  Waktu LLM 1–3 s per perintah (dokumen 12 s). Permintaan ketiga dan keempat terjadi sesudah video dibuka. Pemicu palsu dari suara video belum diukur, karena saat itu baris "(terdengar: …)" belum ada.
- **Volume mic menentukan:** mic internal laptop uji semula 100% (Capture +30 dB dan Internal Mic Boost +30 dB), sehingga derau ruangan hampir penuh (RMS 0,69). Di 30% hasilnya 2–5/10, di 20% 9–10/10.
- `pytest`: 674 lulus di venv aplikasi (73 test di `tests/test_wake.py`, 1 baru di `tests/test_voice_input.py`); Python sistem seperti CI: 653 lulus, 59 dilewati. `test_without_dry_run_the_wizard_installs_for_real` gagal dan menggantung di venv aplikasi di Linux karena `winreg`, sudah begitu di `main` sebelum perubahan ini; dukungan Linux untuk wizard ada di #41.

- **Windows** (1 Nov; Windows 11, RTX 4050, mic laptop "Microphone Array (Realtek)" di 45%, `test/v1.7.0`), oleh user:
  - Level mic: derau ruangan RMS 0,0000, tanpa peringatan "Volume mikrofon terlalu tinggi".
  - Uji berpandu (`live_guided.py`): skor 8/10. Wake phrase sendiri tertangkap 9/10: sekali Whisper menulis "Opi Miku buka notepad", dan sekali wake phrase tertangkap tetapi perintah Jepang tertulis katakana ("メモチョウ、アイティ", keterbatasan di bawah). Kalimat biasa 5/5 tidak memicu. Perintah sekaligus: "volume ke 30" dan "Putar lagu di YouTube" langsung diproses.
  - `python miku.py`: "Oke Miku" lalu sapaan 「はい、何でしょうか？」, lalu "buka Notepad" → Notepad terbuka (dua kali); "Kecilkan volume ke 30" → volume 30%; "(terdengar: 'Oke, Rigo')" tidak memicu. Pendengar dan perekam membuka mic bersamaan tanpa error. Ctrl+Shift+M dan menyeret maskot tetap mulai merekam; `--trigger` juga (uji terpisah). Keluar lewat menu maskot tanpa error.
  - GUI: tombol Wake Phrase dan model visi (memahami tangkapan layar) jalan, menurut user.
  - Diam 3 menit dengan pendengar aktif: CPU proses 6,5% dari satu inti (0,4% dari 16 inti), GPU 0%.
  - Speaker laptop yang memutar "Okay Miku" (suara sintetis Windows) hampir tidak terdengar di mic (RMS puncak 0,005), jadi pemicu dari speaker sendiri tidak terukur di sini.
  - Belum terlihat: "Oke Miku" saat Miku sedang bicara, dan mic dipakai aplikasi lain setelah keluar.

### Keterbatasan diketahui
- Belum diuji dengan suara orang lain. Di Windows baru satu laptop dan satu suara.
- Lagu yang liriknya berbunyi "oke Miku" akan memicu Miku, sama seperti orang yang mengucapkannya.
- Perintah berbahasa Jepang yang diucapkan sekaligus kadang tertulis katakana ("メモチョウ、ハイテ") saat rekaman diputar ulang.

---

## v1.7.0 (2026-11-01): binary MikuVision Setup untuk Linux di rilis (PLAN_INSTALLER IL3)

Mulai v1.7.0 rilis melampirkan **`MikuVisionSetup-linux-x86_64`** di samping `MikuVisionSetup.exe`. User Linux cukup mengunduhnya, mengizinkannya dijalankan, lalu membukanya; tidak perlu git atau terminal.

### Ditambahkan
- **Job `linux` di `release-setup.yml`:** PyInstaller dengan `miku_setup.spec` yang sama, di kontainer `ubuntu:22.04` pada runner `ubuntu-latest`:
  - glibc 2.35, jadi binary jalan di Ubuntu 22.04+, Linux Mint 21+, Fedora, dan Arch;
  - Python 3.10 dan Tk dari apt (dengan Xft), karena Tk dari uv membuat wizard tampak rusak (IL2);
  - uji jalan: binary dibuka dengan `--dry-run` di Xvfb dan harus masih berjalan setelah 20 detik.
- **Job Windows** menunggu job Linux, lalu `SHA256SUMS` memuat zip, exe, dan binary Linux; ketiganya dan `version.json` dilampirkan ke rilis. Zip kode, `version.json`, dan `SHA256SUMS` tetap dibuat job Windows.
- **Pull request** yang mengubah Setup (`miku_setup/`, spec, workflow) ikut membangun semuanya tanpa melampirkan ke rilis; hasilnya artifact `rilis-uji` (versi `0.0.0-pr<nomor>`) untuk dicoba di Windows dan Linux.
- **Environment bersih untuk program yang dijalankan Setup** (`miku_setup/procenv.py`): binary Linux tidak lagi mewariskan `LD_LIBRARY_PATH` ke library bawaannya (Ubuntu 22.04, di `/tmp/_MEI…`) kepada `install.sh`, MikuVision, dan alat sistem. Tanpa ini curl dan git di distro yang lebih baru bisa memuat OpenSSL yang lebih lama. Dari kode sumber dan di Windows tidak berubah.
- README: cara memasang di Linux dengan binary, termasuk izin "Allow executing file as program". Catatan menghapus instalasi git tidak lagi menyuruh `rm -rf ~/.local/share/mikuvision`, yang sekarang juga berisi instalasi Setup.

### Pengujian
- **CI di PR #42** (`release-setup`, tanpa melampirkan ke rilis): job `linux` membangun `MikuVisionSetup-linux-x86_64` (19,7 MB) di `ubuntu:22.04`, dan binary itu masih berjalan setelah 20 detik di Xvfb dengan `--dry-run`. Job Windows membangun exe, zip `0.0.0-pr42`, `version.json`, dan `SHA256SUMS` berisi tiga file; semuanya menjadi artifact `rilis-uji`. Aset rilis v1.6.0 tidak tersentuh. Percobaan pertama gagal karena kontainer belum punya `libpython3.10` (PyInstaller butuh `libpython3.10.so.1.0`), lalu diperbaiki.
- **Binary dari CI di Linux Mint 22.3:** `sha256sum -c SHA256SUMS` cocok untuk ketiga file. Binary yang diunduh belum bisa dijalankan sebelum diberi izin, seperti yang dijelaskan README. Rilis uji disajikan `python -m http.server`, dan semua tombol diklik di jendela sungguhan lewat `xdotool`:
  - **Perbarui** dari 1.7.0-rc2 (dipasang sebelumnya oleh binary buatan lokal) ke 0.0.0-pr42: 50 detik; salinan di `.tools` diganti binary CI.
  - **Hapus MikuVision** dari menu, yaitu salinan di `.tools` yang menghapus dirinya sendiri: kedua proses binary itu tidak dianggap "MikuVision masih berjalan"; 0 masalah; folder, `install.json`, entri menu, dan peluncur Desktop hilang; Tutup menutup jendela.
  - **Pasang dari nol** lewat semua halaman: 6 menit 14 detik, MikuVision terbuka dari halaman Selesai.
  - `install.sh` dan MikuVision yang dijalankan binary tidak lagi membawa `LD_LIBRARY_PATH` atau `_PYI_*`. Sebelum perbaikan, keduanya mewarisi `LD_LIBRARY_PATH=/tmp/_MEI…`; di MikuVision folder itu sudah terhapus begitu Setup ditutup.
- Binary buatan lokal (Python 3.12 Mint, spec yang sama): pasang dari nol dengan pilihan bawaan dalam 5 menit 38 detik; binary menyalin dirinya ke `.tools/MikuVisionSetup`, dan entri menu menunjuk ke sana.
- `pytest`: 685 lulus di venv aplikasi (38 dilewati); Python sistem seperti CI: 667 lulus, 56 dilewati. 3 test baru untuk environment bersih.
- Sesudah uji, instalasi uji dihapus dan peluncur clone git di menu dan Desktop dikembalikan.
- **Jendela password `pkexec`** (1 Nov, di `test/v1.7.0`):
  - `install.sh --yes --sudo-cmd pkexec --skip-ollama --skip-shortcut --skip-test`, dengan argumen yang sama seperti dari Setup. `xclip` (terpasang, 0.13-3) disembunyikan dari PATH proses itu saja, supaya installer menganggapnya kurang.
  - Jendela password sistem muncul dan user mengisinya. `pkexec apt-get install -y xclip` lalu menjawab "xclip is already the newest version (0.13-3). 0 upgraded, 0 newly installed", dan installer selesai dalam 21 s tanpa error.
  - Sistem tidak berubah: versi `xclip` sama, dan riwayat apt kosong.
  - Belum: memasang Ollama sebagai root lewat `pkexec` (Ollama sudah ada di laptop ini).
- **Cek ulang di Windows** (1 Nov; Windows 11, RTX 4050, skala 125%), dengan exe dari artifact `rilis-uji` PR #42 dan rilis uji yang disajikan `python -m http.server`:
  - `install.ps1` pada `test/v1.7.0`: kode 0, `miku.py --test` lulus. `pytest` 704 lulus, 95 dilewati (sama dengan CI #42 dan #43).
  - **Perbarui** (exe baru, instalasi 1.6.0-i4b): 1 menit 24 detik, argumen tetap `-Yes -Progress -StartMenu -SkipShortcut`, `data/` utuh, exe di `.tools` diganti.
  - **Perbaiki dari Modify** (exe di `.tools`): exe PR #42 yang pertama menolak dengan "Tutup MikuVision dulu (MikuVisionSetup.exe masih berjalan)". Exe satu file di Windows juga dua proses, dan pengecualian "exe yang sama" dari IL2 hanya berlaku di Linux. Bug ini sudah ada sejak v1.6.0; uji v1.6.0 menjalankan Perbaiki dari exe di luar InstallDir, jadi tidak tertangkap. Diperbaiki untuk semua OS (`running_processes`, 2 test baru; tanpa perbaikan test `win32` gagal). Dengan exe dari build sesudahnya: masuk Perbaiki langsung, 1 menit 23 detik, kode 0. Versi terbaru dibaca dari GitHub (1.6.0).
  - **Hapus** lewat `UninstallString` (salinan di Temp): 0 masalah; registry dan Start Menu hilang; shortcut Desktop clone git dan model di D: tidak tersentuh. **Tutup** dan **X** di halaman terakhir menutup jendela (diuji di dua kali Hapus).
  - **Pasang lagi** ke folder yang tinggal berisi `data/`: 9,5 menit dari nol, kode 0, tercatat lagi.
  - Log hanya berbeda di tanda kutip `Tercatat di "Apps & features"`.
  - Teks di bawah "Hapus juga percakapan…" terpotong di Windows ("dipasang d"); lebar 470 px sekarang berlaku untuk semua OS.
  - `notes_url` di `version.json` build pull request menjadi `releases/tag/42/merge` (tidak dipakai wizard; rilis bertag tidak terpengaruh).
- **Belum diuji:** distro selain Mint. Teman pengguna Arch bisa mencoba artifact `rilis-uji` (atau rilis v1.7.0); hasilnya dicatat di sini.

---

## v1.7.0 (2026-11-01): MikuVision Setup jalan di Linux (PLAN_INSTALLER IL2)

Wizard yang sama dengan Windows (`miku_setup/`) sekarang memasang, memperbarui, memperbaiki, dan menghapus MikuVision di Linux, memakai opsi `install.sh` dari IL1. Perilaku di Windows tidak berubah, kecuali perbaikan tombol Tutup di bawah. Binary Linux untuk user menyusul di IL3; sampai saat itu Setup dijalankan dari kode sumber dengan Python sistem yang sudah memasang `requirements-setup.txt`: `python3 MikuVisionSetup.py`.

### Ditambahkan
- **Cek sistem Linux** (halaman 3): distro dari `/etc/os-release` (x86_64; package manager apt, dnf, pacman, atau zypper), sesi desktop (X11 ✓, Wayland ⚠ karena shortcut, membaca layar, dan aksi keyboard/mouse butuh X11), GPU lewat `nvidia-smi`, situs unduhan, Ollama (layanan sistem dikenali), mikrofon (`pactl`, tanpa sumber `.monitor`; cadangannya `arecord -l`), dan **Hak admin**: apa yang akan dipasang `install.sh` dengan root (git, curl, PortAudio, xdotool, wmctrl, playerctl, xclip, Ollama). ✗ bila ada yang perlu dipasang tapi `pkexec` tidak ada.
- **Ruang disk per titik mount** (`/`, `/home`, partisi lain) dari `/proc/mounts`, bukan huruf drive.
- **Halaman 4 di Linux:**
  - folder bawaan `~/.local/share/mikuvision/app`; `~/…` boleh diketik;
  - folder aplikasi di partisi Windows (NTFS/FAT) ditolak, karena venv di sana lambat dan tidak didukung; folder model boleh di sana. Karakter `\`, `` ` ``, `$`, dan `%` di folder ditolak karena merusak peluncur `.desktop` dan file environment.d;
  - Ollama yang berjalan (atau akan berjalan) sebagai layanan sistem memakai foldernya sendiri (`/usr/share/ollama/.ollama/models`): ruangnya dihitung di sana, dan halaman menyebut bahwa folder lain hanya untuk Whisper dan MeloTTS (keputusan IL1). Ollama sendiri dihitung di `/usr/local`;
  - bila ada yang perlu dipasang dengan root (termasuk g++ untuk RVC), kotak **Izinkan Setup memakai hak admin** harus dicentang dulu. Password diminta lewat jendela sistem (`pkexec`), bukan terminal.
- **Runner:** `bash install.sh --yes --progress --menu-entry --skip-shortcut --sudo-cmd pkexec` plus opsi pilihan, di grup proses sendiri. Batal mengirim SIGTERM ke seluruh grup (install.sh, uv, python, ollama pull), lalu SIGKILL bila belum berhenti dalam 5 detik.
- **Pengganti "Apps & features":** catatan `~/.local/share/mikuvision/install.json` (versi, folder, folder model, komponen, ukuran, perintah Setup) dan dua entri di menu aplikasi, **MikuVision Setup** (Perbarui, Perbaiki, Hapus) dan **Hapus MikuVision** (`--uninstall`). `write_entry`, `read_installed`, dan `delete_entry` sama untuk kedua OS, jadi halaman Pilih tindakan, Perbarui, Perbaiki, dan Hapus tidak berubah.
- **Hapus di Linux:** peluncur `mikuvision.desktop` di menu dan `MikuVision.desktop` di Desktop hanya dihapus bila menunjuk ke folder instalasi (peluncur clone git di folder lain dibiarkan). Folder `applications` dan `~/.local/share/mikuvision` tidak pernah dihapus (bisa berisi venv clone git di NTFS). `HF_HOME`/`OLLAMA_MODELS` dihapus dari `~/.config/environment.d/60-mikuvision.conf` hanya bila menunjuk ke folder model yang dihapus; file yang jadi kosong ikut dihapus.
- **Halaman Selesai di Linux:** peluncur Desktop (salinan entri menu dari `install.sh`, ditandai tepercaya lewat `gio` supaya Nemo/Nautilus menjalankannya), dan MikuVision dijalankan lewat `run.sh` di sesinya sendiri.
- Log Setup di `~/.local/share/mikuvision/setup/`. Jendela 760×580 di Linux, karena baris teksnya lebih tinggi.

### Diperbaiki
- **Tombol Tutup setelah Hapus tidak menutup jendela** (juga di Windows): `Wizard.go_next` memanggil `finish()`, yang tidak ada di halaman Hapus, sehingga Tutup dan tombol X hanya menghasilkan `AttributeError`. Ditemukan di uji terima Linux; test alur Hapus sekarang ikut menekan Tutup.
- `test_without_dry_run_the_wizard_installs_for_real` tidak lagi mengganti `sys.platform` (gagal di Linux karena `winreg`).

### Catatan teknis
- **Python dari uv tidak cocok untuk Setup di Linux.** Tk 9 di python-build-standalone dibangun tanpa Xft: hanya font X lama yang terlihat, teks kasar, dan tanda centang customtkinter tampil sebagai "Z". Python sistem (Tk 8.6 dengan Xft) normal. Uji di bawah memakai venv dari `/usr/bin/python3`; binary IL3 dibangun dengan Python dari apt.
- Di Linux, binary satu file PyInstaller berjalan sebagai dua proses dengan exe yang sama (bootloader dan Python); `running_processes` tidak menghitung keduanya sebagai "MikuVision masih berjalan". Kode Windows tidak diubah; exe Windows juga dua proses, jadi Perbarui dari salinan di `.tools` perlu dicek di Windows.

### Pengujian
- `tests/test_miku_setup_linux.py`: 53 test baru, sebagian juga jalan di Windows:
  - os-release dan package manager (Mint, Fedora, Manjaro, Arch, openSUSE, distro tak dikenal), cek Linux, sesi, dan hak admin, keluaran `pactl` dan `arecord`;
  - daftar paket root sama dengan `install.sh`; titik mount (spasi `\040`, mount bertumpuk); folder model layanan Ollama dari `systemctl show`;
  - folder bawaan, argumen `install.sh` (semua opsinya ada di `install.sh`), validasi folder, ruang per mount, file environment.d, dan `/api/tags` bila folder layanan tidak terbaca;
  - `install.json` dan entri menu (round trip, file rusak, tanpa `install.sh`), kutipan `Exec`, peluncur clone lain dibiarkan, Hapus lengkap, binary yang tidak menghitung dirinya sendiri;
  - `run.sh` di sesi sendiri, dan Batal yang ikut mematikan anak proses.
- `test_miku_setup_wizard.py`: izin hak admin di halaman 4, dan Tutup setelah Hapus. Test lama yang memeriksa argumen `install.ps1` sekarang menyebut `platform="win32"`.
- `pytest`: 682 lulus di venv aplikasi (38 dilewati). Python sistem seperti CI (tanpa customtkinter): 664 lulus, 56 dilewati. Semua test Setup dengan customtkinter asli di Tk 8.6, termasuk 12 test wizard GUI yang dijalankan bersamaan: 173 lulus, 13 dilewati (khusus Windows).
- **Uji terima** di Linux Mint 22.3 (X11, RTX 4050, Ollama layanan sistem dengan model yang sudah ada). Rilis uji dibuat seperti workflow (`git -c core.autocrlf=true archive`, jadi `.py` ber-CRLF seperti zip dari runner Windows; `version.json`; `SHA256SUMS`) dan disajikan `python -m http.server` di `127.0.0.1:8765`. Setup dijalankan dari kode sumber dengan Python sistem; tombol ditekan lewat fungsi wizard yang sama (`go_next`, `page.stop`), dengan tangkapan layar tiap halaman:
  - **Batal di tengah PyTorch:** di langkah 5/12, setelah 28 detik dan ±0,3 GB terunduh. `install.sh`, uv, dan python berhenti semua (tidak ada proses tersisa), dan log `install.sh` ditutup dengan "Installer dihentikan".
  - **Jalankan lagi sampai Selesai:** zip yang sudah cocok tidak diunduh lagi; 12/12 langkah (membaca layar, dan RVC dari file `.pth`/`.index`) dalam 6 menit 13 detik, `miku.py --test` lulus. `install.json`, entri menu MikuVision, MikuVision Setup, dan Hapus MikuVision, serta peluncur Desktop dibuat; MikuVision terbuka dari halaman Selesai.
  - **MikuVision masih terbuka:** Lanjut di Pilih tindakan ditolak dengan "Tutup MikuVision dulu (python masih berjalan)".
  - **Perbarui** 1.7.0-rc1 → 1.7.0-rc2: zip baru diunduh sekali, 11 langkah dalam 53 detik, versi di `install.json` naik, dan file penanda di `data/` utuh.
  - **Perbaiki:** tanpa unduhan kode, 53 detik, berhasil.
  - **Hapus** lewat `--uninstall` (perintah entri Hapus MikuVision) dengan opsi bawaan: ±1 detik, tanpa masalah. Sisa folder hanya `data/`; `install.json`, ketiga entri menu, dan peluncur Desktop hilang; model Ollama utuh. Tombol Tutup di halaman terakhirnya memunculkan bug di atas.
  - **Pasang lagi** ke folder yang tinggal berisi `data/`: uv, Python, PyTorch, dan semua langkah dari nol dalam 6 menit 27 detik, `miku.py --test` lulus dengan RVC dimuat di `cuda:0`, penanda di `data/` dipakai lagi, tercatat lagi (12,9 GB).
  - **Hapus semuanya** (data dicentang): folder aplikasi hilang seluruhnya, dan Tutup menutup jendela. Peluncur clone git di menu dan Desktop, yang tertimpa selama uji, dikembalikan sesudahnya.
  - Belum diuji: jendela password `pkexec` (semua paket dan Ollama sudah ada di laptop ini), sesi Wayland, distro selain Mint, dan alur sungguhan dengan binary PyInstaller (IL3; binary buatan lokal sudah terbuka di mode uji).

---

## v1.7.0 (2026-11-01): opsi `install.sh` untuk MikuVision Setup di Linux (PLAN_INSTALLER IL1)

Rencana: fase IL di [`docs/PLAN_INSTALLER.md`](docs/PLAN_INSTALLER.md). `install.sh` sekarang bisa dijalankan wizard seperti `install.ps1`; tanpa opsi baru perilakunya tetap sama.

### Ditambahkan
- **`--progress`**: selain log biasa, satu baris `##MIKU {json}` per kejadian, dengan format yang sama dengan `install.ps1 -Progress` (`step` {index, total, title}, `warn`/`error` {message}, `done` {ok}).
  - Total langkah dihitung dari `install_steps`; setiap fungsi langkah memanggil `step` tepat sekali (dicek test).
  - Baris penutup error ("Instalasi berhenti…", lokasi log) tidak dipancarkan, jadi `error` terakhir selalu penyebabnya.
- **Kode keluar** seperti `install.ps1`: 0 selesai, 1 gagal yang dijelaskan (`die`), 2 error tak terduga (trap EXIT, misalnya variabel tak terdefinisi di bawah `set -u`). Dihentikan dengan Ctrl+C atau SIGTERM: 130.
- **`--model-dir DIR`**: cache Hugging Face (Whisper, MeloTTS) di `DIR/huggingface`. Model Ollama pindah ke `DIR/ollama` hanya bila Ollama dijalankan user sendiri; Ollama milik user yang sedang jalan dengan lokasi lama dimatikan lalu dinyalakan lagi.
  - Pilihan ini dicatat di `~/.config/environment.d/60-mikuvision.conf` (setara variabel user di Windows, berlaku di sesi login berikutnya). `run.sh` dan `install.sh` membacanya, jadi berlaku sejak MikuVision dibuka lagi; nilai yang sudah ada di environment tidak ditimpa.
  - **Ollama yang berjalan sebagai layanan sistem** (installer resmi: user `ollama`, model di home user itu) tidak dipindah. Memindahkannya butuh `chown` ke user `ollama` dan drop-in systemd, folder di dalam `/home` biasanya tidak bisa dibaca user lain, dan menghapusnya kelak butuh root. Installer menyebut lokasi modelnya sebagai peringatan.
- **`--with-vision`**: unduh juga `VISION_MODEL` dari `config.py` setelah model utama.
- **`--rvc-model PTH --rvc-index INDEX`**: salin model RVC milik user ke `models/miku_default_rvc` (index dengan nama tetap yang dibaca `config.py`, dicek test). Ekstensi tidak peka huruf besar-kecil, sama seperti `install.ps1`.
- **`--menu-entry`**: peluncur di menu aplikasi. Bersama `--skip-shortcut`: hanya di menu, tanpa Desktop (dipakai wizard, setara `-StartMenu -SkipShortcut`). Tanpa opsi baru tetap seperti sebelumnya: menu dan Desktop, atau tidak sama sekali dengan `--skip-shortcut`.
- **`--sudo-cmd CMD`**: perintah untuk hak root (bawaan `sudo`). Untuk wizard tanpa terminal: `pkexec` (jendela password grafis). Dengan `--sudo-cmd` selain `sudo`, skrip resmi Ollama dijalankan sebagai root sekaligus, supaya password hanya diminta sekali untuk langkah itu.
- `--self-check` (tersembunyi, untuk test): tiga baris `##MIKU` lalu keluar, log di `$TMPDIR`.

### Pengujian
- `tests/test_install_sh.py`: 54 test (28 baru):
  - self-check, baris progres hanya dengan `--progress`, tanda kutip dan backslash di JSON;
  - `die` → `error` + `done` dan kode 1; error tak terduga → kode 2;
  - daftar langkah per kombinasi opsi, satu `step` per fungsi langkah;
  - nama index RVC dan nama model sama dengan `config.py`;
  - salin RVC dan tiga penolakannya;
  - `--model-dir`, file environment.d, dan peringatan lokasi lama;
  - Ollama layanan sistem (model tidak dipindah) dan Ollama milik user (dimatikan lalu dinyalakan dengan `OLLAMA_MODELS` baru);
  - peluncur hanya-menu, `--sudo-cmd`, dan `run.sh` yang mengekspor folder model.

  Test memakai `XDG_CONFIG_HOME`, log, dan folder RVC sementara, sehingga tidak menyentuh konfigurasi atau model asli.
- `pytest`: 628 lulus di venv aplikasi. Satu yang gagal, `test_without_dry_run_the_wizard_installs_for_real` (`No module named 'winreg'`), juga gagal di `main`: test wizard GUI belum pernah jalan di Linux, dan diperbaiki di IL2. Python sistem seperti CI: 612 lulus, 54 dilewati.
- **Uji sungguhan** di Linux Mint 22.3 (repo di NTFS, instalasi yang sudah ada), stdout dibaca dengan `miku_setup.runner.parse_progress`:
  - `--yes --progress --skip-shortcut --with-vision`: kode keluar 0 dalam 55 s; 10 langkah dengan indeks 1–10 berurutan dan total 10; model visi yang sudah ada tidak diunduh lagi; `miku.py --test` lulus; `done ok`.
  - `--model-dir` ke folder sementara (dengan `XDG_CONFIG_HOME` sementara): `HF_HOME` pindah, peringatan "Ollama berjalan sebagai layanan sistem; modelnya tetap di /usr/share/ollama/.ollama/models" sebagai baris `warn`, kode keluar 0. `~/.config/environment.d` asli tidak tersentuh.

---

## v1.6.0 (2026-11-01): ringkasan rilis

**MikuVision Setup**: installer berantarmuka untuk Windows. Unduh `MikuVisionSetup.exe` dari rilis ini, klik Lanjut, dan Miku terpasang tanpa git atau terminal. Setup yang dibuka lagi (atau Modify di "Apps & features") menawarkan Perbarui, Perbaiki, dan Hapus. Aplikasi MikuVision sendiri tidak berubah sejak v1.5.0; `install.bat`/`install.sh` tetap jalan seperti biasa. Rinciannya ada di entri v1.6.0 di bawah, satu per bagian.

| PR | Isi |
|---|---|
| [#35](https://github.com/MocArjunnaja/MikuVision/pull/35) | Kerangka wizard: 6 halaman, cek sistem nyata, `--dry-run` (I2) |
| [#36](https://github.com/MocArjunnaja/MikuVision/pull/36) | Unduh rilis, jalankan `install.ps1` dengan progres, batal lalu lanjut (I3) |
| [#37](https://github.com/MocArjunnaja/MikuVision/pull/37) | Model RVC dari link yang ditempel user |
| [#38](https://github.com/MocArjunnaja/MikuVision/pull/38) | `MikuVisionSetup.exe`, entri "Apps & features", Perbarui/Perbaiki/Hapus, workflow rilis (I4, I5) |

**Uji di Windows** (Windows 11, RTX 4050, skala layar 125%): dengan exe dan rilis uji yang dibuat seperti workflow, pasang → Perbarui → Perbaiki → Hapus → pasang lagi semuanya lulus; pasang dari nol 10 menit. Batal di tengah PyTorch lalu jalankan lagi melanjutkan dari langkah terakhir. 609 test lulus di Ubuntu dan Windows.

**Keterbatasan yang diketahui**
- Exe belum ditandatangani: SmartScreen menampilkan "Windows protected your PC" (More info → Run anyway). Sebagian antivirus bisa menandai exe PyInstaller.
- Belum diuji di VM Windows bersih (tanpa Python, git, dan Ollama), tanpa GPU NVIDIA, atau dengan nama user non-ASCII.
- Batal saat wheel `torch` sedang diunduh membuat wheel itu diunduh ulang dari nol (uv tidak melanjutkan unduhan parsial).
- "x GB terunduh" menghitung semua unduhan di komputer selama instalasi, jadi angkanya perkiraan.
- Setup baru untuk Windows; Linux tetap memakai `install.sh` (fase IL menyusul).
- Klik tombol Hapus di salinan Setup di Temp belum diuji langsung (fungsi di baliknya sudah).

---

## v1.6.0 (2026-11-01): MikuVisionSetup.exe, "Apps & features", Perbarui/Perbaiki/Hapus (PLAN_INSTALLER I4 dan I5)

Rencana: I4 dan I5 di [`docs/PLAN_INSTALLER.md`](docs/PLAN_INSTALLER.md). Setup sekarang satu file exe, tercatat di Windows, dan bisa merawat instalasinya sendiri.

### Ditambahkan
- **Entri "Apps & features"** (`miku_setup/registry.py`, HKCU tanpa admin): nama, versi, publisher, ikon, ukuran, perintah Uninstall dan Modify, plus folder model dan komponen yang dipakai lagi oleh Perbarui/Perbaiki. Exe Setup menyalin dirinya ke `<InstallDir>\.tools\MikuVisionSetup.exe` supaya Uninstall dan Modify tetap jalan walau file unduhan sudah dihapus.
- **Setup yang dibuka lagi** menampilkan halaman **Pilih tindakan** (versi terpasang dan versi terbaru):
  - **Perbarui** ke rilis terbaru; `data/`, `models/`, `.venv`, dan `.tools` tidak ditimpa. Dinonaktifkan bila sudah versi terbaru.
  - **Perbaiki**: `install.ps1` dijalankan lagi dengan pilihan yang sama, tanpa mengunduh kode.
  - **Hapus**: percakapan, memori, dan skill (`data/`) serta folder model pilihan user disimpan kecuali dicentang. Model di lokasi bawaan Ollama tidak pernah dihapus (bisa dipakai aplikasi lain); Ollama sendiri juga tidak. Hanya shortcut yang menunjuk ke folder instalasi yang dihapus, jadi shortcut Desktop milik clone git tetap ada. `OLLAMA_MODELS`/`HF_HOME` hanya dihapus bila menunjuk ke folder model yang dihapus. Bila ada file terkunci, entri registry dibiarkan supaya Hapus bisa diulang.
  - `--update`, `--repair`, `--uninstall` langsung ke modenya. Uninstall dari "Apps & features" menyalin exe ke Temp dulu, karena exe di `.tools` tidak bisa menghapus dirinya sendiri.
  - Bila MikuVision masih berjalan dari folder itu, Setup meminta menutupnya dulu.
- **`MikuVisionSetup.exe`** (`miku_setup.spec`, PyInstaller 6.11.1, satu file, tanpa konsol, tanpa UPX): 16,8 MB. `requirements-setup.txt` mematok versi build.
- **Workflow `release-setup.yml`**: tag `vX.Y.Z` → runner Windows membangun exe, `git archive` tag itu menjadi `MikuVision-<versi>.zip`, menulis `version.json` dan `SHA256SUMS`, lalu melampirkan keempatnya ke rilis (membuat rilis bila belum ada). Bisa dijalankan ulang untuk tag lama.
- README: Instalasi dimulai dari `MikuVisionSetup.exe`, dengan catatan SmartScreen ("More info → Run anyway").

### Diperbaiki
- Dialog konfirmasi berbahasa Indonesia ("Hentikan"/"Lanjutkan", "Keluar"/"Kembali"), bukan "Yes"/"No" dari Windows.
- "x GB terunduh" menghitung byte yang diterima jaringan (psutil), bukan pertumbuhan cache uv yang sekitar dua kali lipat data internet. Ditampilkan sebagai perkiraan (±), karena unduhan aplikasi lain ikut terhitung.
- Dari uji terima exe: ukuran di "Apps & features" menghitung file yang di-hardlink sekali (14,4 → 8,5 GB), dan RVC tidak lagi tercatat hanya karena folder kosong `models/miku_default_rvc` ikut di zip rilis.

### Pengujian
- 26 test baru di `test_miku_setup_maintenance.py` dan `test_miku_setup_wizard.py`: mode dari opsi dan registry, nilai dan round-trip registry (kunci uji sementara di HKCU), pilihan Perbarui/Perbaiki tanpa file RVC, ukuran dengan hardlink, Hapus (bawaan, semua, model di lokasi bawaan, file terkunci), shortcut yang menunjuk ke tempat lain, proses yang masih berjalan, alur Pilih tindakan → Perbarui/Perbaiki/Hapus di mode uji, dan dialog berbahasa Indonesia. 609 test lulus di venv aplikasi.
- Sebagian test wizard kadang gagal di laptop pengembang karena Tk sesekali tidak bisa membaca `init.tcl` dari Python uv di `.tools` ("couldn't read file … No error"); lulus saat diulang. Masalah lingkungan, bukan kode wizard.
- **Uji terima dengan exe** (Windows 11, RTX 4050, rilis uji dari `git archive` yang disajikan `python -m http.server`, langkah yang sama dengan workflow):
  - Pasang di atas instalasi uji I3: tercatat di "Apps & features", exe tersalin ke `.tools`, penanda di `data/` tetap ada.
  - Perbarui dengan exe baru (seperti mengunduh Setup versi baru): halaman Pilih tindakan menampilkan 1.6.0-i4a terpasang dan 1.6.0-i4b terbaru. Zip baru diunduh sekali, selesai 3 menit 20 detik, `DisplayVersion` naik, `data/` utuh.
  - Modify (exe di `.tools`): instalasi dikenali. Rilis GitHub yang sekarang belum punya `version.json` (404), dan itu tampil sebagai peringatan, bukan error.
  - Perbaiki: tanpa unduhan kode, 1 menit 55 detik, kode keluar 0.
  - Uninstall (`UninstallString`): exe di `.tools` menyalin dirinya ke Temp dan keluar; salinannya membuka halaman Hapus. Izin klik untuk salinan di Temp tidak bisa diberikan dari jarak jauh, jadi tombol Hapus diganti panggilan fungsi yang sama (`remove_installation`, opsi bawaan): 31 s, tanpa masalah. Sisa folder hanya `data/`; entri registry dan Start Menu hilang; shortcut Desktop clone git, `OLLAMA_MODELS`/`HF_HOME`, dan 26 blob di `D:\ollama_models` tidak tersentuh.
  - Pasang lagi dengan exe ke folder yang tinggal berisi `data/` (Hapus lalu pasang lagi): uv, Python, PyTorch, dan semua langkah dari nol, `install.ps1` selesai dalam 10 menit dengan kode 0, `miku.py --test` lulus, tercatat lagi di "Apps & features" (8,3 GB). Percakapan dan penanda di `data/` dari instalasi sebelumnya dipakai lagi.
  - Selama uji, Task Manager dengan "Always on top" menutupi wizard; jendela wizard digeser supaya tombolnya terlihat. Shortcut Desktop tidak dicentang di halaman Selesai, supaya shortcut clone git pengembang tidak tertimpa.

---

## v1.6.0 (2026-11-01): model RVC dari link di MikuVision Setup

### Ditambahkan
- Halaman 4, komponen **Suara khas Miku (RVC)**: pilih "File di komputer" (seperti sebelumnya) atau "Unduh dari link" (`miku_setup/rvc.py`).
  - Link bisa satu `.zip` berisi `.pth` dan `.index`, atau dua link terpisah. Hanya `https`; link halaman Hugging Face (`/blob/`) diubah otomatis ke link unduhan (`/resolve/`).
  - Isi zip dipilih otomatis: checkpoint latihan `G_*.pth`/`D_*.pth` dilewati, index `added_*` diutamakan. Bila masih ambigu, wizard menyebut nama filenya dan meminta "File di komputer".
  - Diunduh setelah ekstrak kode ke `%LOCALAPPDATA%\MikuVision-setup\downloads\rvc\<hash link>\`, lalu diteruskan ke `install.ps1 -RvcModel/-RvcIndex`. "Coba lagi" memakai file yang sudah lengkap dan melanjutkan `.part`.
  - Halaman web (`text/html`) dan file di atas 2 GB ditolak. Peringatan bahwa `.pth` bisa menjalankan kode tampil di bawah kolom link. Query link tidak ditulis ke log.
  - Kebutuhan ruang ditambah ±1 GB perkiraan, dan dihitung ulang saat link diketik.
- Repo tetap tidak menunjuk ke model RVC tertentu (README, "Lisensi & kredit").

### Pengujian
- 26 test baru di `tests/test_miku_setup_rvc.py`: normalisasi link, validasi, nama file aman, isi zip, unduh dua link dan zip, pemakaian ulang saat "Coba lagi", halaman web, batas ukuran, zip rusak, kebutuhan ruang, dan runner yang meneruskan file ke `-RvcModel/-RvcIndex`. Dua mutasi (pemeriksaan `text/html` dimatikan; checkpoint `G_`/`D_` tidak dilewati) masing-masing membuat test gagal. 582 test lulus di venv aplikasi (31 dilewati).
- Halaman 4 dicoba di `--dry-run` (Windows 11, skala 125%): pilihan sumber, dua kolom link, dan peringatan muat di jendela 760×520. Link `.pth` tanpa `.index` menampilkan "Tempel juga link file .index", dan ruang C: naik dari 11,6 ke 12,6 GB setelah link `.zip` ditempel.
- Belum diuji: unduhan dari link `https` sungguhan (test memakai server lokal `http`).

---

## v1.6.0 (2026-11-01): MikuVision Setup memasang sungguhan (PLAN_INSTALLER I3)

Rencana: I3 di [`docs/PLAN_INSTALLER.md`](docs/PLAN_INSTALLER.md). Tanpa `--dry-run`, wizard sekarang mengunduh rilis, menjalankan `install.ps1`, dan membuka MikuVision di akhir.

### Ditambahkan
- **`miku_setup/download.py`**: unduh `version.json`, `SHA256SUMS`, dan `MikuVision-<versi>.zip` dari `releases/latest/download/` (tanpa GitHub API). Unduhan disimpan di `%LOCALAPPDATA%\MikuVision-setup\downloads`. Unduhan terputus dilanjutkan dari `.part` lewat HTTP Range, dan zip yang hash-nya cocok tidak diunduh lagi. Hash yang tidak cocok membuang file dan meminta "Coba lagi".
  - Ekstrak aman: semua entri diperiksa dulu, sehingga zip berisi `..`, path absolut, atau huruf drive tidak menulis apa pun. `data/`, `models/`, `.venv/`, `.tools/`, dan `logs/` yang sudah ada dibiarkan.
- **`InstallRunner`** (`miku_setup/runner.py`): unduh → ekstrak → `install.ps1 -Yes -Progress …` lewat PowerShell tanpa jendela konsol. Baris `##MIKU` diteruskan ke halaman instalasi.
  - "x GB terunduh" dihitung dari pertumbuhan `.tools\uv-cache` dan `blobs\` Ollama setiap 2 detik.
  - Kode keluar `install.ps1` menentukan berhasil atau gagal.
  - Batal mematikan seluruh pohon proses (`taskkill /T`: PowerShell, uv, python, `ollama pull`).
- **Halaman Selesai:** shortcut Desktop (`pythonw.exe gui.py`, ikon Miku) dan "Jalankan MikuVision sekarang" tanpa jendela konsol. Bila salah satunya gagal, muncul peringatan dan MikuVision tetap bisa dibuka dari Start Menu.
- Opsi tersembunyi `--release-url` untuk folder rilis lain, misalnya server lokal saat uji terima.

### Pengujian
- 19 test baru di `test_miku_setup_download.py`, `test_miku_setup_runner.py`, dan `test_miku_setup_wizard.py`:
  - unduh dengan resume, HTTP 416, dan hash rusak;
  - `SHA256SUMS` dan `version.json` yang tidak valid;
  - zip slip, dan folder `keep` yang tidak ditimpa;
  - urutan kejadian runner, kode keluar, dan pembatalan;
  - runner nyata dipakai tanpa `--dry-run`.

  556 test lulus di venv aplikasi (31 dilewati). `test_dry_run_installs_nothing_in_make_runner` gagal sekali pada jalan pertama, lalu lulus pada 4 jalan berikutnya; penyebabnya belum diketahui.
- **Uji terima I3** di laptop pengembang (Windows 11, RTX 4050, driver 621.01, Ollama dan model sudah ada di D:). Aset rilis dibuat dari commit ini (`git archive`, `version.json`, `SHA256SUMS`) dan disajikan `python -m http.server` di `127.0.0.1`. Wizard dijalankan dengan `python -m miku_setup.main --release-url http://127.0.0.1:8765/` ke folder bawaan `%LOCALAPPDATA%\Programs\MikuVision` yang belum ada.
  - **Batal di tengah PyTorch:** di langkah 4/10, setelah 1 menit 24 detik dan "2,2 GB terunduh". Konfirmasi → semua proses berhenti (tidak ada PowerShell, uv, atau python tersisa), log mencatat "Dibatalkan saat instalasi", dan wizard menutup.
  - **Dijalankan lagi:** zip tidak diminta ulang dari server (hanya `version.json` dan `SHA256SUMS`). Langkah uv, Python 3.10, dan `.venv` dilewati, dan resolusi paket turun dari 23,7 s menjadi 1,2 s. Delapan paket yang sudah selesai diunduh di run pertama tidak diunduh lagi.
  - **Sampai Selesai:** 10/10 langkah, `install.ps1` keluar dengan kode 0 dalam 7,5 menit, `miku.py --test` lulus. Model `qwen3:4b-instruct` yang sudah ada tidak diunduh lagi. Shortcut Start Menu dibuat.
  - **Halaman Selesai:** shortcut Desktop menunjuk ke `.venv\Scripts\pythonw.exe gui.py` di folder instalasi. MikuVision terbuka dengan judul "MikuVision - Hatsune Miku" dan memuat LLM 100% di GPU (3,6 GB VRAM). `WM_CLOSE` menutupnya dalam 4 s, dan `ollama ps` kosong sesudahnya.
  - Shortcut Start Menu dan Desktop dari uji ini dihapus atau dikembalikan sesudahnya.

### Keterbatasan yang diketahui
- uv tidak melanjutkan unduhan wheel yang terpotong. Batal saat wheel `torch` (±2,5 GB) sedang diunduh membuat wheel itu diunduh lagi dari nol; paket yang sudah selesai tetap dipakai.
- "x GB terunduh" menghitung pertumbuhan cache uv, termasuk wheel yang dibongkar dan paket yang dibangun. Angkanya lebih besar dari data internet yang sebenarnya (5,3 GB tampil di run kedua).
- Tombol dialog konfirmasi Batal berbahasa sistem ("Yes"/"No" di Windows berbahasa Inggris), bukan Indonesia.
- Cek ruang disk menghitung kebutuhan penuh lagi saat melanjutkan instalasi yang sebagian sudah terpasang.
- Belum diuji: run tanpa batal dari folder kosong (uji di atas memakai satu folder dengan batal di tengah), internet yang putus, dan hash yang tidak cocok dari server sungguhan.

---

## v1.6.0 (2026-10-31): kerangka MikuVision Setup (PLAN_INSTALLER I2)

Rencana: I2 di [`docs/PLAN_INSTALLER.md`](docs/PLAN_INSTALLER.md). Installer berantarmuka untuk user yang tidak memakai GitHub atau terminal; fase ini kerangka wizard-nya, tanpa memasang apa pun.

### Ditambahkan
- **`miku_setup/`**: wizard customtkinter 760×520 dengan 6 halaman (Selamat datang, Lisensi karakter, Cek sistem, Lokasi dan komponen, Unduh dan pasang, Selesai), daftar langkah di kiri, dan Kembali/Lanjut/Batal. Tema gelap dengan aksen teal Miku, sama dengan GUI MikuVision. Coba dengan `python -m miku_setup.main --dry-run`.
  - **Lisensi karakter** wajib dicentang sebelum lanjut (keputusan 2).
  - **Cek sistem nyata** di thread latar, hasilnya muncul satu per satu dengan ✓/⚠/✗ dan "Periksa lagi":
    - Windows 10/11 64-bit (build dari `platform.version()`);
    - GPU dan VRAM dari `nvidia-smi`;
    - internet per situs unduhan (pypi.org, download.pytorch.org, ollama.com, huggingface.co), jadi situs yang diblokir proxy disebut namanya;
    - Ollama yang sudah terpasang, mikrofon, folder user non-ASCII, dan ruang disk.

    ✗ menghentikan instalasi; ruang kurang di lokasi bawaan boleh diperbaiki di halaman berikutnya.
  - **Lokasi dan komponen:** folder aplikasi bawaan `%LOCALAPPDATA%\Programs\MikuVision` (keputusan 3), folder model (lokasi yang sudah dipakai, atau folder lain → `-ModelDir`), dan komponen dengan ukurannya. Komponen opsional: membaca layar → `-WithVision`; RVC dengan pemilih file `.pth`/`.index`. Kebutuhan ruang dihitung per drive setiap kali pilihan berubah, model Ollama yang sudah diunduh tidak dihitung, dan drive lain yang cukup disarankan bila ruang kurang. Folder dicek: lengkap dengan drive, tanpa tanda kutip, bisa ditulis (bukan `C:\Program Files`).
  - **Unduh dan pasang:** langkah aktif ("Langkah 6 dari 13: PyTorch…") dari baris `##MIKU`, bar progres, waktu berjalan, jumlah peringatan, panel log, dan "Buka folder log". Halaman Selesai tampil sendiri setelah instalasi.
  - **Selesai:** centang shortcut Desktop dan "Jalankan MikuVision sekarang", plus tips `Ctrl+Shift+M`. Bila gagal: pesan error terakhir, "Coba lagi", dan "Buka log".
  - Batal saat instalasi meminta konfirmasi lalu menghentikan proses dengan rapi. Log wizard di `%LOCALAPPDATA%\MikuVision-setup\setup-<waktu>.log`, tanpa `print`.
- **`--dry-run`** memutar ulang stdout nyata uji terima I1 (`miku_setup/assets/dry_run_stdout.txt`, path pribadi diganti); `--dry-run-fail` berakhir dengan error. Runner `install.ps1`, unduhan, registry, dan exe menyusul di I3–I5; tanpa `--dry-run`, `main.py` keluar dengan kode 2.
- `components.install_args()`: argumen `install.ps1` untuk pilihan user (`-Yes -Progress -StartMenu -SkipShortcut`, `-ModelDir`, `-WithVision`, `-RvcModel/-RvcIndex`), untuk runner I3.

### Pengujian
- 57 test baru:
  - `test_miku_setup_checks.py`: Windows/build, `nvidia-smi` termasuk dua GPU dan keluaran error, VRAM, ruang disk per drive, internet, mikrofon, folder non-ASCII, Ollama, manifest model;
  - `test_miku_setup_components.py`: kebutuhan ruang untuk instalasi baru, folder model di D:, mode CPU, model yang sudah ada, dan file RVC; validasi folder dan RVC; argumen `install.ps1` yang harus ada di `install.ps1`; nama model sama dengan `config.py`;
  - `test_miku_setup_runner.py`: baris `##MIKU`, termasuk BOM dan `\u003c` dari PowerShell 5.1; log contoh berhasil dan gagal; runner dry-run dan pembatalannya;
  - `test_miku_setup_wizard.py`: semua halaman sampai Selesai, cek ✗ memblokir, pesan folder tidak valid, instalasi gagal lalu "Coba lagi".

  Test wizard butuh customtkinter asli dan layar, jadi dilewati di CI. 534 test lulus di venv aplikasi.
- Dijalankan sungguhan di laptop pengembang (Windows 11, skala layar 125%). Cek sistem selesai dalam ±5 s dan ketujuh baris ✓: Windows 11 build 26300, RTX 4050 6,0 GB, keempat situs terjangkau, Ollama sudah ada, Microphone Array (Realtek), folder user ASCII, dan ruang disk (C: 10,8 GB dari 61,2 GB; D: 3,9 GB, karena kedua model sudah ada di `D:\ollama_models`). Tangkapan layar tiap halaman diperiksa: tiga perbaikan tata letak (lebar sidebar tetap, teks pembuka terbungkus, baris cek rata atas) sebelum commit.

---

## v1.5.0 (2026-10-31): ringkasan rilis

Maskot transparan di Linux, buka aplikasi apa pun, skill buatan user dan "simpan ini sebagai skill", shortcut `Ctrl+Shift+M`, Miku membaca layar, installer untuk lebih banyak distro dan opsi baru untuk installer Windows. Kode Windows yang berubah sejak v1.3.0 (selama ini hanya dites di CI) kini sudah dicoba langsung di Windows. Rinciannya ada di entri v1.5.0 di bawah, satu per bagian.

| PR | Isi |
|---|---|
| [#22](https://github.com/MocArjunnaja/MikuVision/pull/22) | Maskot transparan di Linux (L3) |
| [#23](https://github.com/MocArjunnaja/MikuVision/pull/23) | Buka aplikasi apa pun dari menu sistem, dan Miku mengingatnya |
| [#24](https://github.com/MocArjunnaja/MikuVision/pull/24) | Skill buatan user (S1); spike agent visi di Linux |
| [#25](https://github.com/MocArjunnaja/MikuVision/pull/25) | Installer untuk Fedora, Arch, dan openSUSE (L5) |
| [#26](https://github.com/MocArjunnaja/MikuVision/pull/26) | Shortcut `Ctrl+Shift+M` dan `miku.py --trigger` (T1) |
| [#27](https://github.com/MocArjunnaja/MikuVision/pull/27) | Miku membaca layar (agent visi Fase 1) |
| [#28](https://github.com/MocArjunnaja/MikuVision/pull/28) | "Simpan ini sebagai skill" (S2) |
| [#29](https://github.com/MocArjunnaja/MikuVision/pull/29), [#21](https://github.com/MocArjunnaja/MikuVision/pull/21) | README: langkah Linux, lalu diringkas (381 → 174 baris); rencana MikuVision Setup |
| [#30](https://github.com/MocArjunnaja/MikuVision/pull/30) | Opsi baru `install.ps1` untuk installer berantarmuka (I1); dua perbaikan installer Windows |
| [#31](https://github.com/MocArjunnaja/MikuVision/pull/31) | Windows: pesan bila shortcut sudah dipakai aplikasi lain |
| [#32](https://github.com/MocArjunnaja/MikuVision/pull/32), [#33](https://github.com/MocArjunnaja/MikuVision/pull/33) | Skill menyimpan tugas yang baru selesai; skill bernilai tetap selalu dijalankan; "X lalu Y" diselesaikan |

**Daftar cek Windows** ([`docs/ROADMAP.md`](docs/ROADMAP.md) bagian 2; Windows 11, RTX 4050, skala layar 125%): install ulang, pytest, volume/mute/media, buka/tutup aplikasi, folder/dokumen/WhatsApp, maskot, buka aplikasi apa pun + cache, dan shortcut lulus. Urutan muat VRAM dan membaca layar lulus dengan catatan waktu. Baris skill diterima untuk rilis ini dengan keterbatasan di bawah. 477 test lulus di Ubuntu dan Windows.

**Keterbatasan yang diketahui**
- Permintaan berurutan seperti "kecilkan volume ke 20 lalu putar lofi di youtube" masih hanya menjalankan bagian pertama di ±1 dari 3 percobaan (qwen3:4b), walau sudah diminta ulang. Skill yang disimpan sesudahnya ikut hanya berisi bagian itu; pratinjaunya memperlihatkan isinya sebelum disimpan.
- Membaca layar di Windows: pemuatan model visi pertama ±30 s, sesudahnya ±13 s. "Tombol apa saja di jendela ini?" baru ada di Linux.
- Bagian suara (bicara ke mikrofon) belum diuji oleh manusia di Windows untuk rilis ini; shortcut, maskot, dan mode teks diuji dengan input yang disimulasikan.
- Linux tetap eksperimental: maskot, shortcut, dan klik butuh sesi X11; Fedora, Arch, dan openSUSE baru didukung installer, belum dicoba langsung.

## v1.5.0 (2026-10-31): skill bernilai tetap selalu dijalankan, dan "X lalu Y" diselesaikan

Dari uji ulang daftar cek Windows ([`docs/ROADMAP.md`](docs/ROADMAP.md) bagian 2) di `main` setelah #32: penyimpanan skill sudah benar 3/3, tetapi baris "Skill buatan user" masih gagal karena dua perilaku qwen3:4b. Di giliran "kecilkan volume ke 20 lalu putar lofi di youtube", model hanya mengatur volume (4/4 run). Saat "mode fokus dong", model menjawab "モード fokus に切り替えますね！" tanpa tool call (2/3 run).

### Diubah
- **Skill bernilai tetap dijalankan oleh kode.** Bila setiap langkah `SKILL.md` berbentuk `Panggil <tool>: <param> = <nilai JSON>` (seperti hasil "simpan ini sebagai skill" tanpa isian dari user), langkah yang belum dipanggil model diambil langsung dari file (`UserSkill.fixed_calls`), bukan lewat satu panggilan LLM lagi. Model tetap dipakai lebih dulu, jadi variasi dari user ("mode fokus, volume 35 aja") tetap dihormati, dan langkah yang sudah dipanggil model tidak diulang.
  - Hanya bila tepat satu skill user aktif, dan tidak bila user menyangkal ("jangan", "tidak usah", "やめて", "don't"): di situ model yang memutuskan seperti sebelumnya.
  - Skill dengan petunjuk bebas (seperti contoh `laporan harian` dan `musik mood`) atau isian dari user tetap lewat model.
  - Nilai dibaca dengan `json.JSONDecoder.raw_decode`, jadi teks yang berisi `"; "` tidak terpotong; nilai yang bukan JSON membuat skill kembali ke model.
- **"simpan ini sebagai skill": `query` yang ditandai isian dari user menyimpan nilai tadi sebagai bawaan** (`query = "lofi music" (atau dari permintaan user saat ini bila disebut: …)`). Skill seperti itu tidak bertanya lagi dan tetap bernilai tetap. Isi dokumen, pesan, dan teks panjang tetap sekali pakai dan tidak pernah disalin.
- **Permintaan berurutan tanpa skill.** Bila ucapan berisi ≥ 2 bagian yang masing-masing meminta aksi, dipisah "lalu", "terus", "kemudian", "dan", "、", "それから", dst., tetapi tool yang jalan lebih sedikit, model diminta sekali lagi dengan menyebut bagian yang belum dikerjakan (`AIBrain.next_request_calls`). Tool call yang persis sama dengan yang sudah jalan dibuang. Bila model sudah memanggil semuanya, tidak ada panggilan tambahan.
- **`run_routine` ke routine yang tidak ada dibuang selama skill user aktif.** "mode fokus dong" juga memicu skill bawaan routine (kata "mode"), dan model kadang memanggil `run_routine('mode fokus')`; routine itu pasti gagal dan menghentikan langkah skill. Routine yang ada tetap jalan.

### Pengujian
- 24 test baru di `tests/test_user_skills.py` dan `tests/test_skill_builder.py`: pembacaan langkah tetap (Indonesia dan Jepang, nilai bawaan berkurung, isian dari user, petunjuk bebas, tool di luar daftar), skill tetap dijalankan walau model hanya mengobrol atau melewatkan langkah, penyangkalan, routine yang tidak ada vs yang ada, pembagian ucapan berurutan, satu kali lanjutan dengan tool call kembar dibuang, dan isi dokumen yang tidak pernah jadi nilai bawaan. Mematikan jalur langkah tetap atau jalur lanjutan masing-masing membuat test gagal. 476 test lulus.
- `experiments/skills/bench_save_skill.py 3` (6 skenario × 3), `main` setelah #32 vs branch ini:

  | | Tool skill tepat | Pakai ulang benar |
  |---|---|---|
  | `main`, riwayat disuntikkan | 18/18 | 17/18 |
  | Branch ini, riwayat disuntikkan | 18/18 | **18/18** |
  | `main`, `--live` | 10/18 | 9/18 |
  | Branch ini, `--live` | **18/18** | **18/18** |

  - Satu run `--live` di tengah pengerjaan (sebelum `run_routine` disaring) gagal di `campur_id`: model memanggil `run_routine('mode fokus')` dulu. Run akhir di atas sudah dengan saringan itu.
- `bench_skills.py 3 regression` (perintah umum, tanpa skill user): 27/30 dengan skill dan 25/30 tanpa skill. Acuan `main` di hari yang sama: 26/30 dan 24/30. Perintah yang meleset tetap sama (次の曲にして, ミュートして), jadi lanjutan permintaan berurutan tidak mengganggu perintah tunggal.
- Urutan daftar cek di aplikasi sungguhan (`miku.py --text`: laporan harian → lagu buat belajar → "kecilkan volume ke 20 lalu putar lofi di youtube" → simpan "mode fokus" → "mode fokus dong"):
  - giliran tugas yang menjalankan volume + YouTube: 6/9 run dengan perubahan ini, dan 0/4 di `main`. Di run yang gagal, kedua percobaan lanjutan jalan, tetapi qwen3:4b tetap tidak memanggil YouTube;
  - "mode fokus dong" menjalankan semua langkah skill yang tersimpan di setiap run sejak nilai bawaan `query` ditambahkan (6/6). Di `main`, 2 dari 3 run tidak menjalankan apa pun.

### Keterbatasan diketahui
- Giliran tugas berurutan masih kadang hanya menjalankan bagian pertama (±1 dari 3 di urutan daftar cek). Skill yang disimpan sesudahnya setia pada yang berhasil, dan pratinjau `SKILL.md` memperlihatkannya sebelum disimpan.
- Bila model tidak memanggil tool, langkah skill bernilai tetap dijalankan dengan nilai yang tersimpan, termasuk `query`; variasi yang hanya diucapkan ("mode fokus tapi jazz") dihormati hanya bila model sendiri memanggil tool-nya.

## v1.5.0 (2026-10-31): "simpan ini sebagai skill" menyimpan tugas yang baru selesai

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

## v1.5.0 (2026-10-31): shortcut di Windows memberi tahu bila kombinasinya sudah dipakai

Dari daftar cek Windows ([`docs/ROADMAP.md`](docs/ROADMAP.md) bagian 2): baris "Shortcut `Ctrl+Shift+M` (T1)" gagal di kriteria "pesan jelas bila kombinasi sudah dipakai aplikasi lain". Deteksi tekan sendiri lulus (6/6 saat Miku diam, 63–66 ms; `--trigger` 342–410 ms).

### Diperbaiki
- Windows: sebelum memasang hook `keyboard`, `KeyboardHotkey` mencoba `RegisterHotKey` lalu langsung `UnregisterHotKey` (ctypes, tetap library standar untuk `--trigger`). Bila gagal dengan `ERROR_HOTKEY_ALREADY_REGISTERED` (1409), Miku menampilkan pesan yang sama dengan Linux, "Shortcut Ctrl+Shift+M tidak dipasang: sudah dipakai aplikasi lain…", dan jalan tanpa shortcut. Sebelumnya Miku mengaku shortcut aktif, lalu satu tekan menjalankan Miku dan aplikasi lain sekaligus.
  - Kombinasinya tidak dipegang Miku. Tekan tetap dideteksi hook `keyboard` seperti sebelumnya, jadi shortcut di dalam aplikasi tidak ditelan.
  - Error `RegisterHotKey` lain bukan bukti bentrok: diabaikan, hook tetap dipasang.
  - Mengganti `keyboard` seluruhnya dengan `RegisterHotKey` + message loop tidak dipilih. Kombinasinya akan ditelan dari semua aplikasi, dan deteksi tekan yang baru lulus di daftar cek harus diuji ulang.

### Pengujian
- `tests/test_hotkey.py` (+6 test, user32 palsu): kombinasi yang sudah dipakai menghasilkan pesan tanpa memasang hook, pengecekan melepas kombinasinya lagi, error lain tetap memasang hook, kode virtual-key angka dan F1/F24, pesan `ListenTriggers` di Windows. `conftest.py` menolak panggilan `RegisterHotKey` sungguhan dari test.
- Manual di Windows 11 (31 Okt), dengan proses pembantu yang memegang `Ctrl+Shift+M` lewat `RegisterHotKey`:
  - Pembantu jalan dulu, lalu `python miku.py`: setelah sapaan muncul `[Shortcut] Shortcut Ctrl+Shift+M tidak dipasang: sudah dipakai aplikasi lain. …`, dan petunjuk "HOW TO USE" hanya menyebut maskot.
  - Tanpa pembantu: "Shortcut Ctrl+Shift+M: mulai bicara dari aplikasi mana pun."
  - Miku jalan dulu, lalu pembantu: pembantu berhasil mendaftar (pengecekan tidak memegang kombinasinya), dan satu tekan lewat `keybd_event` sampai ke keduanya.

### Dokumentasi
- README Troubleshooting: shortcut di dalam aplikasi (misalnya `Ctrl+Shift+M` di Chrome) tidak bisa dideteksi, dan cara mengganti `WAKE_HOTKEY`.

### Keterbatasan diketahui
- Hanya bentrok saat Miku mulai yang terdeteksi. Aplikasi yang mendaftarkan kombinasi yang sama setelah itu tidak ketahuan, dan satu tekan menjalankan keduanya.
- Shortcut di dalam aplikasi tidak lewat `RegisterHotKey`: di Chrome, `Ctrl+Shift+M` tetap membuka menu profil sekaligus membuat Miku mendengarkan.
- Saran cadangan di pesan ("pasang `python miku.py --trigger` sebagai shortcut di pengaturan keyboard desktop") ditulis untuk Linux. Windows tidak punya pengaturan seperti itu.
- Tekan saat Miku sedang memproses atau bicara tetap dibuang tanpa tanda, seperti sejak T1.

---

## v1.5.0 (2026-10-31): opsi installer untuk MikuVision Setup (PLAN_INSTALLER I1)

Rencana: I1 di [`docs/PLAN_INSTALLER.md`](docs/PLAN_INSTALLER.md). Semua opsi bersifat tambahan; `install.bat` tanpa opsi berperilaku sama seperti sebelumnya.

### Ditambahkan
- `install.ps1 -Progress`: selain log biasa, satu baris `##MIKU {json}` per kejadian di stdout (`step` dengan nomor dan total langkah, `warn`, `error`, `done`), untuk wizard yang menjalankan installer tanpa jendela konsol. Jejak stack dan baris penutup error tidak dipancarkan, jadi `error` terakhir selalu penyebab kegagalannya.
- `-ModelDir <folder>`: model Ollama di `<folder>\ollama` dan cache Hugging Face di `<folder>\huggingface`. `OLLAMA_MODELS` dan `HF_HOME` diatur sebagai variabel user sebelum Ollama dan Whisper dipakai; Ollama yang sedang jalan dimatikan lalu dinyalakan ulang, karena Ollama hanya membaca `OLLAMA_MODELS` saat start.
- `-WithVision`: `ollama pull` model visi dari `VISION_MODEL` di `config.py`, sebagai langkah tersendiri.
- `-RvcModel <pth> -RvcIndex <index>`: menyalin model RVC ke `models\miku_default_rvc\`, lalu `rvc-python` ikut dipasang. Index disalin dengan nama tetap yang dibaca `config.py`.
- `-StartMenu`: shortcut juga di Start Menu (`Programs\MikuVision\MikuVision.lnk`). Berlaku walau `-SkipShortcut` (yang hanya melewati shortcut desktop).
- Cadangan Ollama tanpa winget (Windows LTSC, sebagian laptop kantor): `OllamaSetup.exe` resmi (±1,7 GB) diunduh ke `.tools\`, tanda tangan digitalnya dicek (`Valid`, `CN=Ollama Inc.`), lalu dipasang diam-diam per-user (`/VERYSILENT`, Inno Setup).
- Kode keluar: `0` selesai, `1` gagal yang sudah dijelaskan, `2` error tak terduga (sebelumnya keduanya `1`).

### Diperbaiki
- Driver NVIDIA 621 menulis `CUDA UMD Version: 13.5` di header `nvidia-smi`, sehingga installer melapor "Versi CUDA dari nvidia-smi tidak terbaca" (tetap memakai cu128, jadi hasilnya benar). Kedua format sekarang terbaca.
- Instalasi pertama di Windows: uv gagal me-rename file yang baru diekstrak di cache karena masih dipindai antivirus (`Access is denied. (os error 5)`). Installer melaporkannya sebagai "fairseq butuh Visual Studio Build Tools" lalu lanjut tanpa RVC, padahal Build Tools sudah ada: perintah yang sama berhasil saat installer dijalankan ulang. Sekarang `uv pip install` dicoba sekali lagi bila errornya file terkunci, dan pesannya menyebut penyebab yang benar.

### Diubah
- Langkah instalasi disusun di `Get-InstallSteps` (total langkah untuk `-Progress`); setiap fungsi langkah memanggil `Write-Step` tepat sekali. Deteksi build PyTorch dicatat di bawah judul langkah PyTorch, bukan di atasnya. `install.ps1` bisa di-source oleh test tanpa menjalankan instalasi.

### Pengujian
- `tests/test_install_ps1.py` (27 test, Windows PowerShell 5.1 dan PowerShell 7): parsing script, file tetap ASCII (PowerShell 5.1 membaca script tanpa BOM sebagai ANSI), `-SelfCheck` memancarkan tiga baris `##MIKU` JSON yang valid dengan judul berhuruf Jepang, baris mesin hanya muncul dengan `-Progress`, daftar langkah per kombinasi opsi, satu `Write-Step` per langkah, penyalinan dan penolakan file RVC, `-ModelDir` (variabel user diganti pencatat, tidak diubah sungguhan), dua format header `nvidia-smi`, dan deteksi file terkunci dari potongan log nyata. Dua mutasi (hapus `Write-Step` dari satu langkah; kembalikan regex CUDA lama) masing-masing membuat test gagal.
- Uji terima I1 di laptop pengembang (Windows 11, RTX 4050, Ollama sudah jalan dengan model di `D:\ollama_models`): `install.ps1 -Yes -Progress -ModelDir D:\MikuTest\models -WithVision -RvcModel … -RvcIndex … -StartMenu -SkipShortcut` dari worktree kosong selesai dalam ±11 menit, 13/13 langkah, `{"event":"done","ok":true}`, `miku.py --test` lulus, `RVC ready`. Ollama dimatikan lalu dinyalakan ulang dan hanya melihat dua model yang baru diunduh; model Ollama (5,5 GB) dan cache Hugging Face (1,8 GB: Whisper, MeloTTS) ada di `D:\MikuTest\models`, bukan di lokasi lama. Header `CUDA UMD Version: 13.5` terbaca. `install.ps1` baru tanpa opsi pada instalasi yang sudah ada (sama dengan menjalankan ulang `install.bat`): exit 0 dalam 76 s, langkah yang sama dilewati seperti sebelumnya, tanpa baris `##MIKU`.

---

## v1.5.0 (2026-10-31): "simpan ini sebagai skill" (PLAN_SKILLS S2)

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

## v1.5.0 (2026-10-31): Miku membaca layar (agent visi Fase 1)

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

## v1.5.0 (2026-10-31): shortcut keyboard untuk mulai bicara (T1)

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

## v1.5.0 (2026-10-31): installer untuk Fedora, Arch, dan openSUSE

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

## v1.5.0 (2026-10-31): skill buatan user, dan spike agent visi di Linux

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

## v1.5.0 (2026-10-31): buka aplikasi apa pun dari menu sistem, dan Miku mengingatnya

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

## v1.5.0 (2026-10-31): maskot desktop di Linux (Fase L3)

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
