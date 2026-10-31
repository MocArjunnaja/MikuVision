# Rencana: MikuVision Setup (installer dengan antarmuka)

**Tujuan:** siapa saja bisa memasang MikuVision tanpa membuka GitHub, git, atau terminal. Caranya: unduh satu file `MikuVisionSetup.exe` (±25 MB), klik Lanjut beberapa kali, lalu Miku menyapa. Rasanya seperti installer aplikasi desktop besar (misalnya Ansys): ada pilihan folder, pilihan komponen, progres unduhan, serta Perbarui/Perbaiki/Hapus.

**Status:** rencana (31 Okt 2026). Dikerjakan di Windows dulu (fase I1–I5); Linux menyusul (fase IL). Urutan terhadap rencana lain: [`ROADMAP.md`](ROADMAP.md).

**Untuk yang mengerjakan:** baca bagian 1–4 untuk gambaran, lalu kerjakan fase di bagian 8 satu per satu. Tiap fase satu PR, dengan kriteria selesai yang bisa dicek. Kode installer yang sudah teruji (`install.ps1`) **dibungkus, bukan ditulis ulang**.

---

## 1. Keputusan dasar

| Pertanyaan | Keputusan | Alasan |
|---|---|---|
| Perlu server/VPS? | **Tidak.** `MikuVisionSetup.exe` dilampirkan di GitHub Releases (repo publik: gratis, tanpa akun untuk mengunduh). File besar diunduh dari sumber aslinya (PyPI, download.pytorch.org, ollama.com, Hugging Face) | Batas GitHub hanya ≤ 2 GB per file lampiran; installer kita ±25 MB |
| Link yang dibagikan | `https://github.com/MocArjunnaja/MikuVision/releases/latest/download/MikuVisionSetup.exe`, selalu menunjuk rilis terbaru. Nanti bisa ditambah halaman unduhan di GitHub Pages (gratis) | User awam cukup menerima satu link; tidak perlu melihat halaman repo |
| Bahasa/teknologi wizard | **Python + customtkinter**, dibekukan dengan PyInstaller | Satu kode untuk Windows dan Linux. Tampilannya sama dengan GUI MikuVision. Cek sistem yang khas (GPU, VRAM, X11) mudah ditulis |
| Siapa yang memasang paket | **`install.ps1` yang sudah ada**, dijalankan wizard tanpa jendela konsol | Sudah teruji, idempoten, dan punya log. Satu sumber kebenaran untuk instalasi lewat terminal dan lewat wizard |
| Folder instalasi bawaan | `%LOCALAPPDATA%\Programs\MikuVision` (per-user, **tanpa admin**) | Aplikasi menulis `data/`, `logs/`, `temp_audio/` di foldernya sendiri. Di `C:\Program Files` itu butuh admin dan gagal |
| Folder model | Bisa dipisah dari folder aplikasi (misalnya `D:\MikuVision\models`) lewat `OLLAMA_MODELS` dan `HF_HOME` | Laptop pengembang: C: hanya ±8 GB kosong |
| Paket offline | **Di luar cakupan versi pertama** (lihat bagian 10) | Target pertama: user dengan internet |
| Code signing | Di luar cakupan versi pertama; SmartScreen dijelaskan di halaman unduhan | Sertifikat berbayar; dibahas di bagian 9 |

## 2. Arsitektur

```
MikuVisionSetup.exe  (PyInstaller, ±25 MB: Python 3.10 + customtkinter + kode miku_setup/)
  │
  ├─ 1. Cek sistem            miku_setup/checks.py      (Windows, GPU, VRAM, disk, internet, Ollama)
  ├─ 2. Unduh kode aplikasi   miku_setup/download.py    (zip rilis + SHA256, bisa dilanjutkan)
  │      └─ ekstrak ke InstallDir, tanpa menimpa data/, models/, .venv/, .tools/
  ├─ 3. Jalankan installer    miku_setup/runner.py
  │      └─ powershell -NoProfile -ExecutionPolicy Bypass -File <InstallDir>\install.ps1
  │            -Yes -Progress -ModelDir <ModelDir> [-WithVision] [-RvcModel ...] [-SkipShortcut]
  │         stdout dibaca baris per baris: "##MIKU {json}" → progres di UI, sisanya → panel log
  ├─ 4. Shortcut + daftar "Apps & features"   miku_setup/registry.py
  └─ 5. Jalankan MikuVision (pythonw gui.py)

Jalankan Setup lagi → mode perawatan: Perbarui / Perbaiki / Hapus
```

Yang **tidak** ada di dalam `MikuVisionSetup.exe`: PyTorch, model, dan Ollama. Semuanya diunduh oleh `install.ps1` seperti sekarang. Karena itu installernya kecil, dan pembaruan aplikasi cukup mengganti kode Python (±2 MB).

## 3. Halaman wizard

Ukuran jendela 760×520. Kiri: daftar langkah. Kanan: isi halaman. Bawah: tombol Kembali / Lanjut / Batal. Semua teks berbahasa Indonesia, sentence case, tanpa jargon.

| # | Halaman | Isi | Validasi dan perilaku |
|---|---|---|---|
| 1 | Selamat datang | Logo Miku, satu kalimat apa itu MikuVision, perkiraan ukuran dan waktu ("±12 GB, ±20–40 menit tergantung internet") | Bila sudah terpasang (registry, bagian 6), langsung ke **mode perawatan** |
| 2 | Lisensi karakter | Ringkasan Piapro Character License (non-komersial), link ke bagian "Lisensi & kredit" di README, centang "Saya mengerti" | Lanjut hanya setelah dicentang |
| 3 | Cek sistem | Daftar hasil dengan ikon ✓ / ⚠ / ✗ (tabel di bawah) | ✗ menghentikan instalasi dengan penjelasan; ⚠ boleh lanjut |
| 4 | Lokasi dan komponen | Folder aplikasi, folder model, centang komponen, total unduhan vs ruang kosong (lihat mockup di percakapan) | Folder harus bisa ditulis, path tanpa karakter `"`, ruang kosong ≥ total + 2 GB |
| 5 | Unduh dan pasang | Langkah aktif + bar progres, "x GB terunduh", waktu berjalan, panel log yang bisa dibuka, tombol "Buka folder log" | Batal → konfirmasi, hentikan proses dengan rapi; instalasi bisa dilanjutkan nanti |
| 6 | Selesai | Centang "Buat shortcut di Desktop", "Jalankan MikuVision sekarang"; tips: "Tekan Ctrl+Shift+M untuk bicara" | Bila gagal: pesan dalam bahasa biasa + tombol "Coba lagi" dan "Buka log" |

**Cek sistem (halaman 3)**

| Cek | Cara | Hasil |
|---|---|---|
| Windows 10/11 64-bit | `platform.machine()` dan nomor build dari `platform.version()` (`platform.release()` bisa melaporkan "10" di Windows 11) | ✗ bila 32-bit atau < Windows 10 |
| GPU NVIDIA dan driver | `nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader` | Tidak ada → ⚠ "Tanpa GPU NVIDIA: Miku tetap jalan tapi lambat" (mode CPU, `-Cpu`) |
| VRAM | dari baris di atas | < 6 GB → ⚠ "Membaca layar dan RVC mungkin tidak muat" |
| Ruang disk | `shutil.disk_usage` per drive yang dipilih (dihitung ulang di halaman 4) | < total + 2 GB → ✗ |
| Internet | `HEAD` ke `pypi.org`, `download.pytorch.org`, `ollama.com`, `huggingface.co` (timeout 5 s) | Ada yang gagal → ✗ dengan nama situsnya (proxy kampus sering memblokir salah satunya) |
| Ollama | `ollama.exe` di PATH atau `%LOCALAPPDATA%\Programs\Ollama` | Sudah ada → "dipakai yang sudah ada"; belum → akan dipasang |
| Mic | Daftar perangkat input lewat `sounddevice` tidak tersedia di wizard; pakai `Get-PnpDevice -Class AudioEndpoint -Status OK` (PowerShell) dan cari nama berisi "Microphone". **Cek dulu** hasilnya di laptop dengan dan tanpa mic | Tidak ada → ⚠ "Mode suara butuh mikrofon; mode teks tetap jalan" |
| Path user non-ASCII | `os.environ["LOCALAPPDATA"]` | Ada huruf non-ASCII → ⚠ dan sarankan folder seperti `D:\MikuVision` (perlu diuji, bagian 9) |

**Komponen (halaman 4)**

| Komponen | Wajib | Perkiraan | Diteruskan ke `install.ps1` |
|---|---|---|---|
| Inti: suara, GUI, aksi desktop (Python, PyTorch, Whisper, MeloTTS) | ya | 9,5 GB (6 GB tanpa GPU) | (bawaan) |
| Otak Miku: Ollama + `qwen3:4b-instruct` | ya, kecuali Ollama dan modelnya sudah ada | 2,5 GB | (bawaan) |
| Membaca layar: `qwen3-vl:4b-instruct` | tidak | 3,3 GB | `-WithVision` |
| Suara khas Miku (RVC) | tidak; muncul tombol "Pilih file .pth…" dan "Pilih file .index…" | 0,6 GB | `-RvcModel <pth> -RvcIndex <index>` |

Angka ukuran disimpan di satu tabel di `miku_setup/components.py` dan diperbarui tiap rilis bila berubah.

## 4. Perubahan pada `install.ps1` (fase I1)

Semua opsi baru bersifat tambahan: menjalankan `install.bat` seperti sekarang tidak berubah perilakunya.

| Opsi baru | Perilaku |
|---|---|
| `-Progress` | Selain log biasa, cetak baris mesin ke stdout: `##MIKU {"event":"step","index":3,"total":10,"title":"Python 3.10 + virtualenv"}`, `{"event":"warn","message":"..."}`, `{"event":"error","message":"..."}`, `{"event":"done","ok":true}`. Satu JSON per baris, UTF-8. Dipancarkan dari `Write-Step`, `Write-Log` level WARN/ERROR, dan blok akhir `main` |
| `-ModelDir <path>` | Buat `<path>\ollama` dan `<path>\huggingface`, set `OLLAMA_MODELS` dan `HF_HOME` sebagai **variabel user** (`[Environment]::SetEnvironmentVariable(..., "User")`) dan di proses ini, **sebelum** Ollama dipasang/dinyalakan. Bila Ollama sudah jalan dengan lokasi lama: tutup `ollama app.exe` lalu nyalakan lagi (Ollama hanya membaca `OLLAMA_MODELS` saat start) |
| `-WithVision` | Setelah model utama: `ollama pull qwen3-vl:4b-instruct` (nama dari `VISION_MODEL` di `config.py`, dibaca seperti `Get-ConfiguredModel`) |
| `-RvcModel <pth> -RvcIndex <index>` | Salin kedua file ke `models\miku_default_rvc\weights\miku_default_rvc.pth` dan `models\miku_default_rvc\logs\miku_default_rvc\` (nama index disimpan apa adanya, dan `index_path` di config dibaca dari folder itu, lihat catatan), lalu lanjut seperti `Test-RvcModelPresent` = true |
| `-StartMenu` | Selain shortcut Desktop, buat shortcut di `[Environment]::GetFolderPath("Programs")\MikuVision\MikuVision.lnk` |
| Cadangan Ollama tanpa winget | Bila `winget` tidak ada (Windows LTSC, sebagian laptop kantor): unduh `https://ollama.com/download/OllamaSetup.exe` ke `.tools\`, jalankan diam-diam, tunggu `ollama.exe` muncul. **Cek dulu** opsi diam installer Ollama (`/SILENT` bila berbasis Inno Setup) dan lokasi pasangnya pada versi terbaru |
| Kode keluar | 0 = selesai, 1 = gagal yang sudah dijelaskan (`Stop-Install`), 2 = error tak terduga. Wizard menampilkan pesan `error` terakhir apa adanya |

Catatan:
- **RVC index:** sekarang `config.py` memakai nama file index yang tetap (`added_IVF4457_Flat_nprobe_1_miku_default_rvc_v2.index`). Untuk `-RvcIndex`, salin dengan nama itu (paling sederhana), **atau** ubah `config.py` supaya memakai file `*.index` pertama di folder tersebut. Pilih yang pertama untuk fase I1, dan catat keputusannya di PR.
- **Progres unduhan besar:** uv dijalankan dengan `UV_NO_PROGRESS=1`, dan progres `ollama pull` tidak terbaca rapi. Untuk "x GB terunduh", wizard **menghitung ukuran folder** `.tools\uv-cache` (langkah PyTorch) dan `<ModelDir>\ollama\models\blobs` (langkah model) setiap 2 detik. Tidak perlu mengubah `install.ps1`.

Test fase I1 (pytest, jalan di CI Windows lewat `pwsh`):
- `install.ps1 -Progress` dengan langkah palsu: tambahkan opsi tersembunyi `-SelfCheck`, yang hanya memancarkan 3 baris `##MIKU` lalu keluar. Test memastikan setiap baris adalah JSON valid dengan field yang benar.
- Parser progres di sisi wizard (fase I3) dites dengan potongan stdout nyata dari log instalasi.

## 5. Struktur kode wizard

Nama paket `miku_setup`, bukan `setup` (mudah tertukar dengan `setup.py`) atau `installer` (nama paket PyPA yang bisa terpasang di venv).

```
miku_setup/
  main.py        entry: argumen --uninstall, --repair, --update, --dry-run; memilih mode
  wizard.py      jendela customtkinter, navigasi halaman, tanpa logika berat
  pages/         satu file per halaman (welcome, license, checks, location, install, finish, maintenance)
  checks.py      cek sistem; fungsi murni yang menerima output perintah, supaya mudah dites
  components.py  tabel komponen dan ukuran
  download.py    unduh zip rilis + SHA256SUMS, lanjutkan bila terputus (HTTP Range), ekstrak aman
  runner.py      jalankan install.ps1 tanpa konsol (CREATE_NO_WINDOW), baca stdout, parse ##MIKU
  registry.py    entri "Apps & features" di HKCU, shortcut Start Menu, pembersihan saat hapus
  assets/        ikon .ico (dibuat dari sprite Miku, sama seperti New-DesktopShortcut)
miku_setup.spec  konfigurasi PyInstaller
tests/test_miku_setup_*.py
```

Aturan yang perlu dijaga:
- **Widget Tk hanya diubah dari main thread.** Unduhan dan `install.ps1` berjalan di thread terpisah dan mengirim event lewat `queue.Queue`, sama seperti `gui.py` (lihat crash Tk 9 di CHANGELOG v1.3.0).
- **Tidak ada `print` ke konsol**, karena exe dibangun dengan `--windowed`. Log wizard ditulis ke `%LOCALAPPDATA%\MikuVision-setup\setup-<waktu>.log`.
- **Mode `--dry-run`:** semua halaman bisa dijalani tanpa mengunduh atau memasang apa pun (runner palsu yang memutar ulang log contoh). Dipakai untuk mengembangkan UI dan untuk tangkapan layar README.
- **Ekstrak zip aman:** tolak entri dengan `..` atau path absolut (zip slip). Lewati `data/`, `models/`, `.venv/`, `.tools/`, `logs/` bila sudah ada di InstallDir.
- **Unduhan diverifikasi:** setiap rilis melampirkan `SHA256SUMS`, dan wizard menolak zip yang hash-nya tidak cocok.

## 6. Perawatan: Perbarui, Perbaiki, Hapus (fase I4)

Entri registry (per-user, tanpa admin): `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\MikuVision`

| Nilai | Isi |
|---|---|
| `DisplayName` | `MikuVision` |
| `DisplayVersion` | versi rilis, misalnya `1.6.0` |
| `Publisher` | `MocArjunnaja` |
| `InstallLocation` | InstallDir |
| `DisplayIcon` | `<InstallDir>\.tools\mikuvision.ico` |
| `UninstallString` | `"<InstallDir>\.tools\MikuVisionSetup.exe" --uninstall` (setup menyalin dirinya ke sana) |
| `ModifyPath` | `"<InstallDir>\.tools\MikuVisionSetup.exe"` |
| `EstimatedSize` | KB, dihitung setelah instalasi |
| `MikuModelDir` | ModelDir (dipakai saat hapus dan perbarui) |

| Mode | Yang dilakukan |
|---|---|
| **Perbarui** | Cek rilis terbaru lewat `releases/latest/download/version.json` (dilampirkan tiap rilis; bukan GitHub API, supaya tidak kena batas rate). Unduh zip, ekstrak tanpa menimpa data, jalankan `install.ps1 -Yes -Progress` (langkah yang sudah beres dilewati), perbarui `DisplayVersion` |
| **Perbaiki** | Jalankan ulang `install.ps1 -Yes -Progress` dengan komponen yang sama |
| **Hapus** | Konfirmasi dengan pilihan: [x] Hapus aplikasi (InstallDir kecuali `data/`), [ ] Hapus percakapan, memori, dan skill (`data/`), [ ] Hapus model (ModelDir). Lalu hapus shortcut, entri registry, dan variabel `OLLAMA_MODELS`/`HF_HOME` bila menunjuk ke ModelDir yang dihapus. Ollama **tidak** dihapus (aplikasi terpisah); tampilkan cara menghapusnya dari "Apps & features" |

Folder yang sedang dipakai (Miku masih jalan): cek proses `pythonw.exe` yang berjalan dari InstallDir, lalu minta user menutup Miku dulu.

## 7. Build dan rilis (fase I5)

Workflow baru `.github/workflows/release-setup.yml`, dipicu tag `v*`:
1. `runs-on: windows-latest`, Python 3.10, `pip install pyinstaller==<versi dipatok> customtkinter==<versi requirements>`.
2. `pyinstaller miku_setup.spec`: `--onefile --windowed --icon miku_setup/assets/mikuvision.ico --name MikuVisionSetup`, **tanpa UPX** (UPX sering memicu antivirus).
3. Buat `MikuVision-<versi>.zip` dari `git archive` tag itu, `version.json`, dan `SHA256SUMS`.
4. `gh release upload <tag> MikuVisionSetup.exe MikuVision-<versi>.zip version.json SHA256SUMS`.
5. README: bagian **Instalasi cepat** diganti tombol/link unduhan `MikuVisionSetup.exe`. `install.bat` tetap disebut untuk pengembang.

## 8. Fase kerja

| Fase | Isi | Selesai bila |
|---|---|---|
| **I1** | Opsi baru `install.ps1` (bagian 4) + test `-SelfCheck` | `install.bat` lama tetap jalan seperti sebelumnya; `install.ps1 -Yes -Progress -ModelDir D:\MikuTest\models` memasang lengkap dan model ada di `D:\MikuTest\models`; CI hijau |
| **I2** | Kerangka wizard: 6 halaman, navigasi, validasi, cek sistem nyata, `--dry-run` | Semua halaman bisa dijalani dengan `python -m miku_setup.main --dry-run`; test `checks.py` (parsing `nvidia-smi`, disk, path) hijau di CI |
| **I3** | Unduh + ekstrak + `runner.py` + progres + penanganan gagal/batal | Dari folder kosong sampai "Selesai" lewat `python -m miku_setup.main` di laptop dengan RTX; batal di tengah PyTorch lalu jalankan lagi → lanjut tanpa mengulang dari awal |
| **I4** | Registry, shortcut Start Menu, mode Perbarui/Perbaiki/Hapus | MikuVision muncul di "Apps & features"; Hapus tidak menyisakan file kecuali yang dipilih untuk disimpan; Perbarui dari rilis lama ke baru mempertahankan `data/` |
| **I5** | `miku_setup.spec`, workflow rilis, halaman/link unduhan di README | `MikuVisionSetup.exe` ≤ 40 MB terlampir otomatis di rilis; uji di VM Windows bersih (bagian 9) lulus |
| **IL** (nanti) | Wizard yang sama untuk Linux: runner memanggil `install.sh` dengan opsi setara (`--progress`, `--model-dir`, ...), sudo lewat `pkexec` (jendela password grafis), dibekukan menjadi AppImage atau binary tunggal, entri `.desktop` untuk uninstall | Teman pengguna Arch bisa memasang tanpa terminal |

## 9. Uji dan risiko

**Skenario uji di Windows** (VM Windows 11 bersih tanpa Python/git, ditambah laptop pengembang):

| Skenario | Lulus bila |
|---|---|
| VM tanpa GPU | Cek sistem ⚠ CPU, instalasi selesai dengan PyTorch CPU, Miku menjawab di mode teks |
| Laptop RTX 4050, model di D: | Model Ollama dan Hugging Face ada di D:, bukan C:; `ollama ps` 100% GPU |
| Ollama sudah terpasang | Tidak dipasang ulang; model yang sudah ada tidak diunduh ulang |
| Internet putus saat PyTorch | Pesan jelas; "Coba lagi" melanjutkan |
| Ruang disk kurang | Dihentikan di halaman 4 sebelum mengunduh apa pun |
| Nama user non-ASCII (`C:\Users\Siti Nurhaliza Ñ`) | Instalasi lulus, atau wizard menyarankan folder lain sebelum mulai |
| Tanpa winget | Ollama terpasang lewat `OllamaSetup.exe` |
| SmartScreen | Halaman unduhan menjelaskan "More info → Run anyway" dengan tangkapan layar |
| Hapus lalu pasang lagi | Bersih; skill dan percakapan kembali bila `data/` dipilih untuk disimpan |
| Tidak ada jendela hitam | Tidak satu pun jendela konsol muncul dari awal sampai selesai |

**Target angka:** `MikuVisionSetup.exe` ≤ 40 MB; jumlah klik dari membuka setup sampai Miku menyapa ≤ 8; 0 jendela terminal.

| Risiko | Mitigasi |
|---|---|
| SmartScreen "Windows protected your PC" (exe belum ditandatangani) | Penjelasan di halaman unduhan. Nanti: SignPath (gratis untuk proyek open source) atau Azure Trusted Signing (berbayar bulanan) |
| Antivirus menandai exe PyInstaller | Tanpa UPX, `--onefile` dengan versi PyInstaller dipatok; bila tetap ditandai, kirim ke Microsoft Security Intelligence untuk dianalisis ulang |
| Proxy/firewall kampus | Cek internet per situs di halaman 3, sehingga yang diblokir disebut namanya |
| `install.ps1` bertanya (`Confirm-Action`) | Wizard selalu memakai `-Yes`; persetujuan sudah diberikan user di halaman 4 |
| Execution policy PowerShell | `-ExecutionPolicy Bypass` hanya untuk proses itu, sama seperti `install.bat` |
| Dua versi Python (exe setup vs env aplikasi) | Terpisah sepenuhnya: Python di dalam exe hanya untuk wizard; aplikasi tetap memakai Python 3.10 dari uv di `.tools\python` |
| `OLLAMA_MODELS` berubah saat Ollama jalan | `install.ps1 -ModelDir` menutup dan menyalakan ulang Ollama (bagian 4) |
| Batas rate GitHub API | Wizard tidak memakai API; hanya URL `releases/latest/download/...` |

## 10. Di luar cakupan versi pertama

- **Paket offline**: satu folder berisi semua unduhan (wheel PyTorch, model Ollama, cache Hugging Face, `OllamaSetup.exe`) untuk memasang di komputer tanpa internet, misalnya di lab. MikuVision tetap berjalan 100% lokal dengan atau tanpa paket ini; paket offline hanya mengganti *dari mana* file diunduh saat instalasi. Bisa ditambah nanti dengan opsi `-OfflineDir` di `install.ps1`.
- **Diet dependency** (MeloTTS dan RVC lewat ONNX Runtime, bukan PyTorch): bisa memangkas ±11 GB menjadi ±2–3 GB. Topik riset tersendiri.
- macOS, Microsoft Store, pembaruan otomatis di latar.

## 11. Keputusan yang dibutuhkan dari user

1. Nama di "Apps & features" dan nama file: `MikuVision` / `MikuVisionSetup.exe`, oke?
2. Halaman lisensi karakter wajib dicentang, oke?
3. Folder instalasi bawaan `%LOCALAPPDATA%\Programs\MikuVision` (tanpa admin), oke?
4. Perlu halaman unduhan di GitHub Pages (fase I5), atau cukup link Releases?
5. Anggaran code signing: tidak ada dulu (SmartScreen dijelaskan), atau coba SignPath?
