import React from 'react';
import { 
  ShieldAlert, 
  Activity, 
  Cpu, 
  CheckCircle2, 
  AlertTriangle, 
  Database, 
  Layers, 
  TrendingUp, 
  FileCode2, 
  FileCheck2,
  Lock,
  ArrowRight
} from 'lucide-react';
import { FOLDER_METADATA, STRATEGIC_FINDINGS } from '../data/analyzedProjectData';

interface OverviewTabProps {
  onNavigateTab: (tabId: string) => void;
}

export const OverviewTab: React.FC<OverviewTabProps> = ({ onNavigateTab }) => {
  return (
    <div className="space-y-8">
      {/* Hero Banner / Resumo Executivo */}
      <div className="bg-gradient-to-br from-slate-900 via-slate-900 to-slate-950 border border-slate-800 rounded-2xl p-6 sm:p-8 shadow-xl relative overflow-hidden">
        <div className="absolute -right-16 -top-16 w-64 h-64 bg-amber-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute right-32 -bottom-16 w-48 h-48 bg-orange-500/10 rounded-full blur-2xl pointer-events-none" />

        <div className="relative z-10 max-w-4xl">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs font-semibold mb-4">
            <Cpu className="w-3.5 h-3.5" />
            Análise Concluída com Sucesso
          </div>

          <h2 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight leading-tight">
            Oráculo — Sistema de Trading Algorítmico Autônomo (Binance)
          </h2>
          <p className="mt-3 text-sm sm:text-base text-slate-300 leading-relaxed">
            A pasta analisada hospeda um ecossistema quantitativo completo para micro-trading spot na Binance,
            implementado em <strong>Python / FastAPI</strong> com governança <strong>multi-agente</strong> (Claude Code / Codex),
            decisão híbrida com IA (Gemini / heurística), <strong>346 testes automatizados</strong> e barreira de segurança ativa para capital real.
          </p>

          <div className="mt-6 flex flex-wrap items-center gap-3">
            <button
              id="btn-nav-pipeline"
              onClick={() => onNavigateTab('architecture')}
              className="px-4 py-2 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-semibold text-xs inline-flex items-center shadow-lg shadow-amber-500/20 transition-all"
            >
              Explorar Pipeline de 7 Etapas <ArrowRight className="w-3.5 h-3.5 ml-1.5" />
            </button>
            <button
              id="btn-nav-logs"
              onClick={() => onNavigateTab('logs')}
              className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-medium text-xs border border-slate-700 inline-flex items-center transition-colors"
            >
              <Activity className="w-3.5 h-3.5 mr-1.5 text-amber-400" />
              Ver Logs de Execução em Tempo Real
            </button>
            <button
              id="btn-nav-risk"
              onClick={() => onNavigateTab('risk')}
              className="px-4 py-2 rounded-xl bg-slate-800/80 hover:bg-slate-700 text-slate-300 font-medium text-xs border border-slate-700/80 inline-flex items-center transition-colors"
            >
              <Lock className="w-3.5 h-3.5 mr-1.5 text-emerald-400" />
              Governança de Risco & Edge
            </button>
          </div>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: Testes & Qualidade */}
        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 hover:border-slate-700 transition-colors">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Qualidade de Código</span>
            <div className="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-400 flex items-center justify-center">
              <FileCheck2 className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <span className="text-2xl font-bold text-white tracking-tight">346 / 346</span>
            <span className="text-xs text-emerald-400 font-medium ml-2">100% Verdes</span>
          </div>
          <p className="mt-1 text-xs text-slate-400">
            51 suítes cobrindo risco, sinais, ev_calculator, cliente Binance e adaptadores.
          </p>
        </div>

        {/* Card 2: Proteção de Capital */}
        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 hover:border-slate-700 transition-colors">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Conta Real</span>
            <div className="w-8 h-8 rounded-lg bg-amber-500/10 text-amber-400 flex items-center justify-center">
              <Lock className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <span className="text-2xl font-bold text-amber-400 tracking-tight">Bloqueada</span>
            <span className="text-xs text-slate-400 font-medium ml-2">Por Design</span>
          </div>
          <p className="mt-1 text-xs text-slate-400">
            PERMITIR_CONTA_REAL=false ativo. Requer comprovação de edge líquido walk-forward.
          </p>
        </div>

        {/* Card 3: Decisão Híbrida */}
        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 hover:border-slate-700 transition-colors">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Motor de IA</span>
            <div className="w-8 h-8 rounded-lg bg-purple-500/10 text-purple-400 flex items-center justify-center">
              <Cpu className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <span className="text-2xl font-bold text-white tracking-tight">Híbrido</span>
            <span className="text-xs text-purple-400 font-medium ml-2">65% Num / 35% IA</span>
          </div>
          <p className="mt-1 text-xs text-slate-400">
            Gemini 3.8 + heurística local com garantia fail-open (nunca trava o loop de 30s).
          </p>
        </div>

        {/* Card 4: Pares de Ativos */}
        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 hover:border-slate-700 transition-colors">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Pares Monitorados</span>
            <div className="w-8 h-8 rounded-lg bg-blue-500/10 text-blue-400 flex items-center justify-center">
              <TrendingUp className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <span className="text-2xl font-bold text-white tracking-tight">6 Pares</span>
            <span className="text-xs text-blue-400 font-medium ml-2">Binance Spot</span>
          </div>
          <p className="mt-1 text-xs text-slate-400">
            BTCUSDT, ETHUSDT, BNBUSDT, ETHBTC, BNBBTC e BNBETH avaliados em ciclos contínuos.
          </p>
        </div>
      </div>

      {/* Strategic Findings Grid */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-white tracking-tight flex items-center">
            <Layers className="w-4 h-4 mr-2 text-amber-400" />
            Achados e Diagnóstico da Análise Técnica
          </h3>
          <span className="text-xs text-slate-400">5 pontos-chave estruturais</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {STRATEGIC_FINDINGS.map((finding, idx) => (
            <div 
              key={idx} 
              className="bg-slate-900/80 border border-slate-800/90 rounded-xl p-5 hover:border-slate-700 transition-all"
            >
              <div className="flex items-center justify-between mb-2.5">
                <span className="text-xs font-medium text-slate-400 tracking-wider uppercase">
                  {finding.category}
                </span>
                <span className={`text-[11px] font-semibold px-2.5 py-0.5 rounded-full ${
                  finding.badgeColor === 'emerald' ? 'bg-emerald-950/80 text-emerald-400 border border-emerald-800/80' :
                  finding.badgeColor === 'blue' ? 'bg-blue-950/80 text-blue-400 border border-blue-800/80' :
                  finding.badgeColor === 'amber' ? 'bg-amber-950/80 text-amber-400 border border-amber-800/80' :
                  finding.badgeColor === 'purple' ? 'bg-purple-950/80 text-purple-400 border border-purple-800/80' :
                  'bg-cyan-950/80 text-cyan-400 border border-cyan-800/80'
                }`}>
                  {finding.badge}
                </span>
              </div>
              <h4 className="text-sm font-semibold text-slate-100">
                {finding.title}
              </h4>
              <p className="mt-2 text-xs text-slate-300 leading-relaxed">
                {finding.description}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Tech Stack & Ecosystem */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-6">
        <h3 className="text-base font-bold text-white mb-4 flex items-center">
          <Database className="w-4 h-4 mr-2 text-amber-400" />
          Stack Tecnológica e Ferramentas Identificadas no Repositório
        </h3>
        <div className="flex flex-wrap gap-2">
          {FOLDER_METADATA.techStack.map((tech, idx) => (
            <span 
              key={idx}
              className="px-3 py-1.5 rounded-lg bg-slate-800/90 text-slate-200 border border-slate-700/80 text-xs font-medium"
            >
              {tech}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
};
