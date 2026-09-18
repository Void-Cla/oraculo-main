"""Backup ONLINE do SQLite do Oraculo — consistente mesmo com o bot rodando (WAL).

CONTEXTO (up.md P0 / gap G3): o `dados/oraculo.sqlite` acumula semanas de dado de mercado e
todo o estado operacional; perdê-lo por corrupção/disco cheio/erro humano é irreversível.
Este script NÃO toca no app (é standalone, mesma convenção de `scripts/pesquisa_edge.py` e
`scripts/backtest_walkforward.py` — sem cobertura pytest, verificado manualmente).

Uso:
    python scripts/backup_sqlite.py                    # cria 1 backup + aplica rotação
    python scripts/backup_sqlite.py --restaurar ARQ.sqlite   # drill de restore (NUNCA sobrescreve o banco em uso)

Por que `VACUUM INTO` e não copiar o arquivo bruto: em modo WAL, o estado "commitado" pode
estar parcialmente no arquivo `-wal` separado — copiar só o `.sqlite` pode capturar uma
imagem inconsistente. `VACUUM INTO 'destino'` faz uma cópia TRANSACIONALMENTE consistente
num único arquivo, sem exigir parar o processo nem tirar lock exclusivo por muito tempo, e
SEM modificar a origem (é somente leitura sobre o banco original).

Agendamento (Windows): não é responsabilidade deste script registrar tarefa agendada (ação de
sistema, melhor feita deliberadamente pelo dono). Sugestão:
    schtasks /create /tn "OraculoBackupSQLite" /sc hourly /tr "\"<venv>\\python.exe\" \"<repo>\\scripts\\backup_sqlite.py\""
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.settings import env_int, env_str  # noqa: E402

_PREFIXO_ARQUIVO = "oraculo_"
_SUFIXO_ARQUIVO = ".sqlite"


def _db_path() -> Path:
    return Path(env_str("DB_PATH", "./dados/oraculo.sqlite")).resolve()


def _backup_dir() -> Path:
    destino = Path(env_str("BACKUP_DIR", "./dados/backups")).resolve()
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def _retencao() -> int:
    # Default 72: cobre 3 dias com 1 backup/hora (cadência sugerida no up.md P0).
    return env_int("BACKUP_RETENCAO_ARQUIVOS", 72, minimo=1)


def executar_backup() -> Path:
    origem = _db_path()
    if not origem.exists():
        raise SystemExit(f"DB_PATH nao existe: {origem}")
    destino_dir = _backup_dir()
    # Timestamp com microssegundos: VACUUM INTO falha se o destino já existe — duas execuções
    # no mesmo segundo (double-run manual, ou agendamento futuro de alta frequência) não podem
    # colidir de nome.
    agora = time.time()
    timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(agora)) + f"_{int((agora % 1) * 1_000_000):06d}"
    destino = destino_dir / f"{_PREFIXO_ARQUIVO}{timestamp}{_SUFIXO_ARQUIVO}"

    conexao = sqlite3.connect(str(origem))
    try:
        # VACUUM INTO exige que o path de destino NÃO exista ainda — timestamp garante unicidade.
        conexao.execute("VACUUM INTO ?", (str(destino),))
    finally:
        conexao.close()

    removidos = _rotacionar(destino_dir)
    print(f"backup_criado: {destino}")
    for antigo in removidos:
        print(f"backup_removido_por_rotacao: {antigo}")
    return destino


def _rotacionar(destino_dir: Path) -> list[Path]:
    arquivos = sorted(
        destino_dir.glob(f"{_PREFIXO_ARQUIVO}*{_SUFIXO_ARQUIVO}"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    limite = _retencao()
    removidos = []
    for antigo in arquivos[limite:]:
        antigo.unlink(missing_ok=True)
        removidos.append(antigo)
    return removidos


def restaurar(caminho_backup: str) -> Path:
    """Drill de restore MANUAL: copia o backup para `<DB_PATH>.restaurado.sqlite`, ao lado do
    banco em uso — NUNCA sobrescreve o banco real (restore de verdade é decisão humana
    deliberada, feita fora deste script). Roda `PRAGMA integrity_check` no resultado."""
    origem = Path(caminho_backup).resolve()
    if not origem.exists():
        raise SystemExit(f"backup nao encontrado: {origem}")
    alvo = _db_path().with_suffix(".restaurado.sqlite")
    shutil.copy2(origem, alvo)
    conexao = sqlite3.connect(str(alvo))
    try:
        (integro,) = conexao.execute("PRAGMA integrity_check").fetchone()
    finally:
        conexao.close()
    print(f"restaurado_para: {alvo}")
    print(f"integrity_check: {integro}")
    if integro != "ok":
        raise SystemExit(f"integrity_check FALHOU: {integro}")
    return alvo


def main() -> None:
    parser = argparse.ArgumentParser(description="Backup/restore online do SQLite do Oraculo")
    parser.add_argument(
        "--restaurar",
        metavar="ARQUIVO_BACKUP",
        help="Testa o restore de um backup (drill; NUNCA sobrescreve o banco em uso)",
    )
    args = parser.parse_args()
    if args.restaurar:
        restaurar(args.restaurar)
    else:
        executar_backup()


if __name__ == "__main__":
    main()
