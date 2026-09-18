const DASHBOARD_SYMBOL = "BTCUSDT";
const NEWS_SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ETHBTC", "BNBBTC", "BNBETH"];
const LIMITE_PERCENTUAL_PERFIS = 100;
const TAB_COPY = {
  dashboard: {
    titulo: "Visao geral",
    subtitulo: "Conta, resultado e mercado em uma leitura unica, limpa e objetiva.",
  },
  bot: {
    titulo: "Controle do bot",
    subtitulo: "Estrategias independentes com capital separado e historico dedicado.",
  },
  noticias: {
    titulo: "Radar de noticias",
    subtitulo: "Fontes com retorno confiavel, prioridade por impacto e leitura rapida.",
  },
};

const refs = {
  painelLogin: document.getElementById("painelLogin"),
  painelApp: document.getElementById("painelApp"),
  formLogin: document.getElementById("formLogin"),
  apiKey: document.getElementById("apiKey"),
  apiSecret: document.getElementById("apiSecret"),
  usarTestnet: document.getElementById("usarTestnet"),
  btnEntrar: document.getElementById("btnEntrar"),
  mensagemLogin: document.getElementById("mensagemLogin"),
  nomeSessao: document.getElementById("nomeSessao"),
  detalheSessao: document.getElementById("detalheSessao"),
  btnAtualizar: document.getElementById("btnAtualizar"),
  btnSair: document.getElementById("btnSair"),
  statusConexao: document.getElementById("statusConexao"),
  statusModo: document.getElementById("statusModo"),
  ultimaAtualizacao: document.getElementById("ultimaAtualizacao"),
  statusAviso: document.getElementById("statusAviso"),
  tituloTela: document.getElementById("tituloTela"),
  subtituloTela: document.getElementById("subtituloTela"),
  dashContaModo: document.getElementById("dashContaModo"),
  dashContaResumo: document.getElementById("dashContaResumo"),
  dashMercadoStatus: document.getElementById("dashMercadoStatus"),
  dashMercadoResumo: document.getElementById("dashMercadoResumo"),
  dashAcaoAtual: document.getElementById("dashAcaoAtual"),
  dashModeloResumo: document.getElementById("dashModeloResumo"),
  dashModeloMotivo: document.getElementById("dashModeloMotivo"),
  dashPnlStatus: document.getElementById("dashPnlStatus"),
  dashPnlResumo: document.getElementById("dashPnlResumo"),
  dashTaxasResumo: document.getElementById("dashTaxasResumo"),
  dashScannerStatus: document.getElementById("dashScannerStatus"),
  tabelaOportunidades: document.getElementById("tabelaOportunidades"),
  chartPrecos: document.getElementById("chartPrecos"),
  chartComparativo: document.getElementById("chartComparativo"),
  chartLucroCiclos: document.getElementById("chartLucroCiclos"),
  botStatus: document.getElementById("botStatus"),
  botToggleBtn: document.getElementById("botToggleBtn"),
  botCapitalStatus: document.getElementById("botCapitalStatus"),
  botResumo: document.getElementById("botResumo"),
  botPerfis: document.getElementById("botPerfis"),
  botPerfisStatus: document.getElementById("botPerfisStatus"),
  botPerfisSalvar: document.getElementById("botPerfisSalvar"),
  botCicloStatus: document.getElementById("botCicloStatus"),
  botCicloResumo: document.getElementById("botCicloResumo"),
  botHistoricoPerfisDetalhe: document.getElementById("botHistoricoPerfisDetalhe"),
  newsTabs: document.getElementById("newsTabs"),
  newsResumo: document.getElementById("newsResumo"),
  newsFontesPeso: document.getElementById("newsFontesPeso"),
  newsHeadlinesTotal: document.getElementById("newsHeadlinesTotal"),
  newsHeadlines: document.getElementById("newsHeadlines"),
  newsFrames: document.getElementById("newsFrames"),
  newsPreviewStatus: document.getElementById("newsPreviewStatus"),
  newsAtualizacao: document.getElementById("newsAtualizacao"),
  sidebarConta: document.getElementById("sidebarConta"),
  sidebarContaTexto: document.getElementById("sidebarContaTexto"),
  sidebarModelo: document.getElementById("sidebarModelo"),
  sidebarModeloTexto: document.getElementById("sidebarModeloTexto"),
  sidebarBot: document.getElementById("sidebarBot"),
  sidebarBotTexto: document.getElementById("sidebarBotTexto"),
  sidebarNoticias: document.getElementById("sidebarNoticias"),
  sidebarNoticiasTexto: document.getElementById("sidebarNoticiasTexto"),
};

const state = {
  autenticado: false,
  tabAtual: "dashboard",
  simboloNoticiasAtual: NEWS_SYMBOLS[0],
  painel: null,
  modeloStatus: null,
  auto: null,
  noticias: {},
  sessao: null,
  pollingId: null,
  botCarregando: false,
  perfisCarregando: false,
  newsFonteAtual: "",
  backendIndisponivel: false,
};

function escapeHtml(valor) {
  return String(valor ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
}

function readNumber(valor, fallback = 0) {
  const numero = Number(valor);
  return Number.isFinite(numero) ? numero : fallback;
}

function formatCurrency(valor, moeda = "USD") {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: moeda, minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(readNumber(valor));
}

function formatNumber(valor, casas = 2) {
  return new Intl.NumberFormat("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas }).format(readNumber(valor));
}

function formatPercent(valor, jaEmPct = true) {
  const numero = readNumber(valor);
  return `${formatNumber(jaEmPct ? numero : numero * 100, 2)}%`;
}

function arredondarUsdt(valor) {
  return Number(Math.max(0, readNumber(valor, 0)).toFixed(8));
}

function detalheErroApi(payload, texto) {
  if (payload && typeof payload.detail === "string" && payload.detail.trim()) return payload.detail.trim();
  if (payload && typeof payload.erro === "string" && payload.erro.trim()) return payload.erro.trim();
  if (payload && typeof payload.detail === "object") return JSON.stringify(payload.detail);
  return String(texto || "").trim();
}

function mensagemErroApi(status, payload, texto) {
  if (status === 401) return "Sessao expirada ou ausente. Faca login novamente.";
  if (status === 502) return "Servidor do Oraculo indisponivel (502). A sincronizacao automatica foi pausada.";
  return detalheErroApi(payload, texto) || `HTTP ${status}`;
}

function parseTimestamp(valor) {
  if (valor == null || valor === "") return null;
  if (typeof valor === "number" && Number.isFinite(valor)) {
    return valor < 10_000_000_000 ? valor * 1000 : valor;
  }
  if (typeof valor === "string") {
    const texto = valor.trim();
    if (!texto) return null;
    const numero = Number(texto);
    if (Number.isFinite(numero)) return numero < 10_000_000_000 ? numero * 1000 : numero;
    const parsed = Date.parse(texto);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function formatDate(valor) {
  const ts = parseTimestamp(valor);
  if (!ts) return "--";
  const data = new Date(ts);
  return Number.isNaN(data.getTime()) ? "--" : new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "medium" }).format(data);
}

function normalizarCodigo(valor) {
  return String(valor ?? "").trim().toUpperCase();
}

function traduzirAcao(valor) {
  const mapa = { BUY: "Comprar", SELL: "Vender", HOLD: "Aguardando", COMPRA: "Comprar", VENDA: "Vender", PAUSADO: "Pausado", SEM_HISTORICO: "Sem historico", CICLO: "Ciclo" };
  return mapa[normalizarCodigo(valor)] || (valor ? String(valor) : "Aguardando");
}

function traduzirEstadoCiclo(valor) {
  const mapa = {
    PAUSADO: "Pausado",
    AGUARDANDO_ENTRADA: "Aguardando compra",
    EM_POSICAO: "Em posicao",
    INDISPONIVEL: "Indisponivel",
  };
  return mapa[normalizarCodigo(valor)] || (valor ? String(valor) : "Aguardando");
}

function traduzirMotivo(valor) {
  const mapa = {
    bot_pausado: "Bot desligado",
    sessao_ausente: "Sessao ausente",
    perfil_selecionado: "Perfil selecionado",
    nenhum_perfil_encontrou_lucro_liquido_viavel: "Nenhum perfil encontrou lucro liquido viavel",
    conta_real_bloqueada: "Conta real bloqueada",
    trade_diario_ja_usado_hoje: "Trade diario ja foi usado hoje",
    sinal_hold: "Sinal em espera",
    bloqueado_por_lucro_liquido_minimo: "Lucro liquido previsto abaixo do minimo",
    bloqueado_por_confirmacao_multi_timeframe: "Confirmacao multi-timeframe insuficiente",
    confirmacao_multi_timeframe_superada_por_consenso: "Consenso forte permitiu entrada",
    entrada_sem_confirmacao_composta: "Entrada sem confirmacao composta suficiente",
    saida_sem_confirmacao_composta: "Saida sem confirmacao composta suficiente",
    saldo_legado_abaixo_do_minimo_operacional: "Saldo legado abaixo do minimo operacional da Binance",
    notional_abaixo_do_minimo_saida: "Saida abaixo do minimo operacional da Binance",
    notional_ajuste_falhou_saida: "Binance recusou a saida por valor minimo insuficiente",
    proxima_acao_esperada_e_compra: "Extrato do par indica que o bot deve aguardar compra",
    tempo_minimo_da_estrategia_nao_atingido: "Perfil ainda esta no tempo minimo de posicao",
    perfil_aguardando_sinal_de_saida: "Perfil aguarda um sinal de saida mais claro",
    ciclo_reconciliado_pelo_extrato: "Ciclo restaurado pela ultima operacao do extrato",
    ciclo_assumido_do_saldo_da_conta: "Ciclo restaurado pelo saldo atual da conta",
    ultima_compra_aberta_no_par: "Ultima compra do par ainda esta aberta",
    saldo_base_remanescente_apos_venda: "Ainda existe saldo base remanescente no par",
    ultima_venda_encerrada_sem_posicao_aberta: "Ultima venda encerrou a posicao; proxima perna e compra",
    ultima_compra_ja_foi_encerrada: "Ultima compra do par ja foi encerrada",
    sem_historico_no_par: "Sem historico recente no par",
    aguardando_primeira_leitura: "Aguardando primeira leitura de seguranca",
    sinal_defasado: "Sinal defasado para executar agora",
    sinal_com_timestamp_futuro: "Sinal com timestamp futuro",
    saldo_total_zerado: "Saldo total indisponivel para operar",
    mercado_preco_invalido: "Preco de mercado invalido para operar",
    historico_trades_com_timestamp_futuro: "Historico com timestamp futuro",
    venda_sem_ciclo_sincronizado: "Venda bloqueada sem ciclo sincronizado",
    entrada_da_posicao_sem_compra_confirmada: "Posicao sem compra confirmada; venda bloqueada",
    venda_bloqueada_lucro_minimo_nao_atingido: "Venda bloqueada: lucro minimo ainda nao atingido",
    lucro_liquido_esperado_abaixo_do_minimo_do_perfil: "Compra bloqueada: lucro esperado abaixo do minimo do perfil",
    perfil_desativado: "Perfil desativado pelo cliente",
    saldo_quote_insuficiente_no_par: "Saldo da moeda de cotacao insuficiente para abrir posicao neste par",
    saldo_insuficiente: "Saldo insuficiente para executar a acao",
    fracao_calculada_invalida: "Fracao de entrada invalida para este ciclo",
    capital_do_perfil_abaixo_do_minimo: "Capital do perfil abaixo do minimo operacional",
    nenhum_sinal_confiavel_no_momento: "Nenhum sinal confiavel no momento",
  };
  const texto = String(valor ?? "").trim();
  if (!texto) return "Sem motivo recente";
  const partes = texto
    .split(/[;,|]+/g)
    .map((parte) => parte.trim())
    .filter(Boolean);
  if (partes.length > 1) {
    return partes
      .map((parte) => mapa[parte] || parte.replaceAll("_", " "))
      .join(" | ");
  }
  return mapa[texto] || texto.replaceAll("_", " ");
}

function badgeClass(valor) {
  const codigo = normalizarCodigo(valor);
  if (["LUCRO", "POSITIVO", "PNL_POSITIVO", "WIN"].includes(codigo)) return "badge badge--positive";
  if (["PERDA", "NEGATIVO", "PNL_NEGATIVO", "LOSS", "REJEITADA", "TRAVADO", "BLOQUEADO", "CANCELADA", "ERRO"].includes(codigo)) return "badge badge--danger";
  if (["HOLD", "AGUARDANDO", "AVISO", "INFO"].includes(codigo)) return "badge badge--info";
  if (["BUY", "SELL", "COMPRA", "VENDA", "OPERACIONAL", "SINCRONIZADO", "ATIVO", "EM_POSICAO", "PRONTO", "EXECUTADA"].includes(codigo)) return "badge badge--state";
  return "badge badge--soft";
}

function nomePerfil(perfilId) {
  const id = String(perfilId || "").trim().toLowerCase();
  return {
    todos: "Todos",
    mini: "Mini",
    ganancioso: "Ganancioso",
    diario: "Diario",
    sem_perfil: "Sem perfil",
  }[id] || String(perfilId || "Perfil");
}

function normalizarPerfil(valor) {
  const texto = String(valor || "").trim().toLowerCase();
  if (!texto) return "sem_perfil";
  if (texto.includes("mini")) return "mini";
  if (texto.includes("ganancioso") || texto.includes("greedy")) return "ganancioso";
  if (texto.includes("diario") || texto.includes("daily")) return "diario";
  return texto.replace(/[^a-z0-9_]+/g, "_") || "sem_perfil";
}

function obterPerfilHistorico(item) {
  return normalizarPerfil(item?.perfil_id || item?.perfil || item?.perfil_nome || item?.estrategia || item?.strategy);
}

function obterWinRatePayload(item) {
  const valor = item?.win_rate ?? item?.winrate ?? item?.taxa_acerto ?? item?.taxa_acerto_pct;
  return valor == null ? "--" : formatPercent(valor, readNumber(valor, 0) > 1);
}

function formatDurationMs(valor) {
  const totalSegundos = Math.max(0, Math.round(readNumber(valor, 0) / 1000));
  const horas = Math.floor(totalSegundos / 3600);
  const minutos = Math.floor((totalSegundos % 3600) / 60);
  if (horas > 0) return `${horas}h ${minutos}m`;
  if (minutos > 0) return `${minutos}m`;
  return `${totalSegundos}s`;
}

function renderMetricList(target, itens) {
  const validos = (itens || []).filter(Boolean);
  target.innerHTML = validos.length
    ? validos.map((item) => `
      <article class="metric ${escapeHtml(item.classe || "")}">
        <span class="metric__label">${escapeHtml(item.rotulo)}</span>
        <strong class="metric__value">${escapeHtml(item.valor)}</strong>
        <span class="metric__hint">${escapeHtml(item.detalhe || "")}</span>
      </article>`).join("")
    : `<article class="metric metric--empty"><strong class="metric__value">Sem dados</strong></article>`;
}

function formatChartValue(valor, modo = "number") {
  const numero = readNumber(valor, 0);
  if (modo === "currency") return `$${formatNumber(numero, Math.abs(numero) >= 100 ? 0 : 2)}`;
  if (modo === "percent") return formatPercent(numero, false);
  return formatNumber(numero, Math.abs(numero) >= 100 ? 0 : 2);
}

function formatChartDate(valor) {
  const ts = parseTimestamp(valor);
  if (!ts) return "";
  return new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date(ts));
}

function timestampGrafico(item) {
  return item?.ts ?? item?.timestamp ?? item?.created_ts ?? item?.open_time ?? item?.close_time ?? item?.horario ?? item?.data;
}

function drawChart(svg, series, options = {}) {
  const grupos = (series || []).filter((item) => Array.isArray(item.valores) && item.valores.length);
  if (!grupos.length) {
    svg.innerHTML = `<text x="24" y="120" class="chart-empty">Sem serie suficiente para comparar.</text>`;
    return;
  }
  const largura = 720;
  const altura = 240;
  const pad = { left: 64, right: 24, top: 24, bottom: 42 };
  const valores = grupos.flatMap((item) => item.valores.map((ponto) => readNumber(ponto.valor)));
  const min = Math.min(...valores);
  const max = Math.max(...valores);
  const amplitude = Math.max(max - min, max * 0.001, 1e-9);
  const areaW = largura - pad.left - pad.right;
  const areaH = altura - pad.top - pad.bottom;
  const linhas = [0, 0.5, 1].map((fator) => {
    const y = pad.top + (areaH * fator);
    const valorTick = max - (amplitude * fator);
    return `
      <line x1="${pad.left}" y1="${y.toFixed(2)}" x2="${largura - pad.right}" y2="${y.toFixed(2)}" class="chart-grid"></line>
      <text x="${pad.left - 10}" y="${(y + 4).toFixed(2)}" class="chart-axis-label" text-anchor="end">${escapeHtml(formatChartValue(valorTick, options.modoValor))}</text>`;
  }).join("");
  const serieBase = grupos[0].valores;
  const indicesData = [...new Set([0, Math.floor((serieBase.length - 1) / 2), serieBase.length - 1])].filter((idx) => idx >= 0);
  const datas = indicesData.map((idx) => {
    const ponto = serieBase[idx] || {};
    const x = pad.left + (areaW * (serieBase.length === 1 ? 0 : idx / (serieBase.length - 1)));
    const label = ponto.rotulo || formatChartDate(ponto.data);
    return label ? `<text x="${x.toFixed(2)}" y="${altura - 14}" class="chart-axis-label" text-anchor="middle">${escapeHtml(label)}</text>` : "";
  }).join("");
  const paths = grupos.map((serie) => {
    const path = serie.valores.map((ponto, index, lista) => {
      const x = pad.left + (areaW * (lista.length === 1 ? 0 : index / (lista.length - 1)));
      const y = pad.top + (areaH - (((readNumber(ponto.valor) - min) / amplitude) * areaH));
      return `${index === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    }).join(" ");
    const ultimo = serie.valores[serie.valores.length - 1];
    const xUltimo = pad.left + areaW;
    const yUltimo = pad.top + (areaH - (((readNumber(ultimo.valor) - min) / amplitude) * areaH));
    return `
      <path d="${path}" class="chart-line ${serie.classe}"></path>
      <circle cx="${xUltimo.toFixed(2)}" cy="${yUltimo.toFixed(2)}" r="4" class="chart-marker ${serie.classe || ""}"></circle>
      <text x="${(xUltimo - 6).toFixed(2)}" y="${(yUltimo - 8).toFixed(2)}" class="chart-value-label" text-anchor="end">${escapeHtml(formatChartValue(ultimo.valor, options.modoValor))}</text>`;
  }).join("");
  svg.innerHTML = `${linhas}${paths}${datas}`;
}

function drawBarChart(svg, pontos, options = {}) {
  const validos = (pontos || []).filter((ponto) => Number.isFinite(readNumber(ponto.valor, NaN)));
  if (!validos.length) {
    svg.innerHTML = `<text x="24" y="120" class="chart-empty">Sem ciclos encerrados para mostrar.</text>`;
    return;
  }
  const largura = 720;
  const altura = 240;
  const pad = { left: 64, right: 24, top: 26, bottom: 44 };
  const areaW = largura - pad.left - pad.right;
  const areaH = altura - pad.top - pad.bottom;
  const valores = validos.map((ponto) => readNumber(ponto.valor));
  const min = Math.min(0, ...valores);
  const max = Math.max(0, ...valores);
  const amplitude = Math.max(max - min, 1e-9);
  const yZero = pad.top + (areaH - (((0 - min) / amplitude) * areaH));
  const larguraBarra = Math.max(10, Math.min(34, (areaW / validos.length) * 0.62));
  const eixo = `
    <line x1="${pad.left}" y1="${yZero.toFixed(2)}" x2="${largura - pad.right}" y2="${yZero.toFixed(2)}" class="chart-grid chart-grid--zero"></line>
    <text x="${pad.left - 10}" y="${(pad.top + 6).toFixed(2)}" class="chart-axis-label" text-anchor="end">${escapeHtml(formatChartValue(max, options.modoValor))}</text>
    <text x="${pad.left - 10}" y="${(yZero + 4).toFixed(2)}" class="chart-axis-label" text-anchor="end">${escapeHtml(formatChartValue(0, options.modoValor))}</text>
    <text x="${pad.left - 10}" y="${(altura - pad.bottom).toFixed(2)}" class="chart-axis-label" text-anchor="end">${escapeHtml(formatChartValue(min, options.modoValor))}</text>`;
  const barras = validos.map((ponto, index) => {
    const valor = readNumber(ponto.valor);
    const xCentro = pad.left + (areaW * (validos.length === 1 ? 0.5 : index / (validos.length - 1)));
    const yValor = pad.top + (areaH - (((valor - min) / amplitude) * areaH));
    const y = Math.min(yZero, yValor);
    const h = Math.max(2, Math.abs(yZero - yValor));
    const classe = valor >= 0 ? "chart-bar--positive" : "chart-bar--danger";
    const labelY = valor >= 0 ? y - 8 : y + h + 14;
    return `
      <rect x="${(xCentro - larguraBarra / 2).toFixed(2)}" y="${y.toFixed(2)}" width="${larguraBarra.toFixed(2)}" height="${h.toFixed(2)}" rx="3" class="chart-bar ${classe}"></rect>
      <text x="${xCentro.toFixed(2)}" y="${labelY.toFixed(2)}" class="chart-value-label" text-anchor="middle">${escapeHtml(formatChartValue(valor, options.modoValor))}</text>`;
  }).join("");
  const indicesData = [...new Set([0, Math.floor((validos.length - 1) / 2), validos.length - 1])].filter((idx) => idx >= 0);
  const datas = indicesData.map((idx) => {
    const ponto = validos[idx] || {};
    const x = pad.left + (areaW * (validos.length === 1 ? 0.5 : idx / (validos.length - 1)));
    const label = ponto.rotulo || formatChartDate(ponto.data);
    return label ? `<text x="${x.toFixed(2)}" y="${altura - 14}" class="chart-axis-label" text-anchor="middle">${escapeHtml(label)}</text>` : "";
  }).join("");
  svg.innerHTML = `${eixo}${barras}${datas}`;
}

async function requestJson(url, options = {}) {
  let response;
  try {
    response = await fetch(url, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
  } catch {
    const erro = new Error("Servidor do Oraculo sem resposta. A sincronizacao automatica foi pausada.");
    erro.status = 502;
    throw erro;
  }
  const texto = await response.text();
  let payload = {};
  if (texto) {
    try {
      payload = JSON.parse(texto);
    } catch {
      payload = { detail: texto };
    }
  }
  if (!response.ok) {
    const erro = new Error(mensagemErroApi(response.status, payload, texto));
    erro.status = response.status;
    throw erro;
  }
  return payload;
}

function limparSessaoExpirada(mensagem = "Sessao expirada. Faca login novamente.") {
  state.autenticado = false;
  state.sessao = null;
  state.painel = null;
  state.modeloStatus = null;
  state.auto = null;
  state.noticias = {};
  state.newsFonteAtual = "";
  stopPolling();
  refs.mensagemLogin.textContent = mensagem;
  renderSession();
  renderDashboard();
  renderBot();
  renderNews();
}

function definirAvisoStatus(mensagem, tipo = "info") {
  if (!refs.statusAviso) return;
  refs.statusAviso.className = `status-note status-note--${tipo}`;
  refs.statusAviso.textContent = mensagem;
}

function marcarBackendIndisponivel(erro) {
  state.backendIndisponivel = true;
  stopPolling();
  refs.statusConexao.className = "badge badge--danger";
  refs.statusConexao.textContent = "Servidor indisponivel";
  refs.ultimaAtualizacao.textContent = "Sincronizacao pausada por erro 502.";
  definirAvisoStatus("A API retornou 502. A leitura automatica foi pausada para evitar spam; use Atualizar quando o backend voltar.", "warning");
  if (refs.botCapitalStatus) refs.botCapitalStatus.textContent = erro?.message || "Backend indisponivel (502).";
}

function limparBackendIndisponivel() {
  if (!state.backendIndisponivel) return;
  state.backendIndisponivel = false;
  definirAvisoStatus("Conexao restaurada.", "info");
}

function applyAuth() {
  refs.painelLogin.classList.toggle("hidden", state.autenticado);
  refs.painelApp.classList.toggle("hidden", !state.autenticado);
}

function activateTab(tab) {
  state.tabAtual = tab;
  document.querySelectorAll(".nav-tabs__item").forEach((btn) => btn.classList.toggle("nav-tabs__item--active", btn.dataset.tab === tab));
  document.querySelectorAll(".tab-view").forEach((view) => view.classList.toggle("tab-view--active", view.id === `tab-${tab}`));
  refs.tituloTela.textContent = TAB_COPY[tab].titulo;
  refs.subtituloTela.textContent = TAB_COPY[tab].subtitulo;
  if (tab === "noticias" && !Object.keys(state.noticias).length) {
    carregarNoticias(false).catch((error) => {
      if (error instanceof Error && error.status === 502) marcarBackendIndisponivel(error);
      refs.newsAtualizacao.className = "badge badge--danger";
      refs.newsAtualizacao.textContent = error instanceof Error ? "Falha ao carregar" : "Falha";
    });
  }
}

function renderSession() {
  applyAuth();
  if (!state.autenticado || !state.sessao) {
    refs.nomeSessao.textContent = "Conta nao conectada";
    refs.detalheSessao.textContent = "Sem sessao ativa";
    refs.statusConexao.className = "badge badge--soft";
    refs.statusConexao.textContent = "Aguardando login";
    refs.statusModo.className = "badge badge--soft";
    refs.statusModo.textContent = "Sem sessao";
    definirAvisoStatus("Sem avisos.", "info");
    return;
  }
  refs.nomeSessao.textContent = state.sessao.nome_exibicao || "Conta Binance";
  refs.detalheSessao.textContent = `${state.sessao.api_key_mascarada || "--"} - ${state.sessao.id_conta || "--"}`;
  refs.statusConexao.className = "badge badge--state";
  refs.statusConexao.textContent = "Conectado";
  refs.statusModo.className = state.sessao.modo_testnet ? "badge badge--info" : "badge badge--soft";
  refs.statusModo.textContent = state.sessao.modo_testnet ? "Testnet" : "Conta real";
  if (!state.backendIndisponivel) definirAvisoStatus("Leitura automatica ativa.", "info");
}

function renderDashboard() {
  const painel = state.painel || {};
  const conta = painel.conta || {};
  const mercado = painel.mercado || {};
  const modelos = painel.modelos || {};
  const pnl = painel.pnl || {};
  const scanner = (((painel.multiativos || {}).scanner) || {});
  const feature = mercado.feature_recente || {};
  const taxasEfetivas = conta.taxas_efetivas || {};
  const noticiasMeta = ((painel.noticias || {}).meta) || {};
  const modeloStatus = state.modeloStatus || {};
  const decisao = modelos.decisao_atual || {};
  refs.dashContaModo.className = state.sessao?.modo_testnet ? "badge badge--info" : "badge badge--soft";
  refs.dashContaModo.textContent = state.sessao?.modo_testnet ? "Testnet" : "Conta real";
  refs.dashMercadoStatus.className = badgeClass((painel.operacional || {}).mercado);
  refs.dashMercadoStatus.textContent = (painel.operacional || {}).mercado || "--";
  refs.dashAcaoAtual.className = badgeClass(decisao.acao);
  refs.dashAcaoAtual.textContent = traduzirAcao(decisao.acao);
  refs.dashPnlStatus.className = readNumber(pnl.pnl_total_liquido_usdt) >= 0 ? "badge badge--positive" : "badge badge--danger";
  refs.dashPnlStatus.textContent = readNumber(pnl.pnl_total_liquido_usdt) >= 0 ? "PnL positivo" : "PnL negativo";
  refs.dashModeloMotivo.textContent = traduzirMotivo(decisao.motivo);
  renderMetricList(refs.dashContaResumo, [
    { rotulo: "Saldo total estimado", valor: formatCurrency(conta.saldo_total_estimado_usdt), detalhe: `USDT livre ${formatCurrency((conta.saldo_usdt || {}).livre)}` },
    { rotulo: "Ativo base", valor: `${formatNumber((conta.saldo_base || {}).total, 6)} ${conta.ativo_base || "--"}`, detalhe: `Quote ${formatNumber((conta.saldo_quote || {}).total, 4)} ${conta.ativo_quote || "--"}` },
    { rotulo: "Preco do par", valor: formatCurrency(conta.preco_simbolo), detalhe: `Trade ${conta.permite_trade ? "habilitado" : "bloqueado"}` },
    { rotulo: "Credencial", valor: conta.api_key_mascarada || "--", detalhe: conta.nome_exibicao || "--" },
  ]);
  renderMetricList(refs.dashMercadoResumo, [
    { rotulo: "Preco atual", valor: formatCurrency(mercado.preco_atual), detalhe: `Variacao 1m ${formatPercent((mercado.variacao_1m_pct || 0), true)}` },
    { rotulo: "Spread", valor: formatPercent(feature.spread_rel || 0, false), detalhe: `Book imbalance ${formatNumber(feature.book_imb || 0, 3)}` },
    { rotulo: "Volume", valor: formatNumber(feature.volume_ratio || 0, 3), detalhe: `Amplitude ${formatPercent(feature.amplitude_rel || 0, false)}` },
    { rotulo: "Noticias", valor: formatPercent(noticiasMeta.confianca || 0, false), detalhe: `Sentimento ${formatNumber(noticiasMeta.sentimento_geral || 0, 3)}` },
  ]);
  renderMetricList(refs.dashModeloResumo, [
    { rotulo: "Modelo online", valor: modeloStatus.esta_ajustado ? "Ajustado" : "Cold start", detalhe: `${modeloStatus.amostras_ajustadas || 0} amostras` },
    { rotulo: "Batch", valor: modeloStatus.batch_carregado ? "Carregado" : "Ausente", detalhe: modeloStatus.versao_batch || "--" },
    { rotulo: "Hit rate modelo", valor: formatPercent(modelos.hit_rate_modelo || 0, true), detalhe: `Conf media ${formatPercent(modelos.confianca_media_modelo || 0, true)}` },
    { rotulo: "Hit rate LLM", valor: formatPercent(modelos.hit_rate_llm || 0, true), detalhe: `Conf media ${formatPercent(modelos.confianca_media_llm || 0, true)}` },
  ]);
  renderMetricList(refs.dashPnlResumo, [
    { rotulo: "PnL realizado liquido", valor: formatCurrency(pnl.pnl_realizado_liquido_usdt), detalhe: `Bruto ${formatCurrency(pnl.pnl_realizado_bruto_usdt)}`, classe: readNumber(pnl.pnl_realizado_liquido_usdt) >= 0 ? "metric--positive" : "metric--danger" },
    { rotulo: "PnL aberto", valor: formatCurrency(pnl.pnl_nao_realizado_usdt), detalhe: `Total ${formatCurrency(pnl.pnl_total_liquido_usdt)}`, classe: readNumber(pnl.pnl_nao_realizado_usdt) >= 0 ? "metric--positive" : "metric--danger" },
    { rotulo: "Taxas acumuladas", valor: formatCurrency(pnl.taxas_totais_usdt), detalhe: `Inventario ${formatNumber(pnl.inventario_base || 0, 6)} ${pnl.ativo_base || ""}` },
    { rotulo: "FIFO", valor: pnl.cobertura_fifo_incompleta ? "Parcial" : "Confiavel", detalhe: `Custo medio ${formatCurrency(pnl.custo_medio_base_usdt)}` },
  ]);
  renderMetricList(refs.dashTaxasResumo, [
    { rotulo: "Maker", valor: formatPercent((conta.taxas || {}).maker_pct || 0, true), detalhe: `Maker efetiva ${formatPercent(taxasEfetivas.maker_pct_efetiva || 0, true)}` },
    { rotulo: "Taker", valor: formatPercent((conta.taxas || {}).taker_pct || 0, true), detalhe: `Taker efetiva ${formatPercent(taxasEfetivas.taker_pct_efetiva || 0, true)}` },
    { rotulo: "Compra", valor: formatPercent((conta.taxas || {}).compra_pct || 0, true), detalhe: `Venda ${(conta.taxas || {}).venda_pct ? formatPercent((conta.taxas || {}).venda_pct || 0, true) : "--"}` },
    { rotulo: "Desconto BNB", valor: taxasEfetivas.desconto_bnb_ativo ? "Ativo" : "Inativo", detalhe: `Saldo BNB ${formatNumber(taxasEfetivas.saldo_bnb_total || 0, 4)}` },
  ]);
  const oportunidades = (scanner.pares || []).slice(0, 8);
  refs.dashScannerStatus.className = oportunidades.some((item) => item.valida) ? "badge badge--state" : "badge badge--soft";
  refs.dashScannerStatus.textContent = `${scanner.total_validas || 0} validas`;
  refs.tabelaOportunidades.innerHTML = oportunidades.length ? oportunidades.map((item) => `
    <tr>
      <td>${escapeHtml(item.simbolo)}</td>
      <td><span class="${badgeClass(item.acao_sugerida)}">${escapeHtml(traduzirAcao(item.acao_sugerida))}</span></td>
      <td>${escapeHtml(formatCurrency(item.lucro_liquido_esperado_usdt))}</td>
      <td>${escapeHtml(formatPercent(item.score_oportunidade || 0, false))}</td>
    </tr>`).join("") : `<tr><td colspan="4">Sem oportunidade valida no momento.</td></tr>`;
  drawChart(refs.chartPrecos, [{ classe: "chart-line--primary", valores: (mercado.historico_precos || []).slice(-40).map((item) => ({ valor: item.close, data: timestampGrafico(item) })) }], { modoValor: "currency" });
  const predicoes = (((painel.historico || {}).predicoes) || []).slice(-12);
  const outcomes = new Map((((painel.historico || {}).outcomes) || []).map((item) => [item.ts_previsao, item]));
  drawChart(refs.chartComparativo, [
    { classe: "chart-line--secondary", valores: predicoes.map((item) => ({ valor: item.y_cal ?? item.y_hat ?? 0, data: timestampGrafico(item) })) },
    { classe: "chart-line--ghost", valores: predicoes.map((item) => ({ valor: (outcomes.get(item.created_ts) || {}).y_true ?? (item.meta || {}).preco_atual ?? 0, data: timestampGrafico(item) })) },
  ], { modoValor: "currency" });
  renderChartLucroCiclos();
  refs.sidebarConta.textContent = formatCurrency(conta.saldo_total_estimado_usdt);
  refs.sidebarContaTexto.textContent = conta.nome_exibicao || "Saldo total estimado";
  refs.sidebarModelo.textContent = `${formatPercent(modelos.hit_rate_modelo || 0, true)} / ${formatPercent(modelos.hit_rate_llm || 0, true)}`;
  refs.sidebarModeloTexto.textContent = `${modeloStatus.esta_ajustado ? "Modelo ajustado" : "Modelo em aquecimento"} | ${modeloStatus.batch_carregado ? "batch carregado" : "batch ausente"}`;
}

function perfisRenderizaveis(autoStatus) {
  const perfisApi = Array.isArray((autoStatus || {}).perfis_capital) ? (autoStatus || {}).perfis_capital : [];
  return perfisApi.length ? perfisApi : [];
}

function perfilConfigAtual(autoStatus, perfilId) {
  const perfisCfg = (((autoStatus || {}).config || {}).perfis_capital || {});
  const cfg = perfisCfg[perfilId];
  if (!cfg || typeof cfg.ativo !== "boolean") {
    return { ativo: false, capital_usdt: 0, invalido: true };
  }
  const capital = readNumber(cfg.capital_usdt, NaN);
  return {
    ativo: cfg.ativo,
    capital_usdt: Number.isFinite(capital) && capital >= 0 ? capital : 0,
    invalido: !Number.isFinite(capital) || capital < 0,
  };
}

function configPerfisCanonica(autoStatus, perfis) {
  const perfisCfg = (((autoStatus || {}).config || {}).perfis_capital || {});
  if (!perfis.length || !perfisCfg || typeof perfisCfg !== "object" || Array.isArray(perfisCfg)) return false;
  return perfis.every((perfil) => !perfilConfigAtual(autoStatus, perfil.id).invalido);
}

function resumoSaldoLivreMonitorado() {
  const saldos = (((state.painel || {}).conta || {}).saldos_monitorados || {});
  if (!saldos || typeof saldos !== "object" || Array.isArray(saldos)) {
    return { disponivel: false, total: 0, ativos: 0, invalidos: ["saldos_monitorados"], motivo: "Payload de saldos monitorados indisponivel." };
  }
  const entradas = Object.entries(saldos);
  if (!entradas.length) {
    return { disponivel: false, total: 0, ativos: 0, invalidos: [], motivo: "Sem saldos monitorados no payload de conta." };
  }
  let total = 0;
  let ativos = 0;
  const invalidos = [];
  entradas.forEach(([ativo, saldo]) => {
    if (!saldo || typeof saldo !== "object") {
      invalidos.push(ativo);
      return;
    }
    const livre = Number(saldo.livre);
    if (!Number.isFinite(livre) || livre < 0) {
      invalidos.push(ativo);
      return;
    }
    if (livre === 0) return;
    const preco = Number(saldo.preco_usdt);
    if (!Number.isFinite(preco) || preco <= 0) {
      invalidos.push(ativo);
      return;
    }
    if (livre > 0) ativos += 1;
    total += livre * preco;
  });
  if (invalidos.length) {
    return { disponivel: false, total: 0, ativos, invalidos, motivo: `Saldo livre indisponivel: payload invalido em ${invalidos.join(", ")}.` };
  }
  return { disponivel: true, total: arredondarUsdt(total), ativos, invalidos: [], motivo: "" };
}

function lerResumoPercentualPerfisDaTela() {
  const saldo = resumoSaldoLivreMonitorado();
  let percentualAtivo = 0;
  let capitalAtivo = 0;
  let perfisAtivos = 0;
  perfilIdsRenderizados().forEach((perfilId) => {
    const inputAtivo = document.querySelector(`[data-perfil-ativo="${perfilId}"]`);
    const inputCapital = document.querySelector(`[data-perfil-capital="${perfilId}"]`);
    if (!inputAtivo || !inputCapital) return;
    const ativo = !!inputAtivo.checked;
    const capital = arredondarUsdt(inputCapital.value);
    const percentual = saldo.disponivel && saldo.total > 0 ? Math.max(0, (capital / saldo.total) * 100) : 0;
    if (ativo) {
      percentualAtivo += percentual;
      capitalAtivo += capital;
      perfisAtivos += 1;
    }
  });
  return {
    saldo,
    percentualAtivo,
    capitalAtivo: arredondarUsdt(capitalAtivo),
    perfisAtivos,
    excedeuLimite: percentualAtivo > LIMITE_PERCENTUAL_PERFIS,
  };
}

function atualizarPreviewPerfisBot() {
  const autoStatus = state.auto || {};
  const perfis = perfisRenderizaveis(autoStatus);
  const configCanonicaOk = configPerfisCanonica(autoStatus, perfis);
  const resumo = lerResumoPercentualPerfisDaTela();
  perfilIdsRenderizados().forEach((perfilId) => {
    const inputCapital = document.querySelector(`[data-perfil-capital="${perfilId}"]`);
    const capitalEl = document.querySelector(`[data-perfil-capital-calculado="${perfilId}"]`);
    const percentualEl = document.querySelector(`[data-perfil-percentual-label="${perfilId}"]`);
    const barraEl = document.querySelector(`[data-perfil-barra="${perfilId}"]`);
    if (!inputCapital) return;
    const capital = arredondarUsdt(inputCapital.value);
    const percentual = resumo.saldo.disponivel && resumo.saldo.total > 0 ? Math.max(0, (capital / resumo.saldo.total) * 100) : 0;
    if (capitalEl) capitalEl.textContent = formatCurrency(capital);
    if (percentualEl) percentualEl.textContent = formatPercent(percentual, true);
    if (barraEl) barraEl.style.width = `${Math.max(0, Math.min(100, percentual))}%`;
  });
  const semCapitalPerfis = configCanonicaOk && resumo.capitalAtivo <= 0;
  refs.botPerfisStatus.className = resumo.capitalAtivo > 0 ? "badge badge--state" : "badge badge--soft";
  refs.botPerfisStatus.textContent = configCanonicaOk
    ? (semCapitalPerfis ? "Sem capital" : (resumo.saldo.disponivel ? `${formatPercent(resumo.percentualAtivo, true)} ativo` : `${formatCurrency(resumo.capitalAtivo)} ativo`))
    : "Config bloqueada";
  if (!configCanonicaOk) {
    refs.botCapitalStatus.textContent = "Backend nao enviou config canonica de perfis. Operacao bloqueada.";
  } else if (semCapitalPerfis) {
    refs.botCapitalStatus.textContent = `Saldo carregado. Defina capital em USDT para pelo menos uma estrategia e clique Aplicar perfis. Saldo livre: ${resumo.saldo.disponivel ? formatCurrency(resumo.saldo.total) : "indisponivel"}.`;
  } else if (resumo.excedeuLimite) {
    refs.botCapitalStatus.textContent = `Capital ativo equivale a ${formatPercent(resumo.percentualAtivo, true)} do saldo livre estimado. O backend validara saldo real antes de operar.`;
  } else {
    refs.botCapitalStatus.textContent = resumo.saldo.disponivel
      ? `Saldo livre total ${formatCurrency(resumo.saldo.total)}. Capital ativo declarado ${formatCurrency(resumo.capitalAtivo)}.`
      : `Capital ativo declarado ${formatCurrency(resumo.capitalAtivo)}. Saldo livre indisponivel para comparar.`;
  }
  refs.botPerfisSalvar.disabled = state.perfisCarregando || state.botCarregando || !perfis.length || !configCanonicaOk;
}

function resumoPerfilHistorico(autoStatus, perfilId) {
  const bloco = (((autoStatus || {}).historico_perfis || {})[perfilId]) || {};
  return {
    total_ciclos: readNumber(bloco.total_ciclos, 0),
    win_rate: readNumber(bloco.win_rate, 0),
    lucro_liquido_total_usdt: readNumber(bloco.lucro_liquido_total_usdt, 0),
    tempo_ativo_total_ms: readNumber(bloco.tempo_ativo_total_ms, 0),
  };
}

function capitalTotalPerfisConfigurados(autoStatus, perfis) {
  return (perfis || []).reduce((acc, perfil) => {
    const cfg = perfilConfigAtual(autoStatus, perfil.id);
    return acc + (cfg.ativo ? cfg.capital_usdt : 0);
  }, 0);
}

function capitalTotalPerfisDeclarados(autoStatus, perfis) {
  return (perfis || []).reduce((acc, perfil) => {
    const cfg = perfilConfigAtual(autoStatus, perfil.id);
    return acc + cfg.capital_usdt;
  }, 0);
}

function perfilIdsRenderizados() {
  if (!refs.botPerfis) return [];
  return Array.from(new Set(
    Array.from(refs.botPerfis.querySelectorAll("[data-perfil-ativo]"))
      .map((input) => String(input.dataset.perfilAtivo || "").trim())
      .filter(Boolean)
  ));
}

function resumoGlobalPerfis(autoStatus) {
  const resumo = (autoStatus || {}).historico_ciclos_resumo || {};
  return {
    total_ciclos: readNumber(resumo.total_ciclos, 0),
    win_rate: readNumber(resumo.win_rate, 0),
    lucro_liquido_total_usdt: readNumber(resumo.lucro_liquido_total_usdt, 0),
  };
}

function historicoBotNormalizado() {
  const ciclos = Array.isArray((state.auto || {}).historico_ciclos) ? (state.auto || {}).historico_ciclos : [];
  if (ciclos.length) {
    return ciclos.slice().reverse().map((item) => ({
      origem: "ciclo",
      horario: item.ts_encerramento || item.horario || item.created_ts,
      perfil: obterPerfilHistorico(item),
      lado: item.lado || item.acao || "CICLO",
      preco: item.preco_saida_usdt || item.preco || item.preco_saida,
      valor_usdt: item.notional_entrada || item.valor_usdt,
      lucro_liquido_usdt: item.lucro_liquido_usdt,
      retorno_liquido_pct: item.retorno_liquido_pct,
      win_rate: item.win_rate ?? item.winrate ?? item.taxa_acerto,
      detalhe: item.motivo || item.origem || (item.duracao_ms == null ? "" : `Duracao ${formatDurationMs(item.duracao_ms)}`),
    }));
  }
  return (((state.painel || {}).historico_negociacoes || [])).slice().reverse().map((item) => ({
    origem: "trade",
    ...item,
    perfil: obterPerfilHistorico(item),
  }));
}

function renderChartLucroCiclos() {
  if (!refs.chartLucroCiclos) return;
  const pontos = historicoBotNormalizado()
    .filter((item) => item.lucro_liquido_usdt != null)
    .slice(0, 12)
    .reverse()
    .map((item) => ({
      valor: readNumber(item.lucro_liquido_usdt, 0),
      data: item.horario,
      rotulo: formatChartDate(item.horario),
    }));
  drawBarChart(refs.chartLucroCiclos, pontos, { modoValor: "currency" });
}

function renderBotHistoricoIndividual() {
  if (!refs.botHistoricoPerfisDetalhe) return;
  const historico = historicoBotNormalizado();
  const perfis = perfilIdsRenderizados();
  refs.botHistoricoPerfisDetalhe.innerHTML = perfis.map((perfilId) => {
    const itens = historico.filter((item) => item.perfil === perfilId).slice(0, 5);
    const ultima = itens[0];
    const winrate = obterWinRatePayload(ultima || {});
    const status = ultima ? `${traduzirAcao(ultima.lado)} em ${formatDate(ultima.horario)}` : "Sem operacao recente";
    return `
      <article class="strategy-history-card">
        <div class="strategy-history-card__head">
          <span class="strategy-pill strategy-pill--${escapeHtml(perfilId)}">${escapeHtml(nomePerfil(perfilId))}</span>
          <span class="badge badge--soft">${escapeHtml(winrate === "--" ? "Sem winrate" : `Winrate ${winrate}`)}</span>
        </div>
        <p class="muted">${escapeHtml(status)}</p>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Horario</th>
                <th>Lado</th>
                <th>Lucro</th>
              </tr>
            </thead>
            <tbody>
              ${itens.length ? itens.map((item) => `
                <tr>
                  <td>${escapeHtml(formatDate(item.horario))}</td>
                  <td>${escapeHtml(traduzirAcao(item.lado))}</td>
                  <td>${escapeHtml(item.lucro_liquido_usdt == null ? "--" : formatCurrency(item.lucro_liquido_usdt))}</td>
                </tr>`).join("") : `<tr><td colspan="3">Sem historico.</td></tr>`}
            </tbody>
          </table>
        </div>
      </article>`;
  }).join("");
}

function renderBot() {
  const autoStatus = state.auto || {};
  const perfis = perfisRenderizaveis(autoStatus);
  const saldoLivre = resumoSaldoLivreMonitorado();
  const perfilAtivo = autoStatus.perfil_ativo || {};
  const confirmacao = autoStatus.ultima_confirmacao_composta || {};
  const extratoPar = autoStatus.extrato_par || {};
  const focoSimbolo = autoStatus.simbolo_foco || (autoStatus.config || {}).simbolo || DASHBOARD_SYMBOL;
  const capitalAlocadoPerfis = capitalTotalPerfisConfigurados(autoStatus, perfis);
  const capitalDeclaradoPerfis = capitalTotalPerfisDeclarados(autoStatus, perfis);
  const percentualAtivoConfigurado = saldoLivre.disponivel && saldoLivre.total > 0 ? (capitalAlocadoPerfis / saldoLivre.total) * 100 : 0;
  const percentualDeclaradoConfigurado = saldoLivre.disponivel && saldoLivre.total > 0 ? (capitalDeclaradoPerfis / saldoLivre.total) * 100 : 0;
  const paresRanqueados = (autoStatus.pares_ranqueados || []).slice(0, 3);
  const resumoRanking = paresRanqueados.length
    ? paresRanqueados.map((item) => `${item.simbolo} ${traduzirAcao(item.acao_prioritaria)}`).join(" | ")
    : "Sem ranking multiativo";
  const configCanonicaOk = configPerfisCanonica(autoStatus, perfis);
  const perfisAtivos = configCanonicaOk ? perfis.filter((perfil) => perfilConfigAtual(autoStatus, perfil.id).ativo) : [];
  const semCapitalPerfis = configCanonicaOk && capitalAlocadoPerfis <= 0;
  const pctAlocado = capitalDeclaradoPerfis > 0 ? (capitalAlocadoPerfis / capitalDeclaradoPerfis) : 0;
  const resumoGlobal = resumoGlobalPerfis(autoStatus);
  refs.botStatus.className = autoStatus.ativo ? "badge badge--state" : "badge badge--soft";
  refs.botStatus.textContent = autoStatus.ativo ? "Ligado" : "Pausado";
  refs.botToggleBtn.textContent = autoStatus.ativo ? "Desligar bot" : "Ligar bot";
  refs.botToggleBtn.disabled = state.botCarregando || (!autoStatus.ativo && !configCanonicaOk);
  refs.botPerfisSalvar.disabled = state.perfisCarregando || state.botCarregando || !perfis.length || !configCanonicaOk;
  refs.botPerfisStatus.className = capitalAlocadoPerfis > 0 ? "badge badge--state" : "badge badge--soft";
  refs.botPerfisStatus.textContent = configCanonicaOk
    ? (semCapitalPerfis ? "Sem capital" : (saldoLivre.disponivel ? `${formatPercent(percentualAtivoConfigurado, true)} ativo` : `${formatCurrency(capitalAlocadoPerfis)} ativo`))
    : "Config bloqueada";
  refs.botCapitalStatus.textContent = autoStatus.ativo
    ? `Executando ${traduzirEstadoCiclo(autoStatus.estado_ciclo)} com foco em ${focoSimbolo}.`
    : (!configCanonicaOk
      ? "Backend nao enviou config canonica de perfis. Operacao bloqueada."
      : (semCapitalPerfis
        ? `Saldo carregado. Defina capital em USDT para pelo menos uma estrategia e clique Aplicar perfis. Saldo livre: ${saldoLivre.disponivel ? formatCurrency(saldoLivre.total) : "indisponivel"}.`
        : (saldoLivre.disponivel ? `Capital dos perfis definido. Saldo livre total: ${formatCurrency(saldoLivre.total)}.` : "Capital dos perfis definido.")));
  const bloqueiosSeguranca = (autoStatus.bloqueios || []).map((item) => traduzirMotivo(item)).filter(Boolean);
  renderMetricList(refs.botResumo, [
    { rotulo: "Saldo livre total", valor: saldoLivre.disponivel ? formatCurrency(saldoLivre.total) : "Indisponivel", detalhe: saldoLivre.disponivel ? `${saldoLivre.ativos} ativos com saldo livre` : saldoLivre.motivo },
    { rotulo: "Percentual ativo", valor: formatPercent(percentualAtivoConfigurado, true), detalhe: `${formatCurrency(capitalAlocadoPerfis)} calculados | Perfis ativos ${perfisAtivos.length}/${perfis.length}` },
    { rotulo: "Capital declarado", valor: formatCurrency(capitalDeclaradoPerfis), detalhe: `${formatPercent(percentualDeclaradoConfigurado, true)} do saldo livre | Intervalo ${(autoStatus.config || {}).intervalo_segundos || 30}s` },
    { rotulo: "Winrate global", valor: formatPercent(resumoGlobal.win_rate || 0, false), detalhe: `Ciclos ${resumoGlobal.total_ciclos} | PnL ${formatCurrency(resumoGlobal.lucro_liquido_total_usdt)}` },
    { rotulo: "Seguranca", valor: autoStatus.pronto ? "Pronto" : "Bloqueado", detalhe: autoStatus.sincronizado ? "Sincronizado" : (bloqueiosSeguranca.slice(0, 2).join(" | ") || "Aguardando sincronizacao") },
    { rotulo: "Ultima acao", valor: traduzirAcao(autoStatus.ultima_acao), detalhe: traduzirMotivo(autoStatus.ultimo_motivo) },
    { rotulo: "Foco multiativo", valor: focoSimbolo, detalhe: resumoRanking },
    { rotulo: "Perfil ativo", valor: perfilAtivo.nome || "Aguardando", detalhe: `Capital ${formatCurrency(perfilAtivo.capital_usdt)} | Lucro min ${formatCurrency(perfilAtivo.lucro_minimo_usdt)}` },
    { rotulo: "Estimativa atual", valor: formatCurrency(autoStatus.ultimo_lucro_esperado_pct * capitalAlocadoPerfis), detalhe: `${traduzirAcao(autoStatus.ultima_acao_par)} | Compra ${formatDate(extratoPar.ultima_compra_ts)} | Venda ${formatDate(extratoPar.ultima_venda_ts)}` },
  ]);
  refs.botPerfis.innerHTML = perfis.length ? perfis.map((perfil) => {
    const cfg = perfilConfigAtual(autoStatus, perfil.id);
    const resumoPerfil = resumoPerfilHistorico(autoStatus, perfil.id);
    const capitalDeclarado = arredondarUsdt(cfg.capital_usdt);
    const pctPerfilSaldo = saldoLivre.disponivel && saldoLivre.total > 0 ? Math.max(0, (capitalDeclarado / saldoLivre.total) * 100) : 0;
    const cardClasses = [
      "profile-card",
      perfil.id === perfilAtivo.id ? "profile-card--active" : "",
      !cfg.ativo ? "profile-card--disabled" : "",
    ].filter(Boolean).join(" ");
    return `
    <article class="${cardClasses}">
      <div class="profile-card__top">
        <div>
          <p class="eyebrow">${escapeHtml(perfil.id || "--")}</p>
          <h4>${escapeHtml(perfil.nome || "--")}</h4>
        </div>
        <span class="${badgeClass(perfil.habilitado ? "operacional" : "travado")}">${escapeHtml(perfil.habilitado ? "Pronto" : traduzirMotivo(perfil.motivo_status))}</span>
      </div>
      <p class="muted">${escapeHtml(perfil.descricao || "Perfil automatico.")}</p>
      <div class="profile-card__bar"><span data-perfil-barra="${escapeHtml(perfil.id)}" style="width:${Math.max(0, Math.min(100, pctPerfilSaldo))}%"></span></div>
      <div class="profile-card__config">
        <label class="field field--toggle compact-toggle" for="perfil-ativo-${escapeHtml(perfil.id)}">
          <span>Ativo</span>
          <span class="toggle">
            <input id="perfil-ativo-${escapeHtml(perfil.id)}" type="checkbox" data-perfil-ativo="${escapeHtml(perfil.id)}" ${cfg.ativo ? "checked" : ""} ${configCanonicaOk ? "" : "disabled"} />
            <span>${cfg.ativo ? "Ligado" : "Desligado"}</span>
          </span>
        </label>
        <label class="field compact-field" for="perfil-percentual-${escapeHtml(perfil.id)}">
          <span>Capital autorizado USDT</span>
          <input id="perfil-percentual-${escapeHtml(perfil.id)}" type="number" min="0" step="0.01" data-perfil-capital="${escapeHtml(perfil.id)}" value="${escapeHtml(capitalDeclarado)}" ${configCanonicaOk ? "" : "disabled"} />
        </label>
      </div>
      <div class="profile-card__preview">
        <strong data-perfil-percentual-label="${escapeHtml(perfil.id)}">${escapeHtml(formatPercent(pctPerfilSaldo, true))}</strong>
        <span data-perfil-capital-calculado="${escapeHtml(perfil.id)}">${escapeHtml(formatCurrency(capitalDeclarado))}</span>
      </div>
      <div class="profile-card__meta">
        <span>Payload atual ${escapeHtml(formatCurrency(cfg.capital_usdt))}</span>
        <span>Lucro minimo ${escapeHtml(formatCurrency(perfil.lucro_minimo_usdt))}</span>
        <span>Saldo livre alocado ${escapeHtml(formatPercent(pctPerfilSaldo, true))}</span>
        <span>Ciclos ${escapeHtml(String(resumoPerfil.total_ciclos))} | Winrate ${escapeHtml(formatPercent(resumoPerfil.win_rate || 0, false))}</span>
        <span>Tempo ativo ${escapeHtml(formatDurationMs(resumoPerfil.tempo_ativo_total_ms || 0))} | PnL ${escapeHtml(formatCurrency(resumoPerfil.lucro_liquido_total_usdt))}</span>
      </div>
    </article>`;
  }).join("") : `<article class="empty-state">Backend nao enviou os perfis canonicos. Recarregue o painel antes de alterar capital.</article>`;
  atualizarPreviewPerfisBot();
  refs.botCicloStatus.className = badgeClass(autoStatus.estado_ciclo);
  refs.botCicloStatus.textContent = traduzirEstadoCiclo(autoStatus.estado_ciclo);
  renderMetricList(refs.botCicloResumo, [
    { rotulo: "Ciclo", valor: traduzirEstadoCiclo(autoStatus.estado_ciclo), detalhe: `Inicio ${formatDate(autoStatus.ciclo_iniciado_ts)}` },
    { rotulo: "Entrada / atual", valor: `${formatCurrency(autoStatus.ciclo_preco_entrada)} / ${formatCurrency(autoStatus.ciclo_preco_atual)}`, detalhe: `Qtd ${formatNumber(autoStatus.ciclo_quantidade || 0, 6)}` },
    { rotulo: "Lucro aberto", valor: formatCurrency(autoStatus.ciclo_lucro_liquido_aberto_usdt), detalhe: `Retorno ${formatPercent(autoStatus.ciclo_retorno_liquido_aberto_pct || 0, false)}` },
    { rotulo: "Melhor ponto", valor: formatCurrency(autoStatus.ciclo_melhor_lucro_liquido_usdt), detalhe: `Score composto ${formatPercent(confirmacao.pontuacao || 0, false)}` },
  ]);
  renderBotHistoricoIndividual();
  renderChartLucroCiclos();
  refs.sidebarBot.textContent = autoStatus.ativo ? "Ligado" : "Pausado";
  refs.sidebarBotTexto.textContent = `${traduzirEstadoCiclo(autoStatus.estado_ciclo)} | ${perfilAtivo.nome || traduzirMotivo(autoStatus.ultimo_motivo) || "Sem perfil ativo"}`;
}

function renderNewsTabs() {
  refs.newsTabs.innerHTML = NEWS_SYMBOLS.map((simbolo) => `
    <button class="symbol-tabs__item ${simbolo === state.simboloNoticiasAtual ? "symbol-tabs__item--active" : ""}" type="button" data-simbolo="${simbolo}">
      ${simbolo}
    </button>`).join("");
}

function fonteId(fonte) {
  return String(fonte?.nome || fonte?.dominio || "").trim();
}

function relevanciaFonte(fonte) {
  const peso = readNumber(fonte?.peso, readNumber(fonte?.peso_pct, 0) / 100);
  const itens = readNumber(fonte?.itens_encontrados, 0);
  const cobertura = Math.min(1, itens / 8);
  return (peso * 0.72) + (cobertura * 0.28);
}

function renderNewsPreview(pacote, fontes) {
  const fonte = fontes.find((item) => fonteId(item) === state.newsFonteAtual) || fontes[0];
  if (!fonte) {
    refs.newsPreviewStatus.className = "badge badge--soft";
    refs.newsPreviewStatus.textContent = "Sem preview";
    refs.newsFrames.innerHTML = `<article class="empty-state">Sem fonte disponivel para preview.</article>`;
    return;
  }
  state.newsFonteAtual = fonteId(fonte);
  refs.newsPreviewStatus.className = "badge badge--state";
  refs.newsPreviewStatus.textContent = fonte.nome || "Fonte";
  const iframeUrl = String(fonte.iframe_url || "").trim();
  refs.newsFrames.innerHTML = `
    <article class="preview-card">
      <div>
        <p class="eyebrow">${escapeHtml(pacote.simbolo || state.simboloNoticiasAtual)}</p>
        <h4>${escapeHtml(fonte.nome || "--")}</h4>
        <p class="muted">${escapeHtml(fonte.dominio || "--")} | Peso ${escapeHtml(formatPercent((fonte.peso_pct || 0), true))} | Itens ${escapeHtml(String(fonte.itens_encontrados || 0))} | Relevancia ${escapeHtml(formatPercent(relevanciaFonte(fonte), false))}</p>
      </div>
      <a class="iframe-card__link" href="${escapeHtml(fonte.rss_url || fonte.iframe_url || "#")}" target="_blank" rel="noreferrer noopener">Abrir fonte</a>
    </article>
    <div class="preview-frame-shell">
      ${iframeUrl ? `<iframe title="${escapeHtml(`${pacote.simbolo || state.simboloNoticiasAtual}-${fonte.nome || "fonte"}`)}" loading="lazy" src="${escapeHtml(iframeUrl)}"></iframe>` : `<article class="empty-state">Fonte sem iframe renderizavel. Use "Abrir fonte" para leitura direta.</article>`}
    </div>`;
}

function renderNews() {
  renderNewsTabs();
  const pacote = state.noticias[state.simboloNoticiasAtual];
  if (!pacote) {
    refs.newsAtualizacao.className = "badge badge--soft";
    refs.newsAtualizacao.textContent = "Aguardando";
    renderMetricList(refs.newsResumo, [{ rotulo: "Noticias", valor: "Sem carga", detalhe: "Abra a aba e sincronize para buscar as fontes." }]);
    refs.newsFontesPeso.innerHTML = `<article class="empty-state">Sem fontes carregadas.</article>`;
    refs.newsHeadlines.innerHTML = `<article class="empty-state">Sem manchetes carregadas.</article>`;
    refs.newsHeadlinesTotal.textContent = "0 itens";
    refs.newsPreviewStatus.className = "badge badge--soft";
    refs.newsPreviewStatus.textContent = "Sem preview";
    refs.newsFrames.innerHTML = `<article class="empty-state">Sem preview carregado.</article>`;
    return;
  }
  const meta = pacote.meta || {};
  const fontesComRetorno = (meta.fontes_detalhadas || [])
    .filter((fonte) => {
      const id = fonteId(fonte);
      return id && String(fonte?.status || "").toLowerCase() === "com_retorno" && readNumber(fonte?.itens_encontrados, 0) > 0;
    })
    .sort((a, b) => relevanciaFonte(b) - relevanciaFonte(a))
    .slice(0, 8);
  const fontesFallback = (meta.fontes_detalhadas || [])
    .filter((fonte) => fonteId(fonte))
    .sort((a, b) => relevanciaFonte(b) - relevanciaFonte(a))
    .slice(0, 8);
  const fontes = fontesComRetorno.length ? fontesComRetorno : fontesFallback;
  const prioridadeFonte = new Map(fontes.map((fonte, index) => [String((fonte.nome || fonte.dominio || "")).toLowerCase(), index]));
  const itens = (pacote.itens || [])
    .filter((item) => String(item?.titulo || "").trim())
    .map((item) => {
      const impacto = String(item?.impacto || "medio").toLowerCase();
      const pesoImpacto = impacto === "alto" ? 3 : (impacto === "medio" ? 2 : 1);
      const ts = parseTimestamp(item.publicado_em) || 0;
      const prioridade = prioridadeFonte.get(String(item?.fonte || "").toLowerCase()) ?? 99;
      return { ...item, _pesoImpacto: pesoImpacto, _ts: ts, _prioridade: prioridade };
    })
    .sort((a, b) => {
      if (b._pesoImpacto !== a._pesoImpacto) return b._pesoImpacto - a._pesoImpacto;
      if (a._prioridade !== b._prioridade) return a._prioridade - b._prioridade;
      return b._ts - a._ts;
    })
    .slice(0, 8);
  if (fontes.length && !fontes.some((fonte) => fonteId(fonte) === state.newsFonteAtual)) {
    state.newsFonteAtual = fonteId(fontes[0]);
  }
  refs.newsAtualizacao.className = meta.cache_usado ? "badge badge--soft" : "badge badge--state";
  refs.newsAtualizacao.textContent = meta.cache_usado ? "Cache recente" : "Atualizado";
  renderMetricList(refs.newsResumo, [
    { rotulo: "Simbolo", valor: pacote.simbolo || state.simboloNoticiasAtual, detalhe: `Atualizado ${formatDate(meta.atualizado_em)}` },
    { rotulo: "Sentimento geral", valor: formatNumber(meta.sentimento_geral || 0, 3), detalhe: `Confianca ${formatPercent(meta.confianca || 0, false)}` },
    { rotulo: "Fontes validadas", valor: `${fontesComRetorno.length}/${meta.fontes_monitoradas || 0}`, detalhe: `Somente fontes com titulo e retorno confiavel` },
    { rotulo: "Classificacao", valor: meta.status_classificacao || "--", detalhe: `Buscas hoje ${meta.buscas_hoje || 0}/${meta.max_buscas_dia || 0}` },
  ]);
  refs.newsFontesPeso.innerHTML = fontes.length ? fontes.map((fonte) => `
    <button class="source-item source-item--button ${fonteId(fonte) === state.newsFonteAtual ? "source-item--active" : ""}" type="button" data-news-fonte="${escapeHtml(fonteId(fonte))}">
      <div class="source-item__top">
        <div>
          <h4>${escapeHtml(fonte.nome || "--")}</h4>
          <p class="muted">${escapeHtml(fonte.dominio || "--")}</p>
        </div>
        <span class="${badgeClass(fonte.status === "com_retorno" ? "operacional" : "travado")}">${escapeHtml(formatPercent((fonte.peso_pct || 0), true))}</span>
      </div>
      <div class="source-bar"><span style="width:${Math.max(6, Math.min(100, readNumber(fonte.peso_pct, 0)))}%"></span></div>
      <div class="source-item__meta">
        <span>Relevancia ${escapeHtml(formatPercent(relevanciaFonte(fonte), false))}</span>
        <span>Itens ${escapeHtml(String(fonte.itens_encontrados || 0))}</span>
        <span>Sentimento ${escapeHtml(formatNumber(fonte.sentimento_medio || 0, 3))}</span>
      </div>
    </button>`).join("") : `<article class="empty-state">Nenhuma fonte ranqueada para este simbolo.</article>`;
  refs.newsHeadlinesTotal.textContent = `${itens.length} itens`;
  refs.newsHeadlines.innerHTML = itens.length ? itens.map((item) => `
    <article class="headline">
      <div class="headline__meta">
        <span class="${badgeClass(item.impacto === "alto" ? "operacional" : "sincronizado")}">${escapeHtml(item.fonte || "--")}</span>
        <span class="badge badge--soft">Peso ${escapeHtml(String(item._pesoImpacto || 1))}/3</span>
        <span>${escapeHtml(formatDate(item.publicado_em))}</span>
      </div>
      <a href="${escapeHtml(item.link || "#")}" target="_blank" rel="noreferrer noopener">${escapeHtml(item.titulo || "--")}</a>
      <p>${escapeHtml(item.resumo_analise || item.descricao || "Sem resumo da manchete.")}</p>
    </article>`).join("") : `<article class="empty-state">Sem headlines recentes para este simbolo.</article>`;
  renderNewsPreview(pacote, fontes);
  refs.sidebarNoticias.textContent = pacote.simbolo || state.simboloNoticiasAtual;
  refs.sidebarNoticiasTexto.textContent = `${meta.fontes_com_retorno || 0} fontes com retorno`;
}

async function carregarDashboard() {
  const [painel, modeloStatus] = await Promise.all([
    requestJson(`/v1/painel/conta?simbolo=${DASHBOARD_SYMBOL}`),
    requestJson(`/v1/modelos/status?simbolo=${DASHBOARD_SYMBOL}`),
  ]);
  state.painel = painel;
  state.modeloStatus = modeloStatus;
  renderDashboard();
}

async function carregarBot() {
  state.auto = await requestJson("/v1/auto/status");
  renderBot();
}

function aplicarSessaoPayload(sessao) {
  state.sessao = sessao || null;
  state.autenticado = !!(sessao && (sessao.autenticado !== false));
  if (state.autenticado && sessao && sessao.auto_trade) {
    state.auto = sessao.auto_trade;
  }
}

async function carregarNoticias(force = false) {
  const payload = await requestJson(`/v1/noticias/multi?simbolos=${NEWS_SYMBOLS.join(",")}&atualizar=${force ? "true" : "false"}`);
  const noticias = {};
  (payload.itens || []).forEach((item) => { noticias[item.simbolo] = item; });
  state.noticias = noticias;
  renderNews();
}

function atualizarUltimaSincronizacao() {
  const candidatos = [
    (state.painel || {}).ts_atualizacao,
    (state.auto || {}).ultimo_ts,
    ...Object.values(state.noticias).map((item) => ((item || {}).meta || {}).atualizado_em),
  ].filter(Boolean);
  refs.ultimaAtualizacao.textContent = `Sincronizado ${formatDate(candidatos.length ? Math.max(...candidatos) : Date.now())}`;
}

async function refreshAll(forceNews = false) {
  if (!state.autenticado) return;
  refs.statusConexao.className = "badge badge--soft";
  refs.statusConexao.textContent = "Sincronizando";
  if (!state.backendIndisponivel) definirAvisoStatus("Sincronizando dados da conta.", "info");
  const tarefas = [carregarDashboard(), carregarBot()];
  if (state.tabAtual === "noticias" || forceNews || Object.keys(state.noticias).length) tarefas.push(carregarNoticias(forceNews));
  const resultados = await Promise.allSettled(tarefas);
  const falha = resultados.find((item) => item.status === "rejected");
  if (falha) {
    const erro = falha.reason instanceof Error ? falha.reason : new Error(String(falha.reason || "falha"));
    if (erro.status === 401 || erro.message.includes("sessao_binance_ausente_ou_expirada") || erro.message.includes("401")) {
      limparSessaoExpirada("Sessao expirada ou ausente. Faca login novamente.");
      return;
    }
    if (erro.status === 502) {
      marcarBackendIndisponivel(erro);
      return;
    }
    refs.statusConexao.className = "badge badge--danger";
    refs.statusConexao.textContent = "Falha parcial";
  } else {
    limparBackendIndisponivel();
    refs.statusConexao.className = "badge badge--state";
    refs.statusConexao.textContent = "Conectado";
    if (!state.pollingId) startPolling();
  }
  atualizarUltimaSincronizacao();
}

async function ligarOuDesligarBot() {
  if (state.botCarregando) return;
  let mensagemErroOperacional = "";
  state.botCarregando = true;
  renderBot();
  try {
    if (state.auto?.ativo) {
      await requestJson("/v1/auto/stop", { method: "POST", body: JSON.stringify({}) });
    } else {
      const perfisTela = lerPerfisBotDaTela();
      const perfisAplicados = perfisTela;
      await requestJson("/v1/auto/config", { method: "PUT", body: JSON.stringify({ perfis_capital: perfisAplicados }) });
      await requestJson("/v1/auto/start", {
        method: "POST",
        body: JSON.stringify({
          perfis_capital: perfisAplicados,
        }),
      });
    }
    await refreshAll(false);
  } catch (error) {
    if (error instanceof Error && error.status === 401) {
      limparSessaoExpirada("Sessao expirada ou ausente. Faca login novamente.");
      return;
    }
    if (error instanceof Error && error.status === 502) {
      marcarBackendIndisponivel(error);
      mensagemErroOperacional = error.message;
      return;
    }
    mensagemErroOperacional = error instanceof Error ? error.message : "Falha ao alterar o estado do bot.";
  } finally {
    state.botCarregando = false;
    if (state.autenticado) {
      await carregarBot().catch(() => { renderBot(); });
    } else {
      renderBot();
    }
    if (mensagemErroOperacional) refs.botCapitalStatus.textContent = mensagemErroOperacional;
  }
}

function lerPerfisBotDaTela() {
  const perfis = {};
  const ids = perfilIdsRenderizados();
  if (!ids.length) throw new Error("Backend nao enviou perfis canonicos para configurar.");
  if (!configPerfisCanonica(state.auto || {}, perfisRenderizaveis(state.auto || {}))) {
    throw new Error("Backend nao enviou config canonica de perfis. Operacao bloqueada.");
  }
  ids.forEach((perfilId) => {
    const inputAtivo = document.querySelector(`[data-perfil-ativo="${perfilId}"]`);
    const inputCapital = document.querySelector(`[data-perfil-capital="${perfilId}"]`);
    if (!inputAtivo || !inputCapital) return;
    const ativo = !!inputAtivo.checked;
    const capitalRaw = Number(inputCapital.value);
    if (!Number.isFinite(capitalRaw) || capitalRaw < 0) {
      throw new Error(`Capital invalido no perfil ${nomePerfil(perfilId)}.`);
    }
    const capital = Number(capitalRaw.toFixed(8));
    perfis[perfilId] = { ativo, capital_usdt: capital };
  });
  return perfis;
}

async function salvarPerfisBot() {
  if (!state.autenticado || state.perfisCarregando) return;
  let houveErro = false;
  state.perfisCarregando = true;
  refs.botPerfisStatus.className = "badge badge--soft";
  refs.botPerfisStatus.textContent = "Aplicando";
  try {
    const perfis = lerPerfisBotDaTela();
    await requestJson("/v1/auto/config", {
      method: "PUT",
      body: JSON.stringify({ perfis_capital: perfis }),
    });
    await carregarBot();
    refs.botPerfisStatus.className = "badge badge--state";
    refs.botPerfisStatus.textContent = "Perfis aplicados";
  } catch (error) {
    houveErro = true;
    if (error instanceof Error && error.status === 401) {
      limparSessaoExpirada("Sessao expirada ou ausente. Faca login novamente.");
      return;
    }
    if (error instanceof Error && error.status === 502) {
      marcarBackendIndisponivel(error);
    }
    refs.botPerfisStatus.className = "badge badge--danger";
    refs.botPerfisStatus.textContent = error instanceof Error ? "Falha" : "Erro";
    refs.botCapitalStatus.textContent = error instanceof Error ? error.message : "Falha ao aplicar perfis.";
  } finally {
    state.perfisCarregando = false;
    if (!houveErro) {
      renderBot();
    } else if (state.autenticado) {
      atualizarPreviewPerfisBot();
    }
  }
}

async function entrar(event) {
  event.preventDefault();
  refs.btnEntrar.disabled = true;
  refs.mensagemLogin.textContent = "Validando credenciais na Binance...";
  try {
    const sessao = await requestJson("/v1/sessao/entrar", {
      method: "POST",
      body: JSON.stringify({
        api_key: refs.apiKey.value.trim(),
        api_secret: refs.apiSecret.value.trim(),
        testnet: refs.usarTestnet.checked,
      }),
    });
    aplicarSessaoPayload({ ...sessao, autenticado: true });
    renderSession();
    renderBot();
    startPolling();
    await refreshAll(false);
  } catch (error) {
    if (error instanceof Error && error.status === 502) marcarBackendIndisponivel(error);
    refs.mensagemLogin.textContent = error instanceof Error ? error.message : "Falha ao iniciar sessao.";
  } finally {
    refs.btnEntrar.disabled = false;
  }
}

async function sair() {
  await requestJson("/v1/sessao/sair", { method: "POST", body: JSON.stringify({}) }).catch(() => {});
  state.autenticado = false;
  state.sessao = null;
  state.painel = null;
  state.modeloStatus = null;
  state.auto = null;
  state.noticias = {};
  state.newsFonteAtual = "";
  stopPolling();
  renderSession();
  renderDashboard();
  renderBot();
  renderNews();
}

async function verificarSessao() {
  try {
    const sessao = await requestJson("/v1/sessao/status");
    if (sessao.autenticado) {
      aplicarSessaoPayload(sessao);
    } else {
      state.autenticado = false;
      state.sessao = null;
      state.auto = null;
    }
    renderSession();
    renderBot();
    if (state.autenticado) {
      startPolling();
      await refreshAll(false);
    }
  } catch (error) {
    state.autenticado = false;
    state.sessao = null;
    stopPolling();
    if (error instanceof Error && error.status === 502) {
      refs.mensagemLogin.textContent = error.message;
    }
    renderSession();
    if (error instanceof Error && error.status === 502) marcarBackendIndisponivel(error);
  }
}

function startPolling() {
  if (state.backendIndisponivel) return;
  stopPolling();
  state.pollingId = window.setInterval(() => {
    refreshAll(false).catch(() => {});
  }, 30000);
}

function stopPolling() {
  if (state.pollingId) window.clearInterval(state.pollingId);
  state.pollingId = null;
}

refs.formLogin.addEventListener("submit", entrar);
refs.btnAtualizar.addEventListener("click", () => { refreshAll(state.tabAtual === "noticias").catch(() => {}); });
refs.btnSair.addEventListener("click", () => { sair().catch(() => {}); });
refs.botToggleBtn.addEventListener("click", () => { ligarOuDesligarBot().catch(() => {}); });
refs.botPerfisSalvar.addEventListener("click", () => { salvarPerfisBot().catch(() => {}); });
refs.botPerfis.addEventListener("input", (event) => {
  if (event.target.closest("[data-perfil-capital]")) atualizarPreviewPerfisBot();
});
refs.botPerfis.addEventListener("change", (event) => {
  if (event.target.closest("[data-perfil-ativo], [data-perfil-capital]")) atualizarPreviewPerfisBot();
});
refs.newsTabs.addEventListener("click", (event) => {
  const botao = event.target.closest("[data-simbolo]");
  if (!botao) return;
  state.simboloNoticiasAtual = botao.dataset.simbolo;
  state.newsFonteAtual = "";
  renderNews();
});
refs.newsFontesPeso.addEventListener("click", (event) => {
  const botao = event.target.closest("[data-news-fonte]");
  if (!botao) return;
  state.newsFonteAtual = botao.dataset.newsFonte || "";
  renderNews();
});
document.querySelectorAll(".nav-tabs__item").forEach((btn) => {
  btn.addEventListener("click", () => activateTab(btn.dataset.tab));
});

activateTab("dashboard");
renderDashboard();
renderBot();
renderNews();
verificarSessao();

(function ajustarRotulosOperacionais() {
  const trocas = new Map([
    ["Estimativa atual", "Estimativa do sinal"],
    ["Lucro aberto", "Lucro aberto real"],
  ]);
  const dica =
    "Estimativa do sinal e uma projecao da oportunidade atual; lucro aberto real e o resultado do ciclo em andamento.";

  function normalizarTexto(no) {
    if (!no || no.nodeType !== Node.TEXT_NODE) return;
    const texto = no.nodeValue;
    const limpo = String(texto || "").trim();
    if (!trocas.has(limpo)) return;
    no.nodeValue = String(texto).replace(limpo, trocas.get(limpo));
    if (no.parentElement) no.parentElement.title = dica;
  }

  function aplicarRotulos(raiz) {
    const alvo = raiz || document.body;
    if (!alvo) return;
    const walker = document.createTreeWalker(alvo, NodeFilter.SHOW_TEXT);
    const nos = [];
    while (walker.nextNode()) nos.push(walker.currentNode);
    nos.forEach(normalizarTexto);
  }

  function iniciar() {
    aplicarRotulos(document.body);
    const observador = new MutationObserver((mutacoes) => {
      for (const mutacao of mutacoes) {
        for (const no of mutacao.addedNodes) {
          if (no.nodeType === Node.TEXT_NODE) normalizarTexto(no);
          if (no.nodeType === Node.ELEMENT_NODE) aplicarRotulos(no);
        }
      }
    });
    observador.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", iniciar, { once: true });
  } else {
    iniciar();
  }
})();
