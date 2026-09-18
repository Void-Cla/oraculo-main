"""Camada agêntica (cérebro consultivo) sobre o músculo mecânico do Oráculo.

PRINCÍPIO INVARIANTE (defense in depth): a IA é um FILTRO ADICIONAL que só pode VETAR
uma entrada — NUNCA aprovar, dimensionar posição, ou levantar qualquer gate financeiro
(risk_engine, profit_guard, edge_config). Se a IA falhar, alucinar ou demorar, o bot
mecânico continua operando normalmente (fail-open). Tudo aqui é OPT-IN: sem chave do provedor
escolhido (`AI_PROVIDER`), a camada fica desativada e o comportamento do bot é idêntico ao anterior.

O provedor de IA é PLUGÁVEL (`AI_PROVIDER` = nvidia|gemini|gpt|claude|ollama): a factory `criar_provedor_ia()`
devolve o cliente concreto correspondente por trás do Protocol `ProvedorIA`. Os consumidores
(`PreExecutionFilter`, `AnalistaMercadoIA`, `PostTradeAuditor`) são agnósticos ao provedor.
"""
from __future__ import annotations

__all__ = [
    "NvidiaClient",
    "GeminiClient",
    "GPTClient",
    "ClaudeClient",
    "ProvedorIA",
    "ProvedorIABase",
    "criar_provedor_ia",
    "PreExecutionFilter",
    "PostTradeAuditor",
    "AnalistaMercadoIA",
    "VotoIA",
]


def __getattr__(nome: str):  # import preguiçoso (evita custo de import se a camada não for usada)
    if nome == "NvidiaClient":
        from src.intelligence.nvidia_client import NvidiaClient

        return NvidiaClient
    if nome == "GeminiClient":
        from src.intelligence.gemini_client import GeminiClient

        return GeminiClient
    if nome == "GPTClient":
        from src.intelligence.gpt_client import GPTClient

        return GPTClient
    if nome == "ClaudeClient":
        from src.intelligence.claude_client import ClaudeClient

        return ClaudeClient
    if nome in ("ProvedorIA", "ProvedorIABase", "criar_provedor_ia"):
        from src.intelligence import provedor_ia

        return getattr(provedor_ia, nome)
    if nome == "PreExecutionFilter":
        from src.intelligence.pre_execution_filter import PreExecutionFilter

        return PreExecutionFilter
    if nome == "PostTradeAuditor":
        from src.intelligence.post_trade_auditor import PostTradeAuditor

        return PostTradeAuditor
    if nome == "AnalistaMercadoIA":
        from src.intelligence.market_analyst import AnalistaMercadoIA

        return AnalistaMercadoIA
    if nome == "VotoIA":
        from src.intelligence.market_analyst import VotoIA

        return VotoIA
    raise AttributeError(f"module {__name__!r} has no attribute {nome!r}")
