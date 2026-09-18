import React from 'react';
import { Scale, CheckCircle2, AlertTriangle, ShieldCheck, DollarSign, Percent } from 'lucide-react';

interface RegraLucroLiquidoCardProps {
  lucroMinimoUsd?: number;
}

export const RegraLucroLiquidoCard: React.FC<RegraLucroLiquidoCardProps> = ({
  lucroMinimoUsd = 0.01
}) => {
  return (
    <div className="bg-slate-900/90 border border-emerald-500/30 rounded-2xl p-5 shadow-lg relative overflow-hidden">
      <div className="absolute -right-8 -top-8 w-32 h-32 bg-emerald-500/10 rounded-full blur-2xl pointer-events-none" />

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-800">
        <div className="flex items-center space-x-2.5">
          <div className="w-9 h-9 rounded-xl bg-emerald-500/20 text-emerald-400 flex items-center justify-center font-bold">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div>
            <h4 className="text-sm font-bold text-white flex items-center gap-1.5">
              Regra Mandatória de Lucro Líquido Real
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-300 border border-emerald-800">
                +${lucroMinimoUsd.toFixed(2)} USD Mínimo
              </span>
            </h4>
            <p className="text-xs text-slate-400">
              Nenhuma ordem é autorizada sem cobrir 100% das taxas da exchange + 0,01 centavo líquido
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-3 text-xs">
          <div className="bg-slate-950/80 px-3 py-1.5 rounded-lg border border-slate-800 text-slate-300">
            <span className="text-slate-500 text-[10px] block">Taxa Binance Round-Trip:</span>
            <span className="font-mono font-bold text-amber-400">0.20% (ou 0.15% BNB)</span>
          </div>
          <div className="bg-slate-950/80 px-3 py-1.5 rounded-lg border border-slate-800 text-slate-300">
            <span className="text-slate-500 text-[10px] block">Tolerância de Slippage:</span>
            <span className="font-mono font-bold text-purple-400">0.03% fixado</span>
          </div>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
        <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/80">
          <span className="text-[11px] font-semibold text-slate-400 block mb-1">1. Projeção de Janela Rápida</span>
          <p className="text-slate-300 text-[11px] leading-relaxed">
            O motor local calcula a volatilidade ATR e o book imbalance para estimar a oscilação mínima favorável antes da entrada.
          </p>
        </div>

        <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/80">
          <span className="text-[11px] font-semibold text-rose-400 block mb-1">2. Dedução Total de Custos</span>
          <p className="text-slate-300 text-[11px] leading-relaxed">
            <code className="text-rose-300 font-mono">Taxas = (Entrada × 0.10%) + (Saída × 0.10%) + Slippage</code>. Tudo descontado antes da autorização.
          </p>
        </div>

        <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/80">
          <span className="text-[11px] font-semibold text-emerald-400 block mb-1">3. Gate de Autorização</span>
          <p className="text-slate-300 text-[11px] leading-relaxed">
            Se <code className="text-emerald-300 font-mono">Lucro_Bruto - Taxas &lt; $0.01</code>, o trade é <strong>automaticamente bloqueado</strong> pelo Guardião.
          </p>
        </div>
      </div>
    </div>
  );
};
