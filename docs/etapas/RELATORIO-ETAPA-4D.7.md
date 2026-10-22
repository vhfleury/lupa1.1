# Relatório da Etapa 4D.7 — Densidade anômala

## O que foi feito

- `dados/densidade.yaml` (versão 1): máximo de caracteres por tipo de página: nativa 15.000, ocr 15.000, vazia 200.
- `deteccao.densidade_anomala(texto, tipo)`; `FlagPagina.DENSIDADE_ANOMALA`.

## Decisões não previstas

- Limite por tipo de **página** (nativa, ocr, vazia), porque o tipo de peça só existe na 4E; o YAML pode ganhar chaves por tipo de peça depois.

## Critério

| Critério | Evidência |
| --- | --- |
| Página com 50 mil caracteres sinalizada | `test_densidade_anomala_por_tipo` (50.000 caracteres, nativa e OCR) |
| Páginas dos sintéticos não | `semente_01`: máximo de 2.724 (nativa) e 2.873 (ocr) caracteres; 0 páginas com a flag |

## Comandos e saída

```
docker compose up -d --build --wait
docker compose exec api bash scripts/verificar.sh
```

Saída resumida (21/10/2026): ruff e `ruff format --check` limpos; `mypy --strict` sem erros em 165 arquivos; pytest **588 passed, 1 skipped** (o skip é anterior à 4D; eram 551 testes), cobertura **98,66%**; ponta a ponta 1 passed; regressão de injeção 2 passed (159 s), `recall 1.0`, `falso_positivo 0.0`.
