# Seal Offline Macro Builder

Makro keyboard dengan UI untuk Seal Offline: susun urutan tombol & delay, tambahkan buff otomatis per interval, lalu simpan sebagai profil.

![Screenshot](docs/screenshot.png)

## Fitur

- Sequence tombol & delay: tambah, edit, urutkan, salin, hapus (bisa pilih banyak dengan Ctrl/Shift + klik).
- Rekam tombol langsung dari keyboard.
- Buff otomatis: tombol yang ditekan tiap N menit di sela sequence.
- Preset bawaan dan profil sendiri (disimpan di `profiles.json`).
- Tekan **F12** untuk menghentikan makro secara darurat.

## Cara Pakai

Double-click `run.bat`. Dependensi (`keyboard`, `pynput`) terpasang otomatis saat pertama kali dijalankan.

Atau manual:

```
pip install keyboard pynput
python script.py
```

Jalankan sebagai Administrator jika tombol tidak terbaca di dalam game.
