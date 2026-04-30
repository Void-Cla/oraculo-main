@echo off
SETLOCAL

IF NOT EXIST .venv (
  python -m venv .venv
)

call .venv\Scripts\activate
python -m pip install -r requirements.txt
python scripts\inicializar_db.py
echo Iniciando API Oraculo em http://127.0.0.1:8000
python -m uvicorn src.api.app:app --reload --port 8000
