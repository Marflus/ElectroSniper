@echo off
chcp 65001 >nul
echo ============================================
echo   Installation d'ElectroSniper (Windows 11)
echo ============================================
echo.

set PY_CMD=
py --version >nul 2>&1 && set PY_CMD=py
if "%PY_CMD%"=="" (
    python --version >nul 2>&1 && set PY_CMD=python
)
if "%PY_CMD%"=="" (
    echo [ERREUR] Python 3.11+ n'est pas installe ou pas dans le PATH.
    pause
    exit /b 1
)

if not exist ".venv" (
    echo Creation de l'environnement virtuel .venv...
    %PY_CMD% -m venv .venv
)

echo Mise a jour de pip et installation des dependances...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt

if not exist ".env" (
    copy .env.example .env >nul
    echo.
    echo [INFO] Fichier .env cree depuis .env.example.
    echo Ouvre .env pour renseigner ta cle ANTHROPIC_API_KEY et ton bot Telegram.
)

echo.
echo Installation terminee ! Lance start.bat pour demarrer ElectroSniper.
pause
