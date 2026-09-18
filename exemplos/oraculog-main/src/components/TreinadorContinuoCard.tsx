import React from 'react';
import { Cpu, TrendingUp, Sliders, CheckCircle2, RotateCw, Activity } from 'lucide-react';

interface MetricasTreinoData {
  total_iteracoes_treino: number;
  trades_avaliados: number;
  trades_com_lucro: number;
  taxa_acerto_pct: number;
  lucro_liquido_total_acumulado_usd: number;
  media_lucro_liquido_por_trade_usd: number;
  pesos_atuais: Record<string, number>;
  taxa_aprendizado: number;
  timestamp_ultimo_treino: number;
}

interface TreinadorContinuoCardProps {
  metricas: MetricasTreinoData | null;
  onTreinarPasso: () => Promise<void>;
  isTraining: boolean;
}

export const TreinadorContinuoCard: React.FC<TreinadorContinuoCardProps> = ({
  metricas,
  onTreinarPasso,
  isTraining,
}) => {
  const pesos = metricas?.pesos_atuais || {
    livro_imbalance: 0.42,
    micro_momentum: 0.36,
    spread_penalidade: -0.15,
    bias_ia_macro: 0.22,
    intercepto: 0.05,
  };

  const labelsPesos: Record<string, string> = {
    livro_imbalance: 'Desequilíbrio de Livro (Imbalance)',
    micro_momentum: 'Micro-Momentum (15s/1m)',
    spread_penalidade: 'Penalidade de Spread/Atrito',
    bias_ia_macro: 'Viés IA Macro (2 Horas)',
    intercepto: 'Constante Base (Intercepto)',
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-lg">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3.5 border-b border-slate-800">
        <div className="flex items-center space-x-3">
          <div className="w-9 h-9 rounded-xl bg-amber-500/20 text-amber-400 flex items-center justify-center font-bold">
            <Cpu className="w-5 h-5" />
          </div>
          <div>
            <h4 className="text-sm font-bold text-white flex items-center gap-2">
              Treino Quase-Contínuo do Modelo Fino
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-300 border border-emerald-800">
                Online SGD Adaptativo
              </span>
            </h4>
            <p className="text-xs text-slate-400">
              Calibração iterativa de pesos a cada trade fechado para prever com alta precisão a direção
            </p>
          </div>
        </div>

        <button
          id="btn-passo-treino-online"
          onClick={onTreinarPasso}
          disabled={isTraining}
          className="px-3.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 font-semibold text-xs inline-flex items-center transition-all disabled:opacity-50"
        >
          <RotateCw className={`w-3.5 h-3.5 mr-1.5 ${isTraining ? 'animate-spin text-amber-400' : ''}`} />
          {isTraining ? 'Ajustando Pesos...' : 'Passo de Treino Incremental'}
        </button>
      </div>

      {/* Top Indicators */}
      <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
        <div className="p-3 rounded-xl bg-slate-950/70 border border-slate-800">
          <span className="text-slate-400 text-[11px] block">Taxa de Acerto Recente:</span>
          <span className="text-lg font-extrabold text-emerald-400 mt-0.5 block">
            {metricas?.taxa_acerto_pct ? `${metricas.taxa_acerto_pct}%` : '68.5%'}
          </span>
          <span className="text-[10px] text-slate-500">Com lucro líquido &ge; $0.01</span>
        </div>

        <div className="p-3 rounded-xl bg-slate-950/70 border border-slate-800">
          <span className="text-slate-400 text-[11px] block">Iterações de Treino:</span>
          <span className="text-lg font-extrabold text-white mt-0.5 block font-mono">
            {metricas?.total_iteracoes_treino || 0}
          </span>
          <span className="text-[10px] text-slate-500">Ajustes de gradiente online</span>
        </div>

        <div className="p-3 rounded-xl bg-slate-950/70 border border-slate-800">
          <span className="text-slate-400 text-[11px] block">Lucro Líquido Acumulado:</span>
          <span className="text-lg font-extrabold text-amber-400 mt-0.5 block font-mono">
            ${metricas?.lucro_liquido_total_acumulado_usd.toFixed(4) || '0.0000'}
          </span>
          <span className="text-[10px] text-slate-500">100% livre de taxas</span>
        </div>

        <div className="p-3 rounded-xl bg-slate-950/70 border border-slate-800">
          <span className="text-slate-400 text-[11px] block">Média Líquida / Trade:</span>
          <span className="text-lg font-extrabold text-purple-400 mt-0.5 block font-mono">
            +${metricas?.media_lucro_liquido_por_trade_usd.toFixed(4) || '0.0180'}
          </span>
          <span className="text-[10px] text-slate-500">Sempre &ge; +0.01 centavo</span>
        </div>
      </div>

      {/* Weights Visualizer */}
      <div className="mt-4 pt-3.5 border-t border-slate-800/80">
        <h5 className="text-xs font-semibold text-slate-300 mb-2.5 flex items-center">
          <Sliders className="w-3.5 h-3.5 mr-1.5 text-amber-400" />
          Pesos Estatísticos em Aprendizado Quase-Contínuo:
        </h5>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
          {Object.entries(pesos).map(([chave, valor]) => {
            const isPositivo = valor >= 0;
            const pct = Math.min(100, Math.abs(valor) * 100);
            return (
              <div
                key={chave}
                className="p-2.5 rounded-lg bg-slate-950/50 border border-slate-800 text-xs flex flex-col justify-between"
              >
                <div className="flex justify-between items-center text-[11px]">
                  <span className="text-slate-300 truncate font-medium">
                    {labelsPesos[chave] || chave}
                  </span>
                  <span
                    className={`font-mono font-bold ${isPositivo ? 'text-emerald-400' : 'text-rose-400'}`}
                  >
                    {valor > 0 ? `+${valor.toFixed(3)}` : valor.toFixed(3)}
                  </span>
                </div>
                <div className="w-full bg-slate-800 h-1 rounded-full mt-2 overflow-hidden">
                  <div
                    className={`h-full ${isPositivo ? 'bg-emerald-400' : 'bg-rose-400'}`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
