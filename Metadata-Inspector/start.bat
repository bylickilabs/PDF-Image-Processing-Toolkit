@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [INFO] Virtuelle Umgebung wird erstellt ...
    py -3 -m venv .venv
    if errorlevel 1 goto :error
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 goto :error

python app.py
exit /b 0

:error
echo.
echo [FEHLER] Installation oder Start fehlgeschlagen.
pause
exit /b 1
