"""Pacote do auto-trader — decomposição de `testnet_auto_trader.py` (FASE 6).

Responsabilidades separadas por módulo:
- `calculos`: funções puras de cálculo do ciclo (custos, pisos, teto de notional).

A extração é incremental e segura: cada função movida é re-exportada pelo god-file
original, mantendo todos os imports existentes e testes verdes antes e depois.
"""
