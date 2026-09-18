#!/usr/bin/env python3
"""
Ponto de Entrada e Bridge CLI do Oráculo (PT-BR)
Permite invocar ciclos de avaliação rápida, atualização de IA de 2 horas e treino online.
"""
import sys
import json
from backend_oraculo.motor_orquestrador import MOTOR_ORACULO
from backend_oraculo.ia import GERENCIADOR_IA
from backend_oraculo.modelagem import TREINADOR_MODELO
from backend_oraculo.persistencia import BANCO_DADOS

def main():
    comando = sys.argv[1] if len(sys.argv) > 1 else 'ciclo'

    if comando == 'ciclo':
        resultado = MOTOR_ORACULO.executar_ciclo_completo()
        print(json.dumps(resultado, ensure_ascii=False, indent=2))

    elif comando == 'status':
        resumo_banco = BANCO_DADOS.obter_resumo_lucro_liquido()
        metricas_treino = TREINADOR_MODELO.obter_metricas()
        estado_ia = GERENCIADOR_IA.estado
        status_conta = MOTOR_ORACULO.verificar_conta_real_binance()
        print(json.dumps({
            'saldo_usdt': round(MOTOR_ORACULO.saldo_usdt, 2),
            'status_conta': status_conta,
            'conexao_binance': MOTOR_ORACULO.ultima_verificacao_conectividade,
            'resumo_financeiro': resumo_banco,
            'metricas_treino': metricas_treino.__dict__,
            'estado_ia': estado_ia.__dict__,
            'tempo_restante_ia_segundos': GERENCIADOR_IA.obter_tempo_restante_segundos()
        }, ensure_ascii=False, indent=2))

    elif comando == 'testar_conexao':
        from backend_oraculo.cliente_binance import CLIENTE_BINANCE
        ping_info = CLIENTE_BINANCE.testar_ping()
        status_conta = MOTOR_ORACULO.verificar_conta_real_binance()
        print(json.dumps({
            'conexao': ping_info,
            'conta': status_conta
        }, ensure_ascii=False, indent=2))

    elif comando == 'atualizar_ia':
        # Permite atualizar a IA com novos parâmetros
        try:
            dados_entrada = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
        except Exception:
            dados_entrada = {}
            
        peso = float(dados_entrada.get('peso_noticias_ia', 0.20))
        bias = float(dados_entrada.get('bias_macro_direcional', 0.15))
        regime = dados_entrada.get('regime_mercado', 'TENDENCIA_ALTA')
        intensidade = dados_entrada.get('intensidade_impacto_noticias', 'MEDIO')
        resumo = dados_entrada.get('resumo_executivo_ptbr', 'Análise periódica de 2h concluída via Gemini.')
        fatores = dados_entrada.get('fatores_chave', ['Pressão compradora', 'Fluxo estável'])

        estado = GERENCIADOR_IA.atualizar_analise_ia(
            peso_noticias=peso,
            bias_macro=bias,
            regime=regime,
            intensidade=intensidade,
            resumo=resumo,
            fatores=fatores
        )
        print(json.dumps(estado.__dict__, ensure_ascii=False, indent=2))

    elif comando == 'historico_trades':
        trades = BANCO_DADOS.obter_trades_recentes(50)
        print(json.dumps(trades, ensure_ascii=False, indent=2))

    else:
        print(json.dumps({'erro': f'Comando desconhecido: {comando}'}))

if __name__ == '__main__':
    main()
