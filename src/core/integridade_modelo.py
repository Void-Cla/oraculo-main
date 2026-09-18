"""Integridade de artefatos de modelo — mitigação anti-RCE para `joblib.load` (CRIT-SEC-01).

`joblib.load` desserializa pickle: um arquivo de modelo adulterado executa código arbitrário
no processo do bot (acesso a chaves/saldo/ordens). Defesa: assinar o artefato com HMAC-SHA256
(chave secreta em env) e VERIFICAR a assinatura antes de carregar.

Política (opt-in, fail-safe quando ligado):
  - `MODELO_HMAC_KEY` ausente  → verificação DESLIGADA (comportamento legado; só loga aviso 1×
    se houver `.sig`); não quebra ambientes sem chave.
  - `MODELO_HMAC_KEY` presente → verificação OBRIGATÓRIA: artefato sem `.sig` válido é RECUSADO
    (fail-closed) — modelo não-confiável não entra no processo.

Uso:
    assinar_artefato(caminho)                 # grava caminho.sig (na geração do modelo)
    verificar_artefato(caminho)               # True/False
    carregar_joblib_verificado(caminho)       # joblib.load só se íntegro (ou se desligado)
"""
from __future__ import annotations

import hashlib
import hmac
from pathlib import Path
from typing import Any

from src.core.settings import env_str
from src.observabilidade.logger import get_logger

LOG = get_logger("integridade_modelo")

_SUFIXO_ASSINATURA = ".sig"
_TAMANHO_BLOCO = 1024 * 1024  # 1 MiB por leitura (não carrega o arquivo inteiro em memória)


class IntegridadeModeloError(RuntimeError):
    """Levantada quando um artefato de modelo falha na verificação de integridade."""


def _chave_hmac() -> bytes | None:
    chave = env_str("MODELO_HMAC_KEY", "")
    return chave.encode("utf-8") if chave else None


def verificacao_ativa() -> bool:
    """True se a verificação de integridade está habilitada (há chave HMAC configurada)."""
    return _chave_hmac() is not None


def _digerir(caminho: Path, chave: bytes) -> str:
    mac = hmac.new(chave, digestmod=hashlib.sha256)
    with open(caminho, "rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(_TAMANHO_BLOCO), b""):
            mac.update(bloco)
    return mac.hexdigest()


def assinar_artefato(caminho: str | Path) -> Path | None:
    """Gera `<caminho>.sig` com o HMAC-SHA256 do artefato. No-op se não houver chave."""
    chave = _chave_hmac()
    if chave is None:
        return None
    caminho = Path(caminho)
    assinatura = _digerir(caminho, chave)
    destino = caminho.with_name(caminho.name + _SUFIXO_ASSINATURA)
    destino.write_text(assinatura, encoding="utf-8")
    LOG.info("artefato_assinado", extra={"caminho": str(caminho)})
    return destino


def verificar_artefato(caminho: str | Path) -> bool:
    """Verifica o HMAC do artefato contra `<caminho>.sig`.

    Sem chave configurada → True (verificação desligada). Com chave → True só se a assinatura
    existir e bater (comparação em tempo constante).
    """
    chave = _chave_hmac()
    caminho = Path(caminho)
    if chave is None:
        sig = caminho.with_name(caminho.name + _SUFIXO_ASSINATURA)
        if sig.exists():
            LOG.warning(
                "assinatura_presente_mas_verificacao_desligada",
                extra={"caminho": str(caminho)},
            )
        return True
    sig = caminho.with_name(caminho.name + _SUFIXO_ASSINATURA)
    if not sig.exists():
        LOG.error("assinatura_ausente_artefato_recusado", extra={"caminho": str(caminho)})
        return False
    esperado = _digerir(caminho, chave)
    atual = sig.read_text(encoding="utf-8").strip()
    if not hmac.compare_digest(esperado, atual):
        LOG.error("assinatura_invalida_artefato_recusado", extra={"caminho": str(caminho)})
        return False
    return True


def carregar_joblib_verificado(caminho: str | Path) -> Any:
    """`joblib.load` apenas se o artefato for íntegro. Levanta `IntegridadeModeloError` se não.

    Com verificação desligada (sem chave), carrega normalmente — preserva o comportamento legado.
    """
    caminho = Path(caminho)
    if not verificar_artefato(caminho):
        raise IntegridadeModeloError(f"artefato_de_modelo_nao_confiavel:{caminho}")
    import joblib

    return joblib.load(caminho)
