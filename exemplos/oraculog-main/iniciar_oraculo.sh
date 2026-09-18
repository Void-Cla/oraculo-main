#!/usr/bin/env bash
# Script de Inicialização Rápida para Linux/macOS
set -e

echo "======================================================================="
echo "        ORÁCULO TRADING BOT - INICIALIZADOR DE PRODUÇÃO (PT-BR)        "
echo "======================================================================="

# Verifica se existe arquivo .env
if [ ! -f .env ]; then
  echo "[*] Criando .env inicial a partir de .env.example..."
  cp .env.example .env
fi

# Testa se npm e python3 existem
command -v python3 >/dev/null 2>&1 || { echo "[-] Python3 não encontrado. Instale Python 3.9+"; exit 1; }
command -v node >/dev/null 2>&1 || { echo "[-] Node.js não encontrado. Instale Node.js 18+"; exit 1; }

echo "[+] Instalando dependências se necessário..."
if [ ! -d node_modules ]; then
  npm install
fi

echo "[+] Gerando build executável de produção..."
npm run build

echo "[+] Iniciando Oráculo com Dados 100% Reais da Binance..."
python3 run_production.py
