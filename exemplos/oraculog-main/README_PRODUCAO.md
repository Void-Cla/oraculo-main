# 🚀 Oráculo Trading Bot — Manual de Produção e Execução Real

Sistema Quantitativo de Micro-Trading de Alta Precisão para **Binance Spot** com dados de mercado **100% reais**, validação matemática estrita da **Regra de Lucro Líquido Real (>= +$0,01 USD após todas as taxas e slippage)**, ciclo de IA estratégica a cada 2 horas via Gemini e treino online contínuo de pesos estatísticos.

---

## 🎯 Princípios e Garantias do Sistema

1. **Zero Dados Fictícios / Simulados**: 
   - Cotações, Top Bids, Top Asks, Volume e Desequilíbrio do Livro de Ofertas (Order Book Imbalance) são consumidos diretamente da API oficial da Binance (`https://data-api.binance.vision` e `https://api.binance.com`).
2. **Regra Inegociável de Lucro Líquido**:
   - Todo sinal é submetido à fórmula:
     $$\text{Lucro Líquido} = (\text{P}_{\text{saída}} \times Q \times (1 - \text{taxa}_{\text{saída}})) - (\text{P}_{\text{entrada}} \times Q \times (1 + \text{taxa}_{\text{entrada}})) - \text{Slippage}$$
   - Se o lucro líquido for inferior a **+$0,01 USD**, a ordem é sumariamente rejeitada pelo Guardião de Risco.
3. **Pares Monitorados em Tempo Real**:
   - `BTCUSDT`, `ETHUSDT`, `BNBUSDT`, `SOLUSDT`, `ETHBTC`, `BNBBTC`.

---

## ⚡ Como Executar em Sua Máquina Local

### Opção 1: Linux / macOS (Recomendado)
```bash
chmod +x iniciar_oraculo.sh
./iniciar_oraculo.sh
```

### Opção 2: Windows
Basta dar dois cliques no arquivo `iniciar_oraculo.bat` ou rodar no CMD/PowerShell:
```cmd
iniciar_oraculo.bat
```

### Opção 3: Inicializador Python Direto
```bash
python3 run_production.py
```
O sistema abrirá na porta **3000** (`http://localhost:3000`).

---

## 🔑 Configuração de Dinheiro Real (Binance API Key)

No arquivo `.env`:
```env
# Insira suas credenciais da Binance para operar em conta real:
BINANCE_API_KEY="sua_chave_de_api_aqui"
BINANCE_API_SECRET="sua_chave_secreta_aqui"

# Chave do Gemini para a análise macro de 2h:
GEMINI_API_KEY="sua_chave_gemini"
```

> **Nota de Segurança:**
> - Ao criar sua API Key na Binance, habilite apenas **"Enable Reading"** e **"Enable Spot & Margin Trading"**.
> - **NUNCA** habilite a permissão de "Withdrawals" (Saques). O bot precisa apenas de leitura e ordens spot.
> - Sem as chaves preenchidas, o bot opera em **Modo Auditoria com Dados de Mercado 100% Reais**, registrando no banco SQLite exatamente o que teria sido lucrado.

---

## 📁 Estrutura Limpa do Projeto

```
├── backend_oraculo/               # Motor Quantitativo em Python
│   ├── cliente_binance.py         # Cliente Oficial Binance com fallback e HMAC SHA256
│   ├── motor_orquestrador.py      # Orquestrador com avaliação concorrente em tempo real
│   ├── config.py                  # Parâmetros e travas de segurança
│   ├── executar_ciclo.py          # Bridge CLI
│   ├── calculos/                  # Livro de ofertas, momentum e features
│   ├── risco/                     # Validador de Lucro Líquido Real (>= +$0,01)
│   ├── ia/                        # Sessão de 2h com viés macro
│   ├── modelagem/                 # Treino contínuo estocástico dos pesos
│   └── persistencia/              # Banco SQLite de auditoria (oraculo_producao.db)
├── src/                           # Interface de Comando em React + Tailwind
│   ├── components/                # Painéis de controle, livro de ordens e métricas
│   └── App.tsx                    # Shell principal
├── server.ts                      # Servidor de Produção integrado Express + Vite
├── run_production.py              # Script executável de inicialização
├── iniciar_oraculo.sh             # Inicializador Linux/Mac
└── iniciar_oraculo.bat            # Inicializador Windows
```
