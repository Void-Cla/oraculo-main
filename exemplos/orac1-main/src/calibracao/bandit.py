"""Calibrador Bandit simples que escolhe entre calibradores disponíveis.
Implementação mínima: mantém contadores e escolhe por epsilon-greedy.
"""
from typing import Tuple, Dict, Any
import random


class CalibradorBandit:
    def __init__(self):
        # nome -> (sucessos, tentativas)
        self.stats = {"ewls": [1, 1], "isotonic": [1, 1]}
        self.epsilon = 0.1

    def escolher(self) -> str:
        if random.random() < self.epsilon:
            return random.choice(list(self.stats.keys()))
        # escolher pela taxa de sucesso
        best = None
        best_score = -1
        for k, (s, t) in self.stats.items():
            score = s / t if t else 0
            if score > best_score:
                best = k
                best_score = score
        return best

    def calibrar(self, y_hat: float, features: Dict[str, Any]) -> Tuple[float, float]:
        escolha = self.escolher()
        # stubs: aplicar pequena correção com base na escolha
        if escolha == 'ewls':
            y_cal = y_hat * 1.0
            conf = 0.6
        else:
            y_cal = y_hat * 1.0
            conf = 0.55
        # atualizar estatísticas - placeholder (sem feedback aqui)
        self.stats[escolha][1] += 1
        return y_cal, conf
