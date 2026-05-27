from __future__ import annotations

"""Conexão e inicialização do banco de dados SQLite.

Este módulo garante o schema evolutivo, aplica pragmas de desempenho
e expõe um contexto assíncrono `get_conexao()` para uso por repositórios.
"""

import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import aiosqlite

from src.core.settings import db_path

DDL_BASE = """
CREATE TABLE IF NOT EXISTS ohlcv_1m (
  ts INTEGER NOT NULL,
  simbolo TEXT NOT NULL,
  open REAL,
  high REAL,
  low REAL,
  close REAL,
  volume REAL,
  PRIMARY KEY (ts, simbolo)
);
CREATE INDEX IF NOT EXISTS idx_ohlcv_1m_simbolo_ts ON ohlcv_1m (simbolo, ts DESC);

CREATE TABLE IF NOT EXISTS ohlcv_15s (
  ts INTEGER NOT NULL,
  simbolo TEXT NOT NULL,
  open REAL,
  high REAL,
  low REAL,
  close REAL,
  volume REAL,
  PRIMARY KEY (ts, simbolo)
);
CREATE INDEX IF NOT EXISTS idx_ohlcv_15s_simbolo_ts ON ohlcv_15s (simbolo, ts DESC);

CREATE TABLE IF NOT EXISTS livro_topo (
  ts INTEGER NOT NULL,
  simbolo TEXT NOT NULL,
  bid_price REAL,
  bid_qty REAL,
  ask_price REAL,
  ask_qty REAL,
  PRIMARY KEY (ts, simbolo)
);
CREATE INDEX IF NOT EXISTS idx_livro_topo_simbolo_ts ON livro_topo (simbolo, ts DESC);

CREATE TABLE IF NOT EXISTS features_1m (
  ts INTEGER NOT NULL,
  simbolo TEXT NOT NULL,
  features_json TEXT NOT NULL,
  PRIMARY KEY (ts, simbolo)
);
CREATE INDEX IF NOT EXISTS idx_features_1m_simbolo_ts ON features_1m (simbolo, ts DESC);

CREATE TABLE IF NOT EXISTS predictions (
  created_ts INTEGER NOT NULL,
  simbolo TEXT NOT NULL,
  y_hat REAL,
  y_cal REAL,
  ic68_low REAL,
  ic68_high REAL,
  p_conf REAL,
  meta_json TEXT,
  PRIMARY KEY (created_ts, simbolo)
);
CREATE INDEX IF NOT EXISTS idx_predictions_simbolo_ts ON predictions (simbolo, created_ts DESC);

CREATE TABLE IF NOT EXISTS outcomes (
  ts_previsao INTEGER NOT NULL,
  ts_target INTEGER NOT NULL,
  simbolo TEXT NOT NULL,
  y_true REAL,
  y_hat REAL,
  err_rel REAL,
  PRIMARY KEY (ts_previsao, simbolo)
);
CREATE INDEX IF NOT EXISTS idx_outcomes_simbolo_ts ON outcomes (simbolo, ts_previsao DESC);

CREATE TABLE IF NOT EXISTS config (
  chave TEXT PRIMARY KEY,
  valor TEXT,
  tipo TEXT NOT NULL DEFAULT 'STRING',
  atualizado_em INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS snapshot_estado (
  simbolo TEXT PRIMARY KEY,
  estado_json TEXT NOT NULL,
  atualizado_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS usuarios (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nome TEXT NOT NULL UNIQUE,
  api_key_ref TEXT,
  api_secret_ref TEXT,
  api_key_secret_id TEXT,
  api_secret_secret_id TEXT,
  ativo INTEGER NOT NULL DEFAULT 1,
  testnet INTEGER NOT NULL DEFAULT 1,
  risk_config_json TEXT NOT NULL,
  criado_em INTEGER NOT NULL,
  atualizado_em INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_usuarios_ativo_nome ON usuarios (ativo, nome);

CREATE TABLE IF NOT EXISTS ordens (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_ts INTEGER NOT NULL,
  updated_ts INTEGER NOT NULL,
  usuario_id INTEGER,
  simbolo TEXT NOT NULL,
  lado TEXT NOT NULL,
  status TEXT NOT NULL,
  modo TEXT NOT NULL,
  preco_referencia REAL,
  quantidade REAL,
  notional REAL,
  stop_loss_pct REAL,
  take_profit_pct REAL,
  detalhe_json TEXT NOT NULL,
  FOREIGN KEY(usuario_id) REFERENCES usuarios(id)
);
CREATE INDEX IF NOT EXISTS idx_ordens_usuario_status_ts ON ordens (usuario_id, status, created_ts DESC);
CREATE INDEX IF NOT EXISTS idx_ordens_simbolo_ts ON ordens (simbolo, created_ts DESC);

CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_ts INTEGER NOT NULL,
  simbolo TEXT NOT NULL,
  tipo TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  componente TEXT,
  motivo TEXT,
  meta_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_simbolo_ts ON audit (simbolo, created_ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_tipo_ts ON audit (tipo, created_ts DESC);

CREATE TABLE IF NOT EXISTS fila_sinais (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_ts INTEGER NOT NULL,
  updated_ts INTEGER NOT NULL,
  status TEXT NOT NULL,
  tentativas INTEGER NOT NULL DEFAULT 0,
  disponivel_em INTEGER NOT NULL,
  ordem_id INTEGER,
  usuario_id INTEGER,
  simbolo TEXT NOT NULL,
  correlation_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  erro_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_fila_sinais_status_disponivel ON fila_sinais (status, disponivel_em, id);
CREATE INDEX IF NOT EXISTS idx_fila_sinais_correlation_id ON fila_sinais (correlation_id);
"""


def obter_db_path() -> Path:
    return db_path()


def _garantir_diretorio_db() -> Path:
    caminho = obter_db_path()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    return caminho


def _aplicar_pragmas_sync(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=5000;")


async def _aplicar_pragmas_async(conn: aiosqlite.Connection) -> None:
    await conn.execute("PRAGMA journal_mode=WAL;")
    await conn.execute("PRAGMA synchronous=NORMAL;")
    await conn.execute("PRAGMA foreign_keys=ON;")
    await conn.execute("PRAGMA busy_timeout=5000;")


def _colunas_tabela(conn: sqlite3.Connection, tabela: str) -> set[str]:
    cursor = conn.execute(f"PRAGMA table_info({tabela})")
    return {str(linha[1]) for linha in cursor.fetchall()}


def _garantir_coluna(conn: sqlite3.Connection, tabela: str, coluna_sql: str) -> None:
    nome_coluna = coluna_sql.split()[0]
    if nome_coluna in _colunas_tabela(conn, tabela):
        return
    conn.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna_sql}")


def _garantir_schema_evolutivo(conn: sqlite3.Connection) -> None:
    # Legado
    _garantir_coluna(conn, "usuarios", "api_key_secret_id TEXT")
    _garantir_coluna(conn, "usuarios", "api_secret_secret_id TEXT")
    _garantir_coluna(conn, "audit", "componente TEXT")
    _garantir_coluna(conn, "audit", "motivo TEXT")
    _garantir_coluna(conn, "audit", "meta_json TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_componente_ts ON audit (componente, created_ts DESC)")
    # v2 — colunas adicionais para ML e rastreio de capital
    _garantir_coluna(conn, "ordens", "lucro_usdt REAL")
    _garantir_coluna(conn, "ordens", "lucro_pct REAL")
    _garantir_coluna(conn, "ordens", "duracao_ms INTEGER")
    _garantir_coluna(conn, "ordens", "capital_pct_usado REAL")
    _garantir_coluna(conn, "ordens", "regime TEXT")
    _garantir_coluna(conn, "ordens", "estrategia TEXT")
    _garantir_coluna(conn, "outcomes", "regime TEXT")
    _garantir_coluna(conn, "outcomes", "estrategia TEXT")
    _garantir_coluna(conn, "outcomes", "confianca REAL")
    _garantir_coluna(conn, "outcomes", "capital_pct REAL")
    _garantir_coluna(conn, "outcomes", "lucro_usdt REAL")
    _garantir_coluna(conn, "predictions", "regime TEXT")
    _garantir_coluna(conn, "predictions", "estrategia TEXT")
    _garantir_coluna(conn, "predictions", "capital_pct REAL")
    _garantir_coluna(conn, "predictions", "ai_boost REAL")
    _garantir_coluna(conn, "features_1m", "regime TEXT")
    _garantir_coluna(conn, "features_1m", "vol_regime TEXT")
    # v2 — tabela de insights AI
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ai_insights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_ts INTEGER NOT NULL,
            simbolo TEXT NOT NULL,
            modelo TEXT NOT NULL,
            direcao TEXT NOT NULL,
            confianca REAL,
            capital_pct_sugerido REAL,
            reasoning TEXT,
            risco TEXT,
            dados_entrada_json TEXT,
            executado INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_ai_insights_simbolo_ts ON ai_insights (simbolo, created_ts DESC);
    """)
    # v2 — tabela de sessions para rastrear capital_pct
    _garantir_coluna(conn, "usuarios", "capital_pct INTEGER")



def inicializar_db() -> Path:
    caminho = _garantir_diretorio_db()
    conn = sqlite3.connect(str(caminho))
    try:
        _aplicar_pragmas_sync(conn)
        conn.executescript(DDL_BASE)
        _garantir_schema_evolutivo(conn)
        conn.commit()
    finally:
        conn.close()
    return caminho


async def criar_conexao() -> aiosqlite.Connection:
    caminho = _garantir_diretorio_db()
    conn = await aiosqlite.connect(str(caminho))
    conn.row_factory = aiosqlite.Row
    await _aplicar_pragmas_async(conn)
    return conn


@asynccontextmanager
async def get_conexao() -> AsyncIterator[aiosqlite.Connection]:
    conn = await criar_conexao()
    try:
        yield conn
    finally:
        await conn.close()
