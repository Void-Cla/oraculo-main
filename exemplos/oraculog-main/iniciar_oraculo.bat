@echo off
title Oraculo Trading Bot - Binance Spot
echo =======================================================================
echo         ORACULO TRADING BOT - INICIALIZADOR DE PRODUCAO (WINDOWS)      
echo =======================================================================

if not exist .env (
  echo [*] Criando .env a partir de .env.example...
  copy .env.example .env
)

echo [*] Compilando assets de producao...
call npm run build

echo [*] Iniciando Oraculo com Dados 100%% Reais da Binance...
python run_production.py
pause
