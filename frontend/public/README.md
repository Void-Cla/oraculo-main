# Frontend Publico

## Papel

Esta subpasta contem os assets reais carregados pelo navegador.

## Arquivos

- `index.html`: estrutura semantica do painel e containers das secoes.
- `app.js`: estado da interface, login, consumo de API e renderizacao.
- `estilos.css`: identidade visual, responsividade, sidebar e organizacao dos blocos.
- `img/oraculo.png`: icone e favicon da aplicacao.

## Raciocinio logico

- `index.html` define a malha da pagina e evita gerar DOM inteiro via JavaScript.
- `app.js` centraliza o fluxo de leitura da API para evitar logica espalhada entre componentes ficticios.
- `estilos.css` garante responsividade e leitura didatica, mantendo a paleta visual do projeto.

## Limite de responsabilidade

Qualquer regra de decisao, risco, arbitragem ou scoring deve ficar no backend. O frontend apenas apresenta o estado calculado.
