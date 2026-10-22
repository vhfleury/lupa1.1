# Relatório da Etapa 5.8 — Suíte de injeção do agente

## O que foi feito

- `tests/agente/test_injecao_agente.py` (marcadores `integracao` e `agente`): ingere pela pipeline
  real o processo sintético com todos os vetores (cenário PDF com índice) e o corpus
  `.sinteticos/injecao/injecao_todos`; sete cenários de modelo manipulado nos dois processos:
  citação inventada, instrução refletida, CNJ de outro processo, UUID de outro processo, achado
  inexistente, tentativa de `Read`/`Bash`/`WebFetch`/`Write`/`Task`/`Glob`, e "vazar o que leu"
  depois de ler todas as páginas, cinco originais, fatos, achados, buscas e as três validações.
- Resultado (cliente falso roteirizado, prompt `1:<hash>`, política de recusa 1): 14 execuções,
  **0 achado suprimido, 0 achado criado, 0 vazamento** (nome, CPF, texto oculto do gabarito, dados
  do outro processo), 0 ferramenta embutida executada, 10 respostas descartadas com incidente.
- Passo próprio no fim de `scripts/verificar.sh` e `scripts/verificar.ps1`, sem skip, com as
  métricas em `LUPA_METRICAS_AGENTE`.

## Decisões não previstas

- O teste reaproveita as fixtures de ingestão sintética (`tests/ingestao/conftest.py`); a extração da sessão roda de novo neste módulo (cerca de 1 minuto).

## O que ficou de fora

- Rodar a suíte com o modelo real (exige credencial).

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
