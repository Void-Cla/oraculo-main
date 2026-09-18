@echo off
SETLOCAL

cd /d "%~dp0.."
set "DB_PATH=%CD%\dados\oraculo.sqlite"

IF NOT EXIST .venv (
  python -m venv .venv
)

call .venv\Scripts\activate
python -m pip install -r requirements.txt
python scripts\inicializar_db.py
echo Banco operacional: %DB_PATH%
echo Iniciando API Oraculo em http://127.0.0.1:8000
python -m uvicorn src.main:app --reload --port 8000
