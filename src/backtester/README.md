# Backtester

## Papel

Avaliar offline, de forma honesta, se há edge LÍQUIDO — sem contaminar o fluxo online nem
usar conta real.

## Arquivo

- `walk_forward.py`
  - `backtest_walk_forward`: avaliação WALK-FORWARD (treina no passado, testa no futuro, rola)
    com contabilidade SEMPRE LÍQUIDA. Só entra trade cujo ganho bruto previsto cobre
    `alvo_líquido + custo_round_trip`; o resultado contabilizado é bruto − custo.
  - `custo_pct_round_trip` / `bruto_necessario_para_liquido_*` / `liquido_de_bruto_pct`:
    matemática do lucro líquido (bruto = líquido + taxas). Custo via `EVCalculator` (fonte única).

Runner: `scripts/backtest_walkforward.py` (varre símbolos×horizontes no DB).

## Razao logica

O lucro líquido é o que sobra DEPOIS de todas as taxas (round-trip). Medir lucratividade sem
descontar o custo real infla o resultado e mente. O walk-forward evita vazamento de futuro.
