---
name: oraculo-ambiente
description: Use ao preparar, validar ou corrigir ambiente Codex/MCP do repositorio Oraculo, incluindo .mcp.json, .codex/config.toml, skills, agentes e scripts de verificacao.
---

Fluxo obrigatorio:

1. Ler AGENTS.md, .claude/contexto.md, .claude/skill.md e .claude/00_orquestrador.md.
2. Verificar estado preexistente com Git antes de editar.
3. Validar MCPs com `scripts/mcp/validar_mcp.py` usando Python do ambiente `.ferramentas/mcp/python/.venv`.
4. Manter MCPs dentro do workspace e sem credenciais no manifesto.
5. Usar Serena para simbolos/refatoracao, filesystem para arquivos, git para rastreabilidade e Semgrep para seguranca.
6. Nao ativar Figma sem tarefa de frontend e credencial. Nao ativar Repowise/codegraph se a instalacao nativa falhar no Windows.
7. Antes de codigo financeiro, chamar `guardiao_financeiro`. Depois de mudanca significativa, chamar `revisor_oraculo`.

Comandos:

```powershell
.ferramentas\mcp\python\.venv\Scripts\python.exe scripts\mcp\validar_mcp.py --todos
.ferramentas\mcp\python\.venv\Scripts\python.exe scripts\mcp\validar_mcp.py --servidor filesystem
```
