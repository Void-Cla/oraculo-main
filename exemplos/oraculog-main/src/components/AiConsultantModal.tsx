import React, { useState } from 'react';
import Markdown from 'react-markdown';
import { 
  Sparkles, 
  Send, 
  X, 
  Bot, 
  User, 
  Loader2, 
  HelpCircle,
  CheckCircle2
} from 'lucide-react';
import { FOLDER_METADATA } from '../data/analyzedProjectData';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

interface AiConsultantModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const AiConsultantModal: React.FC<AiConsultantModalProps> = ({ isOpen, onClose }) => {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      content: `Olá! Sou o assistente de inteligência artificial com foco na análise da pasta do Google Drive do **Oraculo Trading Bot** (${FOLDER_METADATA.id}).\n\nVocê pode me fazer qualquer pergunta técnica sobre a arquitetura do bot, os arquivos da pasta (.claude, src, tests, scripts), a governança do Guardião ou os logs operacionais.`
    }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);

  const quickQuestions = [
    'Como funciona o cálculo de EV líquido?',
    'Qual o papel do Guardião no sistema?',
    'Por que o robô não opera com capital real ainda?',
    'O que diz o arquivo up.md sobre ganhos diários?',
    'O que foi corrigido no recente BUG-17?'
  ];

  if (!isOpen) return null;

  const handleSend = async (questionText?: string) => {
    const query = questionText || input.trim();
    if (!query || loading) return;

    const newMessages: Message[] = [...messages, { role: 'user', content: query }];
    setMessages(newMessages);
    if (!questionText) setInput('');
    setLoading(true);

    try {
      const res = await fetch('/api/gemini/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: query,
          context: `Projeto: Oraculo Trading Bot (Binance Spot)
Status: Testnet validado, 346 testes verdes, conta real travada (PERMITIR_CONTA_REAL=false).
Arquivos presentes na pasta do Drive:
- .claude/ (00_orquestrador.md, 01_revisor.md, 02_guardiao.md, 03_sinais.md, 04_quant.md, contexto.md, skill.md)
- src/ (calculos, modelagem, sinais, risco, executor, servicos, persistencia)
- tests/ (51 arquivos de teste com 346 testes verdes)
- scripts/ (backtest_walkforward.py, pesquisa_edge.py, run_testnet_e2e.py)
- README.md, CLAUDE.md, AGENTS.md, up.md, log.txt, pyproject.toml, requirements.txt.
Último bug corrigido: BUG-17 no /v1/auto/start com argumento posicional resolvido.`
        })
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: 'Falha na resposta do servidor' }));
        throw new Error(err.error || 'Erro na requisição');
      }

      const data = await res.json();
      setMessages([...newMessages, { role: 'assistant', content: data.answer }]);
    } catch (err: any) {
      setMessages([
        ...newMessages,
        {
          role: 'assistant',
          content: `⚠️ Não foi possível processar a consulta via Gemini API: ${err.message}. Verifique a chave de API ou tente novamente.`
        }
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-3xl h-[85vh] flex flex-col overflow-hidden shadow-2xl animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-950/80">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-amber-500 to-orange-500 flex items-center justify-center text-slate-950 font-bold shadow-md shadow-orange-500/20">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-white flex items-center gap-1.5">
                Consultor Gemini 3.8 Flash
                <span className="text-[10px] font-normal px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-400 border border-emerald-800/80">
                  Online
                </span>
              </h3>
              <p className="text-[11px] text-slate-400">
                Tire dúvidas sobre o código, arquitetura de trading e arquivos da pasta
              </p>
            </div>
          </div>
          <button
            id="btn-close-ai-modal"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Quick Questions Pill Bar */}
        <div className="px-6 py-2.5 bg-slate-950/40 border-b border-slate-800/60 flex items-center gap-2 overflow-x-auto">
          <span className="text-[11px] text-slate-500 font-medium whitespace-nowrap flex items-center">
            <HelpCircle className="w-3 h-3 mr-1" /> Sugestões:
          </span>
          {quickQuestions.map((q, idx) => (
            <button
              key={idx}
              onClick={() => handleSend(q)}
              disabled={loading}
              className="text-[11px] px-2.5 py-1 rounded-full bg-slate-800/80 hover:bg-slate-700/80 text-slate-300 hover:text-amber-300 border border-slate-700/60 whitespace-nowrap transition-colors disabled:opacity-50"
            >
              {q}
            </button>
          ))}
        </div>

        {/* Messages Stream */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {messages.map((msg, idx) => {
            const isUser = msg.role === 'user';
            return (
              <div
                key={idx}
                className={`flex items-start space-x-3 ${isUser ? 'flex-row-reverse space-x-reverse' : ''}`}
              >
                <div
                  className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 text-xs ${
                    isUser ? 'bg-amber-500 text-slate-950 font-bold' : 'bg-slate-800 text-amber-400 border border-slate-700'
                  }`}
                >
                  {isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
                </div>

                <div
                  className={`rounded-2xl p-4 text-xs leading-relaxed max-w-[85%] ${
                    isUser
                      ? 'bg-amber-500/15 border border-amber-500/30 text-amber-100'
                      : 'bg-slate-950/70 border border-slate-800 text-slate-200'
                  }`}
                >
                  <div className="prose prose-invert prose-xs max-w-none space-y-2">
                    <Markdown>{msg.content}</Markdown>
                  </div>
                </div>
              </div>
            );
          })}

          {loading && (
            <div className="flex items-center space-x-3">
              <div className="w-7 h-7 rounded-lg bg-slate-800 text-amber-400 border border-slate-700 flex items-center justify-center flex-shrink-0">
                <Bot className="w-4 h-4" />
              </div>
              <div className="p-3.5 rounded-2xl bg-slate-950/70 border border-slate-800 text-xs text-slate-400 flex items-center space-x-2">
                <Loader2 className="w-3.5 h-3.5 animate-spin text-amber-400" />
                <span>Consultando modelo Gemini 3.8 Flash...</span>
              </div>
            </div>
          )}
        </div>

        {/* Input Bar */}
        <div className="p-4 border-t border-slate-800 bg-slate-950/80">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
            className="flex items-center space-x-2"
          >
            <input
              id="input-ai-question"
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Pergunte sobre a arquitetura do Oráculo, o Guardião, walk-forward..."
              disabled={loading}
              className="flex-1 bg-slate-900 border border-slate-700 rounded-xl px-4 py-2.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-amber-500 transition-colors disabled:opacity-50"
            />
            <button
              id="btn-send-ai-question"
              type="submit"
              disabled={!input.trim() || loading}
              className="px-4 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs inline-flex items-center disabled:opacity-40 transition-colors shadow-md shadow-amber-500/10"
            >
              <Send className="w-3.5 h-3.5" />
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};
