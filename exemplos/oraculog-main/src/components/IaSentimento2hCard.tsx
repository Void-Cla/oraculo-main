import React, { useState, useEffect } from 'react';
import { Sparkles, Clock, RefreshCw, TrendingUp, TrendingDown, Layers, AlertCircle, CheckCircle } from 'lucide-react';

interface IaSentimento2hData {
  timestamp_ultima_analise: number;
  timestamp_proxima_analise: number;
  peso_noticias_ia: number;
  bias_macro_direcional: number;
  regime_mercado: string;
  intensidade_impacto_noticias: string;
  resumo_executivo_ptbr: string;
  fatores_chave: string[];
  modelo_utilizado?: string;
}

interface IaSentimento2hCardProps {
  dadosIa: IaSentimento2hData | null;
  onForcarAtualizacao: () => Promise<void>;
  isUpdating: boolean;
}

export const IaSentimento2hCard: React.FC<IaSentimento2hCardProps> = ({
  dadosIa,
  onForcarAtualizacao,
  isUpdating,
}) => {
  const [tempoRestante, setTempoRestante] = useState<string>('02:00:00');

  useEffect(() => {
    const timer = setInterval(() => {
      if (!dadosIa?.timestamp_proxima_analise) return;
      const agora = Date.now() / 1000;
      const diff = Math.max(0, Math.floor(dadosIa.timestamp_proxima_analise - agora));
      const horas = Math.floor(diff / 3600);
      const minutos = Math.floor((diff % 3600) / 60);
      const segundos = diff % 60;
      setTempoRestante(
        `${String(horas).padStart(2, '0')}:${String(minutos).padStart(2, '0')}:${String(segundos).padStart(2, '0')}`
      );
    }, 1000);
    return () => clearInterval(timer);
  }, [dadosIa?.timestamp_proxima_analise]);

  const pesoLocalPct = Math.round((1 - (dadosIa?.peso_noticias_ia || 0.18)) * 100);
  const pesoIaPct = Math.round((dadosIa?.peso_noticias_ia || 0.18) * 100);
  const bias = dadosIa?.bias_macro_direcional || 0.15;
  const isBullish = bias > 0;

  return (
    <div className="bg-slate-900 border border-purple-500/30 rounded-2xl p-5 shadow-lg relative overflow-hidden">
      <div className="absolute -right-8 -bottom-8 w-36 h-36 bg-purple-500/10 rounded-full blur-2xl pointer-events-none" />

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3.5 border-b border-slate-800">
        <div className="flex items-center space-x-3">
          <div className="w-9 h-9 rounded-xl bg-purple-500/20 text-purple-400 flex items-center justify-center font-bold">
            <Sparkles className="w-5 h-5" />
          </div>
          <div>
            <h4 className="text-sm font-bold text-white flex items-center gap-2">
              Sentimento Macro e Notícias por IA (Janela de 2 Horas)
              <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-purple-950 text-purple-300 border border-purple-800">
                Gemini 3.8 Flash
              </span>
            </h4>
            <p className="text-xs text-slate-400">
              Define o peso diário das notícias a cada 2h para manter o motor local em altíssima velocidade
            </p>
          </div>
        </div>

        {/* 2-hour countdown badge & refresh button */}
        <div className="flex items-center space-x-2">
          <div className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono">
            <Clock className="w-3.5 h-3.5 text-purple-400 animate-pulse" />
            <span className="text-slate-400 text-[11px]">Próximo ciclo:</span>
            <span className="text-purple-300 font-bold">{tempoRestante}</span>
          </div>

          <button
            id="btn-recalibrar-ia-2h"
            onClick={onForcarAtualizacao}
            disabled={isUpdating}
            className="px-3 py-1.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-semibold text-xs inline-flex items-center shadow-md shadow-purple-600/20 transition-all disabled:opacity-50"
            title="Atualizar análise macro de 2 horas agora via Gemini"
          >
            <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${isUpdating ? 'animate-spin' : ''}`} />
            {isUpdating ? 'Calibrando...' : 'Calibrar Agora'}
          </button>
        </div>
      </div>

      {/* Metric Breakdown */}
      <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
        {/* Card 1: Distribuição de Pesos */}
        <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800">
          <span className="text-slate-400 text-[11px] block">Equilíbrio de Decisão:</span>
          <div className="mt-1 flex items-baseline justify-between">
            <span className="text-sm font-bold text-slate-100">{pesoLocalPct}% Motor Local</span>
            <span className="text-xs font-semibold text-purple-400">{pesoIaPct}% IA Notícias</span>
          </div>
          <div className="mt-2 w-full h-1.5 bg-slate-800 rounded-full overflow-hidden flex">
            <div className="bg-amber-400 h-full" style={{ width: `${pesoLocalPct}%` }} />
            <div className="bg-purple-500 h-full" style={{ width: `${pesoIaPct}%` }} />
          </div>
        </div>

        {/* Card 2: Viés Direcional Macro */}
        <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800">
          <span className="text-slate-400 text-[11px] block">Viés Macro Definido:</span>
          <div className="mt-1 flex items-center space-x-1.5">
            {isBullish ? (
              <TrendingUp className="w-4 h-4 text-emerald-400" />
            ) : (
              <TrendingDown className="w-4 h-4 text-rose-400" />
            )}
            <span className={`text-sm font-bold ${isBullish ? 'text-emerald-400' : 'text-rose-400'}`}>
              {bias > 0 ? `+${bias.toFixed(2)}` : bias.toFixed(2)}
            </span>
            <span className="text-[10px] text-slate-400 ml-1">
              ({isBullish ? 'Comprador' : 'Vendedor'})
            </span>
          </div>
          <span className="text-[10px] text-slate-500 block mt-1">Escala de -1.0 a +1.0</span>
        </div>

        {/* Card 3: Regime de Mercado */}
        <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800">
          <span className="text-slate-400 text-[11px] block">Regime de Mercado (2h):</span>
          <span className="text-xs font-bold text-white mt-1 block truncate">
            {dadosIa?.regime_mercado || 'LATERALIZADO_ACUMULACAO'}
          </span>
          <span className="text-[10px] text-slate-400 mt-1 block">
            Impacto: <strong className="text-amber-400">{dadosIa?.intensidade_impacto_noticias || 'MEDIO'}</strong>
          </span>
        </div>

        {/* Card 4: Fatores Principais */}
        <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800">
          <span className="text-slate-400 text-[11px] block mb-1">Garantia Operacional:</span>
          <span className="text-emerald-400 font-bold text-xs flex items-center">
            <CheckCircle className="w-3.5 h-3.5 mr-1" /> Motor Local Não Trava
          </span>
          <p className="text-[10px] text-slate-400 mt-1">
            Se a IA oscilar, o cache de 2h garante micro-scalping sem interrupções.
          </p>
        </div>
      </div>

      {/* AI Summary Text & Factors */}
      {dadosIa?.resumo_executivo_ptbr && (
        <div className="mt-4 p-3.5 rounded-xl bg-slate-950/60 border border-slate-800/90 text-xs">
          <div className="flex items-center text-purple-300 font-semibold mb-1">
            <Sparkles className="w-3.5 h-3.5 mr-1.5" />
            Síntese da Análise de 2 Horas pelo Gemini:
          </div>
          <p className="text-slate-300 leading-relaxed text-[12px]">
            {dadosIa.resumo_executivo_ptbr}
          </p>

          {dadosIa.fatores_chave && dadosIa.fatores_chave.length > 0 && (
            <div className="mt-2.5 flex flex-wrap gap-1.5 pt-2 border-t border-slate-800/80">
              {dadosIa.fatores_chave.map((fator, idx) => (
                <span
                  key={idx}
                  className="px-2.5 py-1 rounded-md bg-purple-950/40 text-purple-300 border border-purple-800/50 text-[11px]"
                >
                  • {fator}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
