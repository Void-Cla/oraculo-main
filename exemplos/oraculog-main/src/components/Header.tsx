import React from 'react';
import { User } from 'firebase/auth';
import { 
  FolderOpen, 
  ExternalLink, 
  Sparkles, 
  Download, 
  CheckCircle2, 
  ShieldCheck, 
  LogOut,
  RefreshCw
} from 'lucide-react';
import { FOLDER_METADATA } from '../data/analyzedProjectData';

interface HeaderProps {
  user: User | null;
  onSignIn: () => void;
  onSignOut: () => void;
  isSigningIn: boolean;
  onOpenAiModal: () => void;
  onExportReport: () => void;
  onLiveRefresh?: () => void;
  isRefreshingLive?: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  user,
  onSignIn,
  onSignOut,
  isSigningIn,
  onOpenAiModal,
  onExportReport,
  onLiveRefresh,
  isRefreshingLive
}) => {
  return (
    <header className="bg-slate-900 border-b border-slate-800 text-white sticky top-0 z-30 shadow-md">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3.5">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          {/* Logo & Title */}
          <div className="flex items-center space-x-3.5">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-amber-500 to-orange-400 flex items-center justify-center text-slate-950 font-bold shadow-lg shadow-orange-500/20">
              <FolderOpen className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h1 className="text-lg font-bold text-white tracking-tight">
                  Drive Folder Analyzer
                </h1>
                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-950/80 text-emerald-400 border border-emerald-800/80">
                  <CheckCircle2 className="w-3 h-3 mr-1" />
                  Indexado
                </span>
              </div>
              <p className="text-xs text-slate-400 flex items-center gap-1.5 mt-0.5">
                <span>Pasta: <strong className="text-slate-300">{FOLDER_METADATA.name}</strong></span>
                <span className="text-slate-600">•</span>
                <a 
                  href={FOLDER_METADATA.url} 
                  target="_blank" 
                  rel="noopener noreferrer" 
                  className="text-amber-400 hover:text-amber-300 inline-flex items-center text-[11px] underline underline-offset-2 transition-colors"
                >
                  Abrir no Drive <ExternalLink className="w-2.5 h-2.5 ml-1" />
                </a>
              </p>
            </div>
          </div>

          {/* Action buttons & Google Auth */}
          <div className="flex items-center flex-wrap gap-2.5">
            {onLiveRefresh && (
              <button
                id="btn-live-refresh"
                onClick={onLiveRefresh}
                disabled={isRefreshingLive}
                className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium border border-slate-700 inline-flex items-center transition-colors disabled:opacity-50"
                title="Re-sincronizar dados com o Google Drive"
              >
                <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${isRefreshingLive ? 'animate-spin text-amber-400' : ''}`} />
                {isRefreshingLive ? 'Sincronizando...' : 'Atualizar'}
              </button>
            )}

            <button
              id="btn-ask-gemini"
              onClick={onOpenAiModal}
              className="px-3.5 py-1.5 rounded-lg bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-600 hover:to-orange-600 text-slate-950 font-semibold text-xs inline-flex items-center shadow-md shadow-orange-500/10 transition-all hover:scale-[1.02] active:scale-[0.98]"
            >
              <Sparkles className="w-3.5 h-3.5 mr-1.5" />
              Perguntar ao Gemini
            </button>

            <button
              id="btn-export-report"
              onClick={onExportReport}
              className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium border border-slate-700 inline-flex items-center transition-colors"
            >
              <Download className="w-3.5 h-3.5 mr-1.5" />
              Exportar Análise
            </button>

            {/* Google Drive Auth Button */}
            {user ? (
              <div className="flex items-center space-x-2 pl-2 border-l border-slate-800">
                <div className="w-7 h-7 rounded-full bg-slate-700 flex items-center justify-center text-xs font-semibold text-amber-400 overflow-hidden border border-slate-600">
                  {user.photoURL ? (
                    <img src={user.photoURL} alt={user.displayName || 'Usuário'} className="w-full h-full object-cover" />
                  ) : (
                    user.displayName?.charAt(0) || user.email?.charAt(0) || 'U'
                  )}
                </div>
                <div className="hidden sm:block text-left">
                  <p className="text-xs font-medium text-slate-200 leading-tight">
                    {user.displayName || user.email?.split('@')[0]}
                  </p>
                  <p className="text-[10px] text-emerald-400 flex items-center">
                    <ShieldCheck className="w-2.5 h-2.5 mr-0.5" />
                    Drive Conectado
                  </p>
                </div>
                <button
                  id="btn-sign-out"
                  onClick={onSignOut}
                  className="p-1.5 text-slate-400 hover:text-rose-400 rounded-lg hover:bg-slate-800 transition-colors"
                  title="Desconectar do Google"
                >
                  <LogOut className="w-3.5 h-3.5" />
                </button>
              </div>
            ) : (
              <button
                id="btn-sign-in-google"
                onClick={onSignIn}
                disabled={isSigningIn}
                className="gsi-material-button text-xs py-1 px-2.5 bg-white text-slate-800 hover:bg-slate-100 rounded-lg font-medium inline-flex items-center shadow-sm border border-slate-300 transition-colors disabled:opacity-60"
              >
                <div className="w-4 h-4 mr-1.5 flex-shrink-0">
                  <svg viewBox="0 0 48 48" className="w-full h-full">
                    <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
                    <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
                    <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
                    <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
                    <path fill="none" d="M0 0h48v48H0z" />
                  </svg>
                </div>
                <span>{isSigningIn ? 'Conectando...' : 'Conectar Google Drive'}</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </header>
  );
};
