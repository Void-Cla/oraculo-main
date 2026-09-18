@echo off
SETLOCAL

cd /d "%~dp0"

set "DB_PATH=%~dp0dados\oraculo.sqlite"

if not exist ".venv\Scripts\activate.bat" (
  echo [ERRO] Venv nao encontrada em ".venv". Crie com: python -m venv .venv
  exit /b 1
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
  echo [ERRO] Falha ao ativar a venv.
  exit /b 1
)

echo [INFO] Iniciando Oraculo Auto-Trading (servidor unico)...
echo [INFO] Banco operacional: %DB_PATH%
echo [OK] Acesse http://127.0.0.1:8000 no browser

uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

exit /b 0
