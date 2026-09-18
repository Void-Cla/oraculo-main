import React, { useState } from 'react';
import { 
  Activity, 
  TrendingDown, 
  TrendingUp, 
  Clock, 
  Sliders, 
  Bot, 
  CheckCircle, 
  AlertCircle,
  FileSpreadsheet
} from 'lucide-react';
import { LOG_METRICS_EXTRACTED } from '../data/analyzedProjectData';

export const LogsAnalysisTab: React.FC = () => {
  const [selectedLogIndex, setSelectedLogIndex] = useState(0);
  const currentLog = LOG_METRICS_EXTRACTED[selectedLogIndex];

  return (
    <div className="space-y-8">
      <div>
        <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 text-xs font-semibold mb-2">
          <Activity className="w-3.5 h-3.5" />
          Telemetria Operacional Real
        </div>
        <h3 className="text-xl font-bold text-white tracking-tight">
          Análise Detalhada dos Logs de Decisão (log.txt)
        </h3>
        <p className="text-xs sm:text-sm text-slate-300 mt-1 max-w-3xl">
          Dados extraídos diretamente do arquivo <code className="text-amber-400 font-mono text-xs">log.txt</code> da pasta do Drive. O motor híbrido avalia pares em paralelo gerando scores normalizados e aplicando travas de risco.
        </p>
      </div>

      {/* Real-Time Decision Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Decisions Table / List */}
        <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-lg">
          <div className="p-4 bg-slate-950/60 border-b border-slate-800 flex items-center justify-between">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center">
              <FileSpreadsheet className="w-3.5 h-3.5 mr-2 text-amber-400" />
              Sinais e Ordens Recentes Registradas
            </h4>
            <span className="text-[11px] text-slate-500 font-mono">Timestamp: 2026-09-13 01:34:17 UTC</span>
          </div>

          <div className="divide-y divide-slate-800/80">
            {LOG_METRICS_EXTRACTED.map((log, idx) => {
              const isSelected = selectedLogIndex === idx;
              const isBuy = log.action === 'BUY';
              return (
                <button
                  key={idx}
                  id={`btn-log-item-${idx}`}
                  onClick={() => setSelectedLogIndex(idx)}
                  className={`w-full p-4 flex items-center justify-between text-left transition-all ${
                    isSelected 
                      ? 'bg-amber-500/10 border-l-4 border-amber-500 text-white' 
                      : 'hover:bg-slate-800/50 text-slate-300'
                  }`}
                >
                  <div className="flex items-center space-x-3">
                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center font-bold text-xs ${
                      isBuy 
                        ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' 
                        : 'bg-rose-950 text-rose-400 border border-rose-800'
                    }`}>
                      {isBuy ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
                    </div>
                    <div>
                      <div className="flex items-center space-x-2">
                        <span className="font-bold text-sm text-slate-100">{log.symbol}</span>
                        <span className={`text-[10px] font-extrabold px-2 py-0.5 rounded-full ${
                          isBuy ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'
                        }`}>
                          {log.action}
                        </span>
                      </div>
                      <p className="text-xs text-slate-400 mt-0.5 line-clamp-1">{log.motivo}</p>
                    </div>
                  </div>

                  <div className="text-right">
                    <span className="font-mono text-xs font-semibold block text-slate-200">
                      Score: {log.scoreFinal > 0 ? `+${log.scoreFinal.toFixed(3)}` : log.scoreFinal.toFixed(3)}
                    </span>
                    <span className="text-[10px] text-slate-500">
                      Confiança: {(log.confianca * 100).toFixed(0)}%
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Selected Log Detail Inspector */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between pb-3.5 border-b border-slate-800">
              <div>
                <span className="text-xs text-slate-500">Análise de Decisão</span>
                <h4 className="text-base font-bold text-white flex items-center">
                  {currentLog.symbol}
                  <span className={`ml-2 text-xs px-2 py-0.5 rounded font-bold ${
                    currentLog.action === 'BUY' ? 'bg-emerald-950 text-emerald-400' : 'bg-rose-950 text-rose-400'
                  }`}>
                    {currentLog.action}
                  </span>
                </h4>
              </div>
              <div className="text-right font-mono text-xs">
                <span className="text-slate-500 block text-[10px]">Tamanho</span>
                <span className="text-amber-400 font-bold">{currentLog.tamanho.toFixed(4)} un.</span>
              </div>
            </div>

            <div className="mt-5 space-y-4 text-xs">
              {/* Score Breakdown Bar */}
              <div>
                <div className="flex justify-between text-[11px] text-slate-400 mb-1">
                  <span>Score Numérico vs IA</span>
                  <span className="font-mono font-bold text-white">Final: {currentLog.scoreFinal.toFixed(3)}</span>
                </div>
                <div className="grid grid-cols-2 gap-2 text-center text-[10px]">
                  <div className="p-2 rounded-lg bg-slate-950 border border-slate-800">
                    <span className="text-slate-500 block">Modelo Quant (Peso ~80%)</span>
                    <span className="text-amber-400 font-bold font-mono text-xs mt-0.5 block">
                      {currentLog.scoreNumerico.toFixed(3)}
                    </span>
                  </div>
                  <div className="p-2 rounded-lg bg-slate-950 border border-slate-800">
                    <span className="text-slate-500 block">LLM / Sentimento (Peso ~20%)</span>
                    <span className="text-purple-400 font-bold font-mono text-xs mt-0.5 block">
                      {currentLog.scoreLlm > 0 ? `+${currentLog.scoreLlm.toFixed(3)}` : currentLog.scoreLlm.toFixed(3)}
                    </span>
                  </div>
                </div>
              </div>

              {/* Logic Explanation */}
              <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800/80">
                <div className="flex items-center text-xs font-semibold text-slate-300 mb-1">
                  <Bot className="w-3.5 h-3.5 mr-1.5 text-amber-400" />
                  Racional da Decisão Registrada:
                </div>
                <p className="text-xs text-slate-400 leading-relaxed">
                  O bot calculou score quantitativo extremo de <code className="text-amber-300">{currentLog.scoreNumerico}</code>. A camada de IA validou o contexto de livro e notícias sem gerar veto. O EV calculado atendeu aos critérios para emissão da ordem.
                </p>
              </div>

              {/* Performance Latency Note */}
              <div className="p-3 rounded-xl bg-emerald-950/20 border border-emerald-800/30 flex items-start space-x-2">
                <CheckCircle className="w-3.5 h-3.5 text-emerald-400 mt-0.5 flex-shrink-0" />
                <p className="text-[11px] text-emerald-300">
                  <strong>Latência:</strong> O cálculo completo de 5 pares levou apenas <strong>34 milissegundos</strong> no log, sem bloqueios de rede.
                </p>
              </div>
            </div>
          </div>

          <div className="mt-6 pt-3 border-t border-slate-800 text-[10px] text-slate-500 flex items-center justify-between">
            <span>Fonte: log.txt (logger: decisor_hibrido)</span>
            <span>TaskName: Task-738</span>
          </div>
        </div>
      </div>
    </div>
  );
};
