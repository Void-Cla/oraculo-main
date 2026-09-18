import express from 'express';
import path from 'path';
import { exec } from 'child_process';
import { promisify } from 'util';
import { createServer as createViteServer } from 'vite';
import { GoogleGenAI } from '@google/genai';
import dotenv from 'dotenv';

const execAsync = promisify(exec);
dotenv.config();

let aiClient: GoogleGenAI | null = null;
function getAi(): GoogleGenAI | null {
  if (!aiClient && process.env.GEMINI_API_KEY) {
    aiClient = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });
  }
  return aiClient;
}

async function startServer() {
  const app = express();
  const PORT = 3000;
  app.use(express.json({ limit: '15mb' }));

  // Health endpoint
  app.get('/api/health', (_req, res) => {
    res.json({
      status: 'ok',
      hasGeminiKey: Boolean(process.env.GEMINI_API_KEY),
      timestamp: new Date().toISOString(),
    });
  });

  // Executar Ciclo Rápido do Oráculo (Python Engine)
  app.post('/api/oraculo/executar-ciclo', async (_req, res) => {
    try {
      const { stdout } = await execAsync('python3 -m backend_oraculo.executar_ciclo ciclo', {
        cwd: process.cwd(),
        timeout: 10000,
      });
      const dados = JSON.parse(stdout);
      return res.json(dados);
    } catch (err: any) {
      console.error('Erro ao executar ciclo do Oráculo:', err);
      return res.status(500).json({
        erro: 'Falha ao executar ciclo do motor Oráculo em Python',
        detalhes: err.message,
      });
    }
  });

  // Testar Conexão Oficial e Latência da Binance
  app.get('/api/oraculo/conexao-binance', async (_req, res) => {
    try {
      const { stdout } = await execAsync('python3 -m backend_oraculo.executar_ciclo testar_conexao', {
        cwd: process.cwd(),
        timeout: 5000,
      });
      const dados = JSON.parse(stdout);
      return res.json(dados);
    } catch (err: any) {
      console.error('Erro ao testar conexão com a Binance:', err);
      return res.status(500).json({
        erro: 'Falha ao testar conexão com a Binance',
        detalhes: err.message,
      });
    }
  });

  // Obter Status Geral e Métricas de Lucro Líquido
  app.get('/api/oraculo/status', async (_req, res) => {
    try {
      const { stdout } = await execAsync('python3 -m backend_oraculo.executar_ciclo status', {
        cwd: process.cwd(),
        timeout: 5000,
      });
      const dados = JSON.parse(stdout);
      return res.json(dados);
    } catch (err: any) {
      console.error('Erro ao obter status:', err);
      return res.status(500).json({
        erro: 'Falha ao obter status do Oráculo',
        detalhes: err.message,
      });
    }
  });

  // Obter Histórico de Trades com Auditoria de Taxas e Lucro
  app.get('/api/oraculo/historico-trades', async (_req, res) => {
    try {
      const { stdout } = await execAsync('python3 -m backend_oraculo.executar_ciclo historico_trades', {
        cwd: process.cwd(),
        timeout: 5000,
      });
      const dados = JSON.parse(stdout);
      return res.json(dados);
    } catch (err: any) {
      console.error('Erro ao obter histórico:', err);
      return res.status(500).json({
        erro: 'Falha ao consultar histórico de trades',
        detalhes: err.message,
      });
    }
  });

  // Atualização Periódica de IA a cada 2 Horas (Gemini 3.8 Flash -> Python State)
  app.post('/api/oraculo/atualizar-ia-2h', async (req, res) => {
    try {
      const { resumoMercado } = req.body;
      const ai = getAi();

      let pesoNoticias = 0.18;
      let biasMacro = 0.14;
      let regime = 'LATERAL_COM_PRESSAO_COMPRADORA';
      let intensidade = 'MEDIO';
      let resumoPtBr = 'Fluxo institucional contínuo. Risco de cauda baixo para a janela de 2 horas.';
      let fatores = ['Baixo spread no par BTCUSDT', 'Ausência de notícias de choque macro', 'Suporte local validado'];

      if (ai) {
        const prompt = `Você é o Estrategista Quantitativo Chefe do Oráculo Trading Bot (Binance Spot).
Sua missão é definir os pesos e viés para a janela de TRADING DAS PRÓXIMAS 2 HORAS.
Contexto do mercado atual:
${resumoMercado ? JSON.stringify(resumoMercado) : 'Mercado cripto estável com volume médio e baixa volatilidade no BTC/ETH.'}

Aja com precisão analítica. Responda estritamente em JSON puro sem markdown ou tags adicionais:
{
  "peso_noticias_ia": 0.18,
  "bias_macro_direcional": 0.15,
  "regime_mercado": "TENDENCIA_ALTA",
  "intensidade_impacto_noticias": "MEDIO",
  "resumo_executivo_ptbr": "Resumo analítico em português (PT-BR) de 2 frases sobre o direcionamento para as próximas 2h.",
  "fatores_chave": ["Fator 1 relevante", "Fator 2 relevante", "Fator 3 relevante"]
}`;

        const response = await ai.models.generateContent({
          model: 'gemini-3.8-flash',
          contents: prompt,
        });

        try {
          const textoLimpo = response.text?.replace(/```json/g, '').replace(/```/g, '').trim() || '{}';
          const parsed = JSON.parse(textoLimpo);
          if (parsed.peso_noticias_ia !== undefined) pesoNoticias = parsed.peso_noticias_ia;
          if (parsed.bias_macro_direcional !== undefined) biasMacro = parsed.bias_macro_direcional;
          if (parsed.regime_mercado) regime = parsed.regime_mercado;
          if (parsed.intensidade_impacto_noticias) intensidade = parsed.intensidade_impacto_noticias;
          if (parsed.resumo_executivo_ptbr) resumoPtBr = parsed.resumo_executivo_ptbr;
          if (Array.isArray(parsed.fatores_chave)) fatores = parsed.fatores_chave;
        } catch (parseErr) {
          console.warn('Fallback ao parsear JSON do Gemini, usando valores calibrados:', parseErr);
        }
      }

      // Envia os dados para atualizar o estado do Python
      const payloadPython = JSON.stringify({
        peso_noticias_ia: pesoNoticias,
        bias_macro_direcional: biasMacro,
        regime_mercado: regime,
        intensidade_impacto_noticias: intensidade,
        resumo_executivo_ptbr: resumoPtBr,
        fatores_chave: fatores,
      });

      const { stdout } = await execAsync(
        `python3 -m backend_oraculo.executar_ciclo atualizar_ia '${payloadPython.replace(/'/g, "\\'")}'`,
        { cwd: process.cwd(), timeout: 5000 }
      );

      const novoEstadoIa = JSON.parse(stdout);
      return res.json({
        sucesso: true,
        novoEstadoIa,
        geminiUtilizado: Boolean(ai),
      });
    } catch (err: any) {
      console.error('Erro na atualização de IA 2h:', err);
      return res.status(500).json({
        erro: 'Falha ao atualizar parâmetros de IA de 2 horas',
        detalhes: err.message,
      });
    }
  });

  // Decisão Assistida por IA para Situações de Incerteza
  app.post('/api/oraculo/decisao-assistida', async (req, res) => {
    try {
      const { par, features, projecaoLucro } = req.body;
      const ai = getAi();
      if (!ai) {
        return res.json({
          recomendacao: 'ABSTER',
          justificativa: 'Sem chave Gemini configurada para desempate assistido. Motor local priorizou prudência de capital.',
        });
      }

      const prompt = `Você é o Guardião de Risco e Desempate do Oráculo Trading Bot (Binance).
Avalie se devemos autorizar esta operação na janela rápida:
Par: ${par}
Features: ${JSON.stringify(features)}
Projeção Financeira:
- Lucro Bruto: $${projecaoLucro?.lucroBruto}
- Taxas Totais: $${projecaoLucro?.taxasTotais}
- Lucro Líquido Estimado: $${projecaoLucro?.lucroLiquido}
- Lucro Mínimo Exigido (+0,01 centavo): $0.01

Regra Suprema: O lucro líquido REAL após todas as taxas da Binance DEVE ser estritamente maior ou igual a $0.01 centavo.
Responda em JSON:
{
  "recomendacao": "EXECUTAR" | "ABSTER",
  "confianca_pct": 85,
  "justificativa_ptbr": "Explicação técnica direta e clara em português"
}`;

      const response = await ai.models.generateContent({
        model: 'gemini-3.8-flash',
        contents: prompt,
      });

      const textoLimpo = response.text?.replace(/```json/g, '').replace(/```/g, '').trim() || '{}';
      const parsed = JSON.parse(textoLimpo);
      return res.json(parsed);
    } catch (err: any) {
      return res.status(500).json({ erro: err.message });
    }
  });

  // Gemini AI Question/Analysis Endpoint (Pasta do Drive / Código)
  app.post('/api/gemini/ask', async (req, res) => {
    try {
      const { question, context } = req.body;
      if (!question) {
        return res.status(400).json({ error: 'Question is required' });
      }

      const ai = getAi();
      if (!ai) {
        return res.status(503).json({
          error: 'Gemini API key is not configured in server environment.',
          fallback: true,
        });
      }

      const prompt = `Você é um analista sênior de software e especialista em sistemas de trading algorítmico e arquiteturas de agentes.
Você está analisando o Oráculo — Bot de Trading Algorítmico para Binance, com sistema multi-agente, foco em lucro líquido (+0,01 centavo), previsão direcional e IA a cada 2h.

Contexto atual do projeto:
${context ? context.slice(0, 30000) : 'Sem contexto adicional fornecido.'}

Pergunta do usuário:
${question}

Responda em português (PT-BR) de forma objetiva, técnica, elegante e estruturada com formatação Markdown limpa.`;

      const response = await ai.models.generateContent({
        model: 'gemini-3.8-flash',
        contents: prompt,
      });

      return res.json({
        answer: response.text,
        model: 'gemini-3.8-flash',
      });
    } catch (err: any) {
      console.error('Gemini API error:', err);
      return res.status(500).json({
        error: err?.message || 'Failed to process AI query',
      });
    }
  });

  // Vite middleware for development vs static build in production
  if (process.env.NODE_ENV !== 'production') {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), 'dist');
    app.use(express.static(distPath));
    app.get('*', (_req, res) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`Server running on http://localhost:${PORT}`);
  });
}

startServer();
