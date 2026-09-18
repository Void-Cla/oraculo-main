import pytest

from src.servicos.dashboard import montar_dashboard


@pytest.mark.asyncio
async def test_dashboard_prioriza_sinal_final_do_auto_trade(monkeypatch):
    async def _ohlcv(*args, **kwargs):
        return [
            {"ts": 1, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 10.0},
            {"ts": 2, "open": 100.0, "high": 102.0, "low": 99.5, "close": 101.0, "volume": 11.0},
        ]

    async def _livro(*args, **kwargs):
        return {"bid_price": 100.9, "ask_price": 101.1}

    async def _features(*args, **kwargs):
        return [{"ts": 2, "spread_rel": 0.0001}]

    async def _predicoes(*args, **kwargs):
        return [
            {
                "created_ts": 2,
                "y_hat": 102.0,
                "y_cal": 102.0,
                "p_conf": 0.72,
                "meta": {
                    "preco_atual": 101.0,
                    "decisao": {
                        "acao": "BUY",
                        "motivo": "compra_hibrida",
                        "llm": {"insight": "llm otimista", "direcao": "compra"},
                    },
                },
            }
        ]

    async def _outcomes(*args, **kwargs):
        return []

    async def _auditoria(*args, **kwargs):
        return [
            {
                "id": 1,
                "created_ts": 3,
                "simbolo": "BTCUSDT",
                "tipo": "auto_trade",
                "payload": {
                    "sinal": {
                        "acao": "HOLD",
                        "motivo": "sinal_hold",
                        "confianca": 0.61,
                        "estrategia": "volatility_scalping",
                        "regime": "LOW_VOL",
                        "lucro_liquido_esperado_pct": -0.002,
                    }
                },
            }
        ]

    async def _ordens(*args, **kwargs):
        return []

    async def _resumo(*args, **kwargs):
        return {}

    monkeypatch.setattr("src.servicos.dashboard.RepositorioOhlcv.obter_ultimas", _ohlcv)
    monkeypatch.setattr("src.servicos.dashboard.RepositorioLivroTopo.obter_ultimo", _livro)
    monkeypatch.setattr("src.servicos.dashboard.RepositorioFeatures.listar_ultimas", _features)
    monkeypatch.setattr("src.servicos.dashboard.RepositorioPredicoes.listar_recentes", _predicoes)
    monkeypatch.setattr("src.servicos.dashboard.RepositorioOutcomes.listar_recentes", _outcomes)
    monkeypatch.setattr("src.servicos.dashboard.RepositorioAuditoria.listar_recentes", _auditoria)
    monkeypatch.setattr("src.servicos.dashboard.RepositorioOrdens.listar_recentes", _ordens)
    monkeypatch.setattr("src.servicos.dashboard.RepositorioOrdens.resumo_status", _resumo)

    painel = await montar_dashboard(simbolo="BTCUSDT", usuario_id=None, loop_previsao_ativo=True, db_path="db.sqlite")

    assert painel["modelos"]["decisao_hibrida_atual"]["acao"] == "BUY"
    assert painel["modelos"]["decisao_atual"]["acao"] == "HOLD"
    assert painel["modelos"]["decisao_atual"]["origem"] == "auto_trade"
    assert painel["modelos"]["sinal_atual"]["motivo"] == "sinal_hold"
