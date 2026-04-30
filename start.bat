@echo off
SETLOCAL

cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
  echo [ERRO] Venv nao encontrada em ".venv".
  echo Crie a venv antes de iniciar o projeto.
  exit /b 1
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
  echo [ERRO] Falha ao ativar a venv.
  exit /b 1
)

if not exist "frontend\node_modules" (
  echo [INFO] Instalando dependencias do frontend...
  pushd "frontend"
  call npm install
  if errorlevel 1 (
    popd
    echo [ERRO] Falha ao instalar dependencias do frontend.
    exit /b 1
  )
  popd
)

echo [INFO] Iniciando backend e frontend...

start "Oraculo Backend" cmd /k "cd /d ""%~dp0"" && call "".venv\Scripts\activate.bat"" && python src\main.py"
start "Oraculo Frontend" cmd /k "cd /d ""%~dp0frontend"" && node server.js"

echo [OK] Backend:  http://127.0.0.1:8000
echo [OK] Frontend: http://127.0.0.1:3000

exit /b 0
