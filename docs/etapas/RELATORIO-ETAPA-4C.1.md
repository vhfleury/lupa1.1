# Relatório da Etapa 4C.1 — Diagnóstico do contêiner

## O que foi feito

- `src/lupa/ingestao/diagnostico.py`: funções puras que classificam o arquivo em `zip_por_peca`, `pdf_com_bookmarks_e_indice`, `pdf_com_bookmarks`, `pdf_com_indice` ou `pdf_liso` a partir do manifesto (ZIP) ou da inspeção do PDF (sumário e texto das primeiras páginas, lidos no sandbox por `parser_pdf.inspecionar`).
- `parser_pdf.inspecionar` devolve também `toc`, `paginas_indice` e `indice`.
- O worker grava o `DiagnosticoArquivo` (`repositorio.salvar_diagnostico`) ao sair de `validado`.
- Rota de leitura auditada: `GET /processos/{id}/arquivos/{arquivo_id}/diagnostico` (`processo_aberto`, conteúdo; 404 para arquivo de outro processo ou sem diagnóstico).
- Migração 0004: CHECK de `cenario` aceita o novo valor.

## Decisões não previstas

- **Novo valor `CenarioArquivo.PDF_COM_BOOKMARKS_E_INDICE`**: o gabarito 4B espera `pdf_com_bookmarks_e_indice` para o cenário com índice; sem o valor, o critério 30/30 era impossível.
- **ZIP com uma só entrada** é diagnosticado pelo PDF de dentro (sinal `zip_com_um_pdf`).
- **Correção em arquivo da 4A** (`parser_pdf.py`): página sem stream de conteúdo (folha em branco, presente em todos os processos de referência) fazia o PyMuPDF 1.25.1 lançar `AssertionError` em `read_contents()` e o PDF ia para quarentena como `corrompido`. Agora a página sem conteúdo é pulada. Teste: `test_pdf_com_pagina_sem_conteudo_nao_e_corrompido`.

## Ficou de fora

- Diagnóstico do ZIP custa ~0,8 s por entrada (um filho do sandbox por PDF). Aceitável no piloto; agrupar entradas num filho fica para 4F.8 (cache/reprocessamento).

## Comandos e saída

```
docker compose run --rm api python scripts/medir_extracao.py diagnostico
→ "acertos": 30, "total": 30
docker compose exec api bash scripts/verificar.sh   (ver 4C.10)
```

## Critério

| Critério | Evidência |
|---|---|
| Três cenários dos dez processos diagnosticados corretamente | **30/30** (`diagnostico_esperado` do gabarito como referência) |
| Diagnóstico visível no processo | rota GET auditada; `test_rotas_de_diagnostico_e_relatorio_sao_auditadas_e_isoladas` |

Tempo de diagnóstico: PDF único 1,1 a 2,5 s (até 5.000 páginas); ZIP 45 s (51 entradas) a 725 s (878 entradas).
