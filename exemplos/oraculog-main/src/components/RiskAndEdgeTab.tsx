import React from 'react';
import { 
  ShieldAlert, 
  Lock, 
  Scale, 
  Percent, 
  TrendingUp, 
  AlertOctagon, 
  CheckCircle2, 
  ArrowRight,
  BookOpen
} from 'lucide-react';

export const RiskAndEdgeTab: React.FC = () => {
  return (
    <div className="space-y-8">
      <div>
        <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-rose-500/10 text-rose-400 text-xs font-semibold mb-2">
          <Lock className="w-3.5 h-3.5" />
          Segurança Financeira de Nível Institucional
        </div>
        <h3 className="text-xl font-bold text-white tracking-tight">
          Governança de Risco, Edge Líquido e Proteção de Capital
        </h3>
        <p className="text-xs sm:text-sm text-slate-300 mt-1 max-w-3xl">
          Análise detalhada do arquivo <code className="text-amber-400 font-mono text-xs">up.md</code> e das travas de segurança do Guardião em <code className="text-amber-400 font-mono text-xs">src/risco/edge_config.py</code>.
        </p>
      </div>

      {/* The Core Truth: Real Capital Lock */}
      <div className="bg-gradient-to-r from-rose-950/40 via-slate-900 to-slate-900 border border-rose-800/40 rounded-2xl p-6 sm:p-8">
        <div className="flex flex-col sm:flex-row sm:items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-rose-500/20 text-rose-400 flex items-center justify-center flex-shrink-0 border border-rose-700/50">
            <AlertOctagon className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h4 className="text-lg font-bold text-white">
                Trava Ativa: Conta Real Desativada por Design
              </h4>
              <span className="font-mono text-xs px-2.5 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-800">
                PERMITIR_CONTA_REAL=false
              </span>
            </div>
            <p className="mt-2 text-xs sm:text-sm text-slate-300 leading-relaxed">
              O projeto possui um mecanismo de defesa raro em bots de varejo: <strong>o sistema se recusa a enviar ordens com dinheiro real</strong> enquanto os testes de walk-forward não apresentarem retorno líquido estatisticamente comprovado após taxas.
            </p>
          </div>
        </div>
      </div>

      {/* The Math Behind Trading Fees & EV */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
          <div className="flex items-center space-x-3 mb-4">
            <div className="w-9 h-9 rounded-lg bg-amber-500/10 text-amber-400 flex items-center justify-center">
              <Percent className="w-4 h-4" />
            </div>
            <div>
              <h4 className="text-sm font-bold text-white">O Atrito das Taxas da Binance</h4>
              <p className="text-[11px] text-slate-400">Desafio de micro-trading em klines de 1m</p>
            </div>
          </div>
          <p className="text-xs text-slate-300 leading-relaxed">
            Na Binance spot, a taxa padrão é de <strong>0.10% por ponta</strong> (0.20% round-trip entre compra e venda). Em estratégias de micro-oscilações em gráficos de 1 minuto, a variação esperada frequentemente fica entre 0.15% e 0.30%.
          </p>
          <div className="mt-4 p-3 rounded-xl bg-slate-950 border border-slate-800 text-xs space-y-1.5 font-mono">
            <div className="flex justify-between text-slate-400">
              <span>Ganho Bruto Médio:</span>
              <span className="text-slate-200">+0.22%</span>
            </div>
            <div className="flex justify-between text-rose-400">
              <span>Taxa Round-Trip (Taker):</span>
              <span>-0.20%</span>
            </div>
            <div className="border-t border-slate-800 pt-1 flex justify-between font-bold text-amber-400">
              <span>Edge Líquido Real:</span>
              <span>+0.02% (margem vulnerável)</span>
            </div>
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
          <div className="flex items-center space-x-3 mb-4">
            <div className="w-9 h-9 rounded-lg bg-emerald-500/10 text-emerald-400 flex items-center justify-center">
              <Scale className="w-4 h-4" />
            </div>
            <div>
              <h4 className="text-sm font-bold text-white">Calculadora de Expected Value (EV)</h4>
              <p className="text-[11px] text-slate-400">src/probabilidade/ev_calculator.py</p>
            </div>
          </div>
          <p className="text-xs text-slate-300 leading-relaxed">
            Toda operação precisa de uma pontuação positiva de Expected Value antes da execução. A fórmula aplicada desconta spread, slippage e taxas da exchange:
          </p>
          <div className="mt-4 p-3 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono text-emerald-300 leading-relaxed">
            EV = (P_win × Ganho_Líquido) - (P_loss × Perda_Total) - Taxa_Exchange - Slippage_Estimado
          </div>
          <p className="mt-2 text-[11px] text-slate-400">
            Se <code className="text-slate-300">EV &le; 0</code>, o trade é sumariamente rejeitado pelo Risk Engine.
          </p>
        </div>
      </div>

      {/* Up.md Master Roadmap: The 3 Pillars */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
        <div className="flex items-center space-x-2 mb-4">
          <BookOpen className="w-4 h-4 text-amber-400" />
          <h4 className="text-base font-bold text-white">
            Plano Estratégico do Guia Mestre (up.md): Transição Segura para Capital Real
          </h4>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-4">
          <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
            <span className="text-amber-400 font-bold text-xs uppercase block mb-1">Fase 1: Coleta Contínua</span>
            <h5 className="text-sm font-semibold text-white mb-2">Acúmulo de Dados Históricos</h5>
            <p className="text-xs text-slate-400 leading-relaxed">
              Rodar com <code className="text-slate-300">ATIVAR_COLETA_CONTINUA=true</code> por no mínimo 7 a 14 dias para gerar massa crítica de klines e book real para treino de modelos.
            </p>
          </div>

          <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
            <span className="text-emerald-400 font-bold text-xs uppercase block mb-1">Fase 2: Walk-Forward</span>
            <h5 className="text-sm font-semibold text-white mb-2">Comprovação Estatística de Edge</h5>
            <p className="text-xs text-slate-400 leading-relaxed">
              Executar <code className="text-slate-300">scripts/backtest_walkforward.py</code> em janelas deslizantes out-of-sample para provar que o retorno líquido cobre com folga as taxas.
            </p>
          </div>

          <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
            <span className="text-purple-400 font-bold text-xs uppercase block mb-1">Fase 3: Micro-Lote</span>
            <h5 className="text-sm font-semibold text-white mb-2">Entrada com 50 a 100 USDT</h5>
            <p className="text-xs text-slate-400 leading-relaxed">
              Iniciar em conta real com notional mínimo estrito ($10 por trade), com circuit breaker diário de perda de no máximo $2 por dia, operando apenas os melhores pares.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
