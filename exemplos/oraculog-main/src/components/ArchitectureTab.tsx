import React, { useState } from 'react';
import { 
  GitBranch, 
  ShieldCheck, 
  Cpu, 
  Zap, 
  Lock, 
  RefreshCw, 
  ArrowDown, 
  FileCode, 
  ChevronRight,
  UserCheck
} from 'lucide-react';
import { PIPELINE_STAGES, MULTI_AGENT_ROLES } from '../data/analyzedProjectData';

export const ArchitectureTab: React.FC = () => {
  const [selectedStageIndex, setSelectedStageIndex] = useState(2); // default Sinais
  const [selectedAgentCode, setSelectedAgentCode] = useState('GRD'); // default Guardião

  const currentStage = PIPELINE_STAGES[selectedStageIndex];
  const currentAgent = MULTI_AGENT_ROLES.find(a => a.code === selectedAgentCode) || MULTI_AGENT_ROLES[1];

  return (
    <div className="space-y-10">
      {/* Section 1: Pipeline de 7 Etapas */}
      <div>
        <div className="mb-6">
          <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-500/10 text-amber-400 text-xs font-semibold mb-2">
            <Zap className="w-3.5 h-3.5" />
            Fluxo Contínuo de Mercado
          </div>
          <h3 className="text-xl font-bold text-white tracking-tight">
            Pipeline Operacional do Oráculo (Micro-trading na Binance)
          </h3>
          <p className="text-xs sm:text-sm text-slate-300 mt-1 max-w-3xl">
            Ciclo fechado e autônomo executado a cada 30 segundos: da leitura de klines à reconciliação de ordens e aprendizado com o desfecho real.
          </p>
        </div>

        {/* Pipeline Stepper / Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2.5 mb-6">
          {PIPELINE_STAGES.map((stage, idx) => {
            const isSelected = selectedStageIndex === idx;
            return (
              <button
                key={stage.step}
                id={`stage-step-${stage.step}`}
                onClick={() => setSelectedStageIndex(idx)}
                className={`flex flex-col items-center text-center p-3 rounded-xl border transition-all ${
                  isSelected 
                    ? 'bg-amber-500/10 border-amber-500/60 shadow-lg shadow-amber-500/10 text-white' 
                    : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:bg-slate-800/80 hover:text-slate-200'
                }`}
              >
                <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold mb-2 ${
                  isSelected 
                    ? 'bg-amber-500 text-slate-950' 
                    : stage.status === 'gate'
                    ? 'bg-rose-950/80 text-rose-400 border border-rose-800'
                    : 'bg-slate-800 text-slate-300'
                }`}>
                  {stage.step}
                </div>
                <span className="text-xs font-semibold leading-tight line-clamp-1">
                  {stage.name.split('&')[0]}
                </span>
                <span className="text-[10px] text-slate-400 mt-0.5">
                  {stage.status === 'gate' ? 'Gate Restritivo' : 'Processamento'}
                </span>
              </button>
            );
          })}
        </div>

        {/* Selected Stage Detail Panel */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 relative overflow-hidden">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-800">
            <div>
              <span className="text-xs font-semibold text-amber-400 uppercase tracking-wider">
                Etapa {currentStage.step} de 7
              </span>
              <h4 className="text-lg font-bold text-white mt-0.5">
                {currentStage.name}
              </h4>
            </div>
            <div className="flex items-center space-x-2">
              <span className="text-xs font-mono px-2.5 py-1 rounded-md bg-slate-800 text-slate-300 border border-slate-700">
                {currentStage.module}
              </span>
              <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${
                currentStage.status === 'gate' 
                  ? 'bg-rose-950/80 text-rose-400 border border-rose-800'
                  : currentStage.status === 'feedback'
                  ? 'bg-purple-950/80 text-purple-400 border border-purple-800'
                  : 'bg-emerald-950/80 text-emerald-400 border border-emerald-800'
              }`}>
                {currentStage.status === 'gate' ? 'Gate Bloqueante' : currentStage.status === 'feedback' ? 'Loop de Feedback' : 'Execução Contínua'}
              </span>
            </div>
          </div>

          <p className="mt-4 text-sm text-slate-300 leading-relaxed">
            {currentStage.description}
          </p>

          <div className="mt-5">
            <h5 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2.5">
              Mecanismos e Garantias Desta Etapa:
            </h5>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              {currentStage.details.map((detail, dIdx) => (
                <div key={dIdx} className="flex items-start space-x-2.5 p-3 rounded-lg bg-slate-950/60 border border-slate-800/80 text-xs text-slate-200">
                  <div className="w-1.5 h-1.5 rounded-full bg-amber-400 mt-1.5 flex-shrink-0" />
                  <span>{detail}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Section 2: Arquitetura Multi-Agente */}
      <div>
        <div className="mb-6">
          <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-purple-500/10 text-purple-400 text-xs font-semibold mb-2">
            <Cpu className="w-3.5 h-3.5" />
            Engenharia Orientada a Agentes
          </div>
          <h3 className="text-xl font-bold text-white tracking-tight">
            Sistema Multi-Agente (.claude / Claude Code & Codex)
          </h3>
          <p className="text-xs sm:text-sm text-slate-300 mt-1 max-w-3xl">
            A pasta <code className="text-amber-400 font-mono text-xs">.claude/</code> estabelece um protocolo estrito de papéis especializados, onde cada modificação de código passa por revisão e aprovação mandatória do Guardião.
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Agent Selector List */}
          <div className="space-y-2 lg:col-span-1">
            {MULTI_AGENT_ROLES.map((agent) => {
              const isSelected = selectedAgentCode === agent.code;
              return (
                <button
                  key={agent.code}
                  id={`btn-agent-${agent.code}`}
                  onClick={() => setSelectedAgentCode(agent.code)}
                  className={`w-full text-left p-3.5 rounded-xl border transition-all flex items-center justify-between ${
                    isSelected
                      ? 'bg-slate-800 border-purple-500/60 shadow-md text-white'
                      : 'bg-slate-900/70 border-slate-800 text-slate-300 hover:bg-slate-800/60 hover:text-white'
                  }`}
                >
                  <div className="flex items-center space-x-3">
                    <span className={`w-8 h-8 rounded-lg flex items-center justify-center font-mono text-xs font-bold ${
                      agent.code === 'GRD'
                        ? 'bg-rose-950 text-rose-400 border border-rose-800'
                        : isSelected
                        ? 'bg-purple-950 text-purple-300 border border-purple-800'
                        : 'bg-slate-800 text-slate-400'
                    }`}>
                      {agent.code}
                    </span>
                    <div>
                      <p className="text-xs font-bold leading-none text-slate-100">{agent.name}</p>
                      <p className="text-[11px] text-slate-400 mt-0.5">{agent.role}</p>
                    </div>
                  </div>
                  <ChevronRight className={`w-4 h-4 ${isSelected ? 'text-purple-400' : 'text-slate-600'}`} />
                </button>
              );
            })}
          </div>

          {/* Agent Details Card */}
          <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-2xl p-6 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between pb-4 border-b border-slate-800">
                <div className="flex items-center space-x-3">
                  <div className="w-10 h-10 rounded-xl bg-purple-950 border border-purple-800 flex items-center justify-center text-purple-300 font-bold font-mono text-sm">
                    {currentAgent.code}
                  </div>
                  <div>
                    <h4 className="text-base font-bold text-white">{currentAgent.name}</h4>
                    <p className="text-xs text-purple-400">{currentAgent.role}</p>
                  </div>
                </div>
                <span className="text-xs font-mono text-slate-400 px-2.5 py-1 bg-slate-800 rounded-md border border-slate-700">
                  {currentAgent.fileDoc}
                </span>
              </div>

              <div className="mt-5 space-y-4">
                <div>
                  <h5 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                    Responsabilidades Críticas:
                  </h5>
                  <ul className="space-y-2">
                    {currentAgent.responsibilities.map((resp, rIdx) => (
                      <li key={rIdx} className="flex items-start text-xs text-slate-300">
                        <UserCheck className="w-3.5 h-3.5 text-purple-400 mr-2 mt-0.5 flex-shrink-0" />
                        <span>{resp}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                {currentAgent.restrictedFiles && currentAgent.restrictedFiles.length > 0 && (
                  <div className="mt-4 p-4 rounded-xl bg-rose-950/20 border border-rose-800/40">
                    <div className="flex items-center gap-1.5 text-xs font-bold text-rose-400 mb-2">
                      <Lock className="w-3.5 h-3.5" />
                      Arquivos Sob Proteção Rigorosa (Nenhuma alteração sem autorização):
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {currentAgent.restrictedFiles.map((file, fIdx) => (
                        <code key={fIdx} className="text-[11px] font-mono px-2 py-0.5 bg-slate-950 rounded text-rose-300 border border-rose-900/50">
                          {file}
                        </code>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="mt-6 pt-4 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-slate-400">
              <span>Protocolo de inicialização: Obrigatório ler <code className="text-slate-300">.claude/contexto.md</code></span>
              <span>Regra de Ouro: Sem testes verdes, sem commit</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
