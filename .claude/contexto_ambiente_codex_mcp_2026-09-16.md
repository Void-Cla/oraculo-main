# Ambiente Codex/MCP - 2026-09-16

Estado configurado:

- `.mcp.json` e `.codex/config.toml` sao a fonte MCP do repo.
- MCPs ativos: `filesystem`, `git`, `serena`, `semgrep`.
- `semgrep` usa MCP local em `scripts/mcp/semgrep_local_mcp.py`, pois o `semgrep-mcp` oficial so expos `deprecation_notice` sem Pro Engine.
- Skill repo: `.agents/skills/oraculo-ambiente/SKILL.md`.
- Agentes Codex nativos: `.codex/agents/guardiao_financeiro.toml`, `.codex/agents/revisor_oraculo.toml`, `.codex/agents/explorador_codigo.toml`.
- Validador: `scripts/mcp/validar_mcp.py`.
- Serena: `.serena/project.yml` com exclusoes de dados, venv, caches e bancos.
- `codegraph` e `repowise` ficam fora do nucleo ativo: falharam no Windows/Node 24 por dependencias nativas (`better-sqlite3`/tree-sitter).

Validacao:

- MCP 4/4 OK via `validar_mcp.py --todos`.
- Semgrep CLI `1.177.0`.
- Scan Semgrep focado em `scripts/mcp/semgrep_local_mcp.py`: 0 achados, 0 erros.
- `.mcp.json` e `.codex/config.toml`: parse OK.
- Skill `oraculo-ambiente`: `Skill is valid!`.

Escopo:

- Nenhum codigo financeiro alterado.
- Nenhum gate real, halt, risco, ordem, EV ou persistencia financeira alterado.
