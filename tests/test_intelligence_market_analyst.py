"""Voto DIRECIONAL de peso igual (AnalistaMercadoIA) — mockado (sem rede), padrão de
`test_intelligence_gemini.py`. Cobre: resposta válida BUY/SELL/HOLD, JSON quebrado (fail-safe),
timeout (fail-safe), action fora do enum (vira HOLD), desativado, e o LOTE (avaliar_lote +
cache consultado por avaliar_direcional) — economia de RPM/TPM (2026-07-01)."""
import asyncio
import os

import pytest


def _setup_db(tmp_path):
    os.environ["DB_PATH"] = str(tmp_path / "market_analyst.sqlite")
    from src.persistencia.conexao import inicializar_db

    inicializar_db()


# ── VotoIA / normalização ────────────────────────────────────────────────────
def test_voto_ia_default_e_neutro():
    from src.intelligence.market_analyst import VotoIA

    voto = VotoIA()
    assert voto.acao == "HOLD"
    assert voto.confianca == 0.0
    assert voto.score_direcional == 0.0
    assert voto.fonte == "indisponivel"


# ── AnalistaMercadoIA.avaliar_direcional ─────────────────────────────────────
@pytest.mark.asyncio
async def test_analista_desabilitado_retorna_voto_neutro():
    from src.intelligence.gemini_client import GeminiClient
    from src.intelligence.market_analyst import AnalistaMercadoIA

    analista = AnalistaMercadoIA(GeminiClient(api_key=""), habilitado=False)
    voto = await analista.avaliar_direcional(simbolo="BTCUSDT", saldo=100.0)
    assert voto.acao == "HOLD"
    assert voto.confianca == 0.0
    assert voto.fonte == "desativado"


@pytest.mark.asyncio
async def test_analista_buy_valido(monkeypatch, tmp_path):
    _setup_db(tmp_path)
    from src.intelligence.gemini_client import GeminiClient
    from src.intelligence.market_analyst import AnalistaMercadoIA

    cli = GeminiClient(api_key="fake-key")

    async def _buy(system_prompt, user_context, *, temperature=0.2):
        return {
            "action": "BUY",
            "score_direcional": 0.8,
            "confidence": 0.9,
            "sentimento_mercado": 0.5,
            "rationale": "momentum forte",
        }

    monkeypatch.setattr(cli, "analisar", _buy)
    analista = AnalistaMercadoIA(cli, habilitado=True)
    voto = await analista.avaliar_direcional(simbolo="BTCUSDT", saldo=100.0)
    assert voto.acao == "BUY"
    assert voto.score_direcional == pytest.approx(0.8)
    assert voto.confianca == pytest.approx(0.9)
    assert voto.sentimento_mercado == pytest.approx(0.5)
    assert voto.fonte == "gemini"


@pytest.mark.asyncio
async def test_analista_sell_valido(monkeypatch, tmp_path):
    _setup_db(tmp_path)
    from src.intelligence.gemini_client import GeminiClient
    from src.intelligence.market_analyst import AnalistaMercadoIA

    cli = GeminiClient(api_key="fake-key")

    async def _sell(system_prompt, user_context, *, temperature=0.2):
        return {"action": "sell", "score_direcional": -0.6, "confidence": 0.7, "sentimento_mercado": -0.3}

    monkeypatch.setattr(cli, "analisar", _sell)
    analista = AnalistaMercadoIA(cli, habilitado=True)
    voto = await analista.avaliar_direcional(simbolo="ETHUSDT", saldo=50.0)
    assert voto.acao == "SELL"  # normalizado maiúsculo
    assert voto.score_direcional == pytest.approx(-0.6)


@pytest.mark.asyncio
async def test_analista_hold_valido(monkeypatch, tmp_path):
    _setup_db(tmp_path)
    from src.intelligence.gemini_client import GeminiClient
    from src.intelligence.market_analyst import AnalistaMercadoIA

    cli = GeminiClient(api_key="fake-key")

    async def _hold(system_prompt, user_context, *, temperature=0.2):
        return {"action": "HOLD", "score_direcional": 0.05, "confidence": 0.3, "sentimento_mercado": 0.0}

    monkeypatch.setattr(cli, "analisar", _hold)
    analista = AnalistaMercadoIA(cli, habilitado=True)
    voto = await analista.avaliar_direcional(simbolo="BTCUSDT", saldo=100.0)
    assert voto.acao == "HOLD"


@pytest.mark.asyncio
async def test_analista_action_fora_do_enum_vira_hold(monkeypatch, tmp_path):
    _setup_db(tmp_path)
    from src.intelligence.gemini_client import GeminiClient
    from src.intelligence.market_analyst import AnalistaMercadoIA

    cli = GeminiClient(api_key="fake-key")

    async def _invalida(system_prompt, user_context, *, temperature=0.2):
        return {"action": "STRONG_BUY_ALAVANCADO", "score_direcional": 0.99, "confidence": 0.99}

    monkeypatch.setattr(cli, "analisar", _invalida)
    analista = AnalistaMercadoIA(cli, habilitado=True)
    voto = await analista.avaliar_direcional(simbolo="BTCUSDT", saldo=100.0)
    assert voto.acao == "HOLD"  # fail-safe: fora do enum vira HOLD, não propaga acao inventada


@pytest.mark.asyncio
async def test_analista_json_invalido_fail_safe(monkeypatch, tmp_path):
    _setup_db(tmp_path)
    from src.intelligence.gemini_client import GeminiClient
    from src.intelligence.market_analyst import AnalistaMercadoIA

    cli = GeminiClient(api_key="fake-key")

    async def _quebrado(prompt, temperature):
        return "isto nao eh json valido {{{"

    monkeypatch.setattr(cli, "_chamar_api", _quebrado)
    analista = AnalistaMercadoIA(cli, habilitado=True)
    voto = await analista.avaliar_direcional(simbolo="BTCUSDT", saldo=100.0)
    assert voto.acao == "HOLD"
    assert voto.confianca == 0.0
    assert voto.fonte == "indisponivel"


@pytest.mark.asyncio
async def test_analista_sem_chave_fail_safe(tmp_path):
    _setup_db(tmp_path)
    from src.intelligence.gemini_client import GeminiClient
    from src.intelligence.market_analyst import AnalistaMercadoIA

    cli = GeminiClient(api_key="")  # sem chave = indisponível
    analista = AnalistaMercadoIA(cli, habilitado=True)
    voto = await analista.avaliar_direcional(simbolo="BTCUSDT", saldo=100.0)
    assert voto.acao == "HOLD"
    assert voto.confianca == 0.0
    assert voto.fonte == "indisponivel"


@pytest.mark.asyncio
async def test_analista_timeout_fail_safe(monkeypatch, tmp_path):
    _setup_db(tmp_path)
    from src.intelligence.gemini_client import GeminiClient
    from src.intelligence.market_analyst import AnalistaMercadoIA

    cli = GeminiClient(api_key="fake-key")

    async def _lento(system_prompt, user_context, *, temperature=0.2):
        await asyncio.sleep(0.2)
        return {"action": "BUY", "score_direcional": 1.0, "confidence": 1.0}

    monkeypatch.setattr(cli, "analisar", _lento)
    analista = AnalistaMercadoIA(cli, habilitado=True, timeout_s=0.05)
    voto = await analista.avaliar_direcional(simbolo="BTCUSDT", saldo=100.0)
    assert voto.acao == "HOLD"
    assert voto.confianca == 0.0
    assert voto.fonte == "timeout"


@pytest.mark.asyncio
async def test_analista_erro_generico_fail_safe(monkeypatch, tmp_path):
    _setup_db(tmp_path)
    from src.intelligence.gemini_client import GeminiClient
    from src.intelligence.market_analyst import AnalistaMercadoIA

    cli = GeminiClient(api_key="fake-key")

    async def _boom(system_prompt, user_context, *, temperature=0.2):
        raise RuntimeError("falha de rede")

    monkeypatch.setattr(cli, "analisar", _boom)
    analista = AnalistaMercadoIA(cli, habilitado=True)
    voto = await analista.avaliar_direcional(simbolo="BTCUSDT", saldo=100.0)
    assert voto.acao == "HOLD"
    assert voto.confianca == 0.0
    assert voto.fonte == "erro"


@pytest.mark.asyncio
async def test_analista_nao_envia_sinal_mecanico_ao_prompt(monkeypatch, tmp_path):
    """Regressão de design: o contexto enviado à IA NÃO pode conter a ação do motor mecânico
    (evita ancoragem/viés). `sinal_mecanico` é aceito na assinatura, mas não deve vazar ao LLM."""
    _setup_db(tmp_path)
    from src.intelligence.gemini_client import GeminiClient
    from src.intelligence.market_analyst import AnalistaMercadoIA

    cli = GeminiClient(api_key="fake-key")
    capturado = {}

    async def _captura(system_prompt, user_context, *, temperature=0.2):
        capturado["contexto"] = user_context
        return {"action": "HOLD", "score_direcional": 0.0, "confidence": 0.2}

    monkeypatch.setattr(cli, "analisar", _captura)
    analista = AnalistaMercadoIA(cli, habilitado=True)
    await analista.avaliar_direcional(
        simbolo="BTCUSDT",
        sinal_mecanico={"acao": "BUY_SUPER_SECRETO_NAO_VAZAR"},
        saldo=100.0,
    )
    assert "sinal_mecanico" not in capturado["contexto"]
    assert "BUY_SUPER_SECRETO_NAO_VAZAR" not in capturado["contexto"]


# ── AnalistaMercadoIA.avaliar_lote (economia de RPM/TPM) ─────────────────────
@pytest.mark.asyncio
async def test_avaliar_lote_faz_uma_unica_chamada_de_rede(monkeypatch, tmp_path):
    """N símbolos, 1 chamada — a garantia central da correção de rate limit."""
    _setup_db(tmp_path)
    from src.intelligence.gemini_client import GeminiClient
    from src.intelligence.market_analyst import AnalistaMercadoIA

    cli = GeminiClient(api_key="fake-key")
    chamadas = []

    async def _lote(system_prompt, user_context, *, temperature=0.2):
        chamadas.append(user_context)
        return {
            "votos": [
                {"simbolo": "BTCUSDT", "action": "BUY", "score_direcional": 0.7, "confidence": 0.8},
                {"simbolo": "ETHUSDT", "action": "SELL", "score_direcional": -0.4, "confidence": 0.6},
                {"simbolo": "BNBUSDT", "action": "HOLD", "score_direcional": 0.0, "confidence": 0.2},
            ]
        }

    monkeypatch.setattr(cli, "analisar", _lote)
    analista = AnalistaMercadoIA(cli, habilitado=True)
    votos = await analista.avaliar_lote(simbolos=["BTCUSDT", "ETHUSDT", "BNBUSDT"], saldo=100.0)

    assert len(chamadas) == 1  # UMA chamada de rede cobrindo os 3 símbolos
    assert votos["BTCUSDT"].acao == "BUY"
    assert votos["ETHUSDT"].acao == "SELL"
    assert votos["BNBUSDT"].acao == "HOLD"
    assert votos["BTCUSDT"].score_direcional == pytest.approx(0.7)


@pytest.mark.asyncio
async def test_avaliar_direcional_usa_cache_do_lote_sem_nova_chamada(monkeypatch, tmp_path):
    """Depois de avaliar_lote, avaliar_direcional(simbolo=...) NÃO deve tocar a rede de novo."""
    _setup_db(tmp_path)
    from src.intelligence.gemini_client import GeminiClient
    from src.intelligence.market_analyst import AnalistaMercadoIA

    cli = GeminiClient(api_key="fake-key")
    chamadas = []

    async def _resposta(system_prompt, user_context, *, temperature=0.2):
        chamadas.append(1)
        return {"votos": [{"simbolo": "BTCUSDT", "action": "BUY", "score_direcional": 0.5, "confidence": 0.9}]}

    monkeypatch.setattr(cli, "analisar", _resposta)
    analista = AnalistaMercadoIA(cli, habilitado=True)
    await analista.avaliar_lote(simbolos=["BTCUSDT"], saldo=100.0)
    assert len(chamadas) == 1

    voto = await analista.avaliar_direcional(simbolo="BTCUSDT", saldo=100.0)
    assert len(chamadas) == 1  # ainda 1 — serviu do cache, não chamou `analisar` de novo
    assert voto.acao == "BUY"
    assert voto.score_direcional == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_avaliar_direcional_cache_frio_cai_no_caminho_por_simbolo(monkeypatch, tmp_path):
    """Símbolo fora do lote (cache frio) preserva o comportamento antigo: chama a rede sozinho."""
    _setup_db(tmp_path)
    from src.intelligence.gemini_client import GeminiClient
    from src.intelligence.market_analyst import AnalistaMercadoIA

    cli = GeminiClient(api_key="fake-key")

    async def _resposta(system_prompt, user_context, *, temperature=0.2):
        return {"action": "SELL", "score_direcional": -0.3, "confidence": 0.4}

    monkeypatch.setattr(cli, "analisar", _resposta)
    analista = AnalistaMercadoIA(cli, habilitado=True)
    await analista.avaliar_lote(simbolos=["BTCUSDT"], saldo=100.0)

    voto = await analista.avaliar_direcional(simbolo="ETHUSDT", saldo=100.0)  # não estava no lote
    assert voto.acao == "SELL"
    assert voto.score_direcional == pytest.approx(-0.3)


@pytest.mark.asyncio
async def test_avaliar_direcional_cache_expirado_refaz_chamada(monkeypatch, tmp_path):
    """TTL do cache de lote expira ⇒ nova consulta por-símbolo (nunca serve voto obsoleto)."""
    _setup_db(tmp_path)
    from src.intelligence.gemini_client import GeminiClient
    from src.intelligence import market_analyst as ma_mod
    from src.intelligence.market_analyst import AnalistaMercadoIA

    # TTL de sucesso = max(AI_MIN_INTERVALO_SEGUNDOS, _LOTE_CACHE_TTL_PISO_S). Zera os dois p/
    # forçar expiração rápida do cache de lote (throttle=0 desliga o gate de intervalo também).
    monkeypatch.setenv("AI_MIN_INTERVALO_SEGUNDOS", "0")
    monkeypatch.setattr(ma_mod, "_LOTE_CACHE_TTL_PISO_S", 0.01)
    cli = GeminiClient(api_key="fake-key")
    chamadas = []

    async def _lote(system_prompt, user_context, *, temperature=0.2):
        chamadas.append("lote")
        return {"votos": [{"simbolo": "BTCUSDT", "action": "BUY", "score_direcional": 0.5, "confidence": 0.9}]}

    async def _individual(system_prompt, user_context, *, temperature=0.2):
        chamadas.append("individual")
        return {"action": "HOLD", "score_direcional": 0.0, "confidence": 0.1}

    monkeypatch.setattr(cli, "analisar", _lote)
    analista = AnalistaMercadoIA(cli, habilitado=True)
    await analista.avaliar_lote(simbolos=["BTCUSDT"], saldo=100.0)

    await asyncio.sleep(0.05)  # espera o TTL (0.01s) expirar
    monkeypatch.setattr(cli, "analisar", _individual)
    voto = await analista.avaliar_direcional(simbolo="BTCUSDT", saldo=100.0)

    assert chamadas == ["lote", "individual"]  # cache expirado -> caiu no caminho por-símbolo
    assert voto.acao == "HOLD"


@pytest.mark.asyncio
async def test_avaliar_lote_desabilitado_retorna_neutro_para_todos():
    from src.intelligence.gemini_client import GeminiClient
    from src.intelligence.market_analyst import AnalistaMercadoIA

    analista = AnalistaMercadoIA(GeminiClient(api_key=""), habilitado=False)
    votos = await analista.avaliar_lote(simbolos=["BTCUSDT", "ETHUSDT"], saldo=100.0)
    assert votos["BTCUSDT"].acao == "HOLD" and votos["BTCUSDT"].confianca == 0.0
    assert votos["ETHUSDT"].acao == "HOLD" and votos["ETHUSDT"].confianca == 0.0


@pytest.mark.asyncio
async def test_avaliar_lote_vazio_retorna_dict_vazio(tmp_path):
    _setup_db(tmp_path)
    from src.intelligence.gemini_client import GeminiClient
    from src.intelligence.market_analyst import AnalistaMercadoIA

    analista = AnalistaMercadoIA(GeminiClient(api_key="fake-key"), habilitado=True)
    assert await analista.avaliar_lote(simbolos=[], saldo=100.0) == {}


@pytest.mark.asyncio
async def test_avaliar_lote_json_invalido_fail_safe_todos_simbolos(monkeypatch, tmp_path):
    _setup_db(tmp_path)
    from src.intelligence.gemini_client import GeminiClient
    from src.intelligence.market_analyst import AnalistaMercadoIA

    cli = GeminiClient(api_key="fake-key")

    async def _quebrado(prompt, temperature):
        return "nao eh json {{{"

    monkeypatch.setattr(cli, "_chamar_api", _quebrado)
    analista = AnalistaMercadoIA(cli, habilitado=True)
    votos = await analista.avaliar_lote(simbolos=["BTCUSDT", "ETHUSDT"], saldo=100.0)
    assert all(v.acao == "HOLD" and v.confianca == 0.0 for v in votos.values())


@pytest.mark.asyncio
async def test_avaliar_lote_formato_sem_chave_votos_fail_safe(monkeypatch, tmp_path):
    """Resposta é um dict JSON válido mas sem a chave "votos" esperada — fail-safe, não crash."""
    _setup_db(tmp_path)
    from src.intelligence.gemini_client import GeminiClient
    from src.intelligence.market_analyst import AnalistaMercadoIA

    cli = GeminiClient(api_key="fake-key")

    async def _formato_errado(system_prompt, user_context, *, temperature=0.2):
        return {"action": "BUY"}  # formato do prompt individual, não do lote

    monkeypatch.setattr(cli, "analisar", _formato_errado)
    analista = AnalistaMercadoIA(cli, habilitado=True)
    votos = await analista.avaliar_lote(simbolos=["BTCUSDT"], saldo=100.0)
    assert votos["BTCUSDT"].acao == "HOLD"
    assert votos["BTCUSDT"].confianca == 0.0


@pytest.mark.asyncio
async def test_avaliar_lote_simbolo_ausente_na_resposta_vira_hold(monkeypatch, tmp_path):
    """IA responde só para parte dos símbolos — os ausentes recebem HOLD fail-safe, não erro."""
    _setup_db(tmp_path)
    from src.intelligence.gemini_client import GeminiClient
    from src.intelligence.market_analyst import AnalistaMercadoIA

    cli = GeminiClient(api_key="fake-key")

    async def _parcial(system_prompt, user_context, *, temperature=0.2):
        return {"votos": [{"simbolo": "BTCUSDT", "action": "BUY", "score_direcional": 0.5, "confidence": 0.9}]}

    monkeypatch.setattr(cli, "analisar", _parcial)
    analista = AnalistaMercadoIA(cli, habilitado=True)
    votos = await analista.avaliar_lote(simbolos=["BTCUSDT", "ETHUSDT"], saldo=100.0)
    assert votos["BTCUSDT"].acao == "BUY"
    assert votos["ETHUSDT"].acao == "HOLD"
    assert votos["ETHUSDT"].confianca == 0.0


@pytest.mark.asyncio
async def test_avaliar_lote_timeout_fail_safe(monkeypatch, tmp_path):
    _setup_db(tmp_path)
    from src.intelligence.gemini_client import GeminiClient
    from src.intelligence.market_analyst import AnalistaMercadoIA

    cli = GeminiClient(api_key="fake-key")

    async def _lento(system_prompt, user_context, *, temperature=0.2):
        await asyncio.sleep(0.2)
        return {"votos": []}

    monkeypatch.setattr(cli, "analisar", _lento)
    analista = AnalistaMercadoIA(cli, habilitado=True, timeout_s=0.05)
    votos = await analista.avaliar_lote(simbolos=["BTCUSDT", "ETHUSDT"], saldo=100.0)
    assert all(v.acao == "HOLD" and v.fonte == "timeout" for v in votos.values())


# ── REGRESSÃO DO BUG DE PRODUÇÃO (DA-30.1, log.txt 2026-07-02) ───────────────
# `avaliar_lote` FALHOU (429) mas não cacheava o resultado — cada chamador subsequente de
# `avaliar_direcional` no mesmo ciclo achava cache frio e tentava de novo INDIVIDUALMENTE,
# multiplicando 1 falha em várias chamadas de rede extras (5 erros 429 seguidos até o
# cooldown de 60min). Fix: `avaliar_lote` cacheia TAMBÉM o resultado de falha (TTL mais curto).
@pytest.mark.asyncio
async def test_avaliar_lote_com_429_cacheia_falha_e_bloqueia_retry_individual(monkeypatch, tmp_path):
    """O teste que teria pego o bug: depois de `avaliar_lote` falhar com 429 (ou qualquer
    erro), `avaliar_direcional(simbolo=...)` para um símbolo QUE ESTAVA no lote NÃO deve
    tocar rede de novo — deve servir o voto de falha cacheado."""
    _setup_db(tmp_path)
    from src.intelligence.gemini_client import GeminiClient
    from src.intelligence.market_analyst import AnalistaMercadoIA

    cli = GeminiClient(api_key="fake-key")
    chamadas = {"n": 0}

    async def _sempre_429(system_prompt, user_context, *, temperature=0.2):
        chamadas["n"] += 1
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(cli, "analisar", _sempre_429)
    analista = AnalistaMercadoIA(cli, habilitado=True)

    votos = await analista.avaliar_lote(simbolos=["BTCUSDT", "ETHUSDT", "BNBUSDT"], saldo=100.0)
    assert chamadas["n"] == 1  # o LOTE em si é só 1 chamada
    assert all(v.acao == "HOLD" and v.confianca == 0.0 for v in votos.values())

    # Simula o passo 3 do orquestrador / o caminho isolado do trader: cada símbolo do lote
    # tenta `avaliar_direcional` individualmente depois. NENHUM deve tocar rede de novo.
    for simbolo in ["BTCUSDT", "ETHUSDT", "BNBUSDT"]:
        voto = await analista.avaliar_direcional(simbolo=simbolo, saldo=100.0)
        assert voto.acao == "HOLD"
        assert voto.confianca == 0.0

    assert chamadas["n"] == 1  # AINDA 1 — nenhuma chamada extra foi feita (o bug fazia isso virar 4)


@pytest.mark.asyncio
async def test_avaliar_lote_falha_usa_ttl_mais_curto_que_sucesso(monkeypatch, tmp_path):
    """Cache de FALHA expira mais rápido que cache de SUCESSO — uma falha transitória não
    deve prender o bot em HOLD forçado pelo mesmo tempo que um voto real teria vida."""
    _setup_db(tmp_path)
    from src.intelligence.gemini_client import GeminiClient
    from src.intelligence import market_analyst as ma_mod
    from src.intelligence.market_analyst import AnalistaMercadoIA

    monkeypatch.setattr(ma_mod, "_LOTE_CACHE_TTL_FALHA_S", 0.01)
    # Sucesso vale pelo intervalo de throttle — 999s garante que NÃO expira no teste, provando
    # que só o cache de FALHA (0.01s) expirou.
    monkeypatch.setenv("AI_MIN_INTERVALO_SEGUNDOS", "999")

    cli = GeminiClient(api_key="fake-key")
    chamadas = {"n": 0}

    async def _falha_depois_sucesso(system_prompt, user_context, *, temperature=0.2):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise RuntimeError("429")
        # 2ª chamada vem de `avaliar_direcional` (caminho INDIVIDUAL) — formato diferente do lote.
        return {"action": "BUY", "score_direcional": 0.5, "confidence": 0.9}

    monkeypatch.setattr(cli, "analisar", _falha_depois_sucesso)
    analista = AnalistaMercadoIA(cli, habilitado=True)

    await analista.avaliar_lote(simbolos=["BTCUSDT"], saldo=100.0)  # falha, cacheada com TTL curto
    await asyncio.sleep(0.05)  # espera o TTL de FALHA (0.01s) expirar

    voto = await analista.avaliar_direcional(simbolo="BTCUSDT", saldo=100.0)  # cache frio -> tenta de novo
    assert chamadas["n"] == 2  # a 2ª tentativa aconteceu (cache de falha já tinha expirado)
    assert voto.acao == "BUY"


# ── THROTTLE DA IA (DA-31 — caber no free tier do Gemini) ────────────────────
@pytest.mark.asyncio
async def test_avaliar_lote_throttle_bloqueia_segunda_chamada_no_intervalo(monkeypatch, tmp_path):
    """Dentro de AI_MIN_INTERVALO_SEGUNDOS, um 2º avaliar_lote NÃO toca a rede — serve o cache.
    É o que mantém o consumo de IA dentro da cota diária minúscula do free tier do Gemini."""
    _setup_db(tmp_path)
    monkeypatch.setenv("AI_MIN_INTERVALO_SEGUNDOS", "600")
    from src.intelligence.gemini_client import GeminiClient
    from src.intelligence.market_analyst import AnalistaMercadoIA

    cli = GeminiClient(api_key="fake-key")
    chamadas = {"n": 0}

    async def _lote(system_prompt, user_context, *, temperature=0.2):
        chamadas["n"] += 1
        return {"votos": [{"simbolo": "BTCUSDT", "action": "BUY", "score_direcional": 0.6, "confidence": 0.8}]}

    monkeypatch.setattr(cli, "analisar", _lote)
    analista = AnalistaMercadoIA(cli, habilitado=True)

    v1 = await analista.avaliar_lote(simbolos=["BTCUSDT"], saldo=100.0)
    assert chamadas["n"] == 1 and v1["BTCUSDT"].acao == "BUY"

    # 2ª e 3ª chamadas dentro do intervalo: servem do cache, NÃO tocam a rede.
    v2 = await analista.avaliar_lote(simbolos=["BTCUSDT"], saldo=100.0)
    v3 = await analista.avaliar_lote(simbolos=["BTCUSDT"], saldo=100.0)
    assert chamadas["n"] == 1  # AINDA 1 — throttle segurou as chamadas seguintes
    assert v2["BTCUSDT"].acao == "BUY" and v3["BTCUSDT"].acao == "BUY"  # voto real do cache


@pytest.mark.asyncio
async def test_avaliar_lote_throttle_simbolo_novo_no_intervalo_retorna_neutro_sem_rede(monkeypatch, tmp_path):
    """Símbolo que não estava no lote anterior, consultado DENTRO do intervalo: neutro (fonte
    'throttle') sem tocar a rede — não fura o throttle só porque é um símbolo novo."""
    _setup_db(tmp_path)
    monkeypatch.setenv("AI_MIN_INTERVALO_SEGUNDOS", "600")
    from src.intelligence.gemini_client import GeminiClient
    from src.intelligence.market_analyst import AnalistaMercadoIA

    cli = GeminiClient(api_key="fake-key")
    chamadas = {"n": 0}

    async def _lote(system_prompt, user_context, *, temperature=0.2):
        chamadas["n"] += 1
        return {"votos": [{"simbolo": "BTCUSDT", "action": "BUY", "score_direcional": 0.6, "confidence": 0.8}]}

    monkeypatch.setattr(cli, "analisar", _lote)
    analista = AnalistaMercadoIA(cli, habilitado=True)

    await analista.avaliar_lote(simbolos=["BTCUSDT"], saldo=100.0)
    votos = await analista.avaliar_lote(simbolos=["ETHUSDT"], saldo=100.0)  # símbolo novo, no intervalo
    assert chamadas["n"] == 1  # não tocou a rede de novo
    assert votos["ETHUSDT"].acao == "HOLD"
    assert votos["ETHUSDT"].fonte == "throttle"


@pytest.mark.asyncio
async def test_avaliar_lote_throttle_zero_desliga(monkeypatch, tmp_path):
    """AI_MIN_INTERVALO_SEGUNDOS=0 desliga o throttle — cada chamada toca a rede (modo billing)."""
    _setup_db(tmp_path)
    monkeypatch.setenv("AI_MIN_INTERVALO_SEGUNDOS", "0")
    from src.intelligence.gemini_client import GeminiClient
    from src.intelligence.market_analyst import AnalistaMercadoIA

    cli = GeminiClient(api_key="fake-key")
    chamadas = {"n": 0}

    async def _lote(system_prompt, user_context, *, temperature=0.2):
        chamadas["n"] += 1
        return {"votos": [{"simbolo": "BTCUSDT", "action": "BUY", "score_direcional": 0.6, "confidence": 0.8}]}

    monkeypatch.setattr(cli, "analisar", _lote)
    analista = AnalistaMercadoIA(cli, habilitado=True)
    await analista.avaliar_lote(simbolos=["BTCUSDT"], saldo=100.0)
    await analista.avaliar_lote(simbolos=["BTCUSDT"], saldo=100.0)
    assert chamadas["n"] == 2  # throttle desligado: 2 chamadas de rede
