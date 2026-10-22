# Relatório da Etapa 5.4 — Válvula de escape

## O que foi feito

- `src/lupa/agente/ferramentas/original.py`: `ler_pagina_original` devolve `pagina.texto` (sem o
  texto oculto, como gravado) em segmentos com hash e os `trechos_suspeitos` (posições, categoria,
  padrão, origem; sem texto). Limite `LUPA_AGENTE_MAX_PAGINAS_ORIGINAIS` (padrão 20) por
  conversa, contado em `conversa.paginas_originais`; acima dele, recusa clara.
- Cada uso grava `pagina_vista` com `objeto_tipo = "pagina_original_agente"` e o id da página.
- Testes: limite excedido gera recusa; cada uso gera evento; página de outro processo é recusada
  sem consumir o limite.

## Decisões não previstas

- O texto original também sai pseudonimizado (nome e CPF dos réus), como todo texto enviado.

## O que ficou de fora

- Imagem da página para o modelo (visão): fora do escopo.

## Comandos e saída resumida

```
docker compose up -d --build --wait
docker compose exec api alembic -c src/lupa/migrations/alembic.ini upgrade head
docker compose exec api bash scripts/verificar.sh
```

```
== ruff check ==
All checks passed!
== ruff format --check ==
234 files already formatted
== mypy --strict ==
Success: no issues found in 234 source files
== pytest ==
test session starts
TOTAL                                                     9039    116    99%
Required test coverage of 90% reached. Total coverage: 98.72%
766 passed, 1 skipped, 3 deselected in 499.00s (0:08:19)
== ponta a ponta da ingestao (integracao, sem skip) ==
1 passed in 4.31s
== regressao de injecao (corpus 4B.8, metas da 4D.5, sem skip) ==
2 passed in 185.85s (0:03:05)
{'versoes': {'saneamento': '4d.1', 'homoglifos': '1', 'padroes_instrucao': '1', 'idiomas': '1', 'densidade': '1'}, 'recall': 1.0, 'falso_positivo': 0.0, 'injecoes_textuais': 16, 'injecoes_detectadas': 16, 'paginas_semente_01': 196}
== front ==
front: carimbo do build ok ad0b6d353349 2026-10-21T11:27:16.764Z
== suite de injecao do agente (Etapa 5.8, sem skip) ==
9 passed, 54 deselected in 50.07s
{'versao_modelo': 'cliente_falso_roteirizado', 'versao_prompt': '1:1c739e84a6337f5a', 'cenarios': 14, 'achados_suprimidos': 0, 'achados_criados': 0, 'vazamentos': 0, 'embutidas_executadas': 0, 'respostas_bloqueadas': 10}
```
