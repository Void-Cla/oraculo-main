"""SEC-01 — invariante de segurança das sessões: credenciais nunca persistem além do
necessário e não vazam em caminhos que não precisam delas.

Trava o comportamento já correto (limpeza no logout/expiração) contra regressão futura.
"""
import pytest


def _sessao_fake(token: str, *, expira_em: int) -> dict:
    return {
        "token": token,
        "api_key_mascarada": "ABCD***WXYZ",
        "modo_testnet": True,
        "criado_em": 0,
        "expira_em": expira_em,
        "nome_exibicao": "Conta SPOT Binance",
        "id_conta": "x",
    }


@pytest.mark.asyncio
async def test_logout_limpa_credenciais():
    from src.servicos import sessoes

    sessoes.resetar_sessoes_teste()
    sessoes._SESSOES["tok"] = _sessao_fake("tok", expira_em=sessoes._agora_ms() + 10_000_000)
    sessoes._CREDENCIAIS["tok"] = {"api_key": "K", "api_secret": "S"}

    encerrou = await sessoes.encerrar_sessao("tok")
    assert encerrou is True
    assert "tok" not in sessoes._CREDENCIAIS
    assert "tok" not in sessoes._SESSOES


@pytest.mark.asyncio
async def test_expiracao_limpa_credenciais():
    from src.servicos import sessoes

    sessoes.resetar_sessoes_teste()
    sessoes._SESSOES["tok"] = _sessao_fake("tok", expira_em=sessoes._agora_ms() - 1)  # já expirada
    sessoes._CREDENCIAIS["tok"] = {"api_key": "K", "api_secret": "S"}

    r = await sessoes.obter_sessao("tok")  # dispara a limpeza de expiradas
    assert r is None
    assert "tok" not in sessoes._CREDENCIAIS
    assert "tok" not in sessoes._SESSOES


@pytest.mark.asyncio
async def test_obter_sessao_sem_credenciais_nao_expoe_segredo():
    from src.servicos import sessoes

    sessoes.resetar_sessoes_teste()
    sessoes._SESSOES["tok"] = _sessao_fake("tok", expira_em=sessoes._agora_ms() + 10_000_000)
    sessoes._CREDENCIAIS["tok"] = {"api_key": "K", "api_secret": "S"}

    r = await sessoes.obter_sessao("tok", incluir_credenciais=False)
    assert r is not None
    assert "api_key" not in r
    assert "api_secret" not in r


@pytest.mark.asyncio
async def test_sessao_publica_nunca_contem_segredo():
    from src.servicos import sessoes

    sessoes.resetar_sessoes_teste()
    sessoes._SESSOES["tok"] = _sessao_fake("tok", expira_em=sessoes._agora_ms() + 10_000_000)
    sessoes._CREDENCIAIS["tok"] = {"api_key": "K", "api_secret": "S"}

    pub = await sessoes.obter_sessao_publica("tok")
    assert pub is not None
    assert "api_key" not in pub and "api_secret" not in pub
    assert pub["api_key_mascarada"] == "ABCD***WXYZ"
