import { AgentRole, PipelineStage, DriveFileItem, LogMetric } from '../types';

export const FOLDER_METADATA = {
  id: '1eK8R_uPQyEoJ3_3CoApaRBI5IV5UcV5W',
  name: 'Oraculo — Trading Bot (Binance)',
  url: 'https://drive.google.com/drive/folders/1eK8R_uPQyEoJ3_3CoApaRBI5IV5UcV5W?usp=sharing',
  owner: 'hyago.killerb@gmail.com',
  state: 'Pronto para Testnet / Validação de Edge Ativa',
  lastUpdate: '2026-09-13',
  testSuiteStatus: '346 testes passando (100% verde)',
  realMoneyAllowed: false, // Bloqueado por desenho (PERMITIR_CONTA_REAL=false)
  primaryPairs: ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'ETHBTC', 'BNBBTC', 'BNBETH'],
  techStack: [
    'Python 3.11+',
    'FastAPI / Uvicorn',
    'Binance Spot API (Testnet)',
    'SQLite (oraculo.db)',
    'Gemini API (3.8-flash)',
    'Pytest (346 testes)',
    'Machine Learning / Scikit-learn',
    'Multi-Agent System (Claude Code / Codex)',
    'Node.js / React Frontend Dashboard'
  ]
};

export const PIPELINE_STAGES: PipelineStage[] = [
  {
    step: 1,
    name: 'Features & Mercado',
    module: 'src/calculos/gerador_features.py',
    description: 'Ingestão e processamento de dados OHLCV (klines 1m) em tempo real da Binance, calculando volatilidade, spread e médias móveis.',
    status: 'active',
    details: [
      'Ingestão contínua de klines de 1 minuto',
      'Cálculo de volatilidade realizada e spread efetivo',
      'Pressão de livro de ofertas (Order Book Imbalance)',
      'Detector de regime de mercado e anomalias'
    ]
  },
  {
    step: 2,
    name: 'Modelagem Preditiva',
    module: 'src/modelagem/',
    description: 'Combinação de modelos heurísticos locais, modelos estatísticos batch e aprendizado online com gate anti-divergência.',
    status: 'active',
    details: [
      'Modelos numéricos quantitativos com peso base de 65%',
      'Heurística local ultra-rápida (não bloqueante)',
      'Gate anti-divergência entre múltiplos modelos',
      'Detecção de drift de distribuição de dados'
    ]
  },
  {
    step: 3,
    name: 'Sinais & Decisor Híbrido',
    module: 'src/sinais/signal_engine.py + consenso.py',
    description: 'Fusão ponderada entre score numérico quantitativo e sentimento/análise qualitativa de notícias e livro da LLM (Gemini/Ollama).',
    status: 'active',
    details: [
      'Integração com Gemini 3.8-flash com cache e throttle de 300s',
      'Fail-open garantido: se a IA falhar ou estiver sem internet, o bot segue operando com a heurística local',
      'Consenso de voto entre estratégias técnicas e sentimento de notícias',
      'Geração de score direcional contínuo de -1.0 (venda forte) a +1.0 (compra forte)'
    ]
  },
  {
    step: 4,
    name: 'Filtro de EV & Risk Engine',
    module: 'src/risco/risk_engine.py & ev_calculator.py',
    description: 'Cálculo de Expected Value (EV) líquido descontando taxas de corretagem da Binance round-trip (compra + venda).',
    status: 'gate',
    details: [
      'Gate intransponível: EV líquido deve ser estritamente positivo após deduzir 0.15% - 0.20% de taxas estimadas',
      'Dimensionamento de posição baseado em Kelly Criterion fracionário',
      'Breaker diário de perda máxima (Daily Loss Circuit Breaker) persistido em banco',
      'Proteção rigorosa anti-posição-fantasma e verificação de saldo livre'
    ]
  },
  {
    step: 5,
    name: 'Execução Idempotente',
    module: 'src/executor/gerenciador_ordens.py',
    description: 'Envio seguro de ordens na Binance com tokens de idempotência, confirmação de preenchimento (fill) e timeout ativo.',
    status: 'active',
    details: [
      'Idempotência contra envio duplicado de ordens',
      'Checagem assíncrona de status do fill no WebSocket / REST da Binance',
      'Cancelamento automático de ordens pendentes após timeout',
      'Proteção de slippage em ordens a mercado'
    ]
  },
  {
    step: 6,
    name: 'Loop do Auto-Trader',
    module: 'src/servicos/testnet_auto_trader.py',
    description: 'Orquestrador contínuo rodando a cada 30 segundos, monitorando posições abertas e disparando saídas inteligentes (take profit / stop trailing).',
    status: 'active',
    details: [
      'Ciclos autônomos de 30 segundos (não-bloqueante)',
      'Trailing stop dinâmico baseado em ATR',
      'Gestão multiativo simultânea (BTC, ETH, BNB)',
      'Profit Guard para proteção de lucros acumulados'
    ]
  },
  {
    step: 7,
    name: 'Feedback & Reaprendizado',
    module: 'src/persistencia/repositorio_outcomes.py',
    description: 'Registro de desfechos reais de cada trade, realimentando a calibração de probabilidades e pesos do bandit.',
    status: 'feedback',
    details: [
      'Histórico completo de trades com métricas de slippage real',
      'Algoritmo Multi-Armed Bandit para ajuste de pesos de estratégias',
      'Exportação de métricas para walk-forward e pesquisa de edge',
      'Auditoria completa de decisões salvas no SQLite'
    ]
  }
];

export const MULTI_AGENT_ROLES: AgentRole[] = [
  {
    code: 'ORQ',
    name: 'Orquestrador',
    role: 'Líder de Arquitetura e Decisão',
    responsibilities: [
      'Triagem inicial de todas as tarefas',
      'Delegação para os agentes especialistas',
      'Garantia do cumprimento do protocolo multi-agente',
      'Coordenação dos gates de liberação'
    ],
    fileDoc: '.claude/00_orquestrador.md'
  },
  {
    code: 'GRD',
    name: 'Guardião Financeiro',
    role: 'Defesa e Segurança de Capital',
    responsibilities: [
      'Aprovação OBRIGATÓRIA antes de qualquer alteração em arquivos de dinheiro/risco',
      'Manter a trava de conta real (PERMITIR_CONTA_REAL=false) até validação de edge',
      'Verificação dos limites de exposição e stop loss',
      'Auditoria de conformidade com as regras de EV líquido'
    ],
    restrictedFiles: [
      'src/executor/',
      'src/risco/',
      'src/probabilidade/ev_calculator.py',
      'src/multiativo/profit_guard.py',
      'src/servicos/testnet_auto_trader.py',
      'src/main.py'
    ],
    fileDoc: '.claude/02_guardiao.md'
  },
  {
    code: 'QNT',
    name: 'Engenheiro Quantitativo',
    role: 'Pesquisa Matemática & Walk-Forward',
    responsibilities: [
      'Cálculo de métricas estatísticas (Sharpe, Sortino, Calmar)',
      'Execução de backtests walk-forward sem vazamento de futuro',
      'Calibração de probabilidades e decay temporal',
      'Pesquisa de novos fatores de edge de mercado'
    ],
    fileDoc: '.claude/04_quant.md'
  },
  {
    code: 'SIN',
    name: 'Especialista em Sinais & IA',
    role: 'Inteligência de Mercado',
    responsibilities: [
      'Engenharia de features a partir de klines e book',
      'Prompts e integração com Gemini e Ollama',
      'Análise de sentimento de notícias em tempo real',
      'Calibração de consenso entre indicadores e LLM'
    ],
    fileDoc: '.claude/03_sinais.md'
  },
  {
    code: 'EXE',
    name: 'Engenheiro de Execução',
    role: 'Conexão Binance & Latência',
    responsibilities: [
      'Gerenciamento de conexões REST e WebSockets Binance',
      'Tratamento de rate limits e códigos de erro da exchange',
      'Garantia de idempotência e cancelamento de ordens zumbis',
      'Minimização de slippage e latência de rede'
    ],
    fileDoc: '.claude/05_execucao.md'
  },
  {
    code: 'REV',
    name: 'Revisor Técnico',
    role: 'Qualidade, Docs e Manutenção de Estado',
    responsibilities: [
      'Manutenção contínua do arquivo .claude/contexto.md',
      'Inspeção pós-commit e garantia de 100% testes verdes',
      'Garantia de que nenhum bug seja camuflado por exceções mudas',
      'Documentação de decisões arquiteturais (DAs)'
    ],
    fileDoc: '.claude/01_revisor.md'
  }
];

export const ALL_DRIVE_ITEMS: DriveFileItem[] = [
  // Pastas principais
  {
    id: '1R3arSRsY0PMhwZnA994tX4pi7RJHrMIh',
    name: '.claude',
    mimeType: 'application/vnd.google-apps.folder',
    isFolder: true,
    category: 'folder',
    description: 'Sistema completo de orquestração multi-agente: 10 agentes especializados, contexto do projeto, lições aprendidas (skill.md) e relatórios de execução.'
  },
  {
    id: '1NI6QmDalghITqP04Hmx0SNc1oMWDwICS',
    name: 'src',
    mimeType: 'application/vnd.google-apps.folder',
    isFolder: true,
    category: 'folder',
    description: 'Código-fonte principal da aplicação Python. Contém 25 subpacotes com pipeline de sinais, risco, execução, persistência e auto-trader.'
  },
  {
    id: '1EgA_wWOycreNbwjE3HnHz9eKRJlDAhlH',
    name: 'tests',
    mimeType: 'application/vnd.google-apps.folder',
    isFolder: true,
    category: 'folder',
    description: 'Suíte de testes automatizados com 51 arquivos de teste e 346 asserções verdes (100% de aprovação).'
  },
  {
    id: '1YXfeuj6MCD1Vk3ekIP7coIjxtGYJ7jZg',
    name: 'scripts',
    mimeType: 'application/vnd.google-apps.folder',
    isFolder: true,
    category: 'folder',
    description: 'Scripts operacionais e de pesquisa: backtest walk-forward, pesquisa de edge, reconciliação de ordens e testes de chave Gemini.'
  },
  {
    id: '1Z2RjYTsswHY_96gfnfAxAcKwWAY0RDNe',
    name: 'frontend',
    mimeType: 'application/vnd.google-apps.folder',
    isFolder: true,
    category: 'folder',
    description: 'Interface gráfica web (Dashboard) para acompanhamento em tempo real dos sinais, ordens, saldo e status do bot.'
  },
  {
    id: '1hK-lEF2mUmIIeAdHhpn9oyLBSXFvoTgX',
    name: 'oraculo.egg-info',
    mimeType: 'application/vnd.google-apps.folder',
    isFolder: true,
    category: 'folder',
    description: 'Metadados de distribuição do pacote Python.'
  },

  // Arquivos essenciais da raiz
  {
    id: '1sGWLf9u4vsj-a0h54A82jyTUI6mejUkh',
    name: 'README.md',
    mimeType: 'text/markdown',
    isFolder: false,
    category: 'doc',
    size: '4.8 KB',
    description: 'Documentação principal: visão geral do Oraculo, etapas do pipeline, diretrizes de segurança, comandos de execução e rotas da API.'
  },
  {
    id: '1OYUPiX450jJva9kd-ue1lXzPKBQ3xl5v',
    name: 'CLAUDE.md',
    mimeType: 'text/markdown',
    isFolder: false,
    category: 'doc',
    size: '12.4 KB',
    description: 'Protocolo de governança de IA para Claude Code: regras de delegação, mapa real x alvo, travas de modificação e diretrizes de revisão.'
  },
  {
    id: '1JFUKFqEvbovpo-1_LsYrAfP0vkRoKEL0',
    name: 'AGENTS.md',
    mimeType: 'text/markdown',
    isFolder: false,
    category: 'doc',
    size: '11.8 KB',
    description: 'Protocolo de agentes adaptado para ambientes Codex / OpenAI.'
  },
  {
    id: '1SmsG73gAVJ6_AxsT5EeRRiJeaHsXJ5AG',
    name: 'up.md',
    mimeType: 'text/markdown',
    isFolder: false,
    category: 'doc',
    size: '22.1 KB',
    description: 'Guia mestre de transição Testnet -> Capital Real: metas matemáticas realistas, desmontagem do mito de 10%/dia, plano de 50-100 USDT e resiliência sem IA de nuvem.'
  },
  {
    id: '1ijX78tHF8U54IYjygnmAIm8XLVkqMT8H',
    name: 'log.txt',
    mimeType: 'text/plain',
    isFolder: false,
    category: 'log',
    size: '680 KB',
    description: 'Logs estruturados em JSON Lines da execução mais recente em tempo real (13/09/2026), demonstrando avaliações contínuas de pares ETH, BNB e BTC.'
  },
  {
    id: '1wvwyRbIGHN8yKostANOy3YLB66P43rO1',
    name: 'pyproject.toml',
    mimeType: 'application/octet-stream',
    isFolder: false,
    category: 'config',
    size: '2.1 KB',
    description: 'Configuração de empacotamento, formatação de código (Black, Ruff) e parâmetros do pytest.'
  },
  {
    id: '1tQGIbwUw7CzN43ahAMbN7zuxbQlZz_Q2',
    name: 'requirements.txt',
    mimeType: 'text/plain',
    isFolder: false,
    category: 'config',
    size: '1.4 KB',
    description: 'Dependências Python fixadas: fastapi, uvicorn, pydantic, ccxt, google-genai, scikit-learn, pytest, pandas, numpy.'
  },
  {
    id: '1119wOD_unKvcW7xviajtlXMp73aUldYK',
    name: '.env.example',
    mimeType: 'application/octet-stream',
    isFolder: false,
    category: 'config',
    size: '1.1 KB',
    description: 'Modelo de variáveis de ambiente: chaves de API da Binance (testnet e produção), GEMINI_API_KEY, limites de risco e flags de operação.'
  },
  {
    id: '1g_kJSvHSJnkEqRWnEEpWFLOQ9VDrzpTN',
    name: '.env',
    mimeType: 'application/octet-stream',
    isFolder: false,
    category: 'config',
    size: '1.2 KB',
    description: 'Arquivo de configuração local com chaves de teste da Binance e parametrizações ativas.'
  },
  {
    id: '1uluBfEaHWszDBwt8iTpfGbOD5tWKO48O',
    name: 'start.sh',
    mimeType: 'text/x-sh',
    isFolder: false,
    category: 'script',
    size: '640 B',
    description: 'Script Linux/macOS para inicialização do banco SQLite, checagem de ambiente e subida do servidor FastAPI.'
  },
  {
    id: '1N-Y9lxN2Ty6dz1A1hqCaQwpl2S8byjrY',
    name: 'start.bat',
    mimeType: 'application/x-msdos-program',
    isFolder: false,
    category: 'script',
    size: '720 B',
    description: 'Script Windows batch para inicialização rápida do bot e da interface.'
  },
  {
    id: '1BtSF_qPQgodH2bZ2sKGcQmI8s7ZuBDUD',
    name: '.pre-commit-config.yaml',
    mimeType: 'application/octet-stream',
    isFolder: false,
    category: 'config',
    size: '850 B',
    description: 'Hooks de verificação de commits: linting, trailing-whitespace e formatação automática.'
  }
];

export const LOG_METRICS_EXTRACTED: LogMetric[] = [
  {
    timestamp: '2026-09-13T01:34:17.042Z',
    symbol: 'ETHUSDT',
    action: 'SELL',
    scoreFinal: -0.796,
    scoreNumerico: -1.000,
    scoreLlm: -0.008,
    confianca: 0.90,
    motivo: 'venda_hibrida (pressão de livro 0.300, sentimento -0.15)',
    tamanho: 0.0358
  },
  {
    timestamp: '2026-09-13T01:34:17.050Z',
    symbol: 'BNBUSDT',
    action: 'BUY',
    scoreFinal: 0.826,
    scoreNumerico: 1.000,
    scoreLlm: 0.038,
    confianca: 0.90,
    motivo: 'compra_hibrida (pressão de livro 0.067, variação prevista +0.38%)',
    tamanho: 0.0371
  },
  {
    timestamp: '2026-09-13T01:34:17.059Z',
    symbol: 'ETHBTC',
    action: 'SELL',
    scoreFinal: -0.778,
    scoreNumerico: -1.000,
    scoreLlm: 0.037,
    confianca: 0.90,
    motivo: 'venda_hibrida (spread 0.00031, pressão 0.481)',
    tamanho: 0.0349
  },
  {
    timestamp: '2026-09-13T01:34:17.067Z',
    symbol: 'BNBBTC',
    action: 'BUY',
    scoreFinal: 0.827,
    scoreNumerico: 1.000,
    scoreLlm: 0.031,
    confianca: 0.90,
    motivo: 'compra_hibrida (spread 0.00011, sentimento positivo)',
    tamanho: 0.0372
  },
  {
    timestamp: '2026-09-13T01:34:17.075Z',
    symbol: 'BNBETH',
    action: 'BUY',
    scoreFinal: 0.826,
    scoreNumerico: 1.000,
    scoreLlm: 0.016,
    confianca: 0.90,
    motivo: 'compra_hibrida (pressão -0.015, previsão +0.39%)',
    tamanho: 0.0371
  }
];

export const STRATEGIC_FINDINGS = [
  {
    title: 'Engenharia de Software de Alto Rigor',
    category: 'Arquitetura',
    badge: 'Excelente',
    badgeColor: 'emerald',
    description: 'O projeto não é um simples script de trading: possui arquitetura modular com mais de 25 subpacotes em src/, 346 testes automatizados com cobertura ampla e separação rigorosa de responsabilidades.'
  },
  {
    title: 'Governança & Proteção de Capital (Guardião)',
    category: 'Segurança',
    badge: 'Impenetrável',
    badgeColor: 'blue',
    description: 'A execução em conta real com dinheiro de verdade está bloqueada por desenho (PERMITIR_CONTA_REAL=false). O código só aceitará ordens reais se uma chave de validação matemática comprovar edge líquido após custos.'
  },
  {
    title: 'Desafio do Edge Líquido vs Taxas',
    category: 'Quantitativo',
    badge: 'Atenção Crítica',
    badgeColor: 'amber',
    description: 'Conforme evidenciado em up.md e nos estudos de walk-forward, o maior obstáculo atual não é o código, mas o edge bruto vs o custo da Binance (taxas maker/taker round-trip de 0.15%-0.20%). Micro-operações de 1m sofrem com atrito de taxas.'
  },
  {
    title: 'Desacoplamento e Fail-Open da Inteligência Artificial',
    category: 'Resiliência',
    badge: 'Robusto',
    badgeColor: 'purple',
    description: 'A IA (Gemini/Ollama) não bloqueia o loop operacional de 30s. Possui cache, throttle de 300 segundos e estratégia fail-open com fallback automático para heurística matemática local.'
  },
  {
    title: 'Correção Recente: BUG-17 Resolvido',
    category: 'Histórico',
    badge: 'Corrigido',
    badgeColor: 'cyan',
    description: 'Recentemente foi corrigido um bug sutil onde a rota /v1/auto/start passava argumentos posicionais para o ClienteBinance, caindo em um fallback padrão de $10 que atrasava a expansão das ordens.'
  }
];
