import React, { useState } from 'react';
import { 
  Folder, 
  FileText, 
  FileCode, 
  Settings, 
  FileSearch, 
  ExternalLink, 
  Eye, 
  X, 
  Check, 
  Copy,
  Terminal,
  ChevronRight
} from 'lucide-react';
import { ALL_DRIVE_ITEMS, FOLDER_METADATA } from '../data/analyzedProjectData';
import { DriveFileItem } from '../types';

export const FileExplorerTab: React.FC = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [previewFile, setPreviewFile] = useState<DriveFileItem | null>(null);
  const [copied, setCopied] = useState(false);

  const categories = [
    { id: 'all', label: 'Todos os Itens' },
    { id: 'folder', label: 'Pastas' },
    { id: 'doc', label: 'Documentação' },
    { id: 'config', label: 'Configurações' },
    { id: 'script', label: 'Scripts' },
    { id: 'log', label: 'Logs' },
  ];

  const filteredItems = ALL_DRIVE_ITEMS.filter((item) => {
    const matchesSearch = item.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (item.description && item.description.toLowerCase().includes(searchQuery.toLowerCase()));
    const matchesCat = selectedCategory === 'all' || item.category === selectedCategory;
    return matchesSearch && matchesCat;
  });

  const handleCopyFileId = (id: string) => {
    navigator.clipboard.writeText(id);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h3 className="text-xl font-bold text-white tracking-tight">
            Navegador de Arquivos & Estrutura do Drive
          </h3>
          <p className="text-xs sm:text-sm text-slate-300 mt-0.5">
            Inventário completo dos artefatos indexados da pasta <span className="text-amber-400 font-mono text-xs">{FOLDER_METADATA.id}</span>
          </p>
        </div>

        {/* Search */}
        <div className="w-full sm:w-72 relative">
          <input
            id="input-search-files"
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Buscar arquivo ou descrição..."
            className="w-full bg-slate-900 border border-slate-700/80 rounded-xl px-3.5 py-2 pl-9 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-amber-500 transition-colors"
          />
          <FileSearch className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-2.5 top-2.5 text-slate-500 hover:text-slate-300"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Category Pills */}
      <div className="flex items-center space-x-2 overflow-x-auto pb-1">
        {categories.map((cat) => (
          <button
            key={cat.id}
            id={`filter-cat-${cat.id}`}
            onClick={() => setSelectedCategory(cat.id)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-all ${
              selectedCategory === cat.id
                ? 'bg-amber-500 text-slate-950 font-semibold shadow-sm'
                : 'bg-slate-900 text-slate-400 border border-slate-800 hover:bg-slate-800 hover:text-slate-200'
            }`}
          >
            {cat.label}
          </button>
        ))}
        <span className="text-xs text-slate-500 pl-2">
          ({filteredItems.length} {filteredItems.length === 1 ? 'item' : 'itens'})
        </span>
      </div>

      {/* Files Grid / List */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
        {filteredItems.map((item) => {
          const isFolder = item.isFolder;
          return (
            <div
              key={item.id}
              className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 flex flex-col justify-between hover:border-slate-700 hover:bg-slate-850 transition-all group"
            >
              <div>
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center space-x-2.5 min-w-0">
                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                      isFolder 
                        ? 'bg-amber-500/10 text-amber-400' 
                        : item.category === 'doc'
                        ? 'bg-blue-500/10 text-blue-400'
                        : item.category === 'log'
                        ? 'bg-rose-500/10 text-rose-400'
                        : item.category === 'script'
                        ? 'bg-emerald-500/10 text-emerald-400'
                        : 'bg-slate-800 text-slate-300'
                    }`}>
                      {isFolder ? (
                        <Folder className="w-4 h-4 fill-amber-500/20" />
                      ) : item.category === 'doc' ? (
                        <FileText className="w-4 h-4" />
                      ) : item.category === 'script' ? (
                        <Terminal className="w-4 h-4" />
                      ) : item.category === 'config' ? (
                        <Settings className="w-4 h-4" />
                      ) : (
                        <FileCode className="w-4 h-4" />
                      )}
                    </div>
                    <div className="min-w-0">
                      <h4 className="text-xs font-bold text-slate-100 truncate group-hover:text-amber-400 transition-colors">
                        {item.name}
                      </h4>
                      <p className="text-[10px] text-slate-500 truncate font-mono">
                        {item.size ? item.size : isFolder ? 'Diretório' : 'Arquivo'}
                      </p>
                    </div>
                  </div>

                  <a
                    href={`https://drive.google.com/open?id=${item.id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="p-1 text-slate-500 hover:text-amber-400 transition-colors"
                    title="Abrir no Google Drive"
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                  </a>
                </div>

                <p className="mt-3 text-xs text-slate-300 line-clamp-3 leading-relaxed">
                  {item.description}
                </p>
              </div>

              <div className="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between text-[11px]">
                <button
                  id={`btn-copy-id-${item.id.slice(0, 6)}`}
                  onClick={() => handleCopyFileId(item.id)}
                  className="text-slate-500 hover:text-slate-300 inline-flex items-center gap-1 font-mono transition-colors"
                  title="Copiar ID do Google Drive"
                >
                  <Copy className="w-2.5 h-2.5" />
                  ID: {item.id.slice(0, 8)}...
                </button>

                <button
                  id={`btn-inspect-file-${item.id.slice(0, 6)}`}
                  onClick={() => setPreviewFile(item)}
                  className="text-amber-400 hover:text-amber-300 font-semibold inline-flex items-center text-xs transition-colors"
                >
                  <Eye className="w-3 h-3 mr-1" />
                  Detalhes
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Preview Modal */}
      {previewFile && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-2xl overflow-hidden shadow-2xl animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-950/60">
              <div className="flex items-center space-x-3">
                <div className="w-8 h-8 rounded-lg bg-amber-500/10 text-amber-400 flex items-center justify-center">
                  {previewFile.isFolder ? <Folder className="w-4 h-4" /> : <FileText className="w-4 h-4" />}
                </div>
                <div>
                  <h4 className="text-sm font-bold text-white">{previewFile.name}</h4>
                  <p className="text-[11px] text-slate-400 font-mono">{previewFile.mimeType}</p>
                </div>
              </div>
              <button
                id="btn-close-preview"
                onClick={() => setPreviewFile(null)}
                className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-6 space-y-4 max-h-[70vh] overflow-y-auto text-xs">
              <div>
                <h5 className="font-semibold uppercase tracking-wider text-slate-400 text-[10px] mb-1">
                  Resumo Funcional
                </h5>
                <p className="text-slate-200 leading-relaxed text-sm bg-slate-950/50 p-3.5 rounded-xl border border-slate-800">
                  {previewFile.description}
                </p>
              </div>

              <div className="grid grid-cols-2 gap-3 text-slate-300">
                <div className="bg-slate-950/40 p-3 rounded-xl border border-slate-800">
                  <span className="text-[10px] text-slate-500 uppercase tracking-wider block">ID do Google Drive</span>
                  <span className="font-mono text-xs text-amber-400 break-all">{previewFile.id}</span>
                </div>
                <div className="bg-slate-950/40 p-3 rounded-xl border border-slate-800">
                  <span className="text-[10px] text-slate-500 uppercase tracking-wider block">Tamanho</span>
                  <span className="text-xs text-slate-200">{previewFile.size || 'Pasta / Não calculado'}</span>
                </div>
              </div>

              {previewFile.name === 'README.md' && (
                <div className="mt-4">
                  <h5 className="font-semibold text-slate-300 mb-1.5 flex items-center">
                    <FileText className="w-3.5 h-3.5 mr-1.5 text-amber-400" />
                    Trecho em Destaque do README:
                  </h5>
                  <div className="p-4 rounded-xl bg-slate-950 font-mono text-[11px] text-slate-300 border border-slate-800 whitespace-pre-wrap leading-relaxed">
{`# Oraculo — Bot de Trading Algorítmico (Binance)
Micro-trading autônomo na Binance (spot):
mercado → features → sinal → risco → execução → reaprendizado.

Estado (2026-06): engenharia sólida e validada no testnet.
Walk-forward rigoroso mostra sem edge líquido nos dados atuais —
retorno bruto não cobre taxas.
Próximo passo: mais dado + melhor sinal, não mais código.`}
                  </div>
                </div>
              )}

              {previewFile.name === 'CLAUDE.md' && (
                <div className="mt-4">
                  <h5 className="font-semibold text-slate-300 mb-1.5 flex items-center">
                    <FileText className="w-3.5 h-3.5 mr-1.5 text-amber-400" />
                    Protocolo Mandatório do Guardião:
                  </h5>
                  <div className="p-4 rounded-xl bg-slate-950 font-mono text-[11px] text-slate-300 border border-slate-800 whitespace-pre-wrap leading-relaxed">
{`Acionar o guardião ANTES de qualquer mudança em código que move/avalia dinheiro:
(hoje: src/executor/, src/risco/, src/probabilidade/ev_calculator.py,
 src/multiativo/profit_guard.py, src/servicos/testnet_auto_trader.py, src/main.py).

NUNCA comece a modificar código sem ler contexto.md primeiro.
NUNCA altere arquivos de execução financeira sem aprovação explícita do Guardião.`}
                  </div>
                </div>
              )}

              {previewFile.name === 'up.md' && (
                <div className="mt-4">
                  <h5 className="font-semibold text-slate-300 mb-1.5 flex items-center">
                    <FileText className="w-3.5 h-3.5 mr-1.5 text-amber-400" />
                    Diretriz Central de up.md (Realismo de Capital):
                  </h5>
                  <div className="p-4 rounded-xl bg-slate-950 font-mono text-[11px] text-slate-300 border border-slate-800 whitespace-pre-wrap leading-relaxed">
{`A meta "100 USDT → 10 USDT/dia" é 10% ao dia.
Nenhum sistema sustentável do planeta entrega isso — nem mesas proprietárias de HFT.
O edge real medido do Oráculo hoje é +0,03% líquido/trade em 1 config de 72.
O caminho honesto é aumentar a janela temporal e a qualidade do sinal.`}
                  </div>
                </div>
              )}
            </div>

            <div className="px-6 py-3.5 border-t border-slate-800 bg-slate-950/80 flex items-center justify-between">
              <button
                onClick={() => handleCopyFileId(previewFile.id)}
                className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium border border-slate-700 inline-flex items-center"
              >
                {copied ? <Check className="w-3.5 h-3.5 mr-1.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5 mr-1.5" />}
                {copied ? 'Copiado!' : 'Copiar ID'}
              </button>

              <a
                href={`https://drive.google.com/open?id=${previewFile.id}`}
                target="_blank"
                rel="noopener noreferrer"
                className="px-4 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-semibold inline-flex items-center"
              >
                Abrir Arquivo no Google Drive <ExternalLink className="w-3.5 h-3.5 ml-1.5" />
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
