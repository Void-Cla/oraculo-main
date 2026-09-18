#!/usr/bin/env python3
"""
Script de Inicialização de Produção do Oráculo Trading Bot (PT-BR)
Permite executar o sistema completo localmente com dados 100% reais da Binance.

Uso:
  python3 run_production.py
"""
import os
import sys
import subprocess
import time
import shutil

def imprimir_banner():
    print("=" * 70)
    print("      ORÁCULO TRADING BOT - SISTEMA QUANTITATIVO DE ALTA PRECISÃO")
    print("           BINANCE SPOT | DADOS 100% REAIS | LUCRO LÍQUIDO >= $0.01")
    print("=" * 70)

def verificar_requisitos():
    print("\n[1/4] Verificando ambiente de execução...")
    if sys.version_info < (3, 9):
        print("[-] ERRO: Python 3.9 ou superior é obrigatório.")
        sys.exit(1)
    print(f"[+] Python {sys.version.split()[0]} detectado.")

    node_bin = shutil.which("node")
    npm_bin = shutil.which("npm")
    if not node_bin or not npm_bin:
        print("[-] AVISO: Node.js/npm não encontrados no PATH.")
    else:
        print("[+] Node.js e npm detectados.")

def testar_conexao_binance():
    print("\n[2/4] Testando conexão com a API oficial da Binance (dados reais)...")
    try:
        from backend_oraculo.cliente_binance import CLIENTE_BINANCE
        ping = CLIENTE_BINANCE.testar_ping()
        print(f"[+] Binance Conectada! Latência: {ping['latencia_ms']}ms | Endpoint: {ping['endpoint_ativo']}")
        
        # Testar livro de ofertas real do BTCUSDT
        livro = CLIENTE_BINANCE.obter_livro_ofertas_real("BTCUSDT", limite=5)
        print(f"[+] Cotação Real BTCUSDT: ${livro['preco_atual']:,.2f} USD")
        print(f"[+] Melhor Bid: ${livro['melhor_bid']:,.2f} | Melhor Ask: ${livro['melhor_ask']:,.2f}")
        print(f"[+] Desequilíbrio do Livro: {livro['desequilibrio_livro']:+.4f}")
    except Exception as e:
        print(f"[-] Aviso na conexão com a Binance: {e}")

def verificar_build_frontend():
    print("\n[3/4] Verificando build do frontend de produção...")
    dist_path = os.path.join(os.getcwd(), "dist")
    if not os.path.exists(dist_path) or not os.path.exists(os.path.join(dist_path, "index.html")):
        print("[*] Compilando assets de produção (npm run build)...")
        res = subprocess.run(["npm", "run", "build"], shell=False)
        if res.returncode != 0:
            print("[-] Falha ao compilar frontend. Tentando continuar...")
    else:
        print("[+] Build de produção pronto em /dist.")

def iniciar_servidor():
    print("\n[4/4] Iniciando Servidor Unificado Oráculo na porta 3000...")
    print("----------------------------------------------------------------------")
    print(" Acesse no seu navegador: http://localhost:3000")
    print(" Pressione Ctrl+C para encerrar com segurança.")
    print("----------------------------------------------------------------------\n")
    
    # Inicia via tsx ou node dist/server.cjs
    if os.path.exists("dist/server.cjs"):
        cmd = ["node", "dist/server.cjs"]
    else:
        cmd = ["npx", "tsx", "server.ts"]
        
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\n[*] Oráculo Trading Bot encerrado com segurança.")

def main():
    imprimir_banner()
    verificar_requisitos()
    testar_conexao_binance()
    verificar_build_frontend()
    iniciar_servidor()

if __name__ == "__main__":
    main()
