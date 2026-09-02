@echo off
setlocal
title PDF zu JPG Konverter

if not exist ".venv\Scripts\python.exe" (
    echo Erstelle virtuelle Python-Umgebung...
    py -m venv .venv
    if errorlevel 1 (
        echo FEHLER: Python konnte nicht gestartet werden.
        pause
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"

echo Installiere/aktualisiere Abhaengigkeiten...
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo FEHLER beim Installieren der Abhaengigkeiten.
    pause
    exit /b 1
)

echo Starte Anwendung...
python main.py
