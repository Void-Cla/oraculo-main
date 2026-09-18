/* Oráculo Auto-Trading — frontend minimalista */
"use strict";

const POLL_MS = 20000; // 20s
const PARES = ["BTCUSDT","ETHUSDT","BNBUSDT"];

// ── refs ──────────────────────────────────────────
const $ = id => document.getElementById(id);
const r = {
  login: $("login"), app: $("app"),
  formLogin: $("formLogin"), apiKey: $("apiKey"), apiSecret: $("apiSecret"),
  usarTestnet: $("usarTestnet"), modoLabel: $("modoLabel"),
  btnEntrar: $("btnEntrar"), erroLogin: $("erroLogin"),
  badgeModo: $("badgeModo"), badgeConexao: $("badgeConexao"), labelConta: $("labelConta"),
  btnSair: $("btnSair"),
  badgeBot: $("badgeBot"),
  valSaldo: $("valSaldo"), valSaldoPct: $("valSaldoPct"),
  valSaldoInicial: $("valSaldoInicial"), valMudancaCarteira: $("valMudancaCarteira"),
  saldoInicialData: $("saldoInicialData"), mudancaSessaoInfo: $("mudancaSessaoInfo"),
  btnCarteira: $("btnCarteira"), carteiraDialog: $("carteiraDialog"),
  btnFecharCarteira: $("btnFecharCarteira"), listaCarteira: $("listaCarteira"),
  carteiraVazia: $("carteiraVazia"), carteiraDetalhe: $("carteiraDetalhe"),
  iaPaginaStatus: $("iaPaginaStatus"), iaPaginaModelo: $("iaPaginaModelo"), iaPaginaUso: $("iaPaginaUso"),
  iaPaginaChaves: $("iaPaginaChaves"),
  btnAtualizarNoticias: $("btnAtualizarNoticias"), noticiasStatus: $("noticiasStatus"),
  listaNoticias: $("listaNoticias"), noticiasVazias: $("noticiasVazias"),
  capitalPct: $("capitalPct"), capitalPctLabel: $("capitalPctLabel"), capitalUsdt: $("capitalUsdt"),
  btnToggle: $("btnToggle"), msgBot: $("msgBot"),
  tsAtualiza: $("tsAtualiza"), btnRefresh: $("btnRefresh"),
  mWinRate: $("mWinRate"), mTrades: $("mTrades"), mRegime: $("mRegime"),
  mBnb: $("mBnb"), mTaxa: $("mTaxa"), mMelhorPar: $("mMelhorPar"),
  aiBox: $("aiBox"), aiContent: $("aiContent"), aiModelo: $("aiModelo"), btnAi: $("btnAi"),
  tabelaTrades: $("tabelaTrades"), totalTrades: $("totalTrades"),
};

// ── state ─────────────────────────────────────────
const st = {
  auth: false, sessao: null,
  painel: null, auto: null,
  capitalPct: 30,
  saldoUsdt: 0,
  pollingId: null,
  loading: false,
  // Sincronização slider↔backend (veracidade): "dirty" = usuário mexeu e o novo valor ainda
  // não foi confirmado pelo backend; enquanto dirty, o poll NÃO sobrescreve a posição do slider.
  sliderDirty: false,
  sliderTimer: null,
  aiSaude: null,
  chavesIa: null,
  ativosCarteira: [],
  ativoCarteiraSelecionado: null,
  paginaAtiva: "painel",
  noticias: null,
  carregandoNoticias: false,
};

// ── helpers ───────────────────────────────────────
const esc = v => String(v ?? "").replace(/[&<>"']/g, c =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const num = (v, fb=0) => { if (v == null || v === "" || typeof v === "boolean") return fb; const n=Number(v); return Number.isFinite(n)?n:fb; };
const pct = (v, dec=2) => `${num(v,0).toFixed(dec)}%`;
const usd = v => `$${num(v,0).toFixed(2)}`;
const ts2str = v => { const t=num(v,0); if(!t) return "--"; const d=new Date(t<1e12?t*1000:t); return d.toLocaleTimeString("pt-BR"); };
const MOEDAS_ESTAVEIS = new Set(["USDT", "USDC", "BUSD", "FDUSD", "TUSD", "DAI"]);
const REGIMES_LEIGOS = {
  LOW_VOL: "Mercado calmo",
  HIGH_VOL: "Mercado agitado",
  RANGE: "Mercado lateral",
  TREND_UP: "Tendência de alta",
  TREND_DOWN: "Tendência de baixa",
};
function quantidadeCripto(valor, ativo="") {
  const quantidade = num(valor, null);
  if (quantidade === null) return "--";
  const casas = MOEDAS_ESTAVEIS.has(String(ativo).toUpperCase()) ? 2 : (Math.abs(quantidade) > 0 && Math.abs(quantidade) < 1e-8 ? 12 : 8);
  return quantidade.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
}

async function api(url, opts={}) {
  const r2 = await fetch(url, { credentials:"same-origin", headers:{"Content-Type":"application/json",...(opts.headers||{})}, ...opts });
  const text = await r2.text();
  let data = {};
  try { data = JSON.parse(text); } catch { data = { detail: text }; }
  if (!r2.ok) { const e = new Error(data.detail || `HTTP ${r2.status}`); e.status=r2.status; throw e; }
  return data;
}

function setClass(el, cls) { if(el) el.className = cls; }
function setBadge(el, txt, cls, pulse=false) {
  if(!el) return;
  el.textContent = txt;
  el.className = `badge ${cls||""}${pulse?" badge-pulse":""}`;
}

// ── saldo → capital_usdt ──────────────────────────
function calcCapitalUsdt() {
  return (st.saldoUsdt * st.capitalPct / 100).toFixed(2);
}

function renderCapital() {
  r.capitalPctLabel.textContent = `${st.capitalPct}%`;
  r.capitalPct.setAttribute("aria-valuenow", String(st.capitalPct));
  // Enquanto o usuário arrasta (dirty), mostra a ESTIMATIVA local com aviso de "aplicando";
  // fora disso, mostra o valor CONFIRMADO pelo backend (o que o bot realmente usa).
  const notionalBackend = num(st.auto?.config?.notional_usdt, 0);
  if (st.sliderDirty) {
    r.capitalUsdt.textContent = `≈ ${calcCapitalUsdt()} USDT (aplicando…)`;
  } else if (notionalBackend > 0) {
    r.capitalUsdt.textContent = `✓ ${notionalBackend.toFixed(2)} USDT aplicado no bot`;
  } else {
    r.capitalUsdt.textContent = `≈ ${calcCapitalUsdt()} USDT (será aplicado ao iniciar)`;
  }
}

// Poll → slider: reflete o notional REAL configurado no backend (nunca o contrário enquanto
// o usuário arrasta). Sem isso, a UI mostrava uma % que o bot podia não estar usando.
function syncCapitalDoBackend() {
  if (st.sliderDirty) return;
  const notionalBackend = num(st.auto?.config?.notional_usdt, 0);
  if (notionalBackend <= 0 || st.saldoUsdt <= 0) { renderCapital(); return; }
  const pct = Math.min(100, Math.max(10, Math.round((notionalBackend / st.saldoUsdt) * 100 / 10) * 10));
  st.capitalPct = pct;
  r.capitalPct.value = String(pct);
  renderCapital();
}

// Slider → backend (debounced): aplica o novo capital AO VIVO via PUT /v1/auto/config —
// o bot em execução passa a usar o valor imediatamente (AUTO_TRADER.atualizar_config).
async function aplicarCapital() {
  if (!st.auth) { st.sliderDirty = false; return; }
  const alvo = Number((st.saldoUsdt * st.capitalPct / 100).toFixed(2));
  if (!(alvo > 0)) { st.sliderDirty = false; renderCapital(); return; }
  try {
    const resp = await api("/v1/auto/config", { method: "PUT", body: JSON.stringify({ notional_usdt: alvo }) });
    const aplicado = num(resp?.ajustes?.aplicado?.notional_usdt, alvo);
    st.auto = { ...(st.auto || {}), config: { ...st.auto?.config, notional_usdt: aplicado } };
    st.sliderDirty = false;
    renderCapital();
    r.msgBot.textContent = `capital atualizado: ${aplicado.toFixed(2)} USDT`;
  } catch (e) {
    // Falhou (ex.: config ainda não operacional) — o valor será enviado no próximo Start
    // via capital_pct; a UI deixa claro que ainda NÃO está aplicado.
    st.sliderDirty = false;
    r.capitalUsdt.textContent = `≈ ${calcCapitalUsdt()} USDT (será aplicado ao iniciar)`;
  }
}

// ── render principal ───────────────────────────────
function renderSession() {
  r.login.classList.toggle("hidden", st.auth);
  r.app.classList.toggle("hidden", !st.auth);
  if (!st.sessao) return;
  const testnet = st.sessao.modo_testnet;
  setBadge(r.badgeModo, testnet?"Testnet":"Conta Real", testnet?"badge-ok":"badge-danger");
  setBadge(r.badgeConexao, "Conectado", "badge-ok");
  r.labelConta.textContent = st.sessao.api_key_mascarada || "";
}

function abrirPagina(pagina) {
  const paginas = ["painel", "ia", "mercado"];
  if (!paginas.includes(pagina)) return;
  st.paginaAtiva = pagina;
  for (const nome of paginas) {
    $(`pagina${nome[0].toUpperCase()}${nome.slice(1)}`).classList.toggle("hidden", nome !== pagina);
  }
  document.querySelectorAll("[data-pagina]").forEach(aba => {
    aba.setAttribute("aria-selected", String(aba.dataset.pagina === pagina));
  });
  if (pagina === "ia") renderPaginaIa();
  if (pagina === "mercado") {
    renderNoticias();
    if (st.noticias === null) carregarNoticias().catch(() => {});
  }
}

function renderValor(id, valor, sinal=false) {
  const el = $(id);
  const n = num(valor, null);
  el.textContent = n === null ? "--" : usd(n);
  el.className = `stat-big ${sinal && n !== null ? (n >= 0 ? "ok" : "danger") : ""}`;
}

function renderComparacaoSessao(p) {
  const s = p.comparacao_sessao || {};
  renderValor("valSaldoInicial", s.saldo_inicial_usdt);
  const registro = s.registrado_em;
  const data = registro ? new Date(typeof registro === "number" && registro < 1e12 ? registro * 1000 : registro) : null;
  r.saldoInicialData.textContent = data && !Number.isNaN(data.getTime()) ? `Registrado em ${data.toLocaleString("pt-BR")}` : "Aguardando a primeira leitura";
  const ativos = Array.isArray(s.ativos) ? s.ativos : [];
  const mudancas = ativos.filter(ativo => num(ativo.variacao_quantidade, 0) !== 0);
  if (s.disponivel !== true) {
    r.valMudancaCarteira.textContent = "Indisponível";
    r.valMudancaCarteira.className = "stat-big stat-delta-list neutral";
    r.mudancaSessaoInfo.textContent = "Aguardando a primeira leitura da carteira";
    return;
  }
  r.valMudancaCarteira.textContent = mudancas.length
    ? mudancas.map(ativo => {
      const delta = num(ativo.variacao_quantidade, 0);
      return `${String(ativo.ativo || "").toUpperCase()} ${delta >= 0 ? "+" : "−"}${quantidadeCripto(Math.abs(delta), ativo.ativo)}`;
    }).join(" · ")
    : "Sem mudança";
  r.valMudancaCarteira.className = "stat-big stat-delta-list";
  r.mudancaSessaoInfo.textContent = mudancas.length ? "Quantidade por moeda desde o início da sessão" : "As quantidades estão iguais ao início da sessão";
}

function renderPaginaIa() {
  const saude = st.aiSaude;
  if (!saude) {
    r.iaPaginaStatus.textContent = "Indisponível";
    r.iaPaginaModelo.textContent = "--";
    r.iaPaginaUso.textContent = "--";
  } else {
    r.iaPaginaStatus.textContent = saude.chave_presente === false && saude.provedor !== "ollama"
      ? "Não configurada no servidor"
      : saude.em_cooldown ? "Em pausa por falhas" : saude.disponivel ? "Ativa" : "Indisponível";
    r.iaPaginaModelo.textContent = saude.modelo || saude.provedor || "--";
    const chamadas = num(saude.chamadas_dia, null);
    const limite = num(saude.max_dia, null);
    r.iaPaginaUso.textContent = chamadas === null ? "Não informado" : `${chamadas}${limite !== null && limite > 0 ? ` de ${limite}` : ""} consultas`;
  }
  const provedores = Array.isArray(st.chavesIa?.provedores) ? st.chavesIa.provedores : [];
  r.iaPaginaChaves.textContent = provedores.length
    ? provedores.map(item => `${String(item.provedor || "IA").toUpperCase()}: ${item.configurada === true ? "pronta" : "não configurada"}`).join(" · ")
    : "Status indisponível";
}

function textoDataNoticia(valor) {
  const numero = num(valor, null);
  const data = numero !== null
    ? new Date(numero < 1e12 ? numero * 1000 : numero)
    : new Date(String(valor || ""));
  return Number.isNaN(data.getTime()) ? "Data não informada" : data.toLocaleString("pt-BR");
}

function renderNoticias() {
  const noticias = st.noticias;
  const itens = Array.isArray(noticias?.itens) ? noticias.itens : [];
  r.listaNoticias.replaceChildren();
  r.noticiasVazias.classList.toggle("hidden", itens.length > 0);
  const meta = noticias?.meta || {};
  const atualizado = meta.atualizado_em ? `Atualizado em ${textoDataNoticia(meta.atualizado_em)}` : "Sem atualização informada";
  r.noticiasStatus.textContent = `${atualizado} · ${itens.length} notícia${itens.length === 1 ? "" : "s"}`;
  for (const item of itens) {
    const artigo = document.createElement("article");
    artigo.className = "noticia";
    const titulo = document.createElement("h3");
    titulo.textContent = String(item?.titulo || "Título não disponível").trim() || "Título não disponível";
    const detalhes = document.createElement("p");
    const fonte = String(item?.fonte || "Fonte não informada").trim() || "Fonte não informada";
    detalhes.textContent = `${fonte} · ${textoDataNoticia(item?.publicado_em)}`;
    artigo.append(titulo, detalhes);
    r.listaNoticias.append(artigo);
  }
}

async function carregarNoticias() {
  if (st.carregandoNoticias) return;
  st.carregandoNoticias = true;
  r.btnAtualizarNoticias.disabled = true;
  r.noticiasStatus.textContent = "Atualizando notícias…";
  try {
    st.noticias = await api("/v1/noticias?simbolo=BTCUSDT");
    renderNoticias();
  } catch (erro) {
    r.noticiasStatus.textContent = "Não foi possível carregar notícias agora.";
  } finally {
    st.carregandoNoticias = false;
    r.btnAtualizarNoticias.disabled = false;
  }
}

function normalizarAtivosCarteira(ativos) {
  return (Array.isArray(ativos) ? ativos : [])
    .map(item => ({
      ativo: String(item?.ativo || "").toUpperCase(),
      quantidade: num(item?.total, null),
      valorUsdt: num(item?.valor_usdt, null),
    }))
    .filter(item => item.ativo && item.quantidade !== null && item.quantidade > 0)
    .sort((a, b) => b.quantidade - a.quantidade || a.ativo.localeCompare(b.ativo));
}

function renderCarteira() {
  const ativos = st.ativosCarteira;
  r.btnCarteira.disabled = ativos.length === 0;
  r.btnCarteira.setAttribute("aria-label", ativos.length ? `Ver ${ativos.length} criptomoedas na carteira` : "Sem criptomoedas na carteira");
  r.listaCarteira.replaceChildren();
  r.carteiraVazia.classList.toggle("hidden", ativos.length > 0);
  if (!ativos.some(item => item.ativo === st.ativoCarteiraSelecionado)) st.ativoCarteiraSelecionado = null;
  for (const item of ativos) {
    const botao = document.createElement("button");
    botao.type = "button";
    botao.className = "carteira-ativo";
    botao.textContent = item.ativo;
    botao.setAttribute("aria-pressed", String(item.ativo === st.ativoCarteiraSelecionado));
    botao.addEventListener("click", () => selecionarAtivoCarteira(item.ativo));
    r.listaCarteira.append(botao);
  }
  const selecionado = ativos.find(item => item.ativo === st.ativoCarteiraSelecionado);
  r.carteiraDetalhe.classList.toggle("hidden", !selecionado);
  if (selecionado) {
    const valor = selecionado.valorUsdt === null ? "USDT indisponível" : usd(selecionado.valorUsdt);
    r.carteiraDetalhe.textContent = `${selecionado.ativo}: ${quantidadeCripto(selecionado.quantidade, selecionado.ativo)} · ${valor}`;
  } else {
    r.carteiraDetalhe.textContent = "";
  }
}

function selecionarAtivoCarteira(ativo) {
  st.ativoCarteiraSelecionado = ativo;
  renderCarteira();
}

function abrirCarteira() {
  if (!st.ativosCarteira.length) return;
  if (typeof r.carteiraDialog.showModal === "function") r.carteiraDialog.showModal();
  else r.carteiraDialog.setAttribute("open", "");
  renderCarteira();
  r.btnFecharCarteira.focus();
}

function fecharCarteira() {
  if (typeof r.carteiraDialog.close === "function" && r.carteiraDialog.open) r.carteiraDialog.close();
  else r.carteiraDialog.removeAttribute("open");
  r.btnCarteira.focus();
}

function renderPainel() {
  const p = st.painel || {};
  const conta = p.conta || {};
  const taxa = conta.taxas_efetivas || {};
  const scanner = (((p.multiativos||{}).scanner)||{});
  // Saldo
  st.saldoUsdt = num(conta.saldo_total_estimado_usdt, 0);
  renderValor("valSaldo", conta.saldo_total_estimado_usdt);
  const patrimonioMarcado = conta.patrimonio_marcado || {};
  r.valSaldoPct.textContent = patrimonioMarcado.conversao_completa === true
    ? "Total convertido para USDT"
    : "Alguma moeda ainda não tem cotação em USDT";
  st.ativosCarteira = normalizarAtivosCarteira(patrimonioMarcado.ativos);
  renderCarteira();
  renderComparacaoSessao(p);
  st.noticias = p.noticias || st.noticias;
  if (st.paginaAtiva === "mercado") renderNoticias();
  renderCapital();
  // Taxas / BNB — exibe a taxa que o motor USA nas contas (taker_pct_operacional, com piso).
  // O testnet da Binance devolve 0% cru; mostrar 0.000% aqui seria "verdade da fonte" mas
  // MENTIRA sobre o cálculo — o bot nunca precifica com taxa zero.
  const taxaAplicada = num(taxa.taker_pct_operacional, num(taxa.taker_pct_efetiva, 0.1) || 0.1);
  const bnbOk = !!taxa.desconto_bnb_ativo;
  r.mBnb.textContent = bnbOk ? "✓ Ativo" : "✗ Inativo";
  r.mBnb.className = `${bnbOk?"ok":"danger"}`;
  r.mTaxa.textContent = pct(taxaAplicada, 3);
  // Melhor par
  const melhor = scanner.melhor_oportunidade || {};
  r.mMelhorPar.textContent = melhor.simbolo ? `${melhor.simbolo} ${melhor.acao_sugerida||""}` : "--";
  // Win rate
  const hist = p.historico_negociacoes || [];
  // Ciclos do motor são distintos dos fills da conta e reiniciam com o motor.
  const resumoCiclos = (st.auto||{}).historico_ciclos_resumo || {};
  const wr = num(resumoCiclos.total_ciclos) > 0 && resumoCiclos.win_rate != null
    ? pct(resumoCiclos.win_rate * 100, 1)
    : "Indisponível";
  r.mWinRate.textContent = wr;
  r.mTrades.textContent = resumoCiclos.total_ciclos ?? "--";
  // Regime - read from modelos.decisao_atual or mercado
  const modelos = p.modelos || {};
  const decisao = modelos.decisao_atual || {};
  const regime = decisao.regime || ((p.mercado||{}).feature_recente||{}).regime || ((p.multiativos||{}).regime_dominante) || "--";
  r.mRegime.textContent = REGIMES_LEIGOS[regime] || regime;
  // Tabela trades
  const recentes = [...hist].reverse().slice(0, 10);
  r.totalTrades.textContent = `${hist.length} execuções na janela · ${recentes.length} exibidas`;
  if (!recentes.length) {
    r.tabelaTrades.innerHTML = `<tr><td colspan="7" class="empty">Sem trades registrados.</td></tr>`;
  } else {
    const simb = p.simbolo || (p.conta||{}).ativo_base || "BTCUSDT";
    r.tabelaTrades.innerHTML = recentes.map(t => {
      const pnlT = t.pnl_confiavel === false ? null : num(t.lucro_liquido_usdt, null);
      const pnlPctT = pnlT !== null && num(t.valor_usdt,0) > 0 ? pnlT/num(t.valor_usdt,1)*100 : null;
      const cls = pnlT === null ? "" : pnlT >= 0 ? "ok" : "danger";
      const lado = t.lado === "COMPRA" ? "BUY" : (t.lado === "VENDA" ? "SELL" : t.lado);
      return `<tr>
        <td>${esc(ts2str(t.horario))}</td>
        <td>${esc(t.ativo_base||simb)}</td>
        <td><span class="badge ${lado==="BUY"?"badge-ok":"badge-danger"}">${esc(lado)}</span></td>
        <td>${esc(usd(t.preco))}</td>
        <td>${esc(usd(t.valor_usdt))}</td>
        <td class="${cls}">${pnlT===null?"--":esc(usd(pnlT))}</td>
        <td class="${cls}">${pnlPctT===null?"--":esc((pnlPctT>=0?"+":"")+pct(pnlPctT))}</td>
      </tr>`;
    }).join("");
  }
  const agora = new Date();
  r.tsAtualiza.textContent = agora.toLocaleTimeString("pt-BR");
  r.tsAtualiza.setAttribute("datetime", agora.toISOString());
}

function renderBot() {
  const a = st.auto || {};
  const ativo = !!a.ativo;
  setBadge(r.badgeBot, ativo?"Ativo":"Pausado", ativo?"badge-ok":"", ativo);
  r.btnToggle.textContent = st.loading ? "Aguarde..." : (ativo?"Parar Auto-Trading":"Iniciar Auto-Trading");
  r.btnToggle.className = `btn-primary btn-lg${ativo?" running":""}`;
  r.btnToggle.disabled = st.loading;
  const motivo = a.ultimo_motivo || "";
  const bloqueado = !!a.retomada_operacoes_bloqueadas;
  r.msgBot.textContent = bloqueado ? "⚠ Operações bloqueadas por perda crítica." : (motivo ? motivo.replaceAll("_"," ") : "");
}

// ── AI Insight ─────────────────────────────────────
function renderAiInsight(insight) {
  if (!insight) { r.aiContent.innerHTML = `<p class="muted-sm">Sem dados.</p>`; return; }
  const dir = (insight.direcao||"HOLD").toUpperCase();
  const conf = num(insight.confianca, 0);
  const risco = insight.risco || "baixo";
  const capPct = num(insight.capital_pct_sugerido, 10);
  const dirCls = dir==="BUY"?"buy":dir==="SELL"?"sell":"hold";
  const riscoCls = risco==="alto"?"danger":risco==="medio"?"warn":"ok";
  r.aiModelo.textContent = insight.modelo || "";
  r.aiContent.innerHTML = `
    <div class="ai-row">
      <span class="ai-direction ${dirCls}">${esc(dir)}</span>
      <span class="badge badge-accent">Confiança ${pct(conf*100,1)}</span>
      <span class="badge ${riscoCls==="ok"?"badge-ok":riscoCls==="warn"?"badge-warn":"badge-danger"}">Risco ${esc(risco)}</span>
      <span class="badge badge-accent">Capital sugerido ${esc(capPct)}%</span>
    </div>
    <p class="ai-reasoning">${esc(insight.reasoning||"Sem detalhamento.")}</p>`;
}

// ── API calls ─────────────────────────────────────
async function carregar() {
  r.btnRefresh?.classList.add("spinning");
  try {
    const [painel, auto, aiSaude, chavesIa] = await Promise.all([
      api("/v1/painel/conta?simbolo=BTCUSDT"),
      api("/v1/auto/status"),
      api("/v1/ai/provedor/saude").catch(() => null),  // saúde da IA de decisão (best-effort)
      api("/v1/sessao/ia/chaves").catch(() => null),
    ]);
    st.painel = painel;
    st.auto = auto;
    st.aiSaude = aiSaude;
    st.chavesIa = chavesIa;
    renderPainel();
    renderBot();
    syncCapitalDoBackend();   // slider passa a refletir o notional REAL configurado no bot
  renderAiSaude();
  if (st.paginaAtiva === "ia") renderPaginaIa();
  } catch(e) {
    if (e.status===401) { logout(); return; }
    setBadge(r.badgeConexao, "Erro parcial", "badge-warn");
  } finally {
    r.btnRefresh?.classList.remove("spinning");
  }
}

// Estado REAL da IA de decisão (voto/veto no loop do bot) — transparência: o usuário vê o
// modelo ativo, se está disponível/em cooldown e quanto da cota diária já foi consumido.
function renderAiSaude() {
  const el = $("aiSaudeLine");
  if (!el) return;
  const s = st.aiSaude;
  if (!s) { el.textContent = "IA de decisão: indisponível (sem resposta do backend)"; return; }
  if (s.chave_presente === false && s.provedor !== "ollama") { el.textContent = "IA de decisão: desativada (sem chave de API configurada)"; return; }
  const partes = [`IA de decisão: ${s.modelo || s.provedor || "?"}`];
  if (s.em_cooldown) {
    partes.push(`em pausa por falhas (volta em ${Math.ceil(num(s.cooldown_restante_s, 0) / 60)}min)`);
  } else {
    partes.push(s.disponivel ? "ativa" : "indisponível");
  }
  const chamadas = num(s.chamadas_dia, null);
  const limite = num(s.max_dia, null);
  if (chamadas !== null) partes.push(`${chamadas}${limite > 0 ? `/${limite}` : ""} chamadas hoje`);
  el.textContent = partes.join(" · ");
}

async function consultarAi() {
  r.btnAi.disabled = true;
  r.btnAi.textContent = "Analisando…";
  r.aiContent.innerHTML = `<p class="muted-sm">Consultando IA…</p>`;
  try {
    const insight = await api("/v1/ai/insight?simbolo=BTCUSDT");
    renderAiInsight(insight);
  } catch(e) {
    r.aiContent.innerHTML = `<p class="muted-sm" style="color:var(--danger)">Falha: ${esc(e.message)}</p>`;
  } finally {
    r.btnAi.disabled = false;
    r.btnAi.textContent = "Consultar";
  }
}

async function toggleBot() {
  if (st.loading) return;
  st.loading = true;
  renderBot();
  try {
    if (st.auto?.ativo) {
      await api("/v1/auto/stop", { method:"POST", body:"{}" });
    } else {
      const bloqueado = !!(st.auto||{}).retomada_operacoes_bloqueadas;
      if (bloqueado) throw new Error("operacoes_bloqueadas_por_seguranca");
      await api("/v1/auto/start", {
        method: "POST",
        body: JSON.stringify({
          simbolo: "BTCUSDT",
          intervalo_segundos: 15,
          capital_pct: st.capitalPct,
          lado_inicial: "BUY",
        }),
      });
    }
    await carregar();
  } catch(e) {
    if (e.status===401) { logout(); return; }
    r.msgBot.textContent = e.message || "Falha ao alterar estado do bot.";
  } finally {
    st.loading = false;
    renderBot();
  }
}

async function login(e) {
  e.preventDefault();
  r.btnEntrar.disabled = true;
  r.erroLogin.classList.add("hidden");
  try {
    const sessao = await api("/v1/sessao/entrar", {
      method:"POST",
      body: JSON.stringify({
        api_key: r.apiKey.value.trim(),
        api_secret: r.apiSecret.value.trim(),
        testnet: r.usarTestnet.checked,
      }),
    });
    st.sessao = sessao;
    st.auth = true;
    renderSession();
    startPolling();
    await carregar();
  } catch(e2) {
    r.erroLogin.textContent = e2.message || "Falha no login.";
    r.erroLogin.classList.remove("hidden");
  } finally {
    r.btnEntrar.disabled = false;
  }
}

async function logout() {
  stopPolling();
  if (r.carteiraDialog.open) r.carteiraDialog.close();
  try { await api("/v1/sessao/sair", {method:"POST",body:"{}"}); } catch {}
  st.auth = false; st.sessao = null; st.painel = null; st.auto = null;
  renderSession();
  setBadge(r.badgeConexao, "Desconectado", "");
}

async function verificarSessao() {
  try {
    const s = await api("/v1/sessao/status");
    if (s.autenticado) {
      st.sessao = s; st.auth = true;
      renderSession();
      startPolling();
      await carregar();
    }
  } catch {}
}

function startPolling() {
  stopPolling();
  st.pollingId = setInterval(() => carregar().catch(()=>{}), POLL_MS);
}
function stopPolling() { clearInterval(st.pollingId); }

// ── eventos ───────────────────────────────────────
r.formLogin.addEventListener("submit", login);
r.btnSair.addEventListener("click", () => logout().catch(()=>{}));
r.btnToggle.addEventListener("click", () => toggleBot().catch(()=>{}));
r.btnRefresh.addEventListener("click", () => carregar().catch(()=>{}));
r.btnAi.addEventListener("click", () => consultarAi().catch(()=>{}));
r.btnAtualizarNoticias.addEventListener("click", () => carregarNoticias().catch(()=>{}));
document.querySelectorAll("[data-pagina]").forEach(aba => {
  aba.addEventListener("click", () => abrirPagina(aba.dataset.pagina));
  aba.addEventListener("keydown", evento => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(evento.key)) return;
    const abas = [...document.querySelectorAll("[data-pagina]")];
    const atual = abas.indexOf(aba);
    const destino = evento.key === "Home" ? 0 : evento.key === "End" ? abas.length - 1
      : (atual + (evento.key === "ArrowRight" ? 1 : abas.length - 1)) % abas.length;
    evento.preventDefault();
    abas[destino].focus();
    abrirPagina(abas[destino].dataset.pagina);
  });
});
r.btnCarteira.addEventListener("click", abrirCarteira);
r.btnFecharCarteira.addEventListener("click", fecharCarteira);
r.carteiraDialog.addEventListener("click", evento => {
  if (evento.target === r.carteiraDialog) fecharCarteira();
});
r.usarTestnet.addEventListener("change", () => {
  r.modoLabel.textContent = r.usarTestnet.checked ? "Testnet" : "Conta Real";
});
r.capitalPct.addEventListener("input", () => {
  st.capitalPct = parseInt(r.capitalPct.value);
  st.sliderDirty = true;          // impede o poll de sobrescrever enquanto o usuário decide
  renderCapital();
  clearTimeout(st.sliderTimer);   // debounce: só aplica no backend quando o usuário parar
  st.sliderTimer = setTimeout(() => { aplicarCapital().catch(() => {}); }, 800);
});

// boot
verificarSessao().catch(()=>{});
