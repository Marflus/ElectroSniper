@echo off
chcp 65001 >nul
title ElectroSniper - Scanner Electronique HS

if not exist ".venv\Scripts\python.exe" (
    echo Environnement virtuel introuvable. Lance d'abord install.bat.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
python run.py
pause
