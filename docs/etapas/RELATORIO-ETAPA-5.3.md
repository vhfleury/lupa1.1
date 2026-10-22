# Relatório da Etapa 5.3 — Ferramenta de cálculo

## O que foi feito

- `src/lupa/agente/ferramentas/calculo.py`: `executar_validacao(nome)` lê os fatos do processo,
  roda `executar_catalogo` da Etapa 2 e devolve o achado completo (resultado, valores, fatos
  usados, explicação do template, data de referência). Não grava achado. Gera
  `validacao_executada` com `objeto_tipo = "validacao_agente"`.
- Prompt de sistema e instrução da mensagem mandam usar a ferramenta para prazos e prescrição; a
  recusa por regras bloqueia "calcule você mesmo / sem a ferramenta".
- Teste `test_tempestividade_respondida_so_com_a_ferramenta_de_calculo`: "O recurso é tempestivo?"
  respondido com a única ferramenta `executar_validacao`, citação conferida e evento auditado.

## Decisões não previstas

- Nome da validação no esquema da ferramenta como `enum` do catálogo da matéria.

## O que ficou de fora

- Nada.

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
