# Frontend

## Papel

Esta pasta concentra o painel web servido por Node/Express. Ela nao replica regra de negocio do backend; a responsabilidade aqui e apresentar dados, autenticar via formulario e consumir a API.

## Arquivos principais

- `server.js`: servidor simples que entrega assets estaticos e faz passthrough das rotas `/v1/*`.
- `package.json`: dependencias minimas do painel.
- `public/`: HTML, CSS, JavaScript e imagens.

## Razao logica

O frontend foi mantido propositalmente leve para:

- reduzir pontos de falha;
- facilitar deploy local;
- evitar duplicacao de regra que ja existe na API.

## Fluxo

1. o usuario abre o painel;
2. envia API key e API secret para a rota de sessao;
3. o cookie HttpOnly e mantido pelo backend;
4. o frontend consome `painel/conta`, `dashboard` e demais endpoints.
