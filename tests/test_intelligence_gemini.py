"""Camada agêntica Gemini — VETO-only, fail-open, cost-control. Tudo mockado (sem rede)."""
import os

import pytest


def _setup_db(tmp_path):
    os.environ["DB_PATH"] = str(tmp_path / "ai.sqlite")
    from src.persistencia.conexao import inicializar_db

    inicializar_db()


# ── response_sanitizer ───────────────────────────────────────────────────────
def test_extrair_json_puro():
    from src.intelligence.response_sanitizer import extrair_json

    assert extrair_json('{"action": "PROCEED"}') == {"action": "PROCEED"}


def test_extrair_json_com_cerca_markdown():
    from src.intelligence.response_sanitizer import extrair_json

    texto = '```json\n{"action": "ABORT", "confidence_score": 0.9}\n```'
    assert extrair_json(texto)["action"] == "ABORT"


def test_extrair_json_invalido_retorna_none():
    from src.intelligence.response_sanitizer import extrair_json

    assert extrair_json("isto não é json") is None
    assert extrair_json("") is None
    assert extrair_json(None) is None


# ── guard (normalização de decisão) ──────────────────────────────────────────
def test_guard_default_proceed_em_resposta_invalida():
    from src.intelligence.guard import normalizar_decisao

    d = normalizar_decisao(None, confianca_min_veto=0.7)
    assert d.action == "PROCEED" and d.vetou is False


def test_guard_abort_alta_confianca_veta():
    from src.intelligence.guard import normalizar_decisao

    d = normalizar_decisao(
        {"action": "ABORT", "confidence_score": 0.85, "rationale": "bull trap"},
        confianca_min_veto=0.7,
    )
    assert d.action == "ABORT" and d.vetou is True


def test_guard_abort_baixa_confianca_vira_proceed():
    from src.intelligence.guard import normalizar_decisao

    d = normalizar_decisao(
        {"action": "ABORT", "confidence_score": 0.5}, confianca_min_veto=0.7
    )
    assert d.action == "PROCEED" and d.vetou is False


def test_guard_acao_invalida_vira_proceed():
    from src.intelligence.guard import normalizar_decisao

    d = normalizar_decisao({"action": "BUY", "confidence_score": 0.99}, confianca_min_veto=0.7)
    assert d.action == "PROCEED"


# ── GeminiClient (cost-control + fail-open) ──────────────────────────────────
@pytest.mark.asyncio
async def test_gemini_sem_chave_retorna_none():
    from src.intelligence.gemini_client import GeminiClient

    cli = GeminiClient(api_key="")
    assert cli.disponivel() is False
    assert await cli.analisar("sys", "ctx") is None


@pytest.mark.asyncio
async def test_gemini_parseia_resposta(monkeypatch):
    from src.intelligence.gemini_client import GeminiClient

    cli = GeminiClient(api_key="fake-key")

    async def _fake(prompt, temperature):
        return '{"action": "PROCEED", "confidence_score": 0.2}'

    monkeypatch.setattr(cli, "_chamar_api", _fake)
    r = await cli.analisar("sys", "ctx")
    assert r["action"] == "PROCEED"
    assert cli.health()["chamadas_dia"] == 1


@pytest.mark.asyncio
async def test_gemini_fail_open_em_excecao(monkeypatch):
    from src.intelligence.gemini_client import GeminiClient

    cli = GeminiClient(api_key="fake-key")

    async def _boom(prompt, temperature):
        raise RuntimeError("rede caiu")

    monkeypatch.setattr(cli, "_chamar_api", _boom)
    assert await cli.analisar("sys", "ctx") is None  # nunca lança
    assert cli.health()["falhas_consecutivas"] == 1


@pytest.mark.asyncio
async def test_gemini_nao_vaza_chave_em_log_de_erro(monkeypatch):
    # Regressão: a API key NUNCA pode aparecer em mensagem de erro/log (vazamento de segredo).
    from src.intelligence.gemini_client import GeminiClient

    chave = "AQ.SuperSecreta12345"
    cli = GeminiClient(api_key=chave)

    async def _erro_com_chave(prompt, temperature):
        # Simula o HTTPStatusError do httpx que embute a URL/credencial na mensagem.
        raise RuntimeError(f"401 Unauthorized for url ...?key={chave}")

    capturado: list[str] = []
    monkeypatch.setattr(cli, "_chamar_api", _erro_com_chave)
    # O wrapper `analisar` (com o log de erro + redação `_redigir`) vive agora na base
    # `provedor_ia` — o Gemini herda dela. Patcheamos o LOG da base, onde o erro é registrado.
    monkeypatch.setattr(
        "src.intelligence.provedor_ia.LOG",
        type("L", (), {"error": lambda *a, **k: capturado.append(str(k.get("extra"))),
                       "warning": lambda *a, **k: None})(),
    )
    assert await cli.analisar("s", "c") is None
    assert chave not in " ".join(capturado)
    assert "REDACTED" in " ".join(capturado)


@pytest.mark.asyncio
async def test_gemini_cost_control_limite_diario(monkeypatch):
    from src.intelligence.gemini_client import GeminiClient

    monkeypatch.setenv("GEMINI_MAX_CALLS_DIA", "1")
    cli = GeminiClient(api_key="fake-key")

    async def _ok(prompt, temperature):
        return '{"action": "PROCEED"}'

    monkeypatch.setattr(cli, "_chamar_api", _ok)
    assert await cli.analisar("s", "c") is not None  # 1ª chamada ok
    assert await cli.analisar("s", "c") is None       # limite diário atingido


@pytest.mark.asyncio
async def test_gemini_cost_control_conta_tentativas_com_429(monkeypatch):
    """DA-31: um 429/erro (exceção) TAMBÉM consome o teto interno de chamadas/dia. Antes só o
    sucesso contava, então o bot ficava batendo na rede a cada ciclo mesmo estourando o RPD do
    Google. Agora cada TENTATIVA de rede conta — o teto interno protege a cota de verdade."""
    from src.intelligence.gemini_client import GeminiClient

    monkeypatch.setenv("GEMINI_MAX_CALLS_DIA", "2")
    cli = GeminiClient(api_key="fake-key")

    async def _sempre_429(prompt, temperature):
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(cli, "_chamar_api", _sempre_429)
    assert await cli.analisar("s", "c") is None   # tentativa 1 (429) — conta
    assert cli.health()["chamadas_dia"] == 1
    assert await cli.analisar("s", "c") is None   # tentativa 2 (429) — conta, atinge o teto=2
    assert cli.health()["chamadas_dia"] == 2
    # 3ª: disponivel()=False (teto atingido) → NÃO toca a rede, retorna None sem incrementar.
    assert cli.disponivel() is False
    assert await cli.analisar("s", "c") is None
    assert cli.health()["chamadas_dia"] == 2  # não passou de 2 — a rede não foi tocada


# ── PreExecutionFilter (interceptor) ─────────────────────────────────────────
@pytest.mark.asyncio
async def test_filtro_desabilitado_sempre_proceed():
    from src.intelligence.gemini_client import GeminiClient
    from src.intelligence.pre_execution_filter import PreExecutionFilter

    f = PreExecutionFilter(GeminiClient(api_key=""), habilitado=False)
    d = await f.avaliar(simbolo="BTCUSDT", sinal={"acao": "BUY"}, saldo=100.0)
    assert d.action == "PROCEED" and d.source == "disabled"


@pytest.mark.asyncio
async def test_filtro_veta_quando_ia_aborta(monkeypatch, tmp_path):
    _setup_db(tmp_path)
    from src.intelligence.gemini_client import GeminiClient
    from src.intelligence.pre_execution_filter import PreExecutionFilter

    cli = GeminiClient(api_key="fake-key")

    async def _abort(system_prompt, user_context, *, temperature=0.2):
        return {"action": "ABORT", "confidence_score": 0.9, "rationale": "bear trap"}

    monkeypatch.setattr(cli, "analisar", _abort)
    f = PreExecutionFilter(cli, habilitado=True, confianca_min_veto=0.7)
    d = await f.avaliar(simbolo="BTCUSDT", sinal={"acao": "BUY"}, saldo=100.0)
    assert d.vetou is True


@pytest.mark.asyncio
async def test_filtro_proceed_quando_ia_indisponivel(monkeypatch, tmp_path):
    _setup_db(tmp_path)
    from src.intelligence.gemini_client import GeminiClient
    from src.intelligence.pre_execution_filter import PreExecutionFilter

    cli = GeminiClient(api_key="fake-key")

    async def _none(system_prompt, user_context, *, temperature=0.2):
        return None

    monkeypatch.setattr(cli, "analisar", _none)
    f = PreExecutionFilter(cli, habilitado=True)
    d = await f.avaliar(simbolo="BTCUSDT", sinal={"acao": "BUY"}, saldo=100.0)
    assert d.action == "PROCEED" and d.vetou is False


# ── PostTradeAuditor ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_auditor_persiste_resultado(monkeypatch, tmp_path):
    _setup_db(tmp_path)
    from src.intelligence.gemini_client import GeminiClient
    from src.intelligence.post_trade_auditor import PostTradeAuditor
    from src.persistencia.repositorio_auditoria import RepositorioAuditoria

    cli = GeminiClient(api_key="fake-key")

    async def _audit(system_prompt, user_context, *, temperature=0.2):
        return {"recommendation": "evitar momentum em consolidacao", "patterns_loss": ["a", "b"]}

    monkeypatch.setattr(cli, "analisar", _audit)
    auditor = PostTradeAuditor(cli)
    r = await auditor.executar_ciclo()
    assert r["recommendation"].startswith("evitar")
    registros = await RepositorioAuditoria.listar_recentes(tipo="auditoria_2h", limite=5)
    assert len(registros) == 1
    assert registros[0]["componente"] == "post_trade_auditor"


@pytest.mark.asyncio
async def test_auditor_sem_ia_nao_persiste(monkeypatch, tmp_path):
    _setup_db(tmp_path)
    from src.intelligence.gemini_client import GeminiClient
    from src.intelligence.post_trade_auditor import PostTradeAuditor
    from src.persistencia.repositorio_auditoria import RepositorioAuditoria

    cli = GeminiClient(api_key="")  # indisponível
    auditor = PostTradeAuditor(cli)
    assert await auditor.executar_ciclo() is None
    registros = await RepositorioAuditoria.listar_recentes(tipo="auditoria_2h", limite=5)
    assert registros == []


@pytest.mark.asyncio
async def test_auditor_run_loop_nao_chama_no_boot(monkeypatch, tmp_path):
    """DA-31: o run_loop ESPERA um intervalo antes da 1ª auditoria — NÃO dispara no T+0 do boot
    (era o primeiro 429 que o dono via 'logo após o boot', com quota do Gemini já drenada)."""
    _setup_db(tmp_path)
    import asyncio
    from src.intelligence.gemini_client import GeminiClient
    from src.intelligence.post_trade_auditor import PostTradeAuditor

    cli = GeminiClient(api_key="fake-key")
    chamadas = {"n": 0}

    async def _audit(system_prompt, user_context, *, temperature=0.2):
        chamadas["n"] += 1
        return {"recommendation": "x"}

    monkeypatch.setattr(cli, "analisar", _audit)
    auditor = PostTradeAuditor(cli)
    # Intervalo grande — a 1ª auditoria só ocorreria bem depois. O shutdown é sinalizado logo,
    # então o loop deve encerrar SEM ter chamado executar_ciclo nenhuma vez.
    auditor._intervalo_s = 3600
    shutdown = asyncio.Event()
    shutdown.set()  # já sinalizado: run_loop deve retornar na espera, sem auditar
    await asyncio.wait_for(auditor.run_loop(shutdown), timeout=2.0)
    assert chamadas["n"] == 0  # NENHUMA chamada de rede no boot
