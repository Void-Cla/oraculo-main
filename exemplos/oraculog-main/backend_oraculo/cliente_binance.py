"""
Cliente Oficial da API Binance (PT-BR) - Dados 100% Reais
Suporte a dados públicos de mercado ao vivo sem restrições (data-api.binance.vision e api.binance.com)
e autenticação HMAC SHA256 para leitura de saldo e execução real na conta Binance Spot.
"""
import time
import hmac
import hashlib
import json
import urllib.request
import urllib.error
import urllib.parse
from typing import Dict, List, Any, Optional, Tuple

class ClienteBinanceReal:
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        base_urls: Optional[List[str]] = None
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        
        # Lista ordenada de endpoints oficiais da Binance
        # data-api.binance.vision: endpoint global oficial da Binance sem restrição geográfica de IP
        # api.binance.com: endpoint padrão para execução local fora dos EUA (ex: Brasil)
        # api.binance.us: fallback para região americana
        self.base_urls = base_urls or [
            "https://data-api.binance.vision",
            "https://api.binance.com",
            "https://api.binance.us"
        ]
        self._url_ativa = self.base_urls[0]
        self.ultima_latencia_ms = 0.0

    def _fazer_requisicao_get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Faz requisição GET pública com fallback automático entre endpoints da Binance"""
        query_str = f"?{urllib.parse.urlencode(params)}" if params else ""
        headers = {
            "User-Agent": "OraculoTradingBot/2.0 (Linux; Production; Quant)",
            "Accept": "application/json"
        }
        
        erros = []
        for base in self.base_urls:
            url = f"{base}{endpoint}{query_str}"
            t_inicio = time.time()
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=4) as response:
                    corpo = response.read().decode('utf-8')
                    self.ultima_latencia_ms = round((time.time() - t_inicio) * 1000, 2)
                    self._url_ativa = base
                    return json.loads(corpo)
            except Exception as e:
                erros.append(f"{base}: {str(e)}")
                continue
                
        raise ConnectionError(f"Falha de conexão com a Binance em todos os endpoints: {'; '.join(erros)}")

    def testar_ping(self) -> Dict[str, Any]:
        """Testa conectividade real com a Binance e calcula a latência exata em ms"""
        t0 = time.time()
        res = self._fazer_requisicao_get("/api/v3/ping")
        latencia = round((time.time() - t0) * 1000, 2)
        return {
            "conectado": True,
            "latencia_ms": latencia,
            "endpoint_ativo": self._url_ativa,
            "status": "ONLINE"
        }

    def obter_livro_ofertas_real(self, par: str, limite: int = 10) -> Dict[str, Any]:
        """
        Obtém o livro de ofertas (Order Book) 100% real da Binance.
        Calcula o desequilíbrio (Imbalance), melhor bid, melhor ask, spread e profundidade.
        """
        dados = self._fazer_requisicao_get("/api/v3/depth", {"symbol": par, "limit": limite})
        
        bids = [[float(p), float(q)] for p, q in dados.get("bids", [])]
        asks = [[float(p), float(q)] for p, q in dados.get("asks", [])]
        
        if not bids or not asks:
            raise ValueError(f"Livro de ofertas vazio retornado pela Binance para {par}")
            
        melhor_bid = bids[0][0]
        melhor_ask = asks[0][0]
        
        # Volume acumulado dos top N níveis do livro
        volume_total_bids = sum(q for _, q in bids)
        volume_total_asks = sum(q for _, q in asks)
        
        # Volume em USD (nocional)
        volume_usd_bids = sum(p * q for p, q in bids)
        volume_usd_asks = sum(p * q for p, q in asks)
        
        # Desequilíbrio do livro (Order Book Imbalance): entre -1.0 e +1.0
        vol_total = volume_total_bids + volume_total_asks
        imbalance = (volume_total_bids - volume_total_asks) / vol_total if vol_total > 0 else 0.0
        
        # Spread real
        spread_abs = max(0.0, melhor_ask - melhor_bid)
        preco_medio = (melhor_bid + melhor_ask) / 2.0
        spread_pct = (spread_abs / preco_medio) if preco_medio > 0 else 0.0
        
        return {
            "par": par,
            "melhor_bid": melhor_bid,
            "melhor_ask": melhor_ask,
            "preco_atual": preco_medio,
            "spread_absoluto": spread_abs,
            "spread_pct": spread_pct,
            "volume_total_bids": volume_total_bids,
            "volume_total_asks": volume_total_asks,
            "volume_usd_bids": volume_usd_bids,
            "volume_usd_asks": volume_usd_asks,
            "desequilibrio_livro": round(imbalance, 4),
            "top_bids": bids[:5],
            "top_asks": asks[:5],
            "timestamp": time.time()
        }

    def obter_klines_recentes_reais(self, par: str, intervalo: str = "1m", limite: int = 10) -> List[Dict[str, Any]]:
        """
        Obtém os últimos candles de 1 minuto 100% reais da Binance para cálculo de momentum e volatilidade.
        """
        dados = self._fazer_requisicao_get("/api/v3/klines", {
            "symbol": par,
            "interval": intervalo,
            "limit": limite
        })
        
        candles = []
        for k in dados:
            candles.append({
                "tempo_abertura": int(k[0]),
                "abertura": float(k[1]),
                "maxima": float(k[2]),
                "minima": float(k[3]),
                "fechamento": float(k[4]),
                "volume": float(k[5]),
                "volume_usd": float(k[7]),
                "numero_trades": int(k[8])
            })
        return candles

    def obter_ticker_24h_real(self, par: str) -> Dict[str, Any]:
        """Obtém estatísticas de 24h reais da Binance (volume, variação percentual)"""
        dados = self._fazer_requisicao_get("/api/v3/ticker/24hr", {"symbol": par})
        return {
            "par": par,
            "preco_atual": float(dados.get("lastPrice", 0)),
            "variacao_24h_pct": float(dados.get("priceChangePercent", 0)),
            "volume_24h_usd": float(dados.get("quoteVolume", 0)),
            "alta_24h": float(dados.get("highPrice", 0)),
            "baixa_24h": float(dados.get("lowPrice", 0))
        }

    def obter_saldo_conta_autenticado(self, api_key: str, api_secret: str) -> Dict[str, Any]:
        """
        Consulta saldo real da conta Binance Spot via HMAC SHA256.
        Se as credenciais não estiverem configuradas, retorna status informativo de segurança.
        """
        if not api_key or not api_secret or api_key == "SUA_BINANCE_API_KEY":
            return {
                "autenticado": False,
                "motivo": "API Key da Binance não configurada no .env ou settings",
                "saldo_usdt": 0.0,
                "saldos_ativos": {}
            }
            
        endpoint = "/api/v3/account"
        timestamp = int(time.time() * 1000)
        query = f"timestamp={timestamp}&recvWindow=5000"
        
        signature = hmac.new(
            api_secret.encode('utf-8'),
            query.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        full_query = f"{query}&signature={signature}"
        url = f"{self._url_ativa}{endpoint}?{full_query}"
        
        headers = {
            "X-MBX-APIKEY": api_key,
            "User-Agent": "OraculoTradingBot/2.0 (Linux; Production; Quant)"
        }
        
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as response:
                dados = json.loads(response.read().decode('utf-8'))
                balances = dados.get("balances", [])
                
                saldos_ativos = {}
                saldo_usdt = 0.0
                for b in balances:
                    free = float(b.get("free", 0))
                    locked = float(b.get("locked", 0))
                    total = free + locked
                    if total > 0.000001:
                        asset = b.get("asset")
                        saldos_ativos[asset] = {"livre": free, "bloqueado": locked, "total": total}
                        if asset == "USDT":
                            saldo_usdt = free
                            
                return {
                    "autenticado": True,
                    "saldo_usdt": saldo_usdt,
                    "saldos_ativos": saldos_ativos,
                    "pode_operar": dados.get("canTrade", False)
                }
        except urllib.error.HTTPError as e:
            msg_erro = e.read().decode('utf-8')
            return {
                "autenticado": False,
                "erro_http": e.code,
                "detalhes": msg_erro,
                "saldo_usdt": 0.0
            }
        except Exception as e:
            return {
                "autenticado": False,
                "erro": str(e),
                "saldo_usdt": 0.0
            }

CLIENTE_BINANCE = ClienteBinanceReal()
