# Relatório da Etapa 4D.8 — Origem por trecho

## O que foi feito

- Todo trecho suspeito nasce com `origem` (`desconhecida` na ingestão: as peças só existem a partir da 4E).
- `src/lupa/ingestao/origem.py`: `origem_da_pagina(session, pagina_id) -> OrigemPeca` lê `peca.origem` da peça do mesmo arquivo que cobre a página (a de maior confiança em sobreposição), com fallback `desconhecida`; `rotular` e `trechos_rotulados` devolvem os trechos com a origem da peça.

## Decisões não previstas

- `pagina.origem_peca` não foi criada: a origem é consultada na peça (fonte única); a 4E decide se vale desnormalizar.

## Critério

| Critério | Evidência |
| --- | --- |
| Trecho de defesa nunca sem rótulo | `test_origem.py::test_origem_vem_da_peca_e_cai_em_desconhecida`, com peças inseridas à mão: página de peça da defesa → `defesa`; sobreposição resolvida pela confiança; sem peça → `desconhecida`; página inexistente → `desconhecida` |

## Comandos e saída

```
docker compose up -d --build --wait
docker compose exec api bash scripts/verificar.sh
```

Saída resumida (21/10/2026): ruff e `ruff format --check` limpos; `mypy --strict` sem erros em 165 arquivos; pytest **588 passed, 1 skipped** (o skip é anterior à 4D; eram 551 testes), cobertura **98,66%**; ponta a ponta 1 passed; regressão de injeção 2 passed (159 s), `recall 1.0`, `falso_positivo 0.0`.
