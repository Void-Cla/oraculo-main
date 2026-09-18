export interface DriveFileItem {
  id: string;
  name: string;
  mimeType: string;
  size?: number | string;
  modifiedTime?: string;
  description?: string;
  parentId?: string;
  isFolder: boolean;
  category: 'code' | 'doc' | 'config' | 'test' | 'script' | 'log' | 'folder' | 'other';
  webViewLink?: string;
  summary?: string;
  rawContent?: string;
}

export interface AgentRole {
  code: string;
  name: string;
  role: string;
  responsibilities: string[];
  restrictedFiles?: string[];
  fileDoc: string;
}

export interface PipelineStage {
  step: number;
  name: string;
  module: string;
  description: string;
  status: 'active' | 'gate' | 'feedback';
  details: string[];
}

export interface LogMetric {
  timestamp: string;
  symbol: string;
  action: 'BUY' | 'SELL' | 'HOLD';
  scoreFinal: number;
  scoreNumerico: number;
  scoreLlm: number;
  confianca: number;
  motivo: string;
  tamanho: number;
}
