from __future__ import annotations

from typing import Any

from src.persistencia.repositorio_fila_sinais import RepositorioFilaSinais


class FilaSinaisDuravel:
    async def publicar(self, item: dict[str, Any]) -> dict[str, Any]:
        return await RepositorioFilaSinais.publicar(item)

    async def consumir(self) -> dict[str, Any]:
        return await RepositorioFilaSinais.consumir()

    async def concluir(self, fila_id: int, resultado: dict[str, Any] | None = None) -> None:
        await RepositorioFilaSinais.concluir(fila_id, resultado)

    async def falhar(self, fila_id: int, erro: dict[str, Any], *, refileirar: bool) -> None:
        await RepositorioFilaSinais.falhar(fila_id, erro, refileirar=refileirar)

    async def snapshot(self, limite: int = 100) -> list[dict[str, Any]]:
        return await RepositorioFilaSinais.snapshot(limite=max(1, limite))

    async def resetar_teste(self) -> None:
        await RepositorioFilaSinais.resetar_teste()


fila_sinais_global = FilaSinaisDuravel()
