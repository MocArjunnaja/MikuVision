# Fase 0 Agent Visi di Linux: Hasil Spike

Diukur 31 Okt 2026 di laptop pengembang: RTX 4050 Laptop 6 GB, Linux Mint (Cinnamon, sesi X11), layar 1920×1080, Ollama dengan `qwen3:4b-instruct` dan `qwen3-vl:4b-instruct`.
Rencana lengkap: [`docs/PLAN_VISION_AGENT.md`](../../docs/PLAN_VISION_AGENT.md). Hasil versi Windows: [`../vision_phase0/RESULTS.md`](../vision_phase0/RESULTS.md).

Screenshot dan daftar elemen tidak disimpan di repo, karena bisa memuat data pribadi (nama folder, akun). Skrip menulisnya ke folder yang diberikan saat dijalankan.

## Ringkasan

- **AT-SPI2 bisa menggantikan UI Automation**: jalan tanpa mengubah pengaturan, < 1 s per jendela, tanpa GPU. Celahnya: ikon toolbar dan slider tanpa nama, dan file di tampilan ikon Nemo tidak terbaca.
- **Qwen-VL memilih elemen: 51/54 dengan daftar AT-SPI + gambar** (daftar saja 45/54, gambar saja 24/54), 0,17 s per pilihan. Semua kesalahan mode daftar ada pada elemen tanpa nama, dan gambar menutup celah itu. Di Windows angkanya 43/45 (keduanya) dan 44/45 (daftar saja).
- **Membaca layar**: kelima nama file dummy di Nemo terbaca 3/3 kali, dan volume "50%" 3/3, sekitar 1 s.
- **Agent mouse/keyboard**: aksi tunggal berhasil (mengetik di Xed, 5/5). Untuk urutan beberapa klik (Kalkulator 12 + 7), model hanya berhasil bila **menyusun rencana dari daftar nama tanpa gambar** (3/3). Dengan gambar, rencananya kacau (0/7 percobaan). Tidak ada satu strategi yang menang di kedua tugas, jadi Fase 3 perlu menggabungkan keduanya.
- **Tukar model jauh lebih cepat dari Windows**: qwen3-vl dimuat 2,4–2,6 s (Windows 6,5–7,3 s), kembali ke qwen3:4b 1,9–2,0 s (Windows 3,6–4,3 s). qwen3-vl memakai 4,3 GB VRAM pada `num_ctx` 8192.
- **Shortcut global** lewat XGrabKey jalan tanpa root (5/5, ±24 ms).

## 1. Cakupan AT-SPI2

Skrip: `atspi_spike.py` (Python sistem, karena `pyatspi` adalah paket sistem). Hanya jendela yang **baru muncul** setelah perintah dijalankan yang dibaca, lalu ditutup lagi. Nemo dibuka di folder berisi file dummy.

| Jendela | Elemen interaktif | Bernama | Node dibaca | Waktu baca pohon |
|---|---|---|---|---|
| Kalkulator (gnome-calculator) | 28 | 26 | 54 | 0,10–0,15 s |
| Editor teks (Xed) | 21 | 8 | 213 | 0,07–0,09 s |
| File manager (Nemo) | 134 | 27 | 483 | 0,25 s |
| Pengaturan Suara (Cinnamon) | 19 | 6 | 107 | 0,06–0,08 s |
| System Monitor | 132 | 132 | 325 | 0,41–0,97 s |

Temuan:
- AT-SPI jalan tanpa mengubah pengaturan apa pun (`toolkit-accessibility` tetap `false`), cepat (< 1 s), dan tanpa GPU. Kotak elemen memakai koordinat layar, jadi bisa langsung diklik.
- **Celah penting**:
  - Ikon toolbar Xed (Baru, Buka, Simpan, Undo, …) tidak bernama.
  - Tombol mute dan slider di Pengaturan Suara tidak bernama; labelnya berupa teks terpisah yang tidak interaktif.
  - File di tampilan ikon Nemo tidak muncul sama sekali.

  Untuk elemen-elemen ini dibutuhkan gambar (VLM) atau OCR. Pilihan lain: menyertakan label teks di dekatnya, atau relasi `labelled-by`.
- Label nomor Set-of-Mark yang ditaruh di dalam kotak menutupi teks tombol ("File" terbaca "1le"). Sekarang nomor ditaruh di kiri luar kotak, dengan huruf tebal 16 px.

## 2. Qwen-VL memilih elemen (Set-of-Mark)

Skrip: `vlm_spike.py`. 18 tujuan (Kalkulator, Xed, Pengaturan Suara, Nemo; bahasa Indonesia dan Jepang) × 3 percobaan. Lima tujuan menunjuk elemen **tanpa nama** (ikon Simpan/Baru di Xed, area teks, tombol mute, slider volume); dari daftar teks saja, elemen ini hanya bisa ditebak dari jenisnya.

| Model | Mode | Akurasi | Median | VRAM |
|---|---|---|---|---|
| qwen3-vl:4b-instruct | text | 45/54 | 0,14 s | 4,3 GB |
| qwen3-vl:4b-instruct | image | 24/54 | 0,15 s | 4,3 GB |
| **qwen3-vl:4b-instruct** | **both** | **51/54** | 0,17 s | 4,3 GB |

Temuan:
- Mode **text** benar di semua elemen bernama (15/18 tujuan, 3/3 tiap tujuan). Gagal tepat di tiga tujuan yang elemennya tanpa nama:
  - ikon Simpan dan ikon Baru di toolbar Xed: model memilih menu File / Documents;
  - tombol mute: model memilih slider.
- Mode **image** lemah untuk tombol bernama: untuk "tekan 7" dan "tekan 8" model menjawab nomor label 7 dan 8, bukan tombolnya. Juga gagal di Nemo, di mana label padat. Ikon Simpan justru benar 3/3.
- Mode **both** menggabungkan kelebihan keduanya. Satu-satunya yang gagal: "dokumen baru lewat ikon toolbar" (model memilih menu File).
- Jawaban sangat konsisten: 3 percobaan per tujuan hampir selalu memberi nomor yang sama.

## 3. Qwen-VL membaca layar

Skrip: `vlm_spike.py` mode `read`. Screenshot tanpa nomor, 3 percobaan.

| Jendela | Pertanyaan | Hasil |
|---|---|---|
| Nemo (folder dummy) | Sebutkan nama file dan folder | 5/5 nama terbaca, 3/3 kali (`catatan_kuliah.txt`, `jadwal.odt`, …) |
| Pengaturan Suara | Berapa volume output? | "50%", 3/3 |
| Kalkulator | Aplikasi apa, tombol apa saja? | "calculator" 3/3; menyebut √ dan π hanya 1/3 |

Median ±1,1 s per jawaban. Qwen-VL bisa menutup celah AT-SPI di Nemo (file yang tidak ada di pohon aksesibilitas) tanpa OCR terpisah. Teks Jepang belum diuji.

## 4. Percobaan agent: Qwen-VL menggerakkan mouse dan keyboard

Skrip: `agent_demo.py`. Loop amati → pilih satu aksi → `xdotool` → amati ulang, maksimal 10 langkah, pada jendela yang dibuka sendiri oleh skrip. Model memilih nomor elemen; koordinat klik diambil dari kotak AT-SPI. Kill switch: mouse ke pojok kiri atas.

| Strategi | Kalkulator: "hitung 12 + 7" | Xed: "tulis 'Halo dari Miku'" |
|---|---|---|
| `step`: satu aksi per langkah, dengan gambar | 0/3. Mengulang "+" atau "0" sampai batas 10 langkah | 3/3. Satu aksi: mengetik lewat keyboard |
| `plan`: seluruh urutan aksi sekaligus, dengan gambar | 0/2. Rencana tanpa "+" ("12", "7") | 2/2. Klik area teks, lalu mengetik |
| `names` dengan gambar | 0/2. "12", "plus", "7", "=" | - |
| `names`: urutan **nama** tombol, tanpa gambar; kode mencocokkan nama ke elemen | **3/3**. Klik 1, 2, +, 7, = dengan mouse; 4,8 s, satu panggilan LLM | 0/3. Membuka menu Edit dulu, teks tidak masuk |

Temuan:
- Pada soal perencanaan yang sama tanpa gambar, qwen3-vl dan qwen3:4b sama-sama menjawab `["1","2","+","7","="]` 5/5. Jadi **gambar justru mengacaukan perencanaan beberapa langkah**, sedangkan untuk satu aksi gambar membantu.
- Rancangan untuk Fase 3:
  - susun rencana dari daftar nama AT-SPI tanpa gambar, lalu kode mencocokkan nama ke elemen;
  - gambar dipakai hanya untuk elemen tanpa nama dan untuk tugas satu aksi;
  - setelah tiap langkah, periksa isi field yang bisa diedit.
- Pengecek keberhasilan harus membaca field yang bisa diedit (`STATE_EDITABLE`), bukan hanya elemen interaktif. Hasil Kalkulator ada di elemen `editbar` tanpa aksi.
  - Label tidak boleh dipakai: riwayat Kalkulator tersimpan antar-sesi, sehingga "19" dari percobaan lama ikut terbaca.
  - Bug ini sempat membuat Kalkulator tampak gagal padahal hasilnya sudah 19 di layar.
- Klik selalu mendarat di jendela uji. Fase 2 tetap perlu memeriksa bahwa titik klik ada di dalam jendela target sebelum mengklik.

## 5. Shortcut keyboard global (pemicu)

Skrip: `../triggers_linux/hotkey_spike.py`. XGrabKey pada root window lewat `python-xlib` (tanpa root, library yang sama dengan maskot). Shortcut ditekan 5× lewat `xdotool`.

| Kombinasi | Diterima | Jeda median |
|---|---|---|
| `Ctrl+Shift+M` | 5/5 | 24,7 ms |
| `Ctrl+Alt+M` | 5/5 | 23,8 ms |
| `Super+M` | 0/5 | - (tombol Super diambil Cinnamon) |

Jeda sudah termasuk waktu menjalankan `xdotool`. Grab dilepas setelah tes. Bila kombinasi sudah dipakai aplikasi lain, X11 menolak dengan `BadAccess` dan skrip melaporkannya.

## Langkah berikutnya

1. **T1**: shortcut keyboard untuk mulai bicara (XGrabKey / `keyboard`, cadangan `miku.py --trigger`).
2. **Fase 1** (hanya baca): `describe_screen()` memakai gambar (Nemo, pesan error), dan `find_on_screen(query)` memakai daftar AT-SPI. AT-SPI dibaca lewat helper `/usr/bin/python3`, karena venv tidak punya `pyatspi`.
3. **Fase 2–3**: strategi gabungan dari bagian 4, konfirmasi aksi berisiko, cek titik klik di dalam jendela target, kill switch.
4. Belum diuji: LibreOffice, Firefox/Brave (`--force-renderer-accessibility`), tujuan berbahasa Jepang di agent, dan RapidOCR.
