const DASHBOARD_SYMBOL = "BTCUSDT";
const NEWS_SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ETHBTC", "BNBBTC", "BNBETH"];
const TAB_COPY = {
  dashboard: {
    titulo: "Dashboard inicial",
    subtitulo: "Conta, mercado, modelo, LLM, comparativos e scanner em uma leitura direta.",
  },
  bot: {
    titulo: "Controle do bot",
    subtitulo: "Defina o capital total, ligue ou desligue e acompanhe o ciclo automatico.",
  },
  noticias: {
    titulo: "Noticias multipar",
    subtitulo: "Top 10 fontes por simbolo, peso de confiabilidade, headlines e paineis por fonte.",
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
  botStatus: document.getElementById("botStatus"),
  botCapitalInput: document.getElementById("botCapitalInput"),
  botToggleBtn: document.getElementById("botToggleBtn"),
  botCapitalStatus: document.getElementById("botCapitalStatus"),
  botResumo: document.getElementById("botResumo"),
  botPerfis: document.getElementById("botPerfis"),
  botCicloStatus: document.getElementById("botCicloStatus"),
  botCicloResumo: document.getElementById("botCicloResumo"),
  botTradesTotal: document.getElementById("botTradesTotal"),
  tabelaBotTrades: document.getElementById("tabelaBotTrades"),
  newsTabs: document.getElementById("newsTabs"),
  newsResumo: document.getElementById("newsResumo"),
  newsFontesPeso: document.getElementById("newsFontesPeso"),
  newsHeadlinesTotal: document.getElementById("newsHeadlinesTotal"),
  newsHeadlines: document.getElementById("newsHeadlines"),
  newsFrames: document.getElementById("newsFrames"),
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
  capitalManualTexto: "",
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
  const mapa = { BUY: "Comprar", SELL: "Vender", HOLD: "Aguardando", COMPRA: "Comprar", VENDA: "Vender", PAUSADO: "Pausado", SEM_HISTORICO: "Sem historico" };
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
  };
  const texto = String(valor ?? "").trim();
  return mapa[texto] || (texto ? texto.replaceAll("_", " ") : "Sem motivo recente");
}

function badgeClass(valor) {
  const codigo = normalizarCodigo(valor);
  if (["BUY", "COMPRA", "OPERACIONAL", "SINCRONIZADO", "ATIVO", "EM_POSICAO", "PRONTO", "EXECUTADA"].includes(codigo)) return "badge badge--positive";
  if (["SELL", "VENDA", "REJEITADA", "TRAVADO", "BLOQUEADO", "CANCELADA", "ERRO"].includes(codigo)) return "badge badge--danger";
  return "badge badge--soft";
}

function renderMetricList(target, itens) {
  const validos = (itens || []).filter(Boolean);
  target.innerHTML = validos.length
    ? validos.map((item) => `
      <article class="metric">
        <span class="metric__label">${escapeHtml(item.rotulo)}</span>
        <strong class="metric__value">${escapeHtml(item.valor)}</strong>
        <span class="metric__hint">${escapeHtml(item.detalhe || "")}</span>
      </article>`).join("")
    : `<article class="metric metric--empty"><strong class="metric__value">Sem dados</strong></article>`;
}

function drawChart(svg, series) {
  const grupos = (series || []).filter((item) => Array.isArray(item.valores) && item.valores.length);
  if (!grupos.length) {
    svg.innerHTML = `<text x="24" y="120" class="chart-empty">Sem serie suficiente para comparar.</text>`;
    return;
  }
  const largura = 720;
  const altura = 240;
  const padding = 18;
  const valores = grupos.flatMap((item) => item.valores.map((ponto) => readNumber(ponto.valor)));
  const min = Math.min(...valores);
  const max = Math.max(...valores);
  const amplitude = Math.max(max - min, max * 0.001, 1e-9);
  const linhas = [0.2, 0.5, 0.8].map((fator) => `<line x1="${padding}" y1="${padding + ((altura - padding * 2) * fator)}" x2="${largura - padding}" y2="${padding + ((altura - padding * 2) * fator)}" class="chart-grid"></line>`).join("");
  const paths = grupos.map((serie) => {
    const path = serie.valores.map((ponto, index, lista) => {
      const x = padding + ((largura - padding * 2) * (lista.length === 1 ? 0 : index / (lista.length - 1)));
      const y = altura - padding - (((readNumber(ponto.valor) - min) / amplitude) * (altura - padding * 2));
      return `${index === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    }).join(" ");
    return `<path d="${path}" class="chart-line ${serie.classe}"></path>`;
  }).join("");
  svg.innerHTML = `${linhas}${paths}`;
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
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
    const erro = new Error(payload.detail || texto || `HTTP ${response.status}`);
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
  state.capitalManualTexto = "";
  stopPolling();
  refs.mensagemLogin.textContent = mensagem;
  renderSession();
  renderDashboard();
  renderBot();
  renderNews();
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
    return;
  }
  refs.nomeSessao.textContent = state.sessao.nome_exibicao || "Conta Binance";
  refs.detalheSessao.textContent = `${state.sessao.api_key_mascarada || "--"} • ${state.sessao.id_conta || "--"}`;
  refs.statusConexao.className = "badge badge--positive";
  refs.statusConexao.textContent = "Conectado";
  refs.statusModo.className = state.sessao.modo_testnet ? "badge badge--positive" : "badge badge--danger";
  refs.statusModo.textContent = state.sessao.modo_testnet ? "Testnet" : "Conta real";
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
  refs.dashContaModo.className = state.sessao?.modo_testnet ? "badge badge--positive" : "badge badge--danger";
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
    { rotulo: "PnL realizado liquido", valor: formatCurrency(pnl.pnl_realizado_liquido_usdt), detalhe: `Bruto ${formatCurrency(pnl.pnl_realizado_bruto_usdt)}` },
    { rotulo: "PnL aberto", valor: formatCurrency(pnl.pnl_nao_realizado_usdt), detalhe: `Total ${formatCurrency(pnl.pnl_total_liquido_usdt)}` },
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
  refs.dashScannerStatus.className = oportunidades.some((item) => item.valida) ? "badge badge--positive" : "badge badge--soft";
  refs.dashScannerStatus.textContent = `${scanner.total_validas || 0} validas`;
  refs.tabelaOportunidades.innerHTML = oportunidades.length ? oportunidades.map((item) => `
    <tr>
      <td>${escapeHtml(item.simbolo)}</td>
      <td><span class="${badgeClass(item.acao_sugerida)}">${escapeHtml(traduzirAcao(item.acao_sugerida))}</span></td>
      <td>${escapeHtml(formatCurrency(item.lucro_liquido_esperado_usdt))}</td>
      <td>${escapeHtml(formatPercent(item.score_oportunidade || 0, false))}</td>
    </tr>`).join("") : `<tr><td colspan="4">Sem oportunidade valida no momento.</td></tr>`;
  drawChart(refs.chartPrecos, [{ classe: "chart-line--primary", valores: (mercado.historico_precos || []).slice(-40).map((item) => ({ valor: item.close })) }]);
  const predicoes = (((painel.historico || {}).predicoes) || []).slice(-12);
  const outcomes = new Map((((painel.historico || {}).outcomes) || []).map((item) => [item.ts_previsao, item]));
  drawChart(refs.chartComparativo, [
    { classe: "chart-line--secondary", valores: predicoes.map((item) => ({ valor: item.y_cal ?? item.y_hat ?? 0 })) },
    { classe: "chart-line--ghost", valores: predicoes.map((item) => ({ valor: (outcomes.get(item.created_ts) || {}).y_true ?? (item.meta || {}).preco_atual ?? 0 })) },
  ]);
  refs.sidebarConta.textContent = formatCurrency(conta.saldo_total_estimado_usdt);
  refs.sidebarContaTexto.textContent = conta.nome_exibicao || "Saldo total estimado";
  refs.sidebarModelo.textContent = `${formatPercent(modelos.hit_rate_modelo || 0, true)} / ${formatPercent(modelos.hit_rate_llm || 0, true)}`;
  refs.sidebarModeloTexto.textContent = `${modeloStatus.esta_ajustado ? "Modelo ajustado" : "Modelo frio"} | ${modeloStatus.batch_carregado ? "batch on" : "batch off"}`;
}

function profilesFallback(autoStatus) {
  const total = readNumber((autoStatus || {}).config?.notional_usdt, 0);
  const diario = Math.max(0, total - (total * 0.5) - (total * 0.25));
  return [
    { id: "mini", nome: "Mini trading", descricao: "50% do capital para entradas frequentes.", capital_usdt: total * 0.5, lucro_minimo_usdt: 0.01, habilitado: total > 0, motivo_status: "pronto" },
    { id: "ganancioso", nome: "Trading ganancioso", descricao: "25% do capital para ciclos mais seletivos.", capital_usdt: total * 0.25, lucro_minimo_usdt: 0.5, habilitado: total > 0, motivo_status: "pronto" },
    { id: "diario", nome: "Trade diario", descricao: "25% reservado para a melhor oportunidade do dia.", capital_usdt: diario, lucro_minimo_usdt: 0.15, habilitado: total > 0, motivo_status: "pronto" },
  ];
}

function renderBot() {
  const autoStatus = state.auto || {};
  const perfis = (autoStatus.perfis_capital || []).length ? autoStatus.perfis_capital : profilesFallback(autoStatus);
  const perfilAtivo = autoStatus.perfil_ativo || {};
  const confirmacao = autoStatus.ultima_confirmacao_composta || {};
  const extratoPar = autoStatus.extrato_par || {};
  const focoSimbolo = autoStatus.simbolo_foco || (autoStatus.config || {}).simbolo || DASHBOARD_SYMBOL;
  const paresRanqueados = (autoStatus.pares_ranqueados || []).slice(0, 3);
  const resumoRanking = paresRanqueados.length
    ? paresRanqueados.map((item) => `${item.simbolo} ${traduzirAcao(item.acao_prioritaria)}`).join(" | ")
    : "Sem ranking multiativo";
  const capitalTextoServidor = String(readNumber((autoStatus.config || {}).notional_usdt || 0, 0) || "");
  const capitalTextoExibicao = state.capitalManualTexto || capitalTextoServidor;
  refs.botStatus.className = autoStatus.ativo ? "badge badge--positive" : "badge badge--soft";
  refs.botStatus.textContent = autoStatus.ativo ? "Ligado" : "Pausado";
  refs.botToggleBtn.textContent = autoStatus.ativo ? "Desligar bot" : "Ligar bot";
  refs.botToggleBtn.disabled = state.botCarregando;
  if (document.activeElement !== refs.botCapitalInput) refs.botCapitalInput.value = capitalTextoExibicao;
  refs.botCapitalStatus.textContent = autoStatus.ativo
    ? `Executando ${traduzirEstadoCiclo(autoStatus.estado_ciclo)} com foco em ${focoSimbolo}.`
    : "O bot divide esse capital entre mini, ganancioso e diario automaticamente.";
  renderMetricList(refs.botResumo, [
    { rotulo: "Capital total", valor: formatCurrency((autoStatus.config || {}).notional_usdt), detalhe: `Intervalo ${(autoStatus.config || {}).intervalo_segundos || 30}s` },
    { rotulo: "Ultima acao", valor: traduzirAcao(autoStatus.ultima_acao), detalhe: traduzirMotivo(autoStatus.ultimo_motivo) },
    { rotulo: "Foco multiativo", valor: focoSimbolo, detalhe: resumoRanking },
    { rotulo: "Extrato do par", valor: traduzirAcao(autoStatus.ultima_acao_par), detalhe: `${formatDate(autoStatus.ultima_acao_par_ts)} -> Proxima ${traduzirAcao(autoStatus.proxima_acao_esperada)}` },
    { rotulo: "Perfil ativo", valor: perfilAtivo.nome || "Aguardando", detalhe: `Capital ${formatCurrency(perfilAtivo.capital_usdt)}` },
    { rotulo: "Lucro esperado", valor: formatCurrency(autoStatus.ultimo_lucro_esperado_pct * ((autoStatus.config || {}).notional_usdt || 0)), detalhe: `Preco ${formatCurrency(autoStatus.ultimo_preco)}` },
    { rotulo: "Ultima compra / venda", valor: formatDate(extratoPar.ultima_compra_ts), detalhe: `Venda ${formatDate(extratoPar.ultima_venda_ts)}` },
  ]);
  refs.botPerfis.innerHTML = perfis.map((perfil) => `
    <article class="profile-card ${perfil.id === perfilAtivo.id ? "profile-card--active" : ""}">
      <div class="profile-card__top">
        <div>
          <p class="eyebrow">${escapeHtml(perfil.id || "--")}</p>
          <h4>${escapeHtml(perfil.nome || "--")}</h4>
        </div>
        <span class="${badgeClass(perfil.habilitado ? "operacional" : "travado")}">${escapeHtml(perfil.habilitado ? "Pronto" : traduzirMotivo(perfil.motivo_status))}</span>
      </div>
      <p class="muted">${escapeHtml(perfil.descricao || "Perfil automatico.")}</p>
      <div class="profile-card__bar"><span style="width:${Math.max(8, Math.min(100, readNumber(perfil.fracao_capital, 0) * 100))}%"></span></div>
      <div class="profile-card__meta">
        <span>Capital ${escapeHtml(formatCurrency(perfil.capital_usdt))}</span>
        <span>Lucro minimo ${escapeHtml(formatCurrency(perfil.lucro_minimo_usdt))}</span>
      </div>
    </article>`).join("");
  refs.botCicloStatus.className = badgeClass(autoStatus.estado_ciclo);
  refs.botCicloStatus.textContent = traduzirEstadoCiclo(autoStatus.estado_ciclo);
  renderMetricList(refs.botCicloResumo, [
    { rotulo: "Ciclo", valor: traduzirEstadoCiclo(autoStatus.estado_ciclo), detalhe: `Inicio ${formatDate(autoStatus.ciclo_iniciado_ts)}` },
    { rotulo: "Entrada / atual", valor: `${formatCurrency(autoStatus.ciclo_preco_entrada)} / ${formatCurrency(autoStatus.ciclo_preco_atual)}`, detalhe: `Qtd ${formatNumber(autoStatus.ciclo_quantidade || 0, 6)}` },
    { rotulo: "Lucro aberto", valor: formatCurrency(autoStatus.ciclo_lucro_liquido_aberto_usdt), detalhe: `Retorno ${formatPercent(autoStatus.ciclo_retorno_liquido_aberto_pct || 0, false)}` },
    { rotulo: "Melhor ponto", valor: formatCurrency(autoStatus.ciclo_melhor_lucro_liquido_usdt), detalhe: `Score composto ${formatPercent(confirmacao.pontuacao || 0, false)}` },
  ]);
  const trades = ((state.painel || {}).historico_negociacoes || []).slice(-12).reverse();
  refs.botTradesTotal.textContent = `${trades.length} trades`;
  refs.tabelaBotTrades.innerHTML = trades.length ? trades.map((trade) => `
    <tr>
      <td>${escapeHtml(formatDate(trade.horario))}</td>
      <td><span class="${badgeClass(trade.lado)}">${escapeHtml(traduzirAcao(trade.lado))}</span></td>
      <td>${escapeHtml(formatCurrency(trade.preco))}</td>
      <td>${escapeHtml(formatCurrency(trade.valor_usdt))}</td>
      <td>${trade.lucro_liquido_usdt == null ? "--" : escapeHtml(formatCurrency(trade.lucro_liquido_usdt))}</td>
    </tr>`).join("") : `<tr><td colspan="5">Sem trades executados pela conta ainda.</td></tr>`;
  refs.sidebarBot.textContent = autoStatus.ativo ? "Ligado" : "Pausado";
  refs.sidebarBotTexto.textContent = `${traduzirEstadoCiclo(autoStatus.estado_ciclo)} | ${perfilAtivo.nome || traduzirMotivo(autoStatus.ultimo_motivo) || "Sem perfil ativo"}`;
}

function renderNewsTabs() {
  refs.newsTabs.innerHTML = NEWS_SYMBOLS.map((simbolo) => `
    <button class="symbol-tabs__item ${simbolo === state.simboloNoticiasAtual ? "symbol-tabs__item--active" : ""}" type="button" data-simbolo="${simbolo}">
      ${simbolo}
    </button>`).join("");
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
    refs.newsFrames.innerHTML = `<article class="empty-state">Sem iframes carregados.</article>`;
    return;
  }
  const meta = pacote.meta || {};
  const fontes = (meta.fontes_detalhadas || []).slice(0, 10);
  const itens = (pacote.itens || []).slice(0, 12);
  refs.newsAtualizacao.className = meta.cache_usado ? "badge badge--soft" : "badge badge--positive";
  refs.newsAtualizacao.textContent = meta.cache_usado ? "Cache recente" : "Atualizado";
  renderMetricList(refs.newsResumo, [
    { rotulo: "Simbolo", valor: pacote.simbolo || state.simboloNoticiasAtual, detalhe: `Atualizado ${formatDate(meta.atualizado_em)}` },
    { rotulo: "Sentimento geral", valor: formatNumber(meta.sentimento_geral || 0, 3), detalhe: `Confianca ${formatPercent(meta.confianca || 0, false)}` },
    { rotulo: "Fontes com retorno", valor: `${meta.fontes_com_retorno || 0}/${meta.fontes_monitoradas || 0}`, detalhe: `Minimo ${meta.fontes_minimas_exigidas || 10}` },
    { rotulo: "Classificacao", valor: meta.status_classificacao || "--", detalhe: `Buscas hoje ${meta.buscas_hoje || 0}/${meta.max_buscas_dia || 0}` },
  ]);
  refs.newsFontesPeso.innerHTML = fontes.length ? fontes.map((fonte) => `
    <article class="source-item">
      <div class="source-item__top">
        <div>
          <h4>${escapeHtml(fonte.nome || "--")}</h4>
          <p class="muted">${escapeHtml(fonte.dominio || "--")}</p>
        </div>
        <span class="${badgeClass(fonte.status === "com_retorno" ? "operacional" : "travado")}">${escapeHtml(formatPercent((fonte.peso_pct || 0), true))}</span>
      </div>
      <div class="source-bar"><span style="width:${Math.max(6, Math.min(100, readNumber(fonte.peso_pct, 0)))}%"></span></div>
      <div class="source-item__meta">
        <span>Base ${escapeHtml(formatPercent(fonte.peso_base || 0, false))}</span>
        <span>Itens ${escapeHtml(String(fonte.itens_encontrados || 0))}</span>
        <span>Sentimento ${escapeHtml(formatNumber(fonte.sentimento_medio || 0, 3))}</span>
      </div>
    </article>`).join("") : `<article class="empty-state">Nenhuma fonte ranqueada para este simbolo.</article>`;
  refs.newsHeadlinesTotal.textContent = `${itens.length} itens`;
  refs.newsHeadlines.innerHTML = itens.length ? itens.map((item) => `
    <article class="headline">
      <div class="headline__meta">
        <span class="${badgeClass(item.impacto === "alto" ? "operacional" : "sincronizado")}">${escapeHtml(item.fonte || "--")}</span>
        <span>${escapeHtml(formatDate(item.publicado_em))}</span>
      </div>
      <a href="${escapeHtml(item.link || "#")}" target="_blank" rel="noreferrer noopener">${escapeHtml(item.titulo || "--")}</a>
      <p>${escapeHtml(item.resumo_analise || item.descricao || "Sem resumo da manchete.")}</p>
    </article>`).join("") : `<article class="empty-state">Sem headlines recentes para este simbolo.</article>`;
  refs.newsFrames.innerHTML = fontes.length ? fontes.map((fonte) => `
    <article class="iframe-card">
      <div class="iframe-card__top">
        <div>
          <p class="eyebrow">${escapeHtml(pacote.simbolo || state.simboloNoticiasAtual)}</p>
          <h4>${escapeHtml(fonte.nome || "--")}</h4>
          <p class="muted">Peso ${escapeHtml(formatPercent((fonte.peso_pct || 0), true))} | ${escapeHtml(String(fonte.itens_encontrados || 0))} manchetes</p>
        </div>
        <a class="iframe-card__link" href="${escapeHtml(fonte.rss_url || "#")}" target="_blank" rel="noreferrer noopener">RSS</a>
      </div>
      <iframe title="${escapeHtml(`${pacote.simbolo}-${fonte.nome}`)}" loading="lazy" src="${escapeHtml(fonte.iframe_url || "#")}"></iframe>
    </article>`).join("") : `<article class="empty-state">Sem paineis de fonte para abrir.</article>`;
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
  const capitalServidor = String(readNumber(((state.auto || {}).config || {}).notional_usdt || 0, 0) || "");
  if (!state.capitalManualTexto || state.capitalManualTexto === capitalServidor) {
    state.capitalManualTexto = capitalServidor;
  }
  renderBot();
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
  const tarefas = [carregarDashboard(), carregarBot()];
  if (state.tabAtual === "noticias" || forceNews || Object.keys(state.noticias).length) tarefas.push(carregarNoticias(forceNews));
  const resultados = await Promise.allSettled(tarefas);
  const falha = resultados.find((item) => item.status === "rejected");
  if (falha) {
    const erro = falha.reason instanceof Error ? falha.reason : new Error(String(falha.reason || "falha"));
    if (erro.status === 401 || erro.message.includes("sessao_binance_ausente_ou_expirada") || erro.message.includes("401")) {
      limparSessaoExpirada();
      return;
    }
    refs.statusConexao.className = "badge badge--danger";
    refs.statusConexao.textContent = "Falha parcial";
  } else {
    refs.statusConexao.className = "badge badge--positive";
    refs.statusConexao.textContent = "Conectado";
  }
  atualizarUltimaSincronizacao();
}

async function ligarOuDesligarBot() {
  if (state.botCarregando) return;
  const notionalDigitado = readNumber(state.capitalManualTexto || refs.botCapitalInput.value, 0);
  state.botCarregando = true;
  renderBot();
  try {
    if (state.auto?.ativo) {
      await requestJson("/v1/auto/stop", { method: "POST", body: JSON.stringify({}) });
    } else {
      if (notionalDigitado <= 0) throw new Error("Informe um capital valido em USDT.");
      await requestJson("/v1/auto/config", { method: "PUT", body: JSON.stringify({ notional_usdt: notionalDigitado }) });
      await requestJson("/v1/auto/start", {
        method: "POST",
        body: JSON.stringify({
          simbolo: DASHBOARD_SYMBOL,
          intervalo_segundos: readNumber((state.auto || {}).config?.intervalo_segundos, 30) || 30,
          notional_usdt: notionalDigitado,
          lado_inicial: "BUY",
        }),
      });
      state.capitalManualTexto = String(notionalDigitado);
    }
    await refreshAll(false);
  } catch (error) {
    if (error instanceof Error && error.status === 401) {
      limparSessaoExpirada();
      return;
    }
    refs.botCapitalStatus.textContent = error instanceof Error ? error.message : "Falha ao alterar o estado do bot.";
  } finally {
    state.botCarregando = false;
    if (state.autenticado) {
      await carregarBot().catch(() => {});
    }
  }
}

async function salvarCapitalSeNecessario() {
  if (!state.autenticado || !state.auto?.ativo) return;
  const notional = readNumber(state.capitalManualTexto || refs.botCapitalInput.value, 0);
  if (notional <= 0) return;
  try {
    await requestJson("/v1/auto/config", { method: "PUT", body: JSON.stringify({ notional_usdt: notional }) });
  } catch (error) {
    if (error instanceof Error && error.status === 401) {
      limparSessaoExpirada();
      return;
    }
    throw error;
  }
  await carregarBot();
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
    state.sessao = sessao;
    state.autenticado = true;
    renderSession();
    startPolling();
    await refreshAll(false);
  } catch (error) {
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
  state.capitalManualTexto = "";
  stopPolling();
  renderSession();
  renderDashboard();
  renderBot();
  renderNews();
}

async function verificarSessao() {
  try {
    const sessao = await requestJson("/v1/sessao/status");
    state.autenticado = !!sessao.autenticado;
    state.sessao = state.autenticado ? sessao : null;
    renderSession();
    if (state.autenticado) {
      startPolling();
      await refreshAll(false);
    }
  } catch {
    state.autenticado = false;
    state.sessao = null;
    renderSession();
  }
}

function startPolling() {
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
refs.botCapitalInput.addEventListener("input", () => {
  state.capitalManualTexto = refs.botCapitalInput.value.trim();
});
refs.botCapitalInput.addEventListener("change", () => { salvarCapitalSeNecessario().catch(() => {}); });
refs.newsTabs.addEventListener("click", (event) => {
  const botao = event.target.closest("[data-simbolo]");
  if (!botao) return;
  state.simboloNoticiasAtual = botao.dataset.simbolo;
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
