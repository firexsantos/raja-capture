# Raja Capture

Aplikasi screen capture lintas platform (Linux Wayland/X11, Windows) yang terinspirasi
oleh FastStone Capture: tangkap layar, anotasi, rekam layar, OCR, pemilih warna, dan
penggaris layar. Dibangun dengan Python + PySide6 (Qt 6).

## Fitur

| Fitur | Linux Wayland | Linux X11 | Windows |
|---|---|---|---|
| Layar penuh / area / jeda waktu | ✅ portal | ✅ | ✅ |
| Tangkap jendela | ✅ dialog portal GNOME | ✅ hover-highlight (perlu `python-xlib`) | ✅ hover-highlight |
| Tangkap scroll (halaman panjang) | ✅ scroll manual | ✅ manual + otomatis | ✅ manual + otomatis |
| Editor anotasi (panah, kotak, elips, garis, pena, teks, stabilo, nomor langkah, sensor/pixelate) | ✅ | ✅ | ✅ |
| Crop, ubah ukuran, putar, balik, bingkai, undo/redo | ✅ | ✅ | ✅ |
| Simpan PNG/JPG/BMP/WEBP/PDF, salin, cetak | ✅ | ✅ | ✅ |
| Rekam layar ke MP4 | ✅ portal + GStreamer | ✅ ffmpeg | ✅ ffmpeg |
| Rekam suara (mikrofon / suara sistem / keduanya) | ✅ PipeWire/Pulse | ✅ Pulse | ✅ DirectShow (Stereo Mix) |
| Ubah ukuran objek anotasi (handle) | ✅ | ✅ | ✅ |
| Kirim: upload Imgur / server kustom, email, buka dengan, salin sebagai file | ✅ | ✅ | ✅ |
| Pemilih warna (kaca pembesar) & penggaris | ✅ | ✅ | ✅ |
| OCR (Tesseract) | ✅ | ✅ | ✅ |
| Shortcut global | ✅ via shortcut GNOME | ✅ pynput / GNOME | ✅ RegisterHotKey |
| Tray + toolbar melayang | ✅ | ✅ | ✅ |

## Unduh

Paket siap pakai dibuat otomatis oleh GitHub Actions (tab **Actions** → artefak, atau
halaman **Releases** untuk tag `v*`):

* **Linux:** `RajaCapture-<versi>-x86_64.AppImage` (jalankan langsung) atau
  `raja-capture_<versi>_amd64.deb` (`sudo apt install ./raja-capture_*.deb`)
* **Windows:** `RajaCapture-<versi>-setup.exe` (installer) atau `…-windows-portable.zip`

## Instalasi (mode pengembangan)

```bash
python3 -m venv .venv
.venv/bin/pip install -e .            # Linux/Windows
.venv/bin/pip install -e ".[x11]"     # tambahan untuk X11 (pynput, python-xlib)
.venv/bin/raja-capture
```

Dependensi sistem:

* **Linux (Wayland):** `xdg-desktop-portal` (sudah ada di GNOME/KDE), untuk rekam:
  `gstreamer1.0-tools gstreamer1.0-pipewire gstreamer1.0-plugins-ugly`
* **Linux (X11) & Windows:** `ffmpeg` di PATH untuk merekam
* **OCR:** `tesseract-ocr` (+ `tesseract-ocr-ind` untuk Bahasa Indonesia). Di Windows,
  pasang Tesseract dari UB-Mannheim; lokasinya terdeteksi otomatis.

## Pemakaian

```
raja-capture                 # tampilkan toolbar
raja-capture --tray          # mulai di tray saja
raja-capture --region        # langsung tangkap area (instance yang berjalan menerima perintah)
raja-capture --full | --window | --scroll | --record-region | --record-full
raja-capture --color | --ruler | --ocr | --settings | --quit
raja-capture gambar.png      # buka gambar di editor
```

Shortcut bawaan: `Ctrl+Alt+1` … `Ctrl+Alt+9` (layar penuh, jendela, area, scroll, rekam
area, rekam layar, warna, penggaris, OCR). Bisa diubah di **Pengaturan → Shortcut**.

* **GNOME:** Wayland tidak mengizinkan aplikasi menangkap tombol global. Klik
  **Pengaturan → Shortcut → Terapkan ke GNOME**; Raja Capture akan menulis shortcut kustom
  GNOME yang menjalankan `raja-capture --<aksi>`.
* **Pengaturan → Sistem** berisi tombol untuk memasang entri menu aplikasi (.desktop) dan
  autostart saat login.

Di layar pemilihan: seret = area, klik = jendela (mode jendela), `Enter` = seluruh monitor,
`Esc`/klik kanan = batal. Di editor: tombol huruf memilih alat (V, A, L, R, E, H, P, T, N, B, C),
`Shift` saat menggambar = lurus/persegi, `Ctrl+scroll` = zoom, klik tengah = geser.

## Upload & kirim

Menu **Kirim** di editor: upload ke Imgur (isi *Client ID* gratis di Pengaturan → Kirim),
upload ke server sendiri (POST multipart; atur URL, nama field, header JSON, dan lokasi link
di jawaban JSON, mis. `data.url`), kirim email dengan lampiran, buka dengan program lain
(mis. GIMP), salin sebagai file, dan riwayat upload (beserta link hapus Imgur).

## Membangun paket

```bash
.venv/bin/pip install pyinstaller
PYTHON=.venv/bin/python packaging/build_linux.sh          # AppImage + .deb  -> dist/
SKIP_APPIMAGE=1 PYTHON=.venv/bin/python packaging/build_linux.sh   # .deb saja
```

Windows (PowerShell):

```powershell
pip install . pyinstaller
python packaging\make_icons.py
python -m PyInstaller --noconfirm packaging\raja-capture.spec
iscc /DAppVersion=0.2.0 packaging\windows\installer.iss   # butuh Inno Setup 6
```

Push tag `v0.2.0` untuk membuat GitHub Release berisi semua paket secara otomatis.

## Struktur kode

```
raja_capture/
  app.py              controller utama, tray, alur capture, CLI
  config.py           pengaturan (QSettings) & penamaan file
  capture/            backend: portal.py (Wayland), Qt + winenum/x11enum (Windows/X11)
  ui/overlay.py       layar pilih area/jendela/warna/penggaris (kaca pembesar)
  ui/editor.py        editor anotasi; ui/items.py objek anotasi
  ui/scroll_capture.py + stitch.py   tangkap scroll & penyambungan gambar
  recorder.py         perekam layar (GStreamer/ffmpeg)
  hotkeys.py, ipc.py  shortcut global & single-instance
  share.py            upload (Imgur/kustom), email, buka dengan, salin file
  ocr.py, imageio.py, system.py
packaging/            spec PyInstaller, skrip AppImage/.deb, installer Inno Setup
.github/workflows/    CI: tes + build Linux & Windows + rilis
tests/                pytest (berjalan offscreen)
```

Menjalankan tes: `.venv/bin/pip install pytest && .venv/bin/python -m pytest -q`

## Batasan yang diketahui

* Wayland: tangkap jendela memakai dialog portal (bukan hover); scroll otomatis tidak
  tersedia (scroll manual saja); rekam area memotong stream monitor sehingga paling akurat
  pada satu monitor. GNOME menampilkan izin berbagi layar sekali, lalu pilihan diingat.
* macOS: tangkap & editor berjalan lewat Qt, perekaman belum didukung.
* Windows: suara sistem butuh perangkat loopback seperti "Stereo Mix" (aktifkan di
  pengaturan Sound) karena ffmpeg/DirectShow tidak merekam output secara langsung.
* Paket berukuran besar (~70 MB .deb, ~230 MB terpasang) karena membawa Qt dan Python.
