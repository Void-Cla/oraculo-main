"""Kill-switch financeiro file-based — botão de pânico INDEPENDENTE (defense in depth).

Camada de segurança ortogonal a todo o resto do sistema: se o arquivo de kill-switch
existir, NENHUMA ordem é submetida à corretora — override de qualquer gate (risco, EV,
edge, conta real). Verificado no `gerenciador_ordens` ANTES de todo `create_order`.

Operação (parar o bot IMEDIATAMENTE, sem restart):
    touch ./dados/KILL_SWITCH         # engata → a próxima ordem é bloqueada
    rm ./dados/KILL_SWITCH            # destrava (ação humana explícita)

Princípio (CLAUDE.md): capital perdido não volta — na dúvida, BLOQUEIA. Por isso, falha
ao checar o filesystem é tratada como FAIL-SAFE (considera engatado).
"""
from __future__ import annotations

import time
from pathlib import Path

from src.core.settings import resolve_runtime_path
from src.observabilidade.logger import get_logger

LOG = get_logger("kill_switch")


class KillSwitchEngatadoError(RuntimeError):
    """Levantada quando uma ordem é bloqueada pelo kill-switch financeiro."""


def caminho_kill_switch() -> Path:
    """Caminho do arquivo-sentinela. Configurável por `KILL_SWITCH_PATH`."""
    return resolve_runtime_path("KILL_SWITCH_PATH", "./dados/KILL_SWITCH")


def esta_engatado() -> bool:
    """True se o kill-switch está ativo. Erro de FS ⇒ True (fail-safe — bloqueia)."""
    try:
        return caminho_kill_switch().exists()
    except OSError as exc:
        LOG.error("falha_checar_kill_switch_fail_safe", extra={"erro": str(exc)})
        return True


def engatar(motivo: str) -> Path:
    """Engata o kill-switch (cria o arquivo). Idempotente. Retorna o caminho."""
    caminho = caminho_kill_switch()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(f"{int(time.time() * 1000)}: {motivo}\n", encoding="utf-8")
    LOG.critical("kill_switch_engatado", extra={"motivo": motivo, "caminho": str(caminho)})
    return caminho


def destravar() -> bool:
    """Destrava (remove o arquivo). Retorna True se havia um kill-switch ativo."""
    caminho = caminho_kill_switch()
    if caminho.exists():
        caminho.unlink()
        LOG.warning("kill_switch_destravado", extra={"caminho": str(caminho)})
        return True
    return False


def estado() -> dict[str, object]:
    """Estado observável do kill-switch (para API/diagnóstico)."""
    caminho = caminho_kill_switch()
    engatado = esta_engatado()
    motivo = ""
    if engatado:
        try:
            motivo = caminho.read_text(encoding="utf-8").strip()
        except OSError:
            motivo = "indisponivel"
    return {"engatado": engatado, "caminho": str(caminho), "motivo": motivo}


def exigir_desengatado(*, simbolo: str, lado: str) -> None:
    """Levanta `KillSwitchEngatadoError` se o kill-switch estiver ativo.

    Deve ser chamado ANTES de submeter qualquer ordem à corretora.
    """
    if esta_engatado():
        LOG.critical("ordem_bloqueada_kill_switch", extra={"simbolo": simbolo, "lado": lado})
        raise KillSwitchEngatadoError("kill_switch_financeiro_engatado")
