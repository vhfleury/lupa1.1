# Relatório da Etapa 5.9 — Registro e custo

## O que foi feito

- Migração 0007: `conversa`, `mensagem`, `chamada_modelo`, com RLS forçada por gabinete e
  política do administrador; `lupa_app` só insere em `mensagem` e `chamada_modelo`.
- Cada chamada grava `chamada_modelo` (modelo, versão e hash do prompt de sistema, hash da entrada
  = mensagem + resultados de ferramenta, hash da saída, tokens de entrada e saída, latência,
  ferramentas tentadas, resultado) e o evento `chamada_modelo` com `objeto_id` da linha,
  `versao_modelo` e `versao_prompt`; nunca conteúdo. `pergunta_chat` por pergunta (objeto
  `mensagem`).
- Tetos em `Settings` (`LUPA_AGENTE_MAX_TOKENS_CHAMADA`, `_CONVERSA`, `_PROCESSO`); estouro
  encerra a conversa com mensagem clara; teto do processo bloqueia novas chamadas.

## Decisões não previstas

- Hashes e tokens ficam em tabela própria porque o evento de auditoria tem formato fixo, sem
  campo livre (Etapa 3); a cadeia da auditoria não muda.
- O SDK não tem `max_tokens` por chamada: o teto por chamada é conferido depois (resposta
  descartada) e o laço é limitado por `max_turns`.

## O que ficou de fora

- Custo em dinheiro por chamada (`total_cost_usd`): não gravado; os tokens bastam para o relatório de uso.

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
