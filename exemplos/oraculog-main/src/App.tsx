import React, { useState, useEffect } from 'react';
import { User } from 'firebase/auth';
import { 
  initAuth, 
  googleSignIn, 
  logout 
} from './lib/firebase';
import { 
  extractFolderId, 
  fetchDriveFolderMetadata, 
  listDriveFolderChildren 
} from './lib/driveApi';
import { Header } from './components/Header';
import { OverviewTab } from './components/OverviewTab';
import { ArchitectureTab } from './components/ArchitectureTab';
import { FileExplorerTab } from './components/FileExplorerTab';
import { LogsAnalysisTab } from './components/LogsAnalysisTab';
import { RiskAndEdgeTab } from './components/RiskAndEdgeTab';
import { AiConsultantModal } from './components/AiConsultantModal';
import { OraculoTradingDashboard } from './components/OraculoTradingDashboard';
import { FOLDER_METADATA } from './data/analyzedProjectData';
import { 
  LayoutDashboard, 
  Network, 
  FolderTree, 
  Activity, 
  ShieldCheck, 
  Check, 
  AlertCircle,
  Sparkles,
  Link2,
  Download,
  Zap
} from 'lucide-react';

export default function App() {
  const [activeTab, setActiveTab] = useState<'trading' | 'overview' | 'architecture' | 'files' | 'logs' | 'risk'>('trading');
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isSigningIn, setIsSigningIn] = useState(false);
  const [isAiModalOpen, setIsAiModalOpen] = useState(false);
  const [folderInput, setFolderInput] = useState(FOLDER_METADATA.url);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [isLiveSyncing, setIsLiveSyncing] = useState(false);

  useEffect(() => {
    const unsubscribe = initAuth(
      (currentUser, accessToken) => {
        setUser(currentUser);
        setToken(accessToken);
      },
      () => {
        setUser(null);
        setToken(null);
      }
    );
    return () => unsubscribe();
  }, []);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3500);
  };

  const handleSignIn = async () => {
    try {
      setIsSigningIn(true);
      const res = await googleSignIn();
      if (res) {
        setUser(res.user);
        setToken(res.accessToken);
        showToast('Conectado ao Google Drive com sucesso!');
      }
    } catch (err: any) {
      console.error('Google Sign-in failed', err);
      showToast('Não foi possível conectar com o Google: ' + (err.message || 'Erro'));
    } finally {
      setIsSigningIn(false);
    }
  };

  const handleSignOut = async () => {
    try {
      await logout();
      setUser(null);
      setToken(null);
      showToast('Desconectado do Google Drive.');
    } catch (err) {
      console.error('Logout error', err);
    }
  };

  const handleLiveRefresh = async () => {
    if (!token) {
      handleSignIn();
      return;
    }
    try {
      setIsLiveSyncing(true);
      const folderId = extractFolderId(folderInput);
      const meta = await fetchDriveFolderMetadata(folderId, token);
      const files = await listDriveFolderChildren(folderId, token);
      showToast(`Sincronizado: ${files.length} itens encontrados em "${meta.name}"`);
    } catch (err: any) {
      showToast(`Aviso: ${err.message}`);
    } finally {
      setIsLiveSyncing(false);
    }
  };

  const handleExportReport = () => {
    const markdownReport = `# RELATÓRIO DE ANÁLISE COMPLETA: ORÁCULO TRADING BOT
ID da Pasta: ${FOLDER_METADATA.id}
URL: ${FOLDER_METADATA.url}
Data de Análise: 13 de Setembro de 2026

## 1. RESUMO EXECUTIVO
O projeto "Oraculo" é um bot de micro-trading algorítmico spot para a exchange Binance.
- Status do Testnet: Validado e operacional.
- Status de Conta Real: BLOQUEADO (PERMITIR_CONTA_REAL=false) por design até comprovação de edge.
- Suíte de Testes: 346 testes passando (100% de sucesso).
- Governança de IA: Sistema multi-agente Claude Code/Codex (.claude/) com Guardião de risco.

## 2. ARQUITETURA DO PIPELINE (7 ETAPAS)
1. Features & Mercado: Ingestão de klines de 1m, volatilidade, spread e book imbalance.
2. Modelagem Preditiva: Modelos quantitativos + heurística local rápida com gate anti-divergência.
3. Sinais & Decisão Híbrida: Fusão ponderada (65% numérico + 35% IA Gemini/Ollama).
4. Filtro de EV & Risco: Expected Value líquido estritamente positivo descontando taxas Binance round-trip.
5. Execução: Idempotência de ordens, checagem de fill e proteção de slippage.
6. Loop Auto-Trader: Ciclos autônomos de 30 segundos com trailing stop ATR.
7. Feedback: Registro de outcomes para calibração de probabilidades e pesos do bandit.

## 3. ARTEFATOS E ESTRUTURA IDENTIFICADOS NO GOOGLE DRIVE
- .claude/ (19 arquivos): Agentes (Orquestrador, Guardião, Quant, Sinais, Execução, Revisor, etc.)
- src/ (28 módulos): Core, api, risco, executor, probabilidade, persistência, sinais, etc.
- tests/ (51 suítes): 346 testes unitários e de integração.
- scripts/ (15 utilitários): Walk-forward backtests, pesquisa de edge, migrações, diagnósticos.
- frontend/ (Dashboard Web): Visualizador de sinais e ordens em tempo real.
- Documentos Mestres: README.md, CLAUDE.md, AGENTS.md, up.md, log.txt, pyproject.toml.

## 4. ANÁLISE DOS LOGS OPERACIONAIS (log.txt)
- Pares monitorados em tempo real: ETHUSDT, BNBUSDT, ETHBTC, BNBBTC, BNBETH.
- Latência média de decisão: ~34ms por ciclo multiativo.
- Mecanismo Fail-open: Se a LLM cair, o sistema segue seguro com a heurística quantitativa.

## 5. RECOMENDAÇÕES ESTRATÉGICAS (Baseado em up.md)
1. Coleta Contínua: Manter o coletor ativo por mais 7-14 dias para gerar massa de dados.
2. Filtro de Edge: Validar configurações que superem com folga o atrito das taxas de corretagem (0.20% round-trip).
3. Transição Segura: Liberar conta real apenas para micro-lotes de 50-100 USDT com stop diário restrito.
`;

    const blob = new Blob([markdownReport], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `Analise_Detalhada_Oraculo_Drive_${FOLDER_METADATA.id}.md`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    showToast('Relatório de análise exportado com sucesso!');
  };

  const navTabs = [
    { id: 'trading', label: 'Terminal Oráculo (Trading Rápido & IA)', icon: Zap },
    { id: 'overview', label: 'Diagnóstico da Pasta Drive', icon: LayoutDashboard },
    { id: 'architecture', label: 'Pipeline de 7 Etapas & Agentes', icon: Network },
    { id: 'files', label: 'Navegador de Arquivos', icon: FolderTree },
    { id: 'logs', label: 'Telemetria Operacional (log.txt)', icon: Activity },
    { id: 'risk', label: 'Governança & Risco (+0,01)', icon: ShieldCheck },
  ] as const;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-amber-500 selection:text-slate-950">
      {/* Header */}
      <Header
        user={user}
        onSignIn={handleSignIn}
        onSignOut={handleSignOut}
        isSigningIn={isSigningIn}
        onOpenAiModal={() => setIsAiModalOpen(true)}
        onExportReport={handleExportReport}
        onLiveRefresh={handleLiveRefresh}
        isRefreshingLive={isLiveSyncing}
      />

      {/* Target Folder Banner */}
      <div className="bg-slate-900/60 border-b border-slate-800/80 px-4 sm:px-6 lg:px-8 py-2.5">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
          <div className="flex items-center space-x-2 text-slate-300">
            <Link2 className="w-3.5 h-3.5 text-amber-400 flex-shrink-0" />
            <span className="text-slate-400 font-medium">Pasta Analisada:</span>
            <span className="font-mono text-amber-300 truncate max-w-xs sm:max-w-md">
              {FOLDER_METADATA.url}
            </span>
          </div>

          <div className="flex items-center space-x-2">
            <span className="text-[11px] text-slate-400">Status:</span>
            <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-950 text-emerald-400 border border-emerald-800">
              {FOLDER_METADATA.state}
            </span>
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {/* Navigation Tabs */}
        <div className="flex items-center space-x-1.5 overflow-x-auto pb-2 border-b border-slate-800">
          {navTabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                id={`tab-${tab.id}`}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center space-x-2 px-4 py-2.5 rounded-xl text-xs font-semibold whitespace-nowrap transition-all ${
                  isActive
                    ? 'bg-amber-500 text-slate-950 shadow-md shadow-amber-500/10 scale-[1.01]'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900 border border-transparent'
                }`}
              >
                <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-slate-950' : 'text-slate-400'}`} />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* Tab Views */}
        <div className="pt-2">
          {activeTab === 'trading' && <OraculoTradingDashboard />}
          {activeTab === 'overview' && (
            <OverviewTab onNavigateTab={(tabId) => setActiveTab(tabId as any)} />
          )}
          {activeTab === 'architecture' && <ArchitectureTab />}
          {activeTab === 'files' && <FileExplorerTab />}
          {activeTab === 'logs' && <LogsAnalysisTab />}
          {activeTab === 'risk' && <RiskAndEdgeTab />}
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800/80 bg-slate-900/50 py-4 text-center text-xs text-slate-300">
        <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-2">
          <p>
            Drive Folder Analyzer • Projeto Oráculo (Binance Spot) • ID: <span className="font-mono text-slate-400">{FOLDER_METADATA.id}</span>
          </p>
          <div className="flex items-center space-x-4 text-[11px] text-slate-300">
            <span>Model: Gemini 3.8 Flash</span>
            <span>•</span>
            <span>Suíte: 346 Testes Verdes</span>
          </div>
        </div>
      </footer>

      {/* AI Consultant Modal */}
      <AiConsultantModal
        isOpen={isAiModalOpen}
        onClose={() => setIsAiModalOpen(false)}
      />

      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-5 right-5 z-50 bg-slate-900 border border-slate-700 text-slate-100 text-xs px-4 py-3 rounded-xl shadow-2xl flex items-center space-x-2.5 animate-in fade-in slide-in-from-bottom-5">
          <Check className="w-4 h-4 text-emerald-400 flex-shrink-0" />
          <span>{toastMessage}</span>
        </div>
      )}
    </div>
  );
}
