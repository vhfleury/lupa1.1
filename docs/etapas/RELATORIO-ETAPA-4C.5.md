# Relatório da Etapa 4C.5 — Texto nativo com coordenadas

## O que foi feito

- `src/lupa/ingestao/texto_nativo.py`: blocos e linhas do PyMuPDF com caixas em pontos PDF (origem superior esquerda), ordem de leitura por corte XY com detecção de colunas (faixas consecutivas com mais de uma coluna são lidas coluna a coluna), linhas não horizontais (marca d'água) no fim. Texto = linhas terminadas por `\n`, como `get_text()`; cada bloco e linha guarda `inicio`/`fim` no texto.
- `hash_texto` = sha256 do texto (`calcular_hash`), preenchido pelo repositório na gravação.

## Decisões não previstas

- A página com injeção `texto_branco` tem a linha oculta escrita por último no arquivo, mas posicionada acima do rodapé: a ordem de leitura a põe no lugar físico; o conjunto de linhas é igual ao `texto_camada`.

## Comandos

`scripts/medir_extracao.py roteador` (campo `texto_nativo`); `pytest tests/ingestao/test_paginas.py`.

## Critério

| Critério | Evidência |
|---|---|
| Texto nativo das páginas nativas bate com `texto_camada` | **10.718/10.718** iguais byte a byte (nativas + capas dos dez processos) |
| Offsets reproduzíveis | `test_texto_nativo_igual_a_camada_do_gabarito_com_offsets` (duas extrações iguais; offsets de linha conferidos) |
| Ordem de leitura em duas colunas | `test_duas_colunas_sao_lidas_coluna_por_coluna` (título, coluna esquerda, coluna direita, rodapé, com a coluna direita escrita antes no arquivo) |
