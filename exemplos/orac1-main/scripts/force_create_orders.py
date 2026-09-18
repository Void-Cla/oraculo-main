from __future__ import annotations

import asyncio
import time

from src.persistencia.repositorio_ordens import RepositorioOrdens


async def main():
    for i in range(10):
        lado = 'BUY' if (i % 2) == 0 else 'SELL'
        ordem_id = await RepositorioOrdens.criar(
            usuario_id=2,
            simbolo='BTCUSDT',
            lado=lado,
            status='SIMULADA',
            modo='paper',
            preco_referencia=100.0,
            quantidade=0.001,
            notional=0.1,
            stop_loss_pct=0.01,
            take_profit_pct=0.01,
            detalhe={'manual': 'forced_test'},
        )
        detalhe_exec = {
            'simulada': True,
            'preco_execucao': 100.0,
            'quantidade_executada': 0.001,
            'notional_execucao': 0.1,
            'ts_execucao': int(time.time() * 1000),
        }
        await RepositorioOrdens.atualizar_status(ordem_id, 'EXECUTADA', detalhe_exec)
        print('created_executed', ordem_id)


if __name__ == '__main__':
    asyncio.run(main())
