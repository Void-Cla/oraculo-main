#!/bin/bash
set -e
cd "$(dirname "$0")"

if [ ! -f ".venv/bin/activate" ]; then
  echo "[INFO] Criando venv..."
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -r requirements.txt -q

echo "[INFO] Inicializando banco de dados..."
python -c "from src.persistencia.conexao import inicializar_db; inicializar_db(); print('[OK] DB pronto')"

echo "[INFO] Iniciando Oraculo Auto-Trading em http://0.0.0.0:8000"
uvicorn src.main:app --host 0.0.0.0 --port 8000
