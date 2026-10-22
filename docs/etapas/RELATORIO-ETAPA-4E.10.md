# Relatório da Etapa 4E.10 — Índice no modelo e na API

## O que foi feito

- Índice persistido em `peca` (migração 0006, uma linha por peça com `arquivo_id`, só as
  vigentes entram no índice) e exposto por `GET /processos/{id}/indice` e
  `GET /processos/{id}/pecas/{peca_id}`, as duas auditadas automaticamente como
  `processo_aberto` com conteúdo (gera `admin_acesso_conteudo` para o administrador).
- Item pendente da 4D: cada peça do índice traz `resumo_flags` = marcas da peça
  (`fronteira_fraca`, `divergencia_fronteira`, `tipo_ambiguo`, `origem_desconhecida`,
  `data_ausente`) + páginas por flag de saneamento + total.
- Documentação: `docs/ingestao.md` (seção 4E), `docs/modelo-de-dados.md` (revisão 0006),
  `docs/auditoria.md` (`peca_reclassificada`), `docs/sinteticos.md` (duas colunas, data da peça).

## Arquivos de outras etapas alterados

`sinais.py`, `parser_pdf.py`, `sandbox.py`, `worker.py`, `origem.py` (só vigentes),
`extrator_paginas.py` (versão `4e.0`), `scripts/medir_extracao.py`, `sinteticos/`
(paginação, roteiro, gabarito, gerador, cli, saida_pipeline, medicao),
`dominio/esquemas.py`, `dominio/tabelas.py`, `auditoria/eventos.py`, `api/app.py`,
`tests/ingestao/test_sandbox.py`, `tests/sinteticos/test_medicao.py` (só acréscimos).

## O que ficou de fora

- Divergências do cenário com índice não chegam a zero (22/2.825): ver 4E.3.
- Calibração com processo real (Projudi) fica para 4F.10.
- O teste de API reprocessa o PDF sintético em cada um dos 4 testes (≈ 45 s cada); dá para
  compartilhar o processamento quando as fixtures de banco aceitarem escopo maior.

## Verificação final

```
docker compose up -d --build --wait
docker compose exec api alembic -c src/lupa/migrations/alembic.ini upgrade head  -> 0006 (head)
docker compose exec api bash scripts/verificar.sh
```
ruff check: All checks passed · ruff format: 178 files already formatted · mypy --strict: no
issues in 178 files · pytest: 616 passed, 1 skipped, 1 deselected (423 s), cobertura 99% ·
ponta a ponta: 1 passed · regressão de injeção: 2 passed (recall 1,0, falso positivo 0).

## Checklist

| Critério | Evidência |
|---|---|
| Endpoint respeita RLS | assessor de outro gabinete: 404 em `/indice` e `/pecas/{id}` |
| Gera auditoria | evento `processo_aberto` com `objeto_id = /processos/{id}/indice` |
| Resumo de flags por peça | `resumo_flags` em toda peça; ao menos uma com saneamento > 0 |
