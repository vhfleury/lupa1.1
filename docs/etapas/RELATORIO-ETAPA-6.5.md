# Relatório da Etapa 6.5 — Dossiê e linha do tempo

## O que foi feito

`/processos/[id]/dossie` (`front/src/routes/processos/[id]/dossie/+page.svelte`) consome
`GET /processos/{id}/dossie`, `GET /processos/{id}/indice` e `GET /processos/{id}/fatos` (nova,
ver 6.7):

- Ficha: número CNJ, classe, matéria, status e réus só por pseudônimo (`REU-01`…), como o
  dossiê da 5.10 entrega.
- Linha do tempo: cada evento (data, tipo, folha, trecho) é um link para o visualizador com
  `?evidencia=<id>`; a evidência é a do fato do evento na página do evento (via `/fatos`), e o
  visualizador abre na página dela com o trecho destacado (6.6). Eventos de fatos corrigidos ou
  confirmados mostram o status.
- Índice de peças: ordem, tipo, origem, páginas (link para a página inicial no visualizador),
  data, confiança com o método, marcas da peça e total de alertas de saneamento.
- Alertas de saneamento por página (link para a página) e por peça (no índice).
- Achados do dossiê com resultado e explicação, e link para a tela de validações.
- Campos `gerado`: o botão "Gerar resumos das peças (modelo)" pede `?resumos=true`; cada
  `resumo_peca` aparece num bloco destacado (borda tracejada, fundo de aviso) com o selo
  **GERADO**. Nada do modelo aparece sem o selo. Texto vindo da API é sempre texto (sem
  `{@html}`, regra de lint).

Nenhuma rota de backend nova foi necessária para o dossiê além de `/fatos` (usada para achar
arquivo e evidência de cada evento, já que `linha_do_tempo` traz `pagina_id` e não o arquivo).

## Testes

E2E `6.5 dossiê: ficha, índice e clique no evento abre o visualizador na página certa`: ficha
com número CNJ e réu pseudonimizado; índice com linhas; para os quatro primeiros eventos, o
clique abre `/visualizador?evidencia=…`, o indicador mostra "Página N" igual à folha do evento,
a imagem carrega e o destaque aparece.

## Critério de aceite

Clique em evento abre o visualizador na página certa: passando no E2E sobre o processo sintético
ingerido pelo worker real.

## Fora do escopo

Edição da ficha; exportação do dossiê em PDF; filtro da linha do tempo por tipo.
