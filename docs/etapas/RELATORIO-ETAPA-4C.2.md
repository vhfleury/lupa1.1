# Relatório da Etapa 4C.2 — Bookmarks e índice

## O que foi feito

- `diagnostico.ler_indice`: lê as primeiras páginas consecutivas em que a maioria das linhas segue `Movimentação N - dd/mm/aaaa - título - fls. P` (também `evento`, `mov.`, `seq.`, `pág.`); a primeira precisa de duas linhas reconhecidas.
- `fronteiras_do_indice`, `fronteiras_do_sumario` (bookmarks de nível 1 com destino válido; data tirada do título) e `fronteiras_do_manifesto` (uma por entrada do ZIP, com `pagina_continua`).
- Gravadas em `diagnostico_arquivo.fronteiras_origem` (`{peca, titulo, data, arquivo, pagina, fonte}`).

## Decisões não previstas

- Guardamos as duas fontes (índice e bookmarks) quando existem; a Etapa 4E confere uma contra a outra e contra o conteúdo.
- A página registrada é a física no arquivo (já com as páginas de índice); o deslocamento sai de `sinais.paginas_indice`.

## Comandos e saída

`scripts/medir_extracao.py diagnostico` (campo `fronteiras_indice`, `fronteiras_bookmark`, `paginas_indice`, `fronteiras_manifesto`).

## Critério

| Processo | Peças | Índice: páginas iguais | Índice: datas iguais | Bookmarks iguais | Páginas de índice | ZIP: inícios iguais |
|---|---|---|---|---|---|---|
| semente_01 | 51 | 51 | 51 | 51 | 2/2 | 51 |
| semente_02 | 84 | 84 | 84 | 84 | 3/3 | 84 |
| semente_03 | 79 | 79 | 79 | 79 | 2/2 | 79 |
| semente_04 | 120 | 120 | 120 | 120 | 3/3 | 120 |
| semente_05 | 172 | 172 | 172 | 172 | 5/5 | 172 |
| semente_06 | 240 | 240 | 240 | 240 | 6/6 | 240 |
| semente_07 | 286 | 286 | 286 | 286 | 8/8 | 286 |
| semente_08 | 384 | 384 | 384 | 384 | 10/10 | 384 |
| semente_09 | 531 | 531 | 531 | 531 | 14/14 | 531 |
| semente_10 | 878 | 878 | 878 | 878 | 22/22 | 878 |

**2.825/2.825 fronteiras** batem com `pecas[].pagina_inicial + deslocamento` no cenário `pdf_indice`. Testes: `test_fronteiras_do_indice_batem_com_as_pecas_do_gabarito`, `test_zip_por_peca_tem_uma_fronteira_por_entrada_em_numeracao_continua`.
