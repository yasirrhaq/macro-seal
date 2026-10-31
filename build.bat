@echo off
cd /d "%~dp0"

rem Hasil: dist\MacroSeal.exe (bisa dipakai tanpa Python)
python -m pip install pyinstaller keyboard pynput
python -m PyInstaller --onefile --windowed --name MacroSeal --clean -y script.py
pause
