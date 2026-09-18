import React from 'react';
import { FileText, CheckCircle2, TrendingUp, TrendingDown, DollarSign } from 'lucide-react';

export interface TradeHistoricoItem {
  id: number;
  timestamp: number;
  par: string;
  direcao: string;
  preco_entrada: number;
  preco_saida: number;
  tamanho: number;
  valor_nocional: number;
  lucro_bruto_usd: number;
  taxas_totais_usd: number;
  lucro_liquido_usd: number;
  regra_001_satisfeita: number;
  motivo?: string;
  status: string;
}

interface TradesHistoricoTableProps {
  trades: TradeHistoricoItem[];
}

export const TradesHistoricoTable: React.FC<TradesHistoricoTableProps> = ({ trades }) => {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-lg">
      <div className="p-4 bg-slate-950/60 border-b border-slate-800 flex items-center justify-between">
        <div>
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-200 flex items-center">
            <FileText className="w-3.5 h-3.5 mr-2 text-amber-400" />
            Auditoria de Ordens e Prova de Lucro Líquido Real (+0,01)
          </h4>
          <p className="text-[11px] text-slate-400 mt-0.5">
            Histórico registrado no banco de dados SQLite com dedução exata das taxas da Binance
          </p>
        </div>
        <span className="text-xs font-mono text-emerald-400 font-semibold bg-emerald-950/60 px-2.5 py-1 rounded-md border border-emerald-800/80">
          {trades.length} Trades Registrados
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="bg-slate-950/40 text-slate-400 border-b border-slate-800 text-[11px] uppercase tracking-wider">
            <tr>
              <th className="py-2.5 px-4">Par / Data</th>
              <th className="py-2.5 px-3">Direção</th>
              <th className="py-2.5 px-3">Preço Entrada / Alvo</th>
              <th className="py-2.5 px-3">Valor Nocional</th>
              <th className="py-2.5 px-3">Lucro Bruto</th>
              <th className="py-2.5 px-3">Taxas Binance</th>
              <th className="py-2.5 px-3">Lucro Líquido</th>
              <th className="py-2.5 px-4 text-center">Regra +0,01 Centavo</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/80 text-slate-300">
            {trades.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-8 text-center text-slate-500 text-xs">
                  Nenhum trade executado ainda. Inicie o ciclo rápido ou aguarde os filtros de edge líquido positivo.
                </td>
              </tr>
            ) : (
              trades.map((trade) => {
                const isBuy = trade.direcao.toUpperCase() === 'COMPRA' || trade.direcao.toUpperCase() === 'BUY';
                const dateStr = new Date(trade.timestamp * 1000).toLocaleTimeString('pt-BR');
                const cumpriuRegra = trade.lucro_liquido_usd >= 0.01;

                return (
                  <tr key={trade.id} className="hover:bg-slate-800/40 transition-colors">
                    <td className="py-3 px-4">
                      <div className="font-bold text-white text-xs">{trade.par}</div>
                      <div className="text-[10px] text-slate-500 font-mono">{dateStr}</div>
                    </td>

                    <td className="py-3 px-3">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-extrabold ${
                          isBuy
                            ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                            : 'bg-rose-950 text-rose-400 border border-rose-800'
                        }`}
                      >
                        {isBuy ? <TrendingUp className="w-3 h-3 mr-1" /> : <TrendingDown className="w-3 h-3 mr-1" />}
                        {trade.direcao}
                      </span>
                    </td>

                    <td className="py-3 px-3 font-mono text-[11px]">
                      <div className="text-slate-200">${trade.preco_entrada.toFixed(4)}</div>
                      <div className="text-amber-400 text-[10px]">Alvo: ${trade.preco_saida.toFixed(4)}</div>
                    </td>

                    <td className="py-3 px-3 font-mono text-[11px] text-slate-300">
                      ${trade.valor_nocional.toFixed(2)}
                    </td>

                    <td className="py-3 px-3 font-mono text-[11px] text-slate-200">
                      +${trade.lucro_bruto_usd.toFixed(4)}
                    </td>

                    <td className="py-3 px-3 font-mono text-[11px] text-rose-400">
                      -${trade.taxas_totais_usd.toFixed(4)}
                    </td>

                    <td className="py-3 px-3 font-mono text-xs font-bold text-emerald-400">
                      +${trade.lucro_liquido_usd.toFixed(4)}
                    </td>

                    <td className="py-3 px-4 text-center">
                      {cumpriuRegra ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-950/80 text-emerald-300 border border-emerald-800">
                          <CheckCircle2 className="w-3 h-3 mr-1 text-emerald-400" />
                          Líquido &ge; +$0,01
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-950/80 text-rose-300 border border-rose-800">
                          Bloqueado
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
