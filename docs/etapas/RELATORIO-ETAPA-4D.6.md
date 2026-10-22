# Relatório da Etapa 4D.6 — Idioma inesperado

## O que foi feito

- `dados/idiomas.yaml` (versão 1): palavras funcionais exclusivas de pt, en e es; `min_palavras` 8, `min_funcionais` 3, `min_proporcao` 0,4 e `vantagem` 2.
- `deteccao.detectar_idioma`: segmenta o normalizado em frases (`.`, `!`, `?`) e marca a frase cujo idioma estrangeiro tem 3 ou mais funcionais, 40% ou mais das palavras e o dobro das funcionais do português. Trecho categoria `idioma`, padrão `idioma_en` ou `idioma_es`; `FlagPagina.IDIOMA_INESPERADO`. Sem dependência nova.

## Decisões não previstas

- `min_proporcao` entrou depois que a citação "the burden of proof lies with the prosecution", dentro de frase em português, disparou (4 funcionais em 13 palavras).

## Limitações (registradas no YAML e em `docs/ingestao.md`)

- Frases com menos de 8 palavras não são avaliadas; o espanhol divide muitas palavras com o português e só dispara em frase claramente espanhola; outros idiomas não são detectados.

## Critério

| Critério | Evidência |
| --- | --- |
| Parágrafo em inglês marcado | regressão: `idioma_alternado` (2 casos) com `idioma_inesperado` e `padrao_instrucao` |
| Latim curto não marca | `test_idioma_ingles_marcado_e_latim_nao` ("habeas corpus", "in dubio pro reo") |
| Sem falso positivo | 0 das 196 páginas de `semente_01` |

## Comandos e saída

```
docker compose up -d --build --wait
docker compose exec api bash scripts/verificar.sh
```

Saída resumida (21/10/2026): ruff e `ruff format --check` limpos; `mypy --strict` sem erros em 165 arquivos; pytest **588 passed, 1 skipped** (o skip é anterior à 4D; eram 551 testes), cobertura **98,66%**; ponta a ponta 1 passed; regressão de injeção 2 passed (159 s), `recall 1.0`, `falso_positivo 0.0`.
