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
  valPnl: $("valPnl"), valPnlPct: $("valPnlPct"),
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
};

// ── helpers ───────────────────────────────────────
const esc = v => String(v ?? "").replace(/[&<>"']/g, c =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const num = (v, fb=0) => { const n=Number(v); return isFinite(n)?n:fb; };
const pct = (v, dec=2) => `${num(v,0).toFixed(dec)}%`;
const usd = v => `$${num(v,0).toFixed(2)}`;
const ts2str = v => { const t=num(v,0); if(!t) return "--"; const d=new Date(t<1e12?t*1000:t); return d.toLocaleTimeString("pt-BR"); };

async function api(url, opts={}) {
  const r2 = await fetch(url, { credentials:"same-origin", headers:{"Content-Type":"application/json",...(opts.headers||{})}, ...opts });
  const text = await r2.text();
  let data = {};
  try { data = JSON.parse(text); } catch { data = { detail: text }; }
  if (!r2.ok) { const e = new Error(data.detail || `HTTP ${r2.status}`); e.status=r2.status; throw e; }
  return data;
}

function setClass(el, cls) { if(el) el.className = cls; }
function setBadge(el, txt, cls) { if(!el) return; el.textContent=txt; el.className=`badge ${cls||""}`; }

// ── saldo → capital_usdt ──────────────────────────
function calcCapitalUsdt() {
  return (st.saldoUsdt * st.capitalPct / 100).toFixed(2);
}

function renderCapital() {
  r.capitalPctLabel.textContent = `${st.capitalPct}%`;
  r.capitalUsdt.textContent = `≈ ${calcCapitalUsdt()} USDT`;
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

function renderPainel() {
  const p = st.painel || {};
  const conta = p.conta || {};
  const pnl = p.pnl || {};
  const taxa = conta.taxas_efetivas || {};
  const scanner = (((p.multiativos||{}).scanner)||{});
  // Saldo
  st.saldoUsdt = num(conta.saldo_total_estimado_usdt, 0);
  r.valSaldo.textContent = usd(st.saldoUsdt);
  const pnlV = num(pnl.pnl_total_liquido_usdt, 0);
  const pnlPctV = st.saldoUsdt > 0 ? (pnlV / st.saldoUsdt * 100) : 0;
  r.valPnl.textContent = usd(pnlV);
  r.valPnl.className = `stat-big ${pnlV>=0?"ok":"danger"}`;
  r.valPnlPct.textContent = (pnlV>=0?"+":"")+pct(pnlPctV);
  r.valPnlPct.className = `stat-pct ${pnlV>=0?"ok":"danger"}`;
  renderCapital();
  // Taxas / BNB
  const taxaEfetiva = num(taxa.taker_pct_efetiva, 0.1);
  const bnbOk = !!taxa.desconto_bnb_ativo;
  r.mBnb.textContent = bnbOk ? "✓ Ativo" : "✗ Inativo";
  r.mBnb.className = `${bnbOk?"ok":"danger"}`;
  r.mTaxa.textContent = pct(taxaEfetiva, 3);
  // Melhor par
  const melhor = scanner.melhor_oportunidade || {};
  r.mMelhorPar.textContent = melhor.simbolo ? `${melhor.simbolo} ${melhor.acao_sugerida||""}` : "--";
  // Win rate
  const hist = p.historico_negociacoes || [];
  const ganhos = hist.filter(t => num(t.lucro_liquido_usdt,0) > 0).length;
  // Win rate - prefer auto trader resumo (live), fall back to historical trades
  const resumoCiclos = (st.auto||{}).historico_ciclos_resumo || {};
  const wr = resumoCiclos.win_rate != null
    ? pct(resumoCiclos.win_rate * 100, 1)
    : (hist.length > 0 ? pct(ganhos/hist.length*100, 1) : "--%");
  r.mWinRate.textContent = wr;
  r.mTrades.textContent = resumoCiclos.total_ciclos != null ? resumoCiclos.total_ciclos : hist.length;
  // Regime - read from modelos.decisao_atual or mercado
  const modelos = p.modelos || {};
  const decisao = modelos.decisao_atual || {};
  const regime = decisao.regime || ((p.mercado||{}).feature_recente||{}).regime || ((p.multiativos||{}).regime_dominante) || "--";
  r.mRegime.textContent = regime;
  // Tabela trades
  const recentes = [...hist].reverse().slice(0, 10);
  r.totalTrades.textContent = `${hist.length} trades`;
  if (!recentes.length) {
    r.tabelaTrades.innerHTML = `<tr><td colspan="7" class="empty">Sem trades registrados.</td></tr>`;
  } else {
    const simb = p.simbolo || (p.conta||{}).ativo_base || "BTCUSDT";
    r.tabelaTrades.innerHTML = recentes.map(t => {
      const pnlT = num(t.lucro_liquido_usdt, null);
      const pnlPctT = num(t.valor_usdt,0) > 0 ? num(t.lucro_liquido_usdt,0)/num(t.valor_usdt,1)*100 : null;
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
  r.tsAtualiza.textContent = new Date().toLocaleTimeString("pt-BR");
}

function renderBot() {
  const a = st.auto || {};
  const ativo = !!a.ativo;
  setBadge(r.badgeBot, ativo?"Ativo":"Pausado", ativo?"badge-ok":"");
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
  try {
    const [painel, auto] = await Promise.all([
      api("/v1/painel/conta?simbolo=BTCUSDT"),
      api("/v1/auto/status"),
    ]);
    st.painel = painel;
    st.auto = auto;
    renderPainel();
    renderBot();
  } catch(e) {
    if (e.status===401) { logout(); return; }
    setBadge(r.badgeConexao, "Erro parcial", "badge-warn");
  }
}

async function consultarAi() {
  r.btnAi.disabled = true;
  r.btnAi.textContent = "...";
  r.aiContent.innerHTML = `<p class="muted-sm">Consultando IA...</p>`;
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
r.usarTestnet.addEventListener("change", () => {
  r.modoLabel.textContent = r.usarTestnet.checked ? "Testnet" : "Conta Real";
});
r.capitalPct.addEventListener("input", () => {
  st.capitalPct = parseInt(r.capitalPct.value);
  renderCapital();
});

// boot
verificarSessao().catch(()=>{});
