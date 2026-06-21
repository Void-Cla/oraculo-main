import json

from src.servicos.ai_advisor import _remover_cerca_markdown


def test_remove_cerca_json_completa():
    bruto = "```json\n{\"direcao\": \"BUY\", \"confianca\": 0.7}\n```"
    assert json.loads(_remover_cerca_markdown(bruto)) == {"direcao": "BUY", "confianca": 0.7}


def test_remove_cerca_simples():
    bruto = "```\n{\"direcao\": \"SELL\"}\n```"
    assert json.loads(_remover_cerca_markdown(bruto)) == {"direcao": "SELL"}


def test_sem_cerca_passa_intacto():
    bruto = "{\"direcao\": \"HOLD\"}"
    assert json.loads(_remover_cerca_markdown(bruto)) == {"direcao": "HOLD"}


def test_nao_corrompe_valor_que_comeca_com_letra_do_conjunto():
    # Regressão do bug lstrip("```json"): um valor iniciando com j/s/o/n não pode ser comido.
    bruto = "```json\n{\"reasoning\": \"sobra de oferta\", \"direcao\": \"SELL\"}\n```"
    parsed = json.loads(_remover_cerca_markdown(bruto))
    assert parsed["reasoning"] == "sobra de oferta"
    assert parsed["direcao"] == "SELL"
