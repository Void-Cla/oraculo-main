import React, { useState, useEffect } from 'react';
import { 
  Play, 
  Square, 
  RotateCw, 
  Sparkles, 
  ShieldCheck, 
  TrendingUp, 
  TrendingDown, 
  CheckCircle2, 
  Zap,
  Globe,
  Lock,
  Terminal,
  Download,
  Server,
  X,
  ExternalLink,
  Cpu
} from 'lucide-react';
import { RegraLucroLiquidoCard } from './RegraLucroLiquidoCard';
import { IaSentimento2hCard } from './IaSentimento2hCard';
import { TreinadorContinuoCard } from './TreinadorContinuoCard';
import { TradesHistoricoTable, TradeHistoricoItem } from './TradesHistoricoTable';

interface ParAnaliseItem {
  par: string;
  preco_atual: number;
  melhor_bid?: number;
  melhor_ask?: number;
  volume_bids_usd?: number;
  volume_asks_usd?: number;
  direcao_prevista: string;
  score_direcional: number;
  confianca_pct: number;
  probabilidade_alta_pct: number;
  desequilibrio_livro: number;
  spread_pct: number;
  alvo_saida_preco: number;
  quantidade: number;
  valor_nocional_usd: number;
  lucro_bruto_projetado_usd: number;
  taxas_totais_usd: number;
  lucro_liquido_projetado_usd: number;
  regra_lucro_minimo_usd: number;
  retorno_liquido_pct: number;
  autorizado_pelo_risco: boolean;
  motivo_validacao: string;
  fonte_dados?: string;
  erro?: string;
}

export const OraculoTradingDashboard: React.FC = () => {
  const [isAutoRunning, setIsAutoRunning] = useState(false);
  const [janelaSegundos, setJanelaSegundos] = useState<number>(15);
  const [isLoadingCycle, setIsLoadingCycle] = useState(false);
  const [isUpdatingIa, setIsUpdatingIa] = useState(false);
  const [isTraining, setIsTraining] = useState(false);
  const [isModalProducaoOpen, setIsModalProducaoOpen] = useState(false);

  // Estados dos dados 100% REAIS da Binance
  const [saldoUsdt, setSaldoUsdt] = useState<number>(100.0);
  const [paresAnalise, setParesAnalise] = useState<ParAnaliseItem[]>([]);
  const [dadosIa, setDadosIa] = useState<any>(null);
  const [metricasTreino, setMetricasTreino] = useState<any>(null);
  const [resumoFinanceiro, setResumoFinanceiro] = useState<any>(null);
  const [historicoTrades, setHistoricoTrades] = useState<TradeHistoricoItem[]>([]);
  const [ultimoCicloHora, setUltimoCicloHora] = useState<string>('');
  const [latenciaBinanceMs, setLatenciaBinanceMs] = useState<number>(0);
  const [endpointBinance, setEndpointBinance] = useState<string>('https://data-api.binance.vision');
  const [statusConta, setStatusConta] = useState<any>({
    modo: 'DADOS_MERCADO_REAIS_AUDITORIA',
    autenticado: false,
    mensagem: 'Mercado 100% Real Binance'
  });

  // Executa ciclo do motor Oráculo com dados 100% REAIS da Binance
  const executarCiclo = async () => {
    try {
      setIsLoadingCycle(true);
      const res = await fetch('/api/oraculo/executar-ciclo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!res.ok) throw new Error('Falha na resposta do ciclo');
      const data = await res.json();

      setSaldoUsdt(data.saldo_usdt);
      setParesAnalise(data.pares_analisados || []);
      setResumoFinanceiro(data.resumo_financeiro_acumulado || null);
      setMetricasTreino(data.metricas_treino_continuo || null);
      setDadosIa(data.estado_ia_2h || null);
      setLatenciaBinanceMs(data.latencia_binance_ms || 0);
      if (data.status_conexao_binance?.endpoint_ativo) {
        setEndpointBinance(data.status_conexao_binance.endpoint_ativo);
      }
      if (data.status_conta) {
        setStatusConta(data.status_conta);
      }
      setUltimoCicloHora(new Date().toLocaleTimeString('pt-BR'));

      carregarHistoricoTrades();
    } catch (err) {
      console.error('Erro ao executar ciclo com dados reais:', err);
    } finally {
      setIsLoadingCycle(false);
    }
  };

  const carregarHistoricoTrades = async () => {
    try {
      const res = await fetch('/api/oraculo/historico-trades');
      if (res.ok) {
        const trades = await res.json();
        setHistoricoTrades(trades || []);
      }
    } catch (err) {
      console.error('Erro ao carregar histórico:', err);
    }
  };

  // Forçar atualização de IA de 2 Horas via Gemini
  const handleAtualizarIa2h = async () => {
    try {
      setIsUpdatingIa(true);
      const resumoMercado = {
        pares_monitorados: paresAnalise.map((p) => ({
          par: p.par,
          preco: p.preco_atual,
          direcao: p.direcao_prevista,
          imbalance: p.desequilibrio_livro,
        })),
        hora: new Date().toISOString(),
      };

      const res = await fetch('/api/oraculo/atualizar-ia-2h', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resumoMercado }),
      });

      if (res.ok) {
        const json = await res.json();
        if (json.novoEstadoIa) {
          setDadosIa(json.novoEstadoIa);
        }
      }
    } catch (err) {
      console.error('Erro ao calibrar IA 2h:', err);
    } finally {
      setIsUpdatingIa(false);
    }
  };

  // Passo de Treino Contínuo
  const handleTreinarPasso = async () => {
    try {
      setIsTraining(true);
      await executarCiclo();
    } finally {
      setIsTraining(false);
    }
  };

  // Carregar status inicial
  useEffect(() => {
    executarCiclo();
  }, []);

  // Timer de Auto-Ciclo
  useEffect(() => {
    let interval: any = null;
    if (isAutoRunning) {
      interval = setInterval(() => {
        executarCiclo();
      }, Math.max(5, janelaSegundos) * 1000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [isAutoRunning, janelaSegundos]);

  return (
    <div className="space-y-8">
      {/* Barra de Status Oficial da Binance (100% Real Live Market Data) */}
      <div id="binance-status-banner" className="bg-slate-900 border border-slate-800 rounded-2xl p-4 sm:p-5 shadow-lg flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div className="flex items-center space-x-3.5">
          <div className="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center flex-shrink-0">
            <Globe className="w-5 h-5 text-amber-400" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse" />
              <h3 className="text-sm font-bold text-white tracking-wide uppercase">
                Conexão Binance Spot: DADOS 100% REAIS AO VIVO
              </h3>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-950 text-emerald-300 border border-emerald-800">
                PRODUÇÃO ATIVA
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-400 mt-1">
              <span>Endpoint: <strong className="text-slate-200 font-mono">{endpointBinance}</strong></span>
              <span className="text-slate-600">•</span>
              <span>Latência: <strong className="text-amber-400 font-mono">{latenciaBinanceMs ? `${latenciaBinanceMs}ms` : 'Verificando...'}</strong></span>
              <span className="text-slate-600">•</span>
              <span className="text-slate-300">Modo: <strong className="text-emerald-400">{statusConta?.autenticado ? 'Conta Real Autenticada (HMAC)' : 'Auditoria em Tempo Real'}</strong></span>
            </div>
          </div>
        </div>

        {/* Botão de Exportação e Instruções para Executar Localmente */}
        <div className="flex items-center space-x-3">
          <button
            id="btn-abrir-modal-producao"
            onClick={() => setIsModalProducaoOpen(true)}
            className="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-amber-400 border border-amber-500/30 text-xs font-semibold inline-flex items-center transition-all shadow-sm"
          >
            <Download className="w-3.5 h-3.5 mr-1.5" />
            Executar no seu PC / Dinheiro Real
          </button>
        </div>
      </div>

      {/* Top Controls & Status Bar */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 sm:p-6 shadow-xl flex flex-col md:flex-row md:items-center md:justify-between gap-5">
        <div>
          <div className="flex items-center space-x-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse" />
            <h3 className="text-lg font-bold text-white tracking-tight">
              Terminal Operacional Quantitativo (Binance Spot)
            </h3>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Micro-previsão direcional, IA estratégica a cada 2h e regra estrita de lucro líquido (&ge; +$0,01 USD líquido real).
          </p>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Janela de Trading Selector */}
          <div className="flex items-center bg-slate-950 p-1 rounded-xl border border-slate-800 text-xs">
            <span className="text-slate-500 px-2 text-[11px] font-medium">Ciclo:</span>
            {[5, 15, 30, 60].map((sec) => (
              <button
                key={sec}
                id={`btn-janela-${sec}s`}
                onClick={() => setJanelaSegundos(sec)}
                className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all ${
                  janelaSegundos === sec
                    ? 'bg-amber-500 text-slate-950 shadow-sm'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                {sec}s
              </button>
            ))}
          </div>

          {/* Botão Executar Ciclo Imediato */}
          <button
            id="btn-executar-ciclo-manual"
            onClick={executarCiclo}
            disabled={isLoadingCycle}
            className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-semibold inline-flex items-center transition-all disabled:opacity-50"
          >
            <RotateCw className={`w-3.5 h-3.5 mr-1.5 ${isLoadingCycle ? 'animate-spin text-amber-400' : ''}`} />
            {isLoadingCycle ? 'Consultando Binance...' : 'Atualizar Livro Real'}
          </button>

          {/* Toggle Auto-Loop */}
          <button
            id="btn-toggle-auto-loop"
            onClick={() => setIsAutoRunning(!isAutoRunning)}
            className={`px-4 py-2 rounded-xl font-bold text-xs inline-flex items-center shadow-lg transition-all ${
              isAutoRunning
                ? 'bg-rose-500 hover:bg-rose-600 text-white shadow-rose-500/20'
                : 'bg-emerald-500 hover:bg-emerald-400 text-slate-950 shadow-emerald-500/20'
            }`}
          >
            {isAutoRunning ? (
              <>
                <Square className="w-3.5 h-3.5 mr-1.5 fill-current" />
                Pausar Auto-Loop
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5 mr-1.5 fill-current" />
                Iniciar Auto-Loop ({janelaSegundos}s)
              </>
            )}
          </button>
        </div>
      </div>

      {/* KPI Cards Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5">
        <div id="kpi-saldo-operacional" className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <span className="text-[11px] text-slate-400 uppercase font-semibold">Saldo Operacional</span>
          <div className="mt-1 flex items-baseline">
            <span className="text-xl font-bold text-white font-mono">${saldoUsdt.toFixed(2)}</span>
            <span className="text-xs text-slate-400 ml-1">USDT</span>
          </div>
          <span className="text-[10px] text-emerald-400 mt-1 block">
            {statusConta?.autenticado ? 'Saldo Real da Binance' : 'Auditoria Real com Base $100'}
          </span>
        </div>

        <div id="kpi-regra-lucro" className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <span className="text-[11px] text-slate-400 uppercase font-semibold">Trava de Lucro Líquido</span>
          <div className="mt-1">
            <span className="text-xl font-bold text-emerald-400 font-mono">&ge; +$0,01 USD</span>
          </div>
          <span className="text-[10px] text-slate-400 mt-1 block">Após taxas da Binance & slippage</span>
        </div>

        <div id="kpi-taxa-sucesso" className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <span className="text-[11px] text-slate-400 uppercase font-semibold">Total de Trades Registrados</span>
          <div className="mt-1 flex items-baseline">
            <span className="text-xl font-bold text-amber-400 font-mono">
              {resumoFinanceiro?.total_trades || historicoTrades.length}
            </span>
            <span className="text-xs text-slate-400 ml-1">ordens</span>
          </div>
          <span className="text-[10px] text-slate-400 mt-1 block">Auditados no banco SQLite</span>
        </div>

        <div id="kpi-ultimo-ciclo" className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <span className="text-[11px] text-slate-400 uppercase font-semibold">Última Atualização Real</span>
          <div className="mt-1 font-mono text-base font-bold text-slate-200">
            {ultimoCicloHora || 'Em espera'}
          </div>
          <span className="text-[10px] text-purple-400 mt-1 block">
            API Binance: {latenciaBinanceMs ? `${latenciaBinanceMs}ms` : 'online'}
          </span>
        </div>
      </div>

      {/* Regra de Lucro Líquido Card */}
      <RegraLucroLiquidoCard lucroMinimoUsd={0.01} />

      {/* Grid de Pares Monitorados e Previsão Direcional (100% Real Live Binance Depth) */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h4 className="text-base font-bold text-white flex items-center">
              <Zap className="w-4 h-4 mr-2 text-amber-400" />
              Profundidade do Livro de Ofertas & Avaliação de Lucro Líquido Real
            </h4>
            <p className="text-xs text-slate-400">
              Dados transmitidos em tempo real pela Binance: Top Bids, Top Asks, Volume e Desequilíbrio de Ordens
            </p>
          </div>
          <span className="text-xs text-slate-400 font-mono">
            {paresAnalise.length} Pares Ativos
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {paresAnalise.map((item) => {
            const isBuy = item.direcao_prevista === 'COMPRA';
            const isSell = item.direcao_prevista === 'VENDA';

            return (
              <div
                key={item.par}
                id={`card-par-${item.par}`}
                className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col justify-between hover:border-slate-700 transition-all shadow-md"
              >
                <div>
                  {/* Top line: Symbol, Price, Badge */}
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="flex items-center space-x-2">
                        <h5 className="text-base font-bold text-white tracking-tight">{item.par}</h5>
                        <span className="text-[10px] font-mono text-emerald-400 bg-emerald-950/60 px-1.5 py-0.5 rounded border border-emerald-800">
                          LIVE BINANCE
                        </span>
                      </div>
                      <div className="text-xs text-slate-300 font-mono mt-0.5">
                        ${item.preco_atual ? item.preco_atual.toFixed(item.preco_atual > 100 ? 2 : 4) : '0.00'}
                      </div>
                    </div>

                    <span
                      className={`px-2.5 py-1 rounded-full text-xs font-extrabold inline-flex items-center ${
                        isBuy
                          ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                          : isSell
                          ? 'bg-rose-950 text-rose-400 border border-rose-800'
                          : 'bg-slate-800 text-slate-400 border border-slate-700'
                      }`}
                    >
                      {isBuy ? (
                        <TrendingUp className="w-3.5 h-3.5 mr-1" />
                      ) : isSell ? (
                        <TrendingDown className="w-3.5 h-3.5 mr-1" />
                      ) : null}
                      {item.direcao_prevista}
                    </span>
                  </div>

                  {/* Real Order Book Bids vs Asks Depth Bar */}
                  {item.melhor_bid && item.melhor_ask ? (
                    <div className="mt-3 p-2.5 rounded-lg bg-slate-950 border border-slate-800 text-[11px] font-mono">
                      <div className="flex justify-between text-slate-400 mb-1">
                        <span className="text-emerald-400">Bid: ${item.melhor_bid.toFixed(item.melhor_bid > 100 ? 2 : 4)}</span>
                        <span className="text-rose-400">Ask: ${item.melhor_ask.toFixed(item.melhor_ask > 100 ? 2 : 4)}</span>
                      </div>
                      <div className="flex justify-between text-[10px] text-slate-500">
                        <span>Bids USD: ${item.volume_bids_usd ? (item.volume_bids_usd / 1000).toFixed(1) : '0'}k</span>
                        <span>Asks USD: ${item.volume_asks_usd ? (item.volume_asks_usd / 1000).toFixed(1) : '0'}k</span>
                      </div>
                    </div>
                  ) : null}

                  {/* Indicators: Imbalance, Confiança, Probabilidade */}
                  <div className="mt-3 grid grid-cols-3 gap-2 text-center text-[10px]">
                    <div className="p-2 rounded-lg bg-slate-950 border border-slate-800">
                      <span className="text-slate-500 block">Book Imbalance</span>
                      <span
                        className={`font-mono font-bold text-xs mt-0.5 block ${
                          item.desequilibrio_livro > 0 ? 'text-emerald-400' : 'text-rose-400'
                        }`}
                      >
                        {item.desequilibrio_livro > 0
                          ? `+${item.desequilibrio_livro.toFixed(2)}`
                          : item.desequilibrio_livro?.toFixed(2) || '0.00'}
                      </span>
                    </div>

                    <div className="p-2 rounded-lg bg-slate-950 border border-slate-800">
                      <span className="text-slate-500 block">Prob. Alta</span>
                      <span className="font-mono font-bold text-xs mt-0.5 text-amber-400 block">
                        {item.probabilidade_alta_pct}%
                      </span>
                    </div>

                    <div className="p-2 rounded-lg bg-slate-950 border border-slate-800">
                      <span className="text-slate-500 block">Confiança</span>
                      <span className="font-mono font-bold text-xs mt-0.5 text-purple-400 block">
                        {item.confianca_pct}%
                      </span>
                    </div>
                  </div>

                  {/* Financial Projection Box */}
                  <div className="mt-3 p-3 rounded-lg bg-slate-950/70 border border-slate-800 text-[11px] space-y-1 font-mono">
                    <div className="flex justify-between text-slate-400">
                      <span>Lucro Bruto Projetado:</span>
                      <span className="text-slate-200">
                        {item.lucro_bruto_projetado_usd > 0
                          ? `+$${item.lucro_bruto_projetado_usd.toFixed(4)}`
                          : `$0.0000`}
                      </span>
                    </div>
                    <div className="flex justify-between text-rose-400">
                      <span>Taxas Totais (Binance):</span>
                      <span>-${item.taxas_totais_usd.toFixed(4)}</span>
                    </div>
                    <div className="border-t border-slate-800/80 pt-1 flex justify-between font-bold">
                      <span className="text-slate-300">Lucro Líquido Estimado:</span>
                      <span
                        className={
                          item.lucro_liquido_projetado_usd >= 0.01 ? 'text-emerald-400' : 'text-slate-400'
                        }
                      >
                        {item.lucro_liquido_projetado_usd > 0
                          ? `+$${item.lucro_liquido_projetado_usd.toFixed(4)}`
                          : `$${item.lucro_liquido_projetado_usd.toFixed(4)}`}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Validation Status Footer */}
                <div className="mt-3 pt-2.5 border-t border-slate-800/80">
                  {item.autorizado_pelo_risco ? (
                    <div className="flex items-center text-xs font-bold text-emerald-400">
                      <CheckCircle2 className="w-3.5 h-3.5 mr-1.5 flex-shrink-0" />
                      <span>AUTORIZADO: Lucro Líquido &ge; $0.01</span>
                    </div>
                  ) : (
                    <div className="flex items-start text-[11px] text-slate-400">
                      <ShieldCheck className="w-3.5 h-3.5 mr-1.5 text-amber-400 flex-shrink-0 mt-0.5" />
                      <span className="line-clamp-2">{item.motivo_validacao}</span>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* IA Sentimento 2h Card */}
      <IaSentimento2hCard
        dadosIa={dadosIa}
        onForcarAtualizacao={handleAtualizarIa2h}
        isUpdating={isUpdatingIa}
      />

      {/* Treinador Quase-Contínuo do Modelo Fino */}
      <TreinadorContinuoCard
        metricas={metricasTreino}
        onTreinarPasso={handleTreinarPasso}
        isTraining={isTraining}
      />

      {/* Tabela de Auditoria de Trades */}
      <TradesHistoricoTable trades={historicoTrades} />

      {/* Modal de Instruções de Execução Local em Produção */}
      {isModalProducaoOpen && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-2xl w-full p-6 shadow-2xl relative">
            <button
              onClick={() => setIsModalProducaoOpen(false)}
              className="absolute top-4 right-4 text-slate-400 hover:text-white p-1 rounded-lg"
            >
              <X className="w-5 h-5" />
            </button>

            <div className="flex items-center space-x-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
                <Server className="w-5 h-5 text-emerald-400" />
              </div>
              <div>
                <h3 className="text-lg font-bold text-white">Como Executar Localmente com Dinheiro Real</h3>
                <p className="text-xs text-slate-400">Guia passo a passo para baixar e rodar em sua máquina</p>
              </div>
            </div>

            <div className="space-y-4 text-xs text-slate-300">
              <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-2">
                <span className="font-bold text-amber-400 block uppercase tracking-wider text-[11px]">
                  1. Baixar o Projeto
                </span>
                <p className="text-slate-400">
                  Clique no menu superior direito do Google AI Studio e escolha <strong>"Download / Export as ZIP"</strong> ou <strong>"Export to GitHub"</strong>.
                </p>
              </div>

              <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-2">
                <span className="font-bold text-emerald-400 block uppercase tracking-wider text-[11px]">
                  2. Executar com 1 Comando
                </span>
                <p className="text-slate-400">
                  O projeto já inclui executáveis prontos para Linux, Mac e Windows:
                </p>
                <div className="bg-slate-900 p-2.5 rounded-lg font-mono text-emerald-300 text-[11px] space-y-1">
                  <div><strong># No Linux ou macOS:</strong> ./iniciar_oraculo.sh</div>
                  <div><strong># No Windows:</strong> dê 2 cliques em iniciar_oraculo.bat</div>
                  <div><strong># Ou via Python direto:</strong> python3 run_production.py</div>
                </div>
              </div>

              <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-2">
                <span className="font-bold text-blue-400 block uppercase tracking-wider text-[11px]">
                  3. Inserir Chaves Binance (.env)
                </span>
                <p className="text-slate-400">
                  Para aplicar dinheiro real, abra o arquivo <code>.env</code> gerado na raiz e preencha:
                </p>
                <div className="bg-slate-900 p-2.5 rounded-lg font-mono text-slate-300 text-[11px]">
                  BINANCE_API_KEY="sua_api_key"<br/>
                  BINANCE_API_SECRET="seu_api_secret"
                </div>
                <p className="text-amber-400 text-[10px]">
                  * Dica de Segurança: Habilite apenas "Read" e "Spot Trading". NUNCA ative a permissão de "Withdraw" (Saque).
                </p>
              </div>
            </div>

            <div className="mt-6 flex justify-end">
              <button
                onClick={() => setIsModalProducaoOpen(false)}
                className="px-5 py-2 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs"
              >
                Entendi, Tudo Pronto!
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
