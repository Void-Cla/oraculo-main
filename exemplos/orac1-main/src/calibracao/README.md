# Calibracao

## Papel

Converter previsao bruta em saida mais confiavel para tomada de decisao.

## Arquivos

- `bandit.py`
  - `CalibradorBandit`: calibra previsao e confianca com ajuste adaptativo leve.
- `ewls.py`
  - `CalibradorEWLS`: alternativa de calibracao com suavizacao ponderada no tempo.

## Razao logica

Modelo que acerta direcao ainda pode errar escala. A calibracao existe para reduzir excesso de confianca e suavizar oscilacoes do preditor bruto.
