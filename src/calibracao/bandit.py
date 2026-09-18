"""Calibrador de previsão e confiança — DETERMINÍSTICO e honesto.

Papel (ver README): converter a previsão bruta do modelo numa saída mais confiável,
reduzindo excesso de confiança e devolvendo uma CONFIANÇA que reflete a qualidade real
do sinal — não um número fixo/aleatório.

⚠️ HISTÓRICO (GAP-FIN-01, corrigido 2026-07-01): a versão anterior era um STUB — `y_cal`
era `y_hat * 1.0` (não calibrava nada) e `conf` era 0.55 ou 0.60 escolhido por epsilon-greedy
ALEATÓRIO, sem nunca aprender (a instância era recriada a cada ciclo). Essa "confiança" falsa
pesava o score numérico e DIMENSIONAVA a posição (`decisor_hibrido.py`) — ou seja, o tamanho
da aposta era parcialmente ruído. Substituído por uma confiança heurística determinística
baseada em relação sinal/ruído (movimento previsto vs volatilidade) e qualidade de execução
(spread), que é honesta sobre o que é: uma heurística, não um calibrador estatístico treinado.
"""
from __future__ import annotations

from typing import Any

# --- Constantes de calibração de confiança (origem: relação sinal/ruído do sinal 1m) ---
# Piso/teto da confiança devolvida. Não vai a 0 (uma previsão sempre carrega ALGUMA info)
# nem a 1.0 (nunca há certeza num sinal ruidoso de 1 minuto).
_CONF_MINIMA: float = 0.05
_CONF_MAXIMA: float = 0.90
# Confiança-base quando o sinal é neutro (relação sinal/ruído ~0). Deliberadamente baixa:
# na dúvida, confiar pouco (menos exposição). Escolhida abaixo do piso de 0.55 que o
# decisor_hibrido usa para dobrar/reduzir por conflito, para não inflar sizing sem sinal.
_CONF_BASE: float = 0.35
# Quanto a relação sinal/ruído (|movimento previsto| / volatilidade) empurra a confiança
# para cima. Um movimento previsto de ~1 desvio-padrão da vol adiciona ~_GANHO_SNR à base.
_GANHO_SNR: float = 0.40
# Volatilidade mínima assumida (evita divisão por ~0 e SNR explosivo em mercado parado).
# 5 bps ≈ desvio típico de retorno de 1 minuto em ativo líquido (fonte: análise de edge).
_VOL_MINIMA: float = 0.0005
# Penalidade máxima por spread alto (execução cara reduz a confiança de que o EV se realiza).
_PENALIDADE_SPREAD_MAX: float = 0.20
# Spread relativo a partir do qual a penalidade satura (0.3% ≈ limiar de spread "alto" no projeto).
_SPREAD_SATURACAO: float = 0.003


def _clamp(valor: float, minimo: float, maximo: float) -> float:
    return max(minimo, min(maximo, valor))


class CalibradorBandit:
    """Calibra a previsão bruta e devolve uma confiança determinística sinal/ruído.

    Mantido o nome `CalibradorBandit` por compatibilidade de import (`preditor.py`), embora
    não seja mais um bandit (não há mais escolha aleatória entre calibradores). A calibração
    de ESCALA (Platt/isotônica com feedback dos `outcomes`) fica como trabalho futuro — ver
    README; hoje `y_cal = y_hat` (sem distorcer a previsão) e o valor entregue é a CONFIANÇA
    honesta, que é o que de fato pesava/dimensionava a decisão.
    """

    def calibrar(self, y_hat: float, features: dict[str, Any]) -> tuple[float, float]:
        """Retorna (y_cal, confianca).

        `y_cal` = `y_hat` (sem calibração de escala ainda — não distorcemos a previsão).
        `confianca` ∈ [_CONF_MINIMA, _CONF_MAXIMA] reflete a relação sinal/ruído do sinal:
        movimento previsto grande vs volatilidade recente ⇒ mais confiança; spread alto
        (execução cara/incerta) ⇒ menos confiança. Determinística: mesmas features ⇒ mesma
        confiança (sem aleatoriedade, ao contrário do stub anterior).
        """
        y_cal = float(y_hat)

        close = float(features.get("close", 0.0) or 0.0)
        # Movimento relativo previsto (fração do preço). Se não há close, não há SNR mensurável.
        movimento_rel = (abs(y_cal - close) / close) if close > 0.0 else 0.0

        # Volatilidade recente como proxy do "ruído" do ativo (usa a maior janela disponível).
        vol = max(
            float(features.get("vol5", 0.0) or 0.0),
            float(features.get("vol10", 0.0) or 0.0),
        )
        vol = max(vol, _VOL_MINIMA)

        # Relação sinal/ruído: quantos "desvios de vol" o movimento previsto representa.
        snr = movimento_rel / vol

        # Penalidade de execução: spread alto reduz a confiança de que o EV se realiza.
        spread_rel = abs(float(features.get("spread_rel", 0.0) or 0.0))
        penalidade_spread = _PENALIDADE_SPREAD_MAX * _clamp(
            spread_rel / _SPREAD_SATURACAO, 0.0, 1.0
        )

        confianca = _CONF_BASE + (_GANHO_SNR * _clamp(snr, 0.0, 1.5)) - penalidade_spread
        confianca = _clamp(confianca, _CONF_MINIMA, _CONF_MAXIMA)
        return y_cal, confianca
