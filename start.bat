@echo off
rem Video Studio with a visible console (for reading errors). Normal use: the Desktop shortcut,
rem which runs launch.py with pythonw and no window. Close this window to stop.
title Video Studio
set PYTHONUTF8=1
set HF_HUB_DISABLE_SYMLINKS_WARNING=1
set PATH=%LOCALAPPDATA%\Microsoft\WinGet\Links;%PATH%
cd /d "%~dp0"
set PY=%~dp0.venv\Scripts\python.exe
if not exist "%PY%" set PY=%USERPROFILE%\Developer\tts-vi\.venv-vieneu\Scripts\python.exe
if not exist "%PY%" (
  echo Chua cai dat. Chay: powershell -ExecutionPolicy Bypass -File install.ps1
  pause
  exit /b 1
)
echo Dang khoi dong Video Studio...
"%PY%" launch.py
pause
