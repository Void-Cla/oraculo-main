"""
Persistência e Histórico de Dados em SQLite (PT-BR)
Garante rastreabilidade total de ordens, taxas descontadas e prova de lucro líquido.
"""
import sqlite3
import time
from typing import Dict, List, Any, Optional
from ..config import CONFIG

class BancoDadosOraculo:
    def __init__(self, db_path: str = CONFIG.DB_PATH):
        self.db_path = db_path
        self._inicializar_tabelas()

    def _conectar(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _inicializar_tabelas(self):
        with self._conectar() as conn:
            cursor = conn.cursor()
            
            # Tabela de Trades com Auditoria de Taxas e Lucro Líquido
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                par TEXT NOT NULL,
                direcao TEXT NOT NULL,
                preco_entrada REAL NOT NULL,
                preco_saida REAL NOT NULL,
                tamanho REAL NOT NULL,
                valor_nocional REAL NOT NULL,
                lucro_bruto_usd REAL NOT NULL,
                taxas_totais_usd REAL NOT NULL,
                lucro_liquido_usd REAL NOT NULL,
                regra_001_satisfeita INTEGER NOT NULL,
                motivo TEXT,
                status TEXT NOT NULL
            )
            """)

            # Tabela de Sessões de IA a cada 2 Horas
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessoes_ia (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                peso_noticias REAL NOT NULL,
                bias_macro REAL NOT NULL,
                regime TEXT NOT NULL,
                resumo TEXT NOT NULL
            )
            """)

            conn.commit()

    def salvar_trade(self, trade_data: Dict[str, Any]) -> int:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO trades (
                timestamp, par, direcao, preco_entrada, preco_saida,
                tamanho, valor_nocional, lucro_bruto_usd, taxas_totais_usd,
                lucro_liquido_usd, regra_001_satisfeita, motivo, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade_data.get('timestamp', time.time()),
                trade_data['par'],
                trade_data['direcao'],
                trade_data['preco_entrada'],
                trade_data['preco_saida'],
                trade_data['tamanho'],
                trade_data.get('valor_nocional', trade_data['preco_entrada'] * trade_data['tamanho']),
                trade_data['lucro_bruto_usd'],
                trade_data['taxas_totais_usd'],
                trade_data['lucro_liquido_usd'],
                1 if trade_data['lucro_liquido_usd'] >= 0.01 else 0,
                trade_data.get('motivo', 'Execução de janela rápida'),
                trade_data.get('status', 'FINALIZADO_COM_LUCRO')
            ))
            conn.commit()
            return cursor.lastrowid or 0

    def obter_trades_recentes(self, limite: int = 50) -> List[Dict[str, Any]]:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT * FROM trades ORDER BY id DESC LIMIT ?
            """, (limite,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def obter_resumo_lucro_liquido(self) -> Dict[str, Any]:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN lucro_liquido_usd >= 0.01 THEN 1 ELSE 0 END) as trades_lucro_real,
                SUM(lucro_bruto_usd) as total_lucro_bruto,
                SUM(taxas_totais_usd) as total_taxas_pagas,
                SUM(lucro_liquido_usd) as total_lucro_liquido,
                AVG(lucro_liquido_usd) as media_lucro_liquido
            FROM trades
            """)
            row = cursor.fetchone()
            if not row or row['total_trades'] == 0:
                return {
                    'total_trades': 0,
                    'trades_lucro_real': 0,
                    'taxa_sucesso_pct': 0.0,
                    'total_lucro_bruto_usd': 0.0,
                    'total_taxas_pagas_usd': 0.0,
                    'total_lucro_liquido_usd': 0.0,
                    'media_lucro_liquido_usd': 0.0
                }
            total = row['total_trades']
            com_lucro = row['trades_lucro_real'] or 0
            return {
                'total_trades': total,
                'trades_lucro_real': com_lucro,
                'taxa_sucesso_pct': round((com_lucro / total) * 100.0, 1),
                'total_lucro_bruto_usd': round(row['total_lucro_bruto'] or 0.0, 4),
                'total_taxas_pagas_usd': round(row['total_taxas_pagas'] or 0.0, 4),
                'total_lucro_liquido_usd': round(row['total_lucro_liquido'] or 0.0, 4),
                'media_lucro_liquido_usd': round(row['media_lucro_liquido'] or 0.0, 4)
            }

BANCO_DADOS = BancoDadosOraculo()
