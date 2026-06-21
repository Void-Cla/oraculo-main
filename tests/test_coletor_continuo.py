import pytest

from src.tarefas import coletor_continuo


def test_simbolos_coleta_csv(monkeypatch):
    monkeypatch.setenv("COLETA_SIMBOLOS", "btcusdt, ethusdt ,BNBUSDT")
    assert coletor_continuo._simbolos_coleta() == ["BTCUSDT", "ETHUSDT", "BNBUSDT"]


def test_simbolos_coleta_default(monkeypatch):
    monkeypatch.delenv("COLETA_SIMBOLOS", raising=False)
    simbolos = coletor_continuo._simbolos_coleta()
    assert len(simbolos) > 0
    assert all(s == s.upper() for s in simbolos)


@pytest.mark.asyncio
async def test_coletar_uma_rodada_isola_falha_de_simbolo(monkeypatch):
    async def _fake(simbolo, limit, cliente):
        if simbolo == "RUIM":
            raise RuntimeError("falha_rede")
        return {"ts": 1, "simbolo": simbolo}

    monkeypatch.setattr(coletor_continuo, "coletar_e_persistir", _fake)
    resumo = await coletor_continuo.coletar_uma_rodada(["BTCUSDT", "RUIM", "ETHUSDT"], 60, cliente=None)
    assert resumo["coletados"] == 2
    assert resumo["total"] == 3
    assert resumo["falhas"] == ["RUIM"]


@pytest.mark.asyncio
async def test_loop_noop_quando_desativado(monkeypatch):
    monkeypatch.setenv("ATIVAR_COLETA_CONTINUA", "false")
    chamou = {"n": 0}

    async def _nao_deveria(*a, **k):
        chamou["n"] += 1
        return {}

    monkeypatch.setattr(coletor_continuo, "coletar_e_persistir", _nao_deveria)
    await coletor_continuo.loop_coleta_continua()  # retorna imediatamente
    assert chamou["n"] == 0
