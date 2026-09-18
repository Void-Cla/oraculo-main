"""GATE DE MOMENTO CRÍTICO no orquestrador multiativo (DA-30, 2026-07-01).

`montar_monitoramento_multiativo` roda o sinal mecânico PURO para todos os símbolos monitorados
primeiro; só os símbolos com EV líquido acionável entram no lote de IA (`avaliar_lote`). Estes
testes mockam `gerar_sinal_orquestrado` diretamente (em vez de depender do pipeline ML real, que
usa um cache de modelo GLOBAL por símbolo compartilhado entre testes — controlar o EV cru por
essa via seria frágil) para provar a lógica de FILTRAGEM do orquestrador de forma determinística."""
import os

import pytest


def _setup_db(tmp_path):
    os.environ["DB_PATH"] = str(tmp_path / "orquestrador_gate_ia.sqlite")
    from src.persistencia.conexao import inicializar_db

    inicializar_db()


class _ClienteBinanceFake:
    """Duck-type mínimo: só os 2 métodos que `_snapshot_par` chama. Conteúdo das klines não
    importa aqui — o EV mecânico é controlado via mock de `gerar_sinal_orquestrado`."""

    async def obter_klines(self, simbolo: str, limit: int = 60):
        return [[idx, 100.0, 100.0, 100.0, 100.0, 20.0] for idx in range(1, 31)]

    async def obter_order_book_top(self, simbolo: str, limit: int = 20):
        return {"bids": [[99.99, 5.0]], "asks": [[100.01, 4.0]]}


class _AnalistaEspiao:
    """Registra os símbolos recebidos em `avaliar_lote` — o que importa é QUEM foi consultado."""

    def __init__(self):
        self.simbolos_consultados: list[str] | None = None

    async def avaliar_lote(self, *, simbolos, saldo=0.0, noticias_por_simbolo=None):
        self.simbolos_consultados = list(simbolos)
        from src.intelligence.market_analyst import VotoIA

        return {s: VotoIA(acao="HOLD", confianca=0.1, fonte="gemini") for s in simbolos}

    async def avaliar_direcional(self, *, simbolo, sinal_mecanico=None, saldo=0.0, noticias=None):
        from src.intelligence.market_analyst import VotoIA

        return VotoIA(acao="HOLD", confianca=0.1, fonte="gemini")


def _fake_gerar_sinal(ev_por_simbolo: dict[str, float]):
    """Fábrica de um `gerar_sinal_orquestrado` fake: cada símbolo recebe o EV cru configurado
    (via `ev_por_simbolo`, default 0.0 = sem oportunidade) no formato exato que o orquestrador
    lê (`sinal["probabilidade_trade"]["ev_buy"]`)."""

    async def _fake(*, simbolo, klines, livro_topo=None, noticias=None, saldo=None, ajustes_sinal=None, analista_ia=None, **kwargs):
        ev = ev_por_simbolo.get(simbolo, 0.0)
        return {
            "simbolo": simbolo,
            "acao": "BUY" if ev > 0.0001 else "HOLD",
            "probabilidade_trade": {"ev_buy": ev, "ev_sell": -ev},
            "lucro_liquido_esperado_pct": max(ev, 0.0),
        }

    return _fake


@pytest.mark.asyncio
async def test_orquestrador_so_manda_ao_lote_simbolos_com_ev_acionavel(tmp_path, monkeypatch):
    _setup_db(tmp_path)
    import src.multiativo.orquestrador as orq_mod

    monkeypatch.setattr(orq_mod, "gerar_sinal_orquestrado", _fake_gerar_sinal({"BTCUSDT": 0.01}))

    analista = _AnalistaEspiao()
    await orq_mod.montar_monitoramento_multiativo(
        cliente=_ClienteBinanceFake(),
        conta_raw={"balances": []},
        persistir_mercado=False,
        analista_ia=analista,
    )

    assert analista.simbolos_consultados is not None  # o lote FOI chamado (havia 1 elegível)
    assert analista.simbolos_consultados == ["BTCUSDT"]  # só o símbolo com EV acionável


@pytest.mark.asyncio
async def test_orquestrador_nao_chama_lote_quando_nenhum_simbolo_tem_ev(tmp_path, monkeypatch):
    _setup_db(tmp_path)
    import src.multiativo.orquestrador as orq_mod

    monkeypatch.setattr(orq_mod, "gerar_sinal_orquestrado", _fake_gerar_sinal({}))  # tudo 0.0

    analista = _AnalistaEspiao()
    await orq_mod.montar_monitoramento_multiativo(
        cliente=_ClienteBinanceFake(),
        conta_raw={"balances": []},
        persistir_mercado=False,
        analista_ia=analista,
    )

    assert analista.simbolos_consultados is None  # avaliar_lote nunca foi chamado


@pytest.mark.asyncio
async def test_orquestrador_multiplos_simbolos_elegiveis_entram_no_mesmo_lote(tmp_path, monkeypatch):
    _setup_db(tmp_path)
    import src.multiativo.orquestrador as orq_mod

    monkeypatch.setattr(
        orq_mod, "gerar_sinal_orquestrado", _fake_gerar_sinal({"BTCUSDT": 0.01, "ETHUSDT": 0.02})
    )

    analista = _AnalistaEspiao()
    await orq_mod.montar_monitoramento_multiativo(
        cliente=_ClienteBinanceFake(),
        conta_raw={"balances": []},
        persistir_mercado=False,
        analista_ia=analista,
    )

    assert set(analista.simbolos_consultados) == {"BTCUSDT", "ETHUSDT"}


@pytest.mark.asyncio
async def test_orquestrador_sem_analista_ia_nao_quebra(tmp_path, monkeypatch):
    """`analista_ia=None` (padrão, sem chave configurada) preserva o comportamento anterior:
    nenhuma tentativa de consultar IA, sinais mecânicos gerados normalmente."""
    _setup_db(tmp_path)
    import src.multiativo.orquestrador as orq_mod

    monkeypatch.setattr(orq_mod, "gerar_sinal_orquestrado", _fake_gerar_sinal({"BTCUSDT": 0.01}))

    resultado = await orq_mod.montar_monitoramento_multiativo(
        cliente=_ClienteBinanceFake(),
        conta_raw={"balances": []},
        persistir_mercado=False,
    )
    assert "BTCUSDT" in resultado["sinais"]


@pytest.mark.asyncio
async def test_orquestrador_falha_no_lote_nao_quebra_ciclo(tmp_path, monkeypatch):
    """Fail-safe belt-and-suspenders: se `avaliar_lote` lançar, o ciclo mecânico continua
    (sinais dos símbolos elegíveis reaproveitam o resultado do passo 1, sem voto de IA)."""
    _setup_db(tmp_path)
    import src.multiativo.orquestrador as orq_mod

    monkeypatch.setattr(orq_mod, "gerar_sinal_orquestrado", _fake_gerar_sinal({"BTCUSDT": 0.01}))

    class _AnalistaQuebrado:
        async def avaliar_lote(self, **kwargs):
            raise RuntimeError("falha de rede simulada")

    resultado = await orq_mod.montar_monitoramento_multiativo(
        cliente=_ClienteBinanceFake(),
        conta_raw={"balances": []},
        persistir_mercado=False,
        analista_ia=_AnalistaQuebrado(),
    )
    assert "BTCUSDT" in resultado["sinais"]  # ciclo mecânico não foi derrubado pela falha


@pytest.mark.asyncio
async def test_orquestrador_lote_fail_safe_sem_excecao_nao_tenta_individual(tmp_path, monkeypatch):
    """REGRESSÃO DO BUG DE PRODUÇÃO (log.txt, 2026-07-02): `avaliar_lote` é FAIL-SAFE por
    design — sob 429/timeout/erro ele NÃO lança, retorna voto neutro por símbolo (fonte
    "erro"/"timeout"/"indisponivel"). Um `except Exception` no orquestrador NUNCA pegava esse
    caso, e o passo 3 caía no cache frio e tentava CADA símbolo elegível INDIVIDUALMENTE —
    1 falha do lote virava até 6 chamadas de rede extras (visto ao vivo: 5 erros 429
    consecutivos até o cooldown de 60min disparar). Este teste prova que, quando o lote
    retorna só votos de falha (sem nenhum de fonte "gemini" real), NENHUMA chamada adicional
    é feita — a contagem de chamadas ao `gerar_sinal_orquestrado` mockado com `analista_ia`
    deve ser ZERO."""
    _setup_db(tmp_path)
    import src.multiativo.orquestrador as orq_mod
    from src.intelligence.market_analyst import VotoIA

    chamadas_com_ia = {"n": 0}

    async def _fake_com_contagem(*, simbolo, klines, livro_topo=None, noticias=None, saldo=None, ajustes_sinal=None, analista_ia=None, **kwargs):
        if analista_ia is not None:
            chamadas_com_ia["n"] += 1
        ev = 0.01  # todos elegíveis — o cenário mais adverso (mais retries possíveis no bug antigo)
        return {
            "simbolo": simbolo,
            "acao": "HOLD",
            "probabilidade_trade": {"ev_buy": ev, "ev_sell": -ev},
            "lucro_liquido_esperado_pct": ev,
        }

    monkeypatch.setattr(orq_mod, "gerar_sinal_orquestrado", _fake_com_contagem)

    class _AnalistaLoteFailSafe:
        """Simula o comportamento REAL de `avaliar_lote` sob 429: retorna dict completo,
        um voto neutro por símbolo, fonte="erro" — SEM lançar exceção."""

        async def avaliar_lote(self, *, simbolos, saldo=0.0, noticias_por_simbolo=None):
            return {s: VotoIA(acao="HOLD", confianca=0.0, fonte="erro", rationale="429") for s in simbolos}

    resultado = await orq_mod.montar_monitoramento_multiativo(
        cliente=_ClienteBinanceFake(),
        conta_raw={"balances": []},
        persistir_mercado=False,
        analista_ia=_AnalistaLoteFailSafe(),
    )

    assert chamadas_com_ia["n"] == 0  # NENHUM símbolo tentou individualmente após o lote falhar
    assert "BTCUSDT" in resultado["sinais"]  # ciclo mecânico segue produzindo sinal (passo 1)


@pytest.mark.asyncio
async def test_orquestrador_lote_com_sucesso_parcial_ainda_usa_resultado(tmp_path, monkeypatch):
    """Se o lote tiver AO MENOS 1 voto de fonte real ("gemini"), o resultado é considerado
    sucesso — não descarta um lote parcialmente útil só porque 1 símbolo veio como erro."""
    _setup_db(tmp_path)
    import src.multiativo.orquestrador as orq_mod
    from src.intelligence.market_analyst import VotoIA

    monkeypatch.setattr(
        orq_mod, "gerar_sinal_orquestrado", _fake_gerar_sinal({"BTCUSDT": 0.01, "ETHUSDT": 0.01})
    )

    class _AnalistaParcial:
        async def avaliar_lote(self, *, simbolos, saldo=0.0, noticias_por_simbolo=None):
            return {
                "BTCUSDT": VotoIA(acao="BUY", confianca=0.8, fonte="gemini"),
                "ETHUSDT": VotoIA(acao="HOLD", confianca=0.0, fonte="erro"),
            }

    resultado = await orq_mod.montar_monitoramento_multiativo(
        cliente=_ClienteBinanceFake(),
        conta_raw={"balances": []},
        persistir_mercado=False,
        analista_ia=_AnalistaParcial(),
    )
    assert "BTCUSDT" in resultado["sinais"]
    assert "ETHUSDT" in resultado["sinais"]
