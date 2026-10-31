@echo off
cd /d "%~dp0"

rem Pasang dependensi otomatis saat pertama kali dijalankan
python -c "import keyboard, pynput" 2>nul || (
  echo Memasang dependensi keyboard dan pynput...
  python -m pip install keyboard pynput || (
    echo Gagal memasang dependensi. Pastikan Python sudah terpasang.
    pause
    exit /b 1
  )
)

rem pythonw = jalankan tanpa jendela console
start "" pythonw script.py
