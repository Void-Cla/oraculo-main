import os

import pytest

from src.observabilidade.audit import registrar_audit
from src.persistencia.conexao import inicializar_db
from src.persistencia.repositorio_auditoria import RepositorioAuditoria


@pytest.mark.asyncio
async def test_audit_enriquecido_preserva_payload_e_meta(tmp_path):
    os.environ["DB_PATH"] = str(tmp_path / "audit.sqlite")
    inicializar_db()

    await registrar_audit(
        "sinal_rejeitado",
        "risk_engine",
        "ev_insuficiente",
        usuario_id=7,
        simbolo="BTCUSDT",
        meta={"ev_liquido_usdt": 0.2},
    )

    itens = await RepositorioAuditoria.listar_recentes(simbolo="BTCUSDT", tipo="sinal_rejeitado", limite=5)

    assert len(itens) == 1
    assert itens[0]["componente"] == "risk_engine"
    assert itens[0]["motivo"] == "ev_insuficiente"
    assert itens[0]["meta"]["ev_liquido_usdt"] == 0.2
    assert itens[0]["payload"]["usuario_id"] == 7
